#!/usr/bin/env python3
"""Benchmark clipper2 against pyclipr, pyclipper and shapely.

    python -m venv benchmarks/.venv
    benchmarks/.venv/bin/pip install pyclipr pyclipper shapely .
    benchmarks/.venv/bin/python benchmarks/bench.py > benchmarks/RESULTS.md

Every library is given the same polygons with the same integer coordinates and the
same fill rule, and every call includes the conversion from numpy that the library
needs, so the numbers are comparable end to end.  The area column is the check that
the libraries computed the same thing; a missing library is skipped.
"""

from __future__ import annotations

import platform
import subprocess
import sys
import timeit
from datetime import date
from importlib.metadata import PackageNotFoundError, version

import numpy as np

import clipper2

try:
    import pyclipr
except ImportError:  # pragma: no cover - reported in the output
    pyclipr = None
try:
    import pyclipper
except ImportError:  # pragma: no cover
    pyclipper = None
try:
    import shapely
except ImportError:  # pragma: no cover
    shapely = None

SEED = 20260919
REPEAT = 5
NON_ZERO = clipper2.FillRule.NON_ZERO


# --------------------------------------------------------------------------- input data


def circle(cx: float, cy: float, r: float, n: int, phase: float = 0.0) -> np.ndarray:
    """A closed n-gon approximating a circle, on the integer grid."""
    t = phase + np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    return np.column_stack((cx + r * np.cos(t), cy + r * np.sin(t))).round().astype(np.int64)


def rosette(n: int, lobes: int = 12, radius: float = 1e6, amplitude: float = 2e5) -> np.ndarray:
    """A wavy, non self-intersecting polygon: something with real corners to offset."""
    t = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    r = radius + amplitude * np.sin(lobes * t)
    return np.column_stack((r * np.cos(t), r * np.sin(t))).round().astype(np.int64)


def random_polygons(count: int) -> list[np.ndarray]:
    rng = np.random.default_rng(SEED)
    return [
        circle(
            *rng.uniform(0.0, 1e6, 2),
            rng.uniform(5e4, 1.5e5),
            16,
            rng.uniform(0.0, 2.0 * np.pi),
        )
        for _ in range(count)
    ]


# --------------------------------------------------------------------------- measuring


def area_of(result) -> float:
    """Total area of a result, whatever shape the library returned it in."""
    if shapely is not None and isinstance(result, shapely.Geometry):
        return abs(result.area)
    total = 0.0
    for path in result:
        p = np.asarray(path, dtype=np.float64)
        if len(p) < 3:
            continue
        x, y = p[:, 0], p[:, 1]
        total += 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
    return abs(total)


def points_of(result) -> int:
    if shapely is not None and isinstance(result, shapely.Geometry):
        return int(shapely.get_num_coordinates(result))
    return sum(len(path) for path in result)


def best(fn, number: int | None = None) -> float:
    """Best of REPEAT runs, seconds per call."""
    fn()  # warm up
    if number is None:
        single = timeit.timeit(fn, number=1)
        number = max(1, int(0.05 / single)) if single > 0 else 1000
    return min(timeit.repeat(fn, repeat=REPEAT, number=number)) / number


# --------------------------------------------------------------------------- workloads


def union_cases(polygons: list[np.ndarray]) -> dict:
    floats = [p.astype(np.float64) for p in polygons]
    stacked = np.stack(floats)
    cases = {"clipper2": lambda: clipper2.union(polygons, NON_ZERO)}

    if pyclipr is not None:

        def with_pyclipr():
            clipper = pyclipr.Clipper()
            clipper.scaleFactor = 1.0
            clipper.addPaths(floats, pyclipr.Subject)
            return clipper.execute(pyclipr.Union, pyclipr.FillRule.NonZero)

        cases["pyclipr"] = with_pyclipr

    if pyclipper is not None:

        def with_pyclipper():
            clipper = pyclipper.Pyclipper()
            clipper.AddPaths(polygons, pyclipper.PT_SUBJECT, True)
            return clipper.Execute(
                pyclipper.CT_UNION, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO
            )

        cases["pyclipper"] = with_pyclipper

    if shapely is not None:
        cases["shapely"] = lambda: shapely.union_all(shapely.polygons(stacked))

    return cases


def intersect_cases(subject: np.ndarray, clip: np.ndarray) -> dict:
    subject_f, clip_f = subject.astype(np.float64), clip.astype(np.float64)
    cases = {"clipper2": lambda: clipper2.intersect([subject], [clip], NON_ZERO)}

    if pyclipr is not None:

        def with_pyclipr():
            clipper = pyclipr.Clipper()
            clipper.scaleFactor = 1.0
            clipper.addPaths([subject_f], pyclipr.Subject)
            clipper.addPaths([clip_f], pyclipr.Clip)
            return clipper.execute(pyclipr.Intersection, pyclipr.FillRule.NonZero)

        cases["pyclipr"] = with_pyclipr

    if pyclipper is not None:

        def with_pyclipper():
            clipper = pyclipper.Pyclipper()
            clipper.AddPath(subject, pyclipper.PT_SUBJECT, True)
            clipper.AddPath(clip, pyclipper.PT_CLIP, True)
            return clipper.Execute(
                pyclipper.CT_INTERSECTION, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO
            )

        cases["pyclipper"] = with_pyclipper

    if shapely is not None:
        cases["shapely"] = lambda: shapely.intersection(
            shapely.polygons(subject_f), shapely.polygons(clip_f)
        )

    return cases


def offset_cases(path: np.ndarray, delta: float) -> dict:
    path_f = path.astype(np.float64)
    cases = {
        "clipper2": lambda: clipper2.inflate_paths(
            [path], delta, clipper2.JoinType.ROUND, clipper2.EndType.POLYGON
        )
    }

    if pyclipr is not None:

        def with_pyclipr():
            offset = pyclipr.ClipperOffset()
            offset.scaleFactor = 1.0
            offset.addPaths([path_f], pyclipr.JoinType.Round, pyclipr.EndType.Polygon)
            return offset.execute(delta)

        cases["pyclipr"] = with_pyclipr

    if pyclipper is not None:

        def with_pyclipper():
            offset = pyclipper.PyclipperOffset()
            offset.AddPath(path, pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
            return offset.Execute(delta)

        cases["pyclipper"] = with_pyclipper

    if shapely is not None:
        cases["shapely"] = lambda: shapely.polygons(path_f).buffer(delta, quad_segs=8)

    return cases


def conversion_cases() -> dict:
    """Two four-point squares: the result is trivial, the time is call overhead."""
    subject = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], dtype=np.int64)
    clip = subject + 50
    return intersect_cases(subject, clip)


# --------------------------------------------------------------------------- reporting


def fmt_time(seconds: float) -> str:
    if seconds < 1e-3:
        return f"{seconds * 1e6:.2f} us"
    if seconds < 1.0:
        return f"{seconds * 1e3:.2f} ms"
    return f"{seconds:.3f} s"


def run(title: str, cases: dict, note: str = "", number: int | None = None) -> None:
    print(f"### {title}\n")
    if note:
        print(f"{note}\n")
    print("| library | best of 5 | vs clipper2 | area | output vertices |")
    print("| --- | --- | --- | --- | --- |")

    baseline_time = baseline_area = None
    for name, call in cases.items():
        seconds = best(call, number)
        result = call()
        area, points = area_of(result), points_of(result)
        if baseline_time is None:
            baseline_time, baseline_area = seconds, area
            ratio = area_text = "-"
        else:
            ratio = f"{seconds / baseline_time:.2f}x"
            delta = (area - baseline_area) / baseline_area if baseline_area else 0.0
            area_text = "exact" if area == baseline_area else f"{delta:+.2e}"
        print(f"| {name} | {fmt_time(seconds)} | {ratio} | {area:.6g} ({area_text}) | {points} |")
    print()


def cpu_name() -> str:
    try:
        if sys.platform == "darwin":
            out = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True
            )
            return out.stdout.strip() or platform.machine()
        if sys.platform.startswith("linux"):
            for line in open("/proc/cpuinfo"):
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine()


def installed(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "not installed"


def main() -> None:
    print("# Benchmarks\n")
    print(f"Generated by `benchmarks/bench.py` on {date.today().isoformat()}.\n")
    print("```")
    print("python -m venv benchmarks/.venv")
    print("benchmarks/.venv/bin/pip install pyclipr pyclipper shapely .")
    print("benchmarks/.venv/bin/python benchmarks/bench.py > benchmarks/RESULTS.md")
    print("```\n")

    print("| | |")
    print("| --- | --- |")
    print(f"| machine | {cpu_name()}, {platform.platform()} |")
    print(f"| python | {platform.python_version()} ({platform.python_implementation()}) |")
    print(f"| clipper2-py | {installed('clipper2-py')} (Clipper2 {clipper2.CLIPPER2_VERSION}) |")
    pyclipr_version = installed("pyclipr")
    if pyclipr is not None:
        pyclipr_version += f" (Clipper2 {pyclipr.clipperVersion})"
    print(f"| pyclipr | {pyclipr_version} |")
    print(f"| pyclipper | {installed('pyclipper')} (Clipper1 6.4.2) |")
    print(f"| shapely | {installed('shapely')} (GEOS {shapely.geos_version_string if shapely else '-'}) |")
    print(f"| numpy | {np.__version__} |")
    print()

    print(
        "Coordinates are integers, so `clipper2` runs its 64 family, `pyclipr` runs with\n"
        "`scaleFactor = 1.0` and `pyclipper` gets the values unscaled: all three see the\n"
        "same integers. Fill rule is non-zero everywhere. Times are the best of 5 runs and\n"
        "include, for every library, the conversion from the numpy input, the clipper\n"
        "object's construction and the conversion of the result back — shapely included,\n"
        "whose geometries are built from the same arrays inside the timed call.\n"
        "`area` is the total area of the result and `(...)` its relative difference from\n"
        "clipper2's.\n"
    )

    print("## Union of N random overlapping 16-gons\n")
    for n in (10, 100, 1000):
        run(f"N = {n}", union_cases(random_polygons(n)))

    print("## Intersection of two large polygons\n")
    for n in (1_000, 10_000, 100_000):
        subject = circle(0, 0, 1e6, n)
        clip = circle(6e5, 0, 1e6, n, phase=np.pi / n)
        run(f"{n} vertices each", intersect_cases(subject, clip))

    print("## Offsetting with round joins\n")
    run(
        "1000-vertex rosette, delta = 50000",
        offset_cases(rosette(1000), 5e4),
        note=(
            "Round joins are approximated differently by each library (clipper2 and "
            "pyclipr from `arc_tolerance`, pyclipper from Clipper1's `ArcTolerance`, "
            "shapely from `quad_segs`), so the areas differ by construction; the vertex "
            "count shows how finely each one drew the arcs."
        ),
    )

    print("## Call overhead\n")
    run(
        "Intersection of two squares, 100 000 calls",
        conversion_cases(),
        note="The geometry is trivial, so this is conversion and call overhead.",
        number=100_000,
    )


if __name__ == "__main__":
    main()
