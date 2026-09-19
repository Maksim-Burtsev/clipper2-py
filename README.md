# clipper2-py

[![PyPI](https://img.shields.io/pypi/v/clipper2-py.svg)](https://pypi.org/project/clipper2-py/)
[![Python versions](https://img.shields.io/pypi/pyversions/clipper2-py.svg)](https://pypi.org/project/clipper2-py/)
[![CI](https://github.com/Maksim-Burtsev/clipper2-py/actions/workflows/wheels.yml/badge.svg)](https://github.com/Maksim-Burtsev/clipper2-py/actions/workflows/wheels.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/Maksim-Burtsev/clipper2-py/blob/main/LICENSE)

Python bindings for [Clipper2](https://github.com/AngusJohnson/Clipper2), Angus Johnson's
C++ library for polygon clipping, offsetting and triangulation. Unofficial; the whole C++
API, numpy in and out.

![intersect, union, difference, xor](https://raw.githubusercontent.com/Maksim-Burtsev/clipper2-py/main/docs/img/booleans.svg)

```python
import clipper2

subject = [[(0, 0), (100, 0), (100, 100), (0, 100)]]
clip = [[(50, 50), (150, 50), (150, 150), (50, 150)]]

solution = clipper2.intersect(subject, clip, clipper2.FillRule.NON_ZERO)
print(solution[0].tolist())
# -> [[100, 100], [50, 100], [50, 50], [100, 50]]
```

```bash
pip install clipper2-py
```

Wheels for Linux (x86_64, aarch64), macOS (x86_64, arm64) and Windows (AMD64),
CPython 3.10–3.14. Clipper2 is compiled in; numpy is the only dependency.

## Offsetting

![round, miter and bevel joins](https://raw.githubusercontent.com/Maksim-Burtsev/clipper2-py/main/docs/img/offsetting.svg)

```python
from clipper2 import EndType, JoinType

square = [[(0, 0), (100, 0), (100, 100), (0, 100)]]
grown = clipper2.inflate_paths(square, 10, JoinType.MITER, EndType.POLYGON)
print(grown[0].tolist())
# -> [[110, 110], [-10, 110], [-10, -10], [110, -10]]
```

Open paths become strokes with `EndType.BUTT`, `SQUARE` or `ROUND`. `ClipperOffset` is
the class behind it, with per-vertex deltas through a callback.

## Triangulation, Minkowski sums, rectangle clipping

![triangulate and minkowski_sum](https://raw.githubusercontent.com/Maksim-Burtsev/clipper2-py/main/docs/img/triangulate-minkowski.svg)

```python
result, triangles = clipper2.triangulate(square)
print(result.name, len(triangles))
# -> SUCCESS 2

rect = clipper2.Rect64(50, 50, 200, 200)
print(clipper2.rect_clip(rect, square)[0].tolist())
# -> [[50, 50], [100, 50], [100, 100], [50, 100]]
```

## Integers or floats

Clipper2 has two families of every function: `Paths64` on `int64` and `PathsD` on
`double`. Here there is one function, and the input picks the family:

```python
print(clipper2.union([[(0, 0), (10, 0), (10, 10)]], clipper2.FillRule.NON_ZERO)[0].dtype)
# -> int64
print(clipper2.union([[(0, 0), (10, 0), (10.5, 10)]], clipper2.FillRule.NON_ZERO)[0].dtype)
# -> float64
```

Paths go in as lists of pairs or N×2 numpy arrays and come back as numpy arrays.

## The same library, not a lookalike

- **Names are upstream's, in snake_case**: `InflatePaths` → `inflate_paths`,
  `Clipper64.AddSubject` → `add_subject`, `FillRule::NonZero` → `FillRule.NON_ZERO`.
  [Every C++ symbol and its Python name](https://github.com/Maksim-Burtsev/clipper2-py/blob/main/docs/api-map.md).
- **Results are upstream's, bit for bit.** 13 500 random cases are compared with a C++
  reference program on every platform, for every wheel, and must be exactly equal —
  including the `USINGZ` build, which is `clipper2.z`. Upstream's own test suite is ported
  one to one.
- **Every difference from C++ is written down** in [DEVIATIONS.md](https://github.com/Maksim-Burtsev/clipper2-py/blob/main/DEVIATIONS.md): out
  parameters became return values, errors became exceptions, and where C++ has undefined
  behaviour Python raises.

More examples — `Clipper64` with open paths and the polytree, offset callbacks, the z
module — are in the [guide](https://github.com/Maksim-Burtsev/clipper2-py/blob/main/docs/guide.md).

## Benchmarks

Apple M4, CPython 3.13, best of 5, conversion from numpy included:

| | clipper2-py | pyclipr | pyclipper | shapely |
| --- | --- | --- | --- | --- |
| union of 1000 polygons | 34.4 ms | 35.7 ms | 71.2 ms | **11.4 ms** |
| intersection, 10⁵ vertices | **5.25 ms** | 5.46 ms | 30.5 ms | 9.51 ms |
| round offset, 1000 vertices | 0.36 ms | 0.39 ms | 1.46 ms | **0.24 ms** |
| one small call | **1.14 µs** | 2.43 µs | 2.31 µs | 13.9 µs |

pyclipr wraps the same Clipper2 and is as fast, but ships no Linux wheels and has its own
API. pyclipper is Clipper1. shapely (GEOS) wins on big unions and on buffering.
[Method and full results](https://github.com/Maksim-Burtsev/clipper2-py/blob/main/benchmarks/RESULTS.md).

## Known upstream issues

Two bugs of Clipper2 2.0.1, also present in its main branch, are reachable from Python.
The binding changes nothing in upstream's algorithms, so it does not hide them:

- `ClipperOffset` crashes on an **empty path with an open end type**
  ([#1](https://github.com/Maksim-Burtsev/clipper2-py/issues/1));
- `triangulate` may never return on paths with **duplicate or self-intersecting
  vertices**, and which inputs do depends on the platform
  ([#2](https://github.com/Maksim-Burtsev/clipper2-py/issues/2)).

## License

MIT for the binding; Clipper2 is under the Boost Software License 1.0. Both texts ship in
every wheel. `clipper2.CLIPPER2_VERSION` tells which Clipper2 is inside (2.0.1).
