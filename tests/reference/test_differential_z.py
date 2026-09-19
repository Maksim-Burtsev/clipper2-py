"""Differential fuzz test for the z build: `clipper2.z` against upstream built with USINGZ.

Same contract as test_differential.py, whose machinery this file reuses: the reference and
the binding must return the very same numbers, and z is compared exactly as strictly as x
and y.  The reference is the second binary the standalone CMakeLists builds from the same
ref_cli.cpp::

    cmake -S tests/reference -B build/ref -DCMAKE_BUILD_TYPE=Release
    cmake --build build/ref            # -> build/ref/ref_cli and build/ref/ref_cli_z

``CLIPPER2_REF_CLI_Z`` overrides the lookup; the tests skip when the binary is absent.

Upstream's z callback writes pt.z through a reference and the binding's returns the new z
(DEVIATIONS 7), so the two sides cannot share one callback.  Instead a record names one of
the fixed *callback programs* below, implemented once in C++ (ref_cli.cpp) and once here.
"""

from __future__ import annotations

import numpy as np
import pytest

from test_differential import (
    DTYPE,
    TRI_MIN_DECIMALS,
    TRI_SPANS,
    Case,
    _ct,
    _enum_int,
    _et,
    _fr,
    _jt,
    _triangulable,
    arr,
    arrs,
    check,
    enc_num,
    find_ref_cli,
    gen_path,
    gen_paths,
    gen_precision,
    pick_span,
    to_family,
    tree_value,
)

clipper2z = pytest.importorskip("clipper2.z")

REF_CLI_Z = find_ref_cli("ref_cli_z", "CLIPPER2_REF_CLI_Z")

pytestmark = pytest.mark.skipif(
    REF_CLI_Z is None,
    reason="ref_cli_z not built: cmake -S tests/reference -B build/ref && cmake --build build/ref",
)


# --------------------------------------------------------------------------- callbacks

# The z callback programs.  ref_cli.cpp implements the same arithmetic on the same values,
# and the record selects one by number (0 = no callback at all).  They read z and nothing
# else: the D callback is handed x and y de-scaled back to doubles, which two languages do
# not reproduce bit for bit by hand, while z is an exact int64 in both families - the
# binding hands it to Python as an `int` even for a D point, so the arithmetic here is
# Python's exact integer arithmetic and matches C++ int64 as long as it does not overflow.
Z_PROGRAMS = (0, 1, 2, 3)


def z_program(prog: int):
    """``fn(e1bot, e1top, e2bot, e2top, pt) -> z``, or None for "no callback"."""
    if prog == 0:
        return None

    def fn(e1bot, e1top, e2bot, e2top, pt):
        b1, t1, b2, t2, p = (int(e1bot[2]), int(e1top[2]), int(e2bot[2]), int(e2top[2]),
                             int(pt[2]))
        if prog == 1:
            return b1 + b2
        if prog == 2:
            return max(b1, t1, b2, t2)
        return 31 * b1 + 37 * t1 + 41 * b2 + 43 * t2 + 47 * p

    return fn


# A z is an int64 upstream, but in the D family the binding carries it in a float64 column,
# so a D case's *output* z has to stay within 2**53 to be exact - program 1 doubles the
# input magnitude, program 3 multiplies it by up to 199.  (Going past 2**53 in the D family
# is a documented limitation, not something this test is here to trip over.)  In the 64
# family nothing is lost: even 199 * 2**53 is a perfectly ordinary int64.
Z_BIG_D = {0: 2**53, 1: 2**52, 2: 2**53, 3: 2**45}


def pick_zmax(rng, family: str = "64", prog: int = 0) -> int:
    """Mostly small z, often repeated - upstream's z logic branches on z values being equal
    (ClipperOffset::ZCB) and on the intersection landing on a vertex (ClipperBase::SetZ)."""
    if rng.random() < 0.25:
        return Z_BIG_D[prog] if family == "d" else 2**53
    return int(rng.choice([3, 1000]))


def with_z(rng, path: np.ndarray, zmax: int) -> np.ndarray:
    """A 2D path plus a random integer z column, in the family's own dtype."""
    path = np.asarray(path)
    if not len(path):
        return np.empty((0, 3), path.dtype)
    z = rng.integers(-zmax, zmax + 1, len(path))
    return np.column_stack([path, z.astype(path.dtype)])


def z_paths(rng, family, zmax, **kw) -> list[np.ndarray]:
    return [with_z(rng, p, zmax) for p in gen_paths(rng, family, **kw)]


def z_path(rng, family, zmax, *args, **kw) -> np.ndarray:
    return with_z(rng, gen_path(rng, family, *args, **kw), zmax)


def empty3(family: str) -> np.ndarray:
    return np.empty((0, 3), DTYPE[family])


# --------------------------------------------------------------------------- record I/O


def enc_path(path) -> str:
    """``<n> x0 y0 z0 x1 y1 z1 ...``  z goes out as a decimal integer in both families,
    which is what ref_cli reads and what upstream stores."""
    a = np.asarray(path)
    if not a.size:
        return "0"
    zs = a[:, 2].astype(np.int64).tolist()
    toks = [t for (x, y), z in zip(a[:, :2].tolist(), zs) for t in (repr(x), repr(y), repr(z))]
    return f"{len(a)} " + " ".join(toks)


def enc_paths(paths) -> str:
    return " ".join([str(len(paths))] + [enc_path(p) for p in paths])


# --------------------------------------------------------------------------- boolean ops

MODES = ("paths", "tree", "clipper", "clipper_tree", "clipper_open", "clipper_open_tree")


def cases_boolean(rng, per_combo=10) -> list[Case]:
    cases = []
    for family in ("64", "d"):
        dtype = DTYPE[family]
        for ct in (1, 2, 3, 4):  # Intersection, Union, Difference, Xor
            for mode in MODES:
                for i in range(per_combo):
                    # The free functions take no callback; the clipper modes cycle through
                    # all four programs.
                    prog = Z_PROGRAMS[i % len(Z_PROGRAMS)] if mode.startswith("clipper") else 0
                    zmax = pick_zmax(rng, family, prog)
                    span = pick_span(rng, family)
                    subj = z_paths(rng, family, zmax, span=span)
                    clip = z_paths(rng, family, zmax, span=span)
                    open_subj = (
                        z_paths(rng, family, zmax, span=span)
                        if mode.startswith("clipper_open")
                        else ([] if family == "64" else [empty3(family)])
                    )
                    cases.append(
                        _boolean_case(
                            family, dtype, ct, int(rng.integers(4)), mode,
                            gen_precision(rng), prog, int(rng.integers(-zmax, zmax + 1)),
                            subj, clip, open_subj,
                            bool(rng.integers(2)), bool(rng.integers(2)),
                        )
                    )
    return cases


def _boolean_case(family, dtype, ct, fr, mode, precision, prog, default_z,
                  subj, clip, open_subj, pc, rs):
    kw = {} if family == "64" else {"precision": precision}
    prefix = "" if family == "64" else f"{precision} "

    if mode == "paths":
        record = f"boolean_op{family} {prefix}{ct} {fr} {enc_paths(subj)} {enc_paths(clip)}"
        return Case(
            record,
            lambda r: [r.paths(dtype)],
            lambda: [arrs(clipper2z.boolean_op(_ct(ct), _fr(fr), subj, clip, **kw),
                          dtype, "closed", 3)],
        )
    if mode == "tree":
        record = f"boolean_op_tree{family} {prefix}{ct} {fr} {enc_paths(subj)} {enc_paths(clip)}"
        return Case(
            record,
            lambda r: [r.tree(dtype)],
            lambda: [
                tree_value(clipper2z.boolean_op_tree(_ct(ct), _fr(fr), subj, clip, **kw),
                           dtype, "tree", 3)
            ],
        )

    as_tree = mode.endswith("_tree")
    record = (
        f"clipper{family} {prog} {default_z} {prefix}{ct} {fr} "
        f"{int(as_tree)} {int(pc)} {int(rs)} "
        f"{enc_paths(subj)} {enc_paths(open_subj)} {enc_paths(clip)}"
    )

    def call():
        c = clipper2z.Clipper64() if family == "64" else clipper2z.ClipperD(precision)
        c.default_z = default_z
        c.set_z_callback(z_program(prog))
        c.preserve_collinear = pc
        c.reverse_solution = rs
        c.add_subject(subj)
        c.add_open_subject(open_subj)
        c.add_clip(clip)
        if as_tree:
            tree, open_sol = c.execute_tree(_ct(ct), _fr(fr))
            return [tree_value(tree, dtype, "tree", 3), arrs(open_sol, dtype, "open", 3)]
        closed, open_sol = c.execute(_ct(ct), _fr(fr))
        return [arrs(closed, dtype, "closed", 3), arrs(open_sol, dtype, "open", 3)]

    parse = (
        (lambda r: [r.tree(dtype), r.paths(dtype)])
        if as_tree
        else (lambda r: [r.paths(dtype), r.paths(dtype)])
    )
    return Case(record, parse, call)


# --------------------------------------------------------------------------- offsetting
#
# Upstream gives an offset vertex the z of the vertex it came from (GetPerpendic, DoBevel,
# DoMiter, DoRound all carry path[j].z through, and a single-point group's circle or square
# is stamped with that point's z).  The union that cleans up self-intersections then runs
# with ClipperOffset::ZCB, which prefers a z shared by two of the four edge ends and only
# calls the user callback when there is none.


def _offset_paths(rng, family, span, zmax) -> list[np.ndarray]:
    """As test_differential.offset_paths: never an empty path, which upstream 2.0.1
    dereferences past the end of."""
    paths = [p for p in z_paths(rng, family, zmax, span=span) if len(p)]
    return paths or [z_path(rng, family, zmax, "convex", span, (0.0, 0.0), 4)]


def cases_offset(rng, per_combo=4, per_class_combo=4) -> list[Case]:
    cases = []
    for family in ("64", "d"):
        dtype = DTYPE[family]
        for jt in (0, 1, 2, 3):  # Square, Bevel, Round, Miter
            for et in (0, 1, 2, 3, 4):  # Polygon, Joined, Butt, Square, Round
                for _ in range(per_combo):
                    span = pick_span(rng, family, huge_p=0.0)
                    paths = _offset_paths(rng, family, span, pick_zmax(rng, family))
                    delta = 0.0 if rng.random() < 0.04 else float(
                        rng.choice([-1, 1]) * span * rng.uniform(0.0, 0.3)
                    )
                    cases.append(
                        _inflate_case(
                            family, dtype, paths, delta, jt, et,
                            miter=float(rng.uniform(1.0, 10.0)),
                            arc=float(rng.choice([0.0, span * 0.01, span * 0.2])),
                            precision=gen_precision(rng),
                        )
                    )
    # ClipperOffset itself is 64-only upstream, and so is its z callback.
    for jt in (0, 1, 2, 3):
        for et in (0, 1, 2, 3, 4):
            for i in range(per_class_combo):
                prog = Z_PROGRAMS[i % len(Z_PROGRAMS)]
                span = pick_span(rng, "64", huge_p=0.0)
                zmax = pick_zmax(rng, "64", prog)
                groups = [
                    (jt, et, _offset_paths(rng, "64", span, zmax)),
                    (int(rng.integers(4)), int(rng.integers(5)),
                     _offset_paths(rng, "64", span, zmax)),
                ][: int(rng.integers(1, 3))]
                cases.append(
                    _offset_class_case(
                        groups, prog,
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
                clipper2z.inflate_paths(paths, delta, _jt(jt), _et(et),
                                        miter_limit=miter, arc_tolerance=arc, **kw),
                dtype, "inflated", 3,
            )
        ],
    )


def _offset_class_case(groups, prog, delta, miter, arc, pc, rs, as_tree):
    record = " ".join(
        [f"offset64 {prog} {enc_num(miter)} {enc_num(arc)} {int(pc)} {int(rs)} "
         f"{enc_num(delta)} {int(as_tree)} {len(groups)}"]
        + [f"{jt} {et} {enc_paths(paths)}" for jt, et, paths in groups]
    )

    def call():
        co = clipper2z.ClipperOffset(
            miter_limit=miter, arc_tolerance=arc, preserve_collinear=pc, reverse_solution=rs
        )
        co.set_z_callback(z_program(prog))
        for jt, et, paths in groups:
            co.add_paths(paths, _jt(jt), _et(et))
        if as_tree:
            return [tree_value(co.execute_tree(delta), np.int64, "tree", 3)]
        return [arrs(co.execute(delta), np.int64, "offset", 3)]

    parse = (lambda r: [r.tree(np.int64)]) if as_tree else (lambda r: [r.paths(np.int64)])
    return Case(record, parse, call)


# --------------------------------------------------------------------------- rect clip
#
# RectClip has no z code of its own: a vertex of the input keeps its z, and a point where an
# edge meets the rectangle is built by GetLineIntersectPt, which sets z to 0.  Rect64 / RectD
# stay two-dimensional in the z build (DEVIATIONS 7), so the rectangle is (l, t, r, b).


def _rect_cases(rng, count, lines: bool) -> list[Case]:
    cases = []
    name = "rect_clip_lines" if lines else "rect_clip"
    for _ in range(count):
        family = "64" if rng.integers(2) else "d"
        dtype = DTYPE[family]
        span = pick_span(rng, family)
        paths = z_paths(rng, family, pick_zmax(rng, family), span=span)
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
            rect_cls = clipper2z.Rect64 if family == "64" else clipper2z.RectD
            kw = {} if family == "64" else {"precision": precision}
            fn = clipper2z.rect_clip_lines if lines else clipper2z.rect_clip
            return [arrs(fn(rect_cls(*rect_args), paths, **kw), dtype, "clipped", 3)]

        cases.append(Case(record, lambda r, dtype=dtype: [r.paths(dtype)], call))
    return cases


def cases_rect_clip(rng, count=500):
    return _rect_cases(rng, count, lines=False)


def cases_rect_clip_lines(rng, count=500):
    return _rect_cases(rng, count, lines=True)


# --------------------------------------------------------------------------- minkowski
#
# Minkowski adds and subtracts points, and Point::operator+ / operator- build a new point
# without a z, so every vertex of the sum starts at z = 0; the union that follows runs
# without a callback.  The whole result is therefore z = 0 - which is exactly what the
# binding has to reproduce.


def cases_minkowski(rng, per_combo=50) -> list[Case]:
    cases = []
    for family in ("64", "d"):
        dtype = DTYPE[family]
        for kind in ("sum", "diff"):
            for is_closed in (False, True):
                for _ in range(per_combo):
                    span = pick_span(rng, family, huge_p=0.0)
                    zmax = pick_zmax(rng, family)
                    lo = 1 if family == "d" else 0
                    pattern = z_path(rng, family, zmax, span=span / 8,
                                     npts=int(rng.integers(lo, 8)))
                    path = z_path(rng, family, zmax, span=span,
                                  npts=int(rng.integers(lo, 12)))
                    decimals = int(rng.integers(0, 9))
                    prefix = "" if family == "64" else f"{decimals} "
                    record = (f"minkowski_{kind}{family} {prefix}{int(is_closed)} "
                              f"{enc_path(pattern)} {enc_path(path)}")
                    kw = {} if family == "64" else {"decimal_places": decimals}

                    def call(kind=kind, pattern=pattern, path=path, is_closed=is_closed,
                             kw=kw, dtype=dtype):
                        fn = (clipper2z.minkowski_sum if kind == "sum"
                              else clipper2z.minkowski_diff)
                        return [arrs(fn(pattern, path, is_closed, **kw), dtype, kind, 3)]

                    cases.append(Case(record, lambda r, dtype=dtype: [r.paths(dtype)], call))
    return cases


# --------------------------------------------------------------------------- triangulate
#
# The triangulator has no z code either: it re-emits input vertices, so their z rides along.
# Same inputs as the non-z test - upstream's Triangulate does not return on some of them
# (issue #2), which is why this is the one group allowed to hang.


def cases_triangulate(rng, per_combo=60) -> list[Case]:
    cases = []
    for family in ("64", "d"):
        dtype = DTYPE[family]
        for use_delaunay in (False, True):
            for i in range(per_combo):
                scale_idx = int(rng.integers(3))
                span = TRI_SPANS[family][scale_idx]
                decimals = int(rng.integers(TRI_MIN_DECIMALS[family][scale_idx], 9))
                zmax = pick_zmax(rng, family)
                if rng.random() < 0.1:  # too little to triangulate: no_polygons
                    paths = [] if family == "64" else [empty3(family)]
                    if rng.random() < 0.5:
                        paths = [z_path(rng, family, zmax, "blob", span,
                                        npts=int(rng.integers(1, 3)))]
                elif i % 2 == 0:
                    paths = [with_z(rng, p, zmax) for p in _triangulable(rng, family, span)]
                else:
                    paths = [
                        z_path(rng, family, zmax, "star" if rng.integers(2) else "blob", span,
                               center=tuple(rng.uniform(-span, span, 2) * 2),
                               npts=int(rng.integers(3, 13)))
                        for _ in range(int(rng.integers(1, 3)))
                    ]
                prefix = "" if family == "64" else f"{decimals} "
                record = f"triangulate{family} {prefix}{int(use_delaunay)} {enc_paths(paths)}"
                kw = {} if family == "64" else {"dec_places": decimals}

                def call(paths=paths, dtype=dtype, use_delaunay=use_delaunay, kw=kw):
                    result, solution = clipper2z.triangulate(
                        paths, use_delaunay=use_delaunay, **kw
                    )
                    return [_enum_int(result), arrs(solution, dtype, "triangles", 3)]

                cases.append(
                    Case(record, lambda r, dtype=dtype: [r.int(), r.paths(dtype)], call)
                )
    return cases


# ------------------------------------------- simplify / RDP / trim collinear / duplicates


def cases_simplify(rng, per_combo=60) -> list[Case]:
    cases = []
    for family in ("64", "d"):
        dtype = DTYPE[family]
        for is_closed in (False, True):
            for _ in range(per_combo):
                span = pick_span(rng, family)
                paths = z_paths(rng, family, pick_zmax(rng, family), span=span,
                                npts=int(rng.integers(0, 40)))
                eps = float(span * rng.choice([0.0, 1e-4, 0.01, 0.2, 2.0]))
                record = (f"simplify_paths{family} {enc_num(eps)} {int(is_closed)} "
                          f"{enc_paths(paths)}")

                def call(paths=paths, eps=eps, is_closed=is_closed, dtype=dtype):
                    return [arrs(clipper2z.simplify_paths(paths, eps, is_closed),
                                 dtype, "simplified", 3)]

                cases.append(Case(record, lambda r, dtype=dtype: [r.paths(dtype)], call))
    return cases


def cases_rdp(rng, count=200) -> list[Case]:
    cases = []
    for i in range(count):
        family = "64" if i % 2 else "d"
        dtype = DTYPE[family]
        span = pick_span(rng, family)
        paths = z_paths(rng, family, pick_zmax(rng, family), count=int(rng.integers(1, 4)),
                        span=span, npts=int(rng.integers(0, 40)))
        eps = float(span * rng.choice([0.0, 1e-4, 0.01, 0.2, 2.0]))
        record = f"rdp{family} {enc_num(eps)} {enc_paths(paths)}"

        def call(paths=paths, eps=eps, dtype=dtype):
            return [arrs(clipper2z.ramer_douglas_peucker(paths, eps), dtype, "rdp", 3)]

        cases.append(Case(record, lambda r, dtype=dtype: [r.paths(dtype)], call))
    return cases


def _single_path(rng, family, zmax, kind=None, npts_hi=30) -> np.ndarray:
    path = z_path(rng, family, zmax, kind, npts=int(rng.integers(0, npts_hi)))
    if family == "d" and not len(path):  # a lone empty array has no dtype to dispatch on
        path = z_path(rng, family, zmax, "convex", npts=int(rng.integers(3, 13)))
    return path


def cases_trim_collinear(rng, count=200) -> list[Case]:
    cases = []
    for i in range(count):
        family = "64" if i % 2 else "d"
        dtype = DTYPE[family]
        is_open = bool(rng.integers(2))
        precision = gen_precision(rng)
        kind = "collinear" if rng.random() < 0.5 else None
        path = _single_path(rng, family, pick_zmax(rng, family), kind)
        prefix = "" if family == "64" else f"{precision} "
        record = f"trim_collinear{family} {prefix}{int(is_open)} {enc_path(path)}"
        kw = {} if family == "64" else {"precision": precision}

        def call(path=path, is_open=is_open, kw=kw, dtype=dtype):
            return [arr(clipper2z.trim_collinear(path, is_open_path=is_open, **kw),
                        dtype, "trimmed", 3)]

        cases.append(Case(record, lambda r, dtype=dtype: [r.path(dtype)], call))
    return cases


def cases_strip_duplicates(rng, count=200) -> list[Case]:
    """Point equality ignores z upstream, so of two points that differ only in z the first
    one survives - worth pinning down."""
    cases = []
    for i in range(count):
        family = "64" if i % 2 else "d"
        dtype = DTYPE[family]
        is_closed = bool(rng.integers(2))
        kind = "dup" if rng.random() < 0.7 else None
        path = _single_path(rng, family, pick_zmax(rng, family), kind, npts_hi=15)
        record = f"strip_duplicates{family} {int(is_closed)} {enc_path(path)}"

        def call(path=path, is_closed=is_closed, dtype=dtype):
            return [arr(clipper2z.strip_duplicates(path, is_closed), dtype, "stripped", 3)]

        cases.append(Case(record, lambda r, dtype=dtype: [r.path(dtype)], call))
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
    "strip_duplicates": (cases_strip_duplicates, 10),
}
BASE_SEED = 20260920


def build(group: str) -> list[Case]:
    generator, offset = GROUPS[group]
    return generator(np.random.default_rng(BASE_SEED + offset))


def run(group: str, may_hang: bool = False) -> None:
    check(build(group), cli=REF_CLI_Z, cols=3, may_hang=may_hang)


def test_boolean_ops():
    run("boolean")


def test_offset():
    run("offset")


def test_rect_clip():
    run("rect_clip")


def test_rect_clip_lines():
    run("rect_clip_lines")


def test_minkowski():
    run("minkowski")


def test_triangulate():
    run("triangulate", may_hang=True)  # upstream issue #2, see test_differential.run_ref


def test_simplify_paths():
    run("simplify")


def test_ramer_douglas_peucker():
    run("rdp")


def test_trim_collinear():
    run("trim_collinear")


def test_strip_duplicates():
    run("strip_duplicates")


def test_at_least_3000_cases():
    counts = {name: len(build(name)) for name in GROUPS}
    assert sum(counts.values()) >= 3000, counts
