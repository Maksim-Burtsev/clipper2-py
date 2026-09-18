"""Differential fuzz test: the binding must return exactly what upstream C++ returns.

Every case is run twice - once by ``tests/reference/ref_cli`` (which calls the public
upstream API directly) and once by ``clipper2`` - and the two results must be identical:
integers equal, doubles bit for bit.  Both sides run the same upstream code on the same
machine, so anything less than exact equality is a binding bug.

Build the reference binary first (the test skips without it)::

    cmake -S tests/reference -B build/ref -DCMAKE_BUILD_TYPE=Release
    cmake --build build/ref

``CLIPPER2_REF_CLI`` overrides the lookup.  Seeds are fixed: the cases are the same on
every run and on every machine.
"""

from __future__ import annotations

import os
import struct
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pytest

clipper2 = pytest.importorskip("clipper2")

REPO_ROOT = Path(__file__).resolve().parents[2]


def _find_ref_cli() -> Path | None:
    override = os.environ.get("CLIPPER2_REF_CLI")
    if override:
        candidates = [Path(override)]
    else:
        build_dir = REPO_ROOT / "build" / "ref"
        names = ("ref_cli", "ref_cli.exe")
        # MSVC puts the binary in a per-configuration subdirectory.
        dirs = [build_dir] + [build_dir / c for c in ("Release", "RelWithDebInfo", "Debug")]
        candidates = [d / n for d in dirs for n in names]
    return next((c for c in candidates if c.is_file() and os.access(c, os.X_OK)), None)


REF_CLI = _find_ref_cli()

pytestmark = pytest.mark.skipif(
    REF_CLI is None,
    reason="ref_cli not built: cmake -S tests/reference -B build/ref && cmake --build build/ref",
)


# --------------------------------------------------------------------------- the binding
# Every call this test makes into `clipper2` is in this block, so a name or signature that
# turns out differently in the binding is a one-line fix here.  Shapes follow docs/spec.md
# "Decisions locked" 2 and 7.  Arguments that sit in different positions in the 64 and D
# families upstream (precision, decimal_places, ...) are always passed by keyword.

def _ct(v):
    return clipper2.ClipType(v)


def _fr(v):
    return clipper2.FillRule(v)


def _jt(v):
    return clipper2.JoinType(v)


def _et(v):
    return clipper2.EndType(v)


def _enum_int(v) -> int:
    """TriangulateResult / PointInPolygonResult as its C++ integer value."""
    try:
        return int(v)
    except (TypeError, ValueError):
        return int(v.value)


def _require(*names: str) -> None:
    missing = [n for n in names if not hasattr(clipper2, n)]
    if missing:
        pytest.skip(f"clipper2.{', clipper2.'.join(missing)}: not bound yet")


# --------------------------------------------------------------------------- record I/O

DTYPE = {"64": np.int64, "d": np.float64}


def _norm(a: np.ndarray) -> np.ndarray:
    """An empty path may legitimately arrive as (0,) or (0, 2); compare it as (0, 2)."""
    return a.reshape(0, 2) if a.size == 0 else a


def enc_path(path) -> str:
    a = _norm(np.asarray(path))
    return f"{len(a)} " + " ".join(map(repr, a.ravel().tolist())) if len(a) else "0"


def enc_paths(paths) -> str:
    return " ".join([str(len(paths))] + [enc_path(p) for p in paths])


def enc_num(v) -> str:
    return repr(v.item() if isinstance(v, np.generic) else v)


class Reply:
    """Cursor over the whitespace-separated tokens of one ref_cli reply."""

    __slots__ = ("toks", "i")

    def __init__(self, payload: str):
        self.toks = payload.split()
        self.i = 0

    def _take(self, n: int) -> list[str]:
        out = self.toks[self.i : self.i + n]
        assert len(out) == n, "truncated ref_cli reply"
        self.i += n
        return out

    def int(self) -> int:
        return int(self._take(1)[0])

    def double(self) -> float:
        return float(self._take(1)[0])

    def path(self, dtype) -> np.ndarray:
        n = self.int()
        flat = self._take(2 * n)
        conv = int if dtype is np.int64 else float
        return np.array([conv(t) for t in flat], dtype=dtype).reshape(n, 2)

    def paths(self, dtype) -> list[np.ndarray]:
        return [self.path(dtype) for _ in range(self.int())]

    def tree(self, dtype) -> list:
        is_hole, level, polygon = self.int(), self.int(), self.path(dtype)
        return [is_hole, level, polygon, [self.tree(dtype) for _ in range(self.int())]]

    def done(self) -> bool:
        return self.i == len(self.toks)


def run_ref(records: list[str]) -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        infile = Path(tmp) / "cases.txt"
        infile.write_text("\n".join(records) + "\n")
        proc = subprocess.run(
            [str(REF_CLI), str(infile)], capture_output=True, text=True, check=False
        )
    assert proc.returncode == 0, f"ref_cli exited {proc.returncode}: {proc.stderr}"
    replies = proc.stdout.splitlines()
    assert len(replies) == len(records), (
        f"ref_cli replied {len(replies)} times to {len(records)} records "
        f"(it probably crashed on record {len(replies)}: {records[len(replies)][:200]})"
    )
    return replies


# --------------------------------------------------------------------------- comparison


def arr(value, dtype, where: str) -> np.ndarray:
    """A path returned by the binding, checked against deviation 3 and normalised."""
    if not isinstance(value, np.ndarray):
        raise AssertionError(f"{where}: expected a numpy array, got {type(value).__name__}")
    if value.dtype != dtype:
        raise AssertionError(f"{where}: expected dtype {np.dtype(dtype)}, got {value.dtype}")
    return _norm(value)


def arrs(value, dtype, where: str) -> list[np.ndarray]:
    if not isinstance(value, list):
        raise AssertionError(f"{where}: expected a list of paths, got {type(value).__name__}")
    return [arr(p, dtype, f"{where}[{i}]") for i, p in enumerate(value)]


def tree_value(node, dtype, where: str = "tree") -> list:
    return [
        int(node.is_hole),
        int(node.level),
        arr(node.polygon, dtype, f"{where}.polygon"),
        [tree_value(c, dtype, f"{where}[{i}]") for i, c in enumerate(node)],
    ]


def diff(ref, got, where: str = "result") -> str | None:
    """None when identical, else why not.  Doubles are compared bit for bit."""
    if isinstance(ref, list):
        if not isinstance(got, list):
            return f"{where}: expected a list, got {type(got).__name__}"
        if len(ref) != len(got):
            return f"{where}: expected {len(ref)} items, got {len(got)}"
        for i, (a, b) in enumerate(zip(ref, got)):
            reason = diff(a, b, f"{where}[{i}]")
            if reason:
                return reason
        return None
    if isinstance(ref, np.ndarray):
        if ref.shape != got.shape:
            return f"{where}: expected shape {ref.shape}, got {got.shape}"
        if ref.dtype != got.dtype:
            return f"{where}: expected dtype {ref.dtype}, got {got.dtype}"
        if ref.tobytes() != got.tobytes():
            return f"{where}: expected {ref.tolist()}, got {got.tolist()}"
        return None
    if isinstance(ref, float):
        if struct.pack("<d", ref) != struct.pack("<d", float(got)):
            return f"{where}: expected {ref!r}, got {float(got)!r}"
        return None
    if ref != got:
        return f"{where}: expected {ref!r}, got {got!r}"
    return None


class Case:
    """One generated operation: its ref_cli record, its reply parser and the binding call."""

    __slots__ = ("record", "parse", "call")

    def __init__(self, record: str, parse, call):
        self.record = record
        self.parse = parse
        self.call = call


def check(cases: list[Case]) -> None:
    replies = run_ref([c.record for c in cases])
    failures = []
    for case, reply in zip(cases, replies):
        error = None
        try:
            got = case.call()
        except Exception as exc:  # any exception is a result to compare, not a test error
            got, error = None, exc

        if reply.startswith("ERROR "):
            want = reply[6:]
            if error is None:
                reason = f"C++ raised Clipper2Exception({want!r}), Python returned {got!r}"
            elif not isinstance(error, clipper2.Clipper2Error):
                reason = f"C++ raised Clipper2Exception({want!r}), Python raised {error!r}"
            elif str(error) != want:
                reason = f"C++ message {want!r}, Python message {str(error)!r}"
            else:
                reason = None
        elif reply == "FAILED":
            reason = (
                None
                if isinstance(error, clipper2.Clipper2Error)
                else f"C++ Execute() returned false, Python gave {error or got!r}"
            )
        elif reply.startswith("OK"):
            if error is not None:
                reason = f"C++ returned a result, Python raised {error!r}"
            else:
                out = Reply(reply[2:])
                ref = case.parse(out)
                assert out.done(), "unparsed tokens left in a ref_cli reply"
                reason = diff(ref, got)
        else:
            reason = f"ref_cli said: {reply[:200]}"

        if reason:
            record = case.record if len(case.record) <= 400 else case.record[:400] + " ..."
            failures.append(f"{reason}\n  record: {record}")

    if failures:
        shown = "\n\n".join(failures[:5])
        pytest.fail(
            f"{len(failures)} of {len(cases)} cases differ from upstream C++\n\n{shown}",
            pytrace=False,
        )


# --------------------------------------------------------------------------- generators

MAX_COORD = (2**63 - 1) >> 2  # upstream's documented limit for the 64 family

SPANS = {
    "64": (8, 100, 10**4, 10**7, 10**12),
    "d": (1e-3, 1.0, 100.0, 1e4, 1e7),
}
HUGE = {"64": MAX_COORD // 8, "d": 1e12}  # 'd' at precision 8 overflows -> range error
KINDS = ("blob", "convex", "star", "rect", "grid", "collinear", "dup", "degenerate")


def to_family(pts: np.ndarray, family: str) -> np.ndarray:
    pts = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
    return np.rint(pts).astype(np.int64) if family == "64" else pts


def pick_span(rng, family: str, huge_p: float = 0.04) -> float:
    if rng.random() < huge_p:
        return HUGE[family]
    return SPANS[family][rng.integers(len(SPANS[family]))]


def gen_path(rng, family, kind=None, span=None, center=(0.0, 0.0), npts=None, huge_p=0.04):
    """One path as an (n, 2) array of the family's dtype."""
    if kind is None:
        kind = KINDS[rng.integers(len(KINDS))]
    if span is None:
        span = pick_span(rng, family, huge_p)
    if npts is None:
        npts = int(rng.integers(3, 13))
    cx, cy = center

    if kind == "degenerate":
        pts = rng.uniform(-span, span, (int(rng.integers(0, 3)), 2))
    elif kind == "rect":
        w, h = rng.uniform(0, span, 2)
        pts = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float64)
        pts -= [w / 2, h / 2]
    elif kind == "grid":
        step = span / 4
        pts = rng.integers(-4, 5, (npts, 2)) * step
    elif kind == "convex":  # sorted angles -> a simple (non self-intersecting) polygon
        ang = np.sort(rng.uniform(0, 2 * np.pi, npts))
        rad = span * rng.uniform(0.3, 1.0, npts)
        pts = np.stack([rad * np.cos(ang), rad * np.sin(ang)], axis=1)
    elif kind == "star":  # {npts/k} star polygon: always self-intersecting
        k = 2 if npts < 7 else 3
        ang = np.arange(npts) * (2 * np.pi * k / max(npts, 1))
        pts = span * np.stack([np.cos(ang), np.sin(ang)], axis=1)
    elif kind == "collinear":
        corners = gen_path(rng, "d", "convex", span, (0, 0), 4)
        pts = []
        for i, a in enumerate(corners):
            b = corners[(i + 1) % len(corners)]
            for t in np.linspace(0.0, 1.0, int(rng.integers(2, 5)), endpoint=False):
                pts.append(a + t * (b - a))
        pts = np.array(pts)
    elif kind == "dup":
        base = gen_path(rng, "d", "convex", span, (0, 0), npts)
        pts = np.repeat(base, rng.integers(1, 4, len(base)), axis=0)
    else:  # blob: unsorted random points, usually self-intersecting
        pts = rng.uniform(-span, span, (npts, 2))

    pts = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
    if len(pts):
        pts = pts + [cx, cy]
    return to_family(pts, family)


def gen_paths(rng, family, count=None, **kw):
    """A list of paths.  A D-family argument always ends up with at least one non-empty
    path in it: an empty list, and an empty array too, leave the binding without a dtype
    to dispatch on (spec decision 4), and that ambiguity is not what this test is about."""
    if count is None:
        count = int(rng.integers(0 if family == "64" else 1, 4))
    span = kw.pop("span", None) or pick_span(rng, family)
    out = []
    for _ in range(count):
        center = rng.uniform(-span, span, 2) * 0.6
        out.append(gen_path(rng, family, span=span, center=tuple(center), **kw))
    if family == "d" and not any(len(p) for p in out):
        out[0] = gen_path(rng, family, "convex", span, npts=int(rng.integers(3, 13)))
    return out


def gen_precision(rng, bad_p=0.06):
    """Upstream accepts -8..8; outside that it throws, which is parity worth checking."""
    if rng.random() < bad_p:
        return int(rng.choice([-9, 9, 20]))
    return int(rng.integers(-8, 9))


def gen_point(rng, family, span):
    pt = to_family(rng.uniform(-span, span, (1, 2)), family)[0]
    return tuple(pt.tolist())


def empty(family):
    return np.empty((0, 2), DTYPE[family])


# --------------------------------------------------------------------------- boolean ops

MODES = ("paths", "tree", "clipper", "clipper_tree", "clipper_open", "clipper_open_tree")


def cases_boolean(rng, per_combo=16) -> list[Case]:
    cases = []
    for family in ("64", "d"):
        dtype = DTYPE[family]
        for ct in (1, 2, 3, 4):  # Intersection, Union, Difference, Xor
            for fr in (0, 1, 2, 3):  # EvenOdd, NonZero, Positive, Negative
                for mode in MODES:
                    for _ in range(per_combo):
                        precision = gen_precision(rng)
                        span = pick_span(rng, family)
                        subj = gen_paths(rng, family, span=span)
                        clip = gen_paths(rng, family, span=span)
                        open_subj = (
                            gen_paths(rng, family, span=span)
                            if mode.startswith("clipper_open")
                            else ([] if family == "64" else [empty(family)])
                        )
                        pc, rs = bool(rng.integers(2)), bool(rng.integers(2))
                        cases.append(
                            _boolean_case(
                                family, dtype, ct, fr, mode, precision,
                                subj, clip, open_subj, pc, rs,
                            )
                        )
    return cases


def _boolean_case(family, dtype, ct, fr, mode, precision, subj, clip, open_subj, pc, rs):
    kw = {} if family == "64" else {"precision": precision}
    prefix = "" if family == "64" else f"{precision} "

    if mode == "paths":
        record = f"boolean_op{family} {prefix}{ct} {fr} {enc_paths(subj)} {enc_paths(clip)}"
        return Case(
            record,
            lambda r: [r.paths(dtype)],
            lambda: [arrs(clipper2.boolean_op(_ct(ct), _fr(fr), subj, clip, **kw), dtype, "closed")],
        )
    if mode == "tree":
        record = f"boolean_op_tree{family} {prefix}{ct} {fr} {enc_paths(subj)} {enc_paths(clip)}"
        return Case(
            record,
            lambda r: [r.tree(dtype)],
            lambda: [
                tree_value(clipper2.boolean_op_tree(_ct(ct), _fr(fr), subj, clip, **kw), dtype)
            ],
        )

    as_tree = mode.endswith("_tree")
    record = (
        f"clipper{family} {prefix}{ct} {fr} {int(as_tree)} {int(pc)} {int(rs)} "
        f"{enc_paths(subj)} {enc_paths(open_subj)} {enc_paths(clip)}"
    )

    def call():
        c = clipper2.Clipper64() if family == "64" else clipper2.ClipperD(precision)
        c.preserve_collinear = pc
        c.reverse_solution = rs
        c.add_subject(subj)
        c.add_open_subject(open_subj)
        c.add_clip(clip)
        if as_tree:
            tree, open_sol = c.execute_tree(_ct(ct), _fr(fr))
            return [tree_value(tree, dtype), arrs(open_sol, dtype, "open")]
        closed, open_sol = c.execute(_ct(ct), _fr(fr))
        return [arrs(closed, dtype, "closed"), arrs(open_sol, dtype, "open")]

    parse = (
        (lambda r: [r.tree(dtype), r.paths(dtype)])
        if as_tree
        else (lambda r: [r.paths(dtype), r.paths(dtype)])
    )
    return Case(record, parse, call)


# --------------------------------------------------------------------------- offsetting


def offset_paths(rng, family, span):
    """Paths for the offsetter, minus the empty ones: upstream 2.0.1 dereferences
    path.size() - 1 for an empty path with any open EndType and segfaults."""
    paths = [p for p in gen_paths(rng, family, span=span) if len(p)]
    if family == "d" and not paths:  # never hand the D family a dtype-less empty list
        paths = [gen_path(rng, "d", "convex", span, (0.0, 0.0), 4)]
    return paths


def cases_offset(rng, per_combo=20, per_class_combo=10) -> list[Case]:
    cases = []
    for family in ("64", "d"):
        dtype = DTYPE[family]
        for jt in (0, 1, 2, 3):  # Square, Bevel, Round, Miter
            for et in (0, 1, 2, 3, 4):  # Polygon, Joined, Butt, Square, Round
                for _ in range(per_combo):
                    span = pick_span(rng, family, huge_p=0.0)
                    paths = offset_paths(rng, family, span)
                    # delta == 0 is upstream's "return the input unchanged" shortcut
                    delta = 0.0 if rng.random() < 0.04 else float(
                        rng.choice([-1, 1]) * span * rng.uniform(0.0, 0.3)
                    )
                    miter = float(rng.uniform(1.0, 10.0))
                    arc = float(rng.choice([0.0, span * 0.01, span * 0.2]))
                    precision = gen_precision(rng)
                    cases.append(_inflate_case(family, dtype, paths, delta, jt, et,
                                               miter, arc, precision))
    # ClipperOffset itself is 64-only upstream.
    for jt in (0, 1, 2, 3):
        for et in (0, 1, 2, 3, 4):
            for _ in range(per_class_combo):
                span = pick_span(rng, "64", huge_p=0.0)
                groups = [
                    (jt, et, offset_paths(rng, "64", span)),
                    (int(rng.integers(4)), int(rng.integers(5)),
                     offset_paths(rng, "64", span)),
                ][: int(rng.integers(1, 3))]
                cases.append(
                    _offset_class_case(
                        groups,
                        delta=float(rng.choice([-1, 1]) * span * rng.uniform(0.0, 0.3)),
                        miter=float(rng.uniform(1.0, 10.0)),
                        arc=float(rng.choice([0.0, span * 0.01])),
                        pc=bool(rng.integers(2)),
                        rs=bool(rng.integers(2)),
                        as_tree=bool(rng.integers(2)),
                    )
                )
    return cases


def _inflate_case(family, dtype, paths, delta, jt, et, miter, arc, precision):
    if family == "64":
        record = (f"inflate64 {enc_num(delta)} {jt} {et} {enc_num(miter)} "
                  f"{enc_num(arc)} {enc_paths(paths)}")
        kw = {}
    else:
        record = (f"inflated {enc_num(delta)} {jt} {et} {enc_num(miter)} {precision} "
                  f"{enc_num(arc)} {enc_paths(paths)}")
        kw = {"precision": precision}
    return Case(
        record,
        lambda r: [r.paths(dtype)],
        lambda: [
            arrs(
                clipper2.inflate_paths(
                    paths, delta, _jt(jt), _et(et),
                    miter_limit=miter, arc_tolerance=arc, **kw,
                ),
                dtype,
                "inflated",
            )
        ],
    )


def _offset_class_case(groups, delta, miter, arc, pc, rs, as_tree):
    record = " ".join(
        [f"offset64 {enc_num(miter)} {enc_num(arc)} {int(pc)} {int(rs)} {enc_num(delta)}",
         f"{int(as_tree)} {len(groups)}"]
        + [f"{jt} {et} {enc_paths(paths)}" for jt, et, paths in groups]
    )

    def call():
        co = clipper2.ClipperOffset(
            miter_limit=miter, arc_tolerance=arc, preserve_collinear=pc, reverse_solution=rs
        )
        for jt, et, paths in groups:
            co.add_paths(paths, _jt(jt), _et(et))
        if as_tree:
            return [tree_value(co.execute_tree(delta), np.int64)]
        return [arrs(co.execute(delta), np.int64, "offset")]

    parse = (lambda r: [r.tree(np.int64)]) if as_tree else (lambda r: [r.paths(np.int64)])
    return Case(record, parse, call)


# --------------------------------------------------------------------------- rect clip


def _rect_cases(rng, count, lines: bool) -> list[Case]:
    cases = []
    name = "rect_clip_lines" if lines else "rect_clip"
    for _ in range(count):
        family = "64" if rng.integers(2) else "d"
        dtype = DTYPE[family]
        span = pick_span(rng, family)
        paths = gen_paths(rng, family, span=span)
        precision = gen_precision(rng)
        corners = to_family(rng.uniform(-span, span, (2, 2)), family)
        left, right = sorted(int(v) if family == "64" else float(v) for v in corners[:, 0])
        top, bottom = sorted(int(v) if family == "64" else float(v) for v in corners[:, 1])
        if rng.random() < 0.08:  # empty rect: upstream returns nothing
            right, bottom = left, top
        rect_args = (left, top, right, bottom)
        prefix = "" if family == "64" else f"{precision} "
        record = (f"{name}{family} {prefix}" + " ".join(map(enc_num, rect_args))
                  + f" {enc_paths(paths)}")

        def call(family=family, dtype=dtype, rect_args=rect_args, paths=paths,
                 precision=precision, lines=lines):
            rect_cls = clipper2.Rect64 if family == "64" else clipper2.RectD
            rect = rect_cls(*rect_args)
            kw = {} if family == "64" else {"precision": precision}
            fn = clipper2.rect_clip_lines if lines else clipper2.rect_clip
            return [arrs(fn(rect, paths, **kw), dtype, "clipped")]

        cases.append(Case(record, lambda r, dtype=dtype: [r.paths(dtype)], call))
    return cases


def cases_rect_clip(rng, count=1000):
    return _rect_cases(rng, count, lines=False)


def cases_rect_clip_lines(rng, count=1000):
    return _rect_cases(rng, count, lines=True)


# --------------------------------------------------------------------------- minkowski


def cases_minkowski(rng, per_combo=100) -> list[Case]:
    cases = []
    for family in ("64", "d"):
        dtype = DTYPE[family]
        for kind in ("sum", "diff"):
            for is_closed in (False, True):
                for _ in range(per_combo):
                    span = pick_span(rng, family, huge_p=0.0)
                    lo = 1 if family == "d" else 0  # see gen_paths on empty D arguments
                    pattern = gen_path(rng, family, span=span / 8,
                                       npts=int(rng.integers(lo, 8)))
                    path = gen_path(rng, family, span=span, npts=int(rng.integers(lo, 12)))
                    decimals = int(rng.integers(0, 9))
                    cases.append(_minkowski_case(family, dtype, kind, is_closed,
                                                 pattern, path, decimals))
    return cases


def _minkowski_case(family, dtype, kind, is_closed, pattern, path, decimals):
    prefix = "" if family == "64" else f"{decimals} "
    record = (f"minkowski_{kind}{family} {prefix}{int(is_closed)} "
              f"{enc_path(pattern)} {enc_path(path)}")
    kw = {} if family == "64" else {"decimal_places": decimals}

    def call():
        fn = clipper2.minkowski_sum if kind == "sum" else clipper2.minkowski_diff
        return [arrs(fn(pattern, path, is_closed, **kw), dtype, kind)]

    return Case(record, lambda r: [r.paths(dtype)], call)


# --------------------------------------------------------------------------- triangulate


# Upstream's triangulation is a beta release and does not terminate on some inputs whose
# vertices collapse onto each other (duplicates, or a D path that rounds to a couple of
# distinct points at the given precision).  That would hang the binding exactly as it hangs
# ref_cli, so these cases keep the vertices distinct: spans big enough to survive rounding,
# and for the D family a precision that matches the span.
TRI_SPANS = {"64": (1e3, 1e5, 1e8), "d": (1e-2, 1.0, 1e3)}
TRI_MIN_DECIMALS = {"64": (0, 0, 0), "d": (6, 4, 1)}


def cases_triangulate(rng, per_combo=150) -> list[Case]:
    cases = []
    for family in ("64", "d"):
        dtype = DTYPE[family]
        for use_delaunay in (False, True):
            for i in range(per_combo):
                scale_idx = int(rng.integers(3))
                span = TRI_SPANS[family][scale_idx]
                decimals = int(rng.integers(TRI_MIN_DECIMALS[family][scale_idx], 9))
                if rng.random() < 0.1:  # too little to triangulate: no_polygons
                    paths = [] if family == "64" else [empty(family)]
                    if rng.random() < 0.5:
                        paths = [gen_path(rng, family, "blob", span,
                                          npts=int(rng.integers(1, 3)))]
                elif i % 2 == 0:
                    paths = _triangulable(rng, family, span)  # valid: no intersections
                else:  # self-intersecting or nested-crossing: fail / paths_intersect
                    paths = [
                        gen_path(rng, family, "star" if rng.integers(2) else "blob", span,
                                 center=tuple(rng.uniform(-span, span, 2) * 2),
                                 npts=int(rng.integers(3, 13)))
                        for _ in range(int(rng.integers(1, 3)))
                    ]
                prefix = "" if family == "64" else f"{decimals} "
                record = (f"triangulate{family} {prefix}{int(use_delaunay)} "
                          f"{enc_paths(paths)}")
                # upstream calls it decPlaces here and decimalPlaces in minkowski
                kw = {} if family == "64" else {"dec_places": decimals}

                def call(paths=paths, dtype=dtype, use_delaunay=use_delaunay, kw=kw):
                    result, solution = clipper2.triangulate(
                        paths, use_delaunay=use_delaunay, **kw
                    )
                    return [_enum_int(result), arrs(solution, dtype, "triangles")]

                cases.append(
                    Case(record, lambda r, dtype=dtype: [r.int(), r.paths(dtype)], call)
                )
    return cases


def _triangulable(rng, family, span):
    """Simple polygons that do not intersect each other: convex rings around centres far
    enough apart to stay clear, or a square with a reversed square inside it (a hole)."""
    if rng.random() < 0.4:
        square = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]], dtype=np.float64)
        return [to_family(square * span, family),
                to_family(square[::-1] * (span * 0.4), family)]
    far = float(span) * 4.0
    return [
        gen_path(rng, family, "convex", span, (far * i, 0.0), int(rng.integers(3, 10)))
        for i in range(int(rng.integers(1, 4)))
    ]


# --------------------------------------------------------- simplify / RDP / trim collinear


def cases_simplify(rng, per_combo=150) -> list[Case]:
    cases = []
    for family in ("64", "d"):
        dtype = DTYPE[family]
        for is_closed in (False, True):
            for _ in range(per_combo):
                span = pick_span(rng, family)
                paths = gen_paths(rng, family, span=span, npts=int(rng.integers(0, 40)))
                eps = float(span * rng.choice([0.0, 1e-4, 0.01, 0.2, 2.0]))
                record = (f"simplify_paths{family} {enc_num(eps)} {int(is_closed)} "
                          f"{enc_paths(paths)}")

                def call(paths=paths, eps=eps, is_closed=is_closed, dtype=dtype):
                    return [arrs(clipper2.simplify_paths(paths, eps, is_closed),
                                 dtype, "simplified")]

                cases.append(Case(record, lambda r, dtype=dtype: [r.paths(dtype)], call))
    return cases


def cases_rdp(rng, count=500) -> list[Case]:
    cases = []
    for i in range(count):
        family = "64" if i % 2 else "d"
        dtype = DTYPE[family]
        span = pick_span(rng, family)
        # count >= 1: ramer_douglas_peucker([]) cannot tell a path from a list of paths
        paths = gen_paths(rng, family, count=int(rng.integers(1, 4)), span=span,
                          npts=int(rng.integers(0, 40)))
        eps = float(span * rng.choice([0.0, 1e-4, 0.01, 0.2, 2.0]))
        record = f"rdp{family} {enc_num(eps)} {enc_paths(paths)}"

        def call(paths=paths, eps=eps, dtype=dtype):
            return [arrs(clipper2.ramer_douglas_peucker(paths, eps), dtype, "rdp")]

        cases.append(Case(record, lambda r, dtype=dtype: [r.paths(dtype)], call))
    return cases


def cases_trim_collinear(rng, count=500) -> list[Case]:
    cases = []
    for i in range(count):
        family = "64" if i % 2 else "d"
        dtype = DTYPE[family]
        is_open = bool(rng.integers(2))
        precision = gen_precision(rng)
        kind = "collinear" if rng.random() < 0.5 else None
        path = gen_path(rng, family, kind, npts=int(rng.integers(0, 30)))
        if family == "d" and not len(path):  # a lone empty array has no dtype to dispatch on
            path = gen_path(rng, family, "convex", npts=int(rng.integers(3, 13)))
        prefix = "" if family == "64" else f"{precision} "
        record = f"trim_collinear{family} {prefix}{int(is_open)} {enc_path(path)}"
        kw = {} if family == "64" else {"precision": precision}

        def call(path=path, is_open=is_open, kw=kw, dtype=dtype):
            return [arr(clipper2.trim_collinear(path, is_open_path=is_open, **kw),
                        dtype, "trimmed")]

        cases.append(Case(record, lambda r, dtype=dtype: [r.path(dtype)], call))
    return cases


# --------------------------------------------------------------------- area / point in poly


def cases_area(rng, count=500) -> list[Case]:
    cases = []
    for i in range(count):
        family = "64" if i % 2 else "d"
        path = gen_path(rng, family, npts=int(rng.integers(0, 40)))
        record = f"area{family} {enc_path(path)}"

        def call(path=path):
            return [float(clipper2.area(path))]

        cases.append(Case(record, lambda r: [r.double()], call))
    return cases


def cases_point_in_polygon(rng, count=800) -> list[Case]:
    cases = []
    for i in range(count):
        family = "64" if i % 2 else "d"
        span = pick_span(rng, family)
        polygon = gen_path(rng, family, span=span, npts=int(rng.integers(0, 20)))
        if len(polygon) and rng.random() < 0.4:  # aim at a vertex: IsOn is the fussy case
            point = tuple(polygon[rng.integers(len(polygon))].tolist())
        else:
            point = gen_point(rng, family, span)
        record = f"pip{family} {enc_num(point[0])} {enc_num(point[1])} {enc_path(polygon)}"

        def call(point=point, polygon=polygon):
            return [_enum_int(clipper2.point_in_polygon(point, polygon))]

        cases.append(Case(record, lambda r: [r.int()], call))
    return cases


# --------------------------------------------------------------------------- the tests

GROUPS = {
    "boolean": (cases_boolean, 1),
    "offset": (cases_offset, 2),
    "rect_clip": (cases_rect_clip, 3),
    "rect_clip_lines": (cases_rect_clip_lines, 4),
    "minkowski": (cases_minkowski, 5),
    "triangulate": (cases_triangulate, 6),
    "simplify": (cases_simplify, 7),
    "rdp": (cases_rdp, 8),
    "trim_collinear": (cases_trim_collinear, 9),
    "area": (cases_area, 10),
    "point_in_polygon": (cases_point_in_polygon, 11),
}
BASE_SEED = 20260919


def build(group: str) -> list[Case]:
    generator, offset = GROUPS[group]
    return generator(np.random.default_rng(BASE_SEED + offset))


def test_boolean_ops():
    _require("boolean_op", "boolean_op_tree", "Clipper64", "ClipperD")
    check(build("boolean"))


def test_offset():
    _require("inflate_paths", "ClipperOffset")
    check(build("offset"))


def test_rect_clip():
    _require("rect_clip", "Rect64", "RectD")
    check(build("rect_clip"))


def test_rect_clip_lines():
    _require("rect_clip_lines", "Rect64", "RectD")
    check(build("rect_clip_lines"))


def test_minkowski():
    _require("minkowski_sum", "minkowski_diff")
    check(build("minkowski"))


def test_triangulate():
    _require("triangulate")
    check(build("triangulate"))


def test_simplify_paths():
    _require("simplify_paths")
    check(build("simplify"))


def test_ramer_douglas_peucker():
    _require("ramer_douglas_peucker")
    check(build("rdp"))


def test_trim_collinear():
    _require("trim_collinear")
    check(build("trim_collinear"))


def test_area():
    _require("area")
    check(build("area"))


def test_point_in_polygon():
    _require("point_in_polygon")
    check(build("point_in_polygon"))


def test_record_format_round_trips_doubles():
    """The whole comparison rests on doubles surviving the text format exactly, in both
    directions.  RamerDouglasPeucker returns paths of fewer than 5 points unchanged, so a
    zero epsilon makes it echo whatever it was given."""
    rng = np.random.default_rng(BASE_SEED)
    raw = rng.integers(0, 2**64, 600, dtype=np.uint64).view(np.float64)
    values = np.concatenate(
        [np.array([0.0, -0.0, 0.1, 1 / 3, 5e-324, 1e-300, 1e16, 1.7976931348623157e308]),
         raw[np.isfinite(raw)]]
    )
    paths = [values[i : i + 2].reshape(1, 2) for i in range(0, len(values) - 1, 2)]
    reply = run_ref([f"rdpd 0.0 {enc_paths(paths)}"])[0]
    assert reply.startswith("OK"), reply
    echoed = Reply(reply[2:]).paths(np.float64)
    assert len(echoed) == len(paths)
    for sent, back in zip(paths, echoed):
        assert sent.tobytes() == back.tobytes(), f"{sent.tolist()} != {back.tolist()}"


def test_at_least_10000_cases():
    """Tests §2 of docs/spec.md asks for >= 10 000 differential cases."""
    counts = {name: len(build(name)) for name in GROUPS}
    assert sum(counts.values()) >= 10_000, counts
