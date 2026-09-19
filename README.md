# clipper2-py

[![PyPI](https://img.shields.io/pypi/v/clipper2-py.svg)](https://pypi.org/project/clipper2-py/)
[![Python versions](https://img.shields.io/pypi/pyversions/clipper2-py.svg)](https://pypi.org/project/clipper2-py/)
[![wheels](https://github.com/Maksim-Burtsev/clipper2-py/actions/workflows/wheels.yml/badge.svg)](https://github.com/Maksim-Burtsev/clipper2-py/actions/workflows/wheels.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

An unofficial binding of [Clipper2](https://github.com/AngusJohnson/Clipper2), Angus
Johnson's C++ library for polygon boolean operations, offsetting, rectangle clipping,
Minkowski sums and triangulation.

```python
import clipper2

subject = [[(0, 0), (100, 0), (100, 100), (0, 100)]]
clip = [[(50, 50), (150, 50), (150, 150), (50, 150)]]

solution = clipper2.union(subject, clip, clipper2.FillRule.NON_ZERO)
print(solution[0].tolist())
# -> [[100, 50], [150, 50], [150, 150], [50, 150], [50, 100], [0, 100], [0, 0], [100, 0]]
print(clipper2.area(solution))
# -> 17500.0
```

```bash
pip install clipper2-py
```

Wheels for Linux (x86_64, aarch64; manylinux_2_28), macOS (x86_64, arm64) and Windows
(AMD64), CPython 3.10–3.14. Clipper2 is compiled into the wheel, so there is nothing else
to install; numpy is the only runtime dependency. Building from the sdist needs CMake and
a C++17 compiler. Building from a git checkout also needs the upstream submodule:
`git clone --recursive`, or `git submodule update --init` in an existing clone.

The whole public C++ API is bound, upstream's algorithms untouched. `clipper2` is the
plain build and `clipper2.z` the same library compiled with `USINGZ`.

## Quick start

### Boolean operations

Upstream has two families of the same functions: `Paths64` on `int64_t` coordinates and
`PathsD` on `double`. There is one Python function for both, and the dtype numpy infers
for the input picks the family — integers run the 64 family, floats run the D family:

```python
import numpy as np

print(clipper2.union([[(0, 0), (10, 0), (10, 10)]], clipper2.FillRule.NON_ZERO)[0].dtype)
# -> int64
print(clipper2.union([[(0, 0), (10, 0), (10.5, 10)]], clipper2.FillRule.NON_ZERO)[0].dtype)
# -> float64
```

A path goes in as any sequence of pairs or an N×2 array and comes back as an N×2 numpy
array; paths come back as a list of those:

```python
square = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]])
strip = np.array([[2.5, -5.0], [7.5, -5.0], [7.5, 15.0], [2.5, 15.0]])

solution = clipper2.intersect([square], [strip], clipper2.FillRule.NON_ZERO)
print(solution[0].tolist())
# -> [[7.5, 10.0], [2.5, 10.0], [2.5, 0.0], [7.5, 0.0]]
print(clipper2.area(solution))
# -> 50.0
```

Mixing the families in one call is a `TypeError`, because in C++ it would not compile:

```python
try:
    clipper2.intersect(
        [[(0, 0), (10, 0), (10, 10)]],
        [[(0.0, 0.0), (5.0, 0.0), (5.0, 5.0)]],
        clipper2.FillRule.NON_ZERO,
    )
except TypeError as exc:
    print(exc)
# -> integer and float coordinates in one call: every point and path argument must be of the same family
```

`union`, `intersect`, `difference` and `xor` are the shorthands; `boolean_op` takes the
`ClipType` as an argument, and `boolean_op_tree` is the overload that fills a `PolyTree`.

### Clipper64: open paths and the polytree

The class is what adds open subjects, reuses one clipper for several operations and
returns a tree. Out parameters became return values, so `execute` returns
`(closed_paths, open_paths)`.

```python
clipper = clipper2.Clipper64()
clipper.add_subject([[(0, 0), (100, 0), (100, 100), (0, 100)]])
clipper.add_open_subject([[(-20, 50), (120, 50)]])
clipper.add_clip([[(50, -20), (150, -20), (150, 120), (50, 120)]])

closed, open_paths = clipper.execute(clipper2.ClipType.INTERSECTION, clipper2.FillRule.NON_ZERO)
print(closed[0].tolist())
# -> [[100, 100], [50, 100], [50, 0], [100, 0]]
print(open_paths[0].tolist())
# -> [[50, 50], [120, 50]]
```

`execute_tree` returns `(tree, open_paths)`. The tree nests outlines and holes; it is
read-only from Python, iterates over its children and knows `level`, `is_hole`, `parent`,
`polygon` and `area()`:

```python
clipper = clipper2.Clipper64()
clipper.add_subject([[(0, 0), (100, 0), (100, 100), (0, 100)],
                     [(20, 20), (20, 80), (80, 80), (80, 20)]])
tree, _ = clipper.execute_tree(clipper2.ClipType.UNION, clipper2.FillRule.EVEN_ODD)


def walk(node):
    for child in node:
        kind = "hole" if child.is_hole else "outline"
        print(f"level {child.level}: {kind}, area {child.area()}, {len(child.polygon)} vertices")
        walk(child)


walk(tree)
# -> level 1: outline, area 6400.0, 4 vertices
# -> level 2: hole, area -3600.0, 4 vertices
print(len(clipper2.poly_tree_to_paths64(tree)))
# -> 2
```

### Offsetting

`inflate_paths` is the free function: a delta, a join type and an end type.

```python
SQUARE = [(0, 0), (100, 0), (100, 100), (0, 100)]

(grown,) = clipper2.inflate_paths(
    [SQUARE], 10.0, clipper2.JoinType.ROUND, clipper2.EndType.POLYGON
)
print(len(grown), clipper2.area([grown]))
# -> 24 14308.0
(shrunk,) = clipper2.inflate_paths(
    [SQUARE], -10.0, clipper2.JoinType.MITER, clipper2.EndType.POLYGON
)
print(shrunk.tolist())
# -> [[90, 10], [90, 90], [10, 90], [10, 10]]
```

An open end type turns a line into a band; `EndType.ROUND` caps it with half circles:

```python
(capsule,) = clipper2.inflate_paths(
    [[(0, 0), (100, 0)]], 10.0, clipper2.JoinType.ROUND, clipper2.EndType.ROUND
)
print(len(capsule), round(clipper2.area([capsule])))
# -> 22 2309
```

`ClipperOffset` is the class behind it, with upstream's properties:

```python
offset = clipper2.ClipperOffset(miter_limit=4.0)
offset.add_path(SQUARE, clipper2.JoinType.MITER, clipper2.EndType.POLYGON)
print(offset.execute(10.0)[0].tolist())
# -> [[110, 110], [-10, 110], [-10, -10], [110, -10]]
```

A delta callback varies the offset along the path. It is upstream's `DeltaCallback64`:
it receives the path, its unit normals and the current and previous vertex indices, and
its return value is the delta used at that vertex, in place of the one passed to
`execute`.

```python
def taper(path, path_normals, curr_idx, prev_idx):
    return 5.0 + 15.0 * curr_idx / len(path)


offset.set_delta_callback(taper)
print(offset.execute(1.0)[0].tolist())
# -> [[113, 113], [-16, 116], [-5, -5], [109, -9]]
```

`execute_tree(delta)` returns a `PolyTree64` instead of the paths.

### Rectangle clipping, Minkowski sums, triangulation

`rect_clip` is upstream's fast path for clipping against an axis-aligned rectangle, and
`rect_clip_lines` does the same for open paths:

```python
rect = clipper2.Rect64(0, 0, 50, 50)
print(clipper2.rect_clip(rect, [SQUARE])[0].tolist())
# -> [[50, 50], [0, 50], [0, 0], [50, 0]]
print(clipper2.rect_clip_lines(rect, [[(-20, 25), (120, 25)]])[0].tolist())
# -> [[0, 25], [50, 25]]
```

`minkowski_sum` and `minkowski_diff` sweep a pattern along a path:

```python
pattern = [(-2, -2), (2, -2), (2, 2), (-2, 2)]
swept = clipper2.minkowski_sum(pattern, [(0, 0), (20, 0), (20, 20), (0, 20)], True)
print(len(swept), clipper2.area(swept))
# -> 2 320.0
```

`triangulate` returns upstream's result code next to the triangles:

```python
result, triangles = clipper2.triangulate(
    [SQUARE, [(20, 20), (20, 80), (80, 80), (80, 20)]]
)
print(result)
# -> TriangulateResult.SUCCESS
print(len(triangles), sum(abs(clipper2.area(t)) for t in triangles))
# -> 8 6400.0
```

### The z module

`clipper2.z` is the same library built with `USINGZ`: points are `(x, y, z)`, paths are
N×3 arrays, and a callback fills in the z of the points the clipper creates. Upstream's
callback writes through a reference; here it returns the value.

```python
import clipper2.z as z

clipper = z.Clipper64()
clipper.set_z_callback(lambda e1bot, e1top, e2bot, e2top, pt: 99)
clipper.add_subject([[(0, 0, 1), (100, 0, 1), (100, 100, 1), (0, 100, 1)]])
clipper.add_clip([[(50, 50, 2), (150, 50, 2), (150, 150, 2), (50, 150, 2)]])

(result,) = clipper.execute(z.ClipType.INTERSECTION, z.FillRule.NON_ZERO)[0]
print(result.tolist())
# -> [[100, 100, 1], [50, 100, 99], [50, 50, 2], [100, 50, 99]]
```

Vertices that come from the input keep their z; the two new intersection points got the
callback's 99. The enums, `Rect64`, `RectD` and `Clipper2Error` are the same objects in
both modules, but the point layout differs, so a `clipper2.PolyTree64` is not a
`clipper2.z.PolyTree64` and the two modules' objects must not be mixed.

## How it maps to the C++ API

Names are the mechanical snake_case of upstream's: classes keep their CamelCase, enum
members are UPPER_SNAKE, a getter/setter pair becomes a property, and keyword-argument
names are upstream's parameter names (upstream is not always consistent, and neither is
this binding).

| C++ | Python |
| --- | --- |
| `InflatePaths(paths, delta, jt, et)` | `inflate_paths(paths, delta, jt, et)` |
| `Clipper64::AddSubject(subjects)` | `Clipper64.add_subject(subjects)` |
| `ClipperOffset::MiterLimit()` / `MiterLimit(v)` | `ClipperOffset.miter_limit` (property) |
| `FillRule::NonZero`, `JoinType::Round` | `FillRule.NON_ZERO`, `JoinType.ROUND` |
| `Clipper64::Execute(ct, fr, closed, open)` | `Clipper64.execute(clip_type, fill_rule) -> (closed, open)` |
| `Path64`, `PathD` | an N×2 numpy array (`int64` / `float64`) |
| `Paths64`, `PathsD` | a list of such arrays |
| `Point64`, `PointD` | a tuple `(x, y)` |
| `PolyTree64` (`= PolyPath64`) | `PolyTree64` — read-only, iterable |
| `Clipper2Lib::Clipper2Exception` | `clipper2.Clipper2Error` |

[docs/api-map.md](docs/api-map.md) lists **every** namespace-scope symbol of the upstream
headers with its Python name or the reason it is not bound.

## Differences from C++

Nothing here changes what the library computes. [DEVIATIONS.md](DEVIATIONS.md) has the
detail; in headline form:

1. **Names** are snake_case, as above; keyword names are upstream's parameter names,
   inconsistencies included (`boolean_op(..., precision=...)` but
   `intersect(..., decimal_prec=...)`, `add_path(path, jt_, et_)` with upstream's
   trailing underscores).
2. **Points and paths** are tuples and numpy arrays; the input dtype picks the 64 or D
   family, mixing families in one call is a `TypeError`, and where C++ picks an overload
   by static type (`Area(Path)` vs `Area(Paths)`) Python picks by nesting depth.
   `rect_clip` and `rect_clip_lines` take the family from the rect; `ClipperOffset`,
   `RectClip64` and `RectClipLines64` are 64-only, as upstream declares them.
3. **Validation** that the C++ compiler does for free: a wrong shape is a `ValueError`,
   an integer that does not fit `int64` is an `OverflowError`, a non-numeric dtype or a
   float where C++ takes `int64_t` is a `TypeError`, and an index outside a `PolyPath`'s
   children is an `IndexError` (C++ has undefined behaviour there). Nothing is ever
   truncated silently.
4. **Out parameters became return values**: `execute` returns `(closed, open)`,
   `execute_tree` returns `(tree, open)`, `ClipperOffset.execute(delta)` returns the
   paths, `triangulate` returns `(result, paths)`, `strip_duplicates` returns the
   stripped path instead of editing its argument, and the `BooleanOp` overload that
   fills a `PolyTree` is `boolean_op_tree`. `Execute` returning `false` raises
   `Clipper2Error`.
5. **`precision` / `decimal_prec` are keyword-only where the D overload inserts them
   mid-list.** One Python function serves both families, so in `inflate_paths`,
   `trim_collinear` and `triangulate` that parameter and everything after it are
   keyword-only — otherwise a positional call would change meaning with the input's
   dtype. They default to `None` and passing one to a 64-family call is a `TypeError`;
   `trim_collinear` and `triangulate` require it for float input, as upstream's overloads
   declare no default.
6. **Errors**: `Clipper2Lib::Clipper2Exception` becomes `clipper2.Clipper2Error` with
   upstream's message. Where C++ silently returns an empty result, so does Python.
7. **The z build** is a second module, `clipper2.z`. Upstream's z is `int64_t` in both
   families, so a D path carries an integer z in its `float64` third column and a
   fractional z is truncated towards zero. `set_z_callback(fn)` uses the callback's
   **return value** as the z, since Python cannot write through a C++ reference. Objects
   must not be passed between `clipper2` and `clipper2.z`.
8. **Callbacks and the GIL**: the GIL is released while upstream code runs, so two
   threads clip in parallel. An exception raised in a callback propagates out of
   `execute`, unwinding through C++ and skipping upstream's end-of-`Execute` cleanup:
   memory is still freed, but call `clear()` before reusing that object.
9. **Not bound**: `clipper.export.h` (a C ABI for DLL users), upstream's C++-only
   plumbing (the type-conversion templates `ScalePath` / `TransformPaths` — use a D
   function's `precision` or numpy's `astype` — the engine-internal structs, and the
   scalar helpers whose Python equivalent is exact), and `GetLineIntersectPt`, whose
   out-parameter has two defensible readings
   ([#3](https://github.com/Maksim-Burtsev/clipper2-py/issues/3)). `MakePath` and
   `MakePathD` are bound, because upstream's own documentation uses them.

## Known upstream issues

Two upstream bugs are reachable from Python. The binding adds no behaviour of its own, so
it adds no guard against them either.

- **`ClipperOffset` segfaults on an empty path with an open end type.** In Clipper2 2.0.1
  and in current upstream main, `DoGroupOffset` handles a one-point path but lets an empty
  one fall through to `OffsetOpenPath`, where `path.size() - 1` underflows.
  `EndType::Polygon` is safe; `Joined`, `Butt`, `Square` and `Round` crash. From Python
  this takes the interpreter down
  ([#1](https://github.com/Maksim-Burtsev/clipper2-py/issues/1)).
- **`Triangulate` does not return on some inputs.** In Clipper2 2.0.1 and in current
  upstream main, inputs with duplicate or self-intersecting vertices can make upstream's
  triangulation loop forever: 29 of 300 small random inputs in one check. An example is in
  the issue ([#2](https://github.com/Maksim-Burtsev/clipper2-py/issues/2)).

## Other Python packages

| | Clipper version | API | wheels on PyPI | typed |
| --- | --- | --- | --- | --- |
| **clipper2-py** 0.1.0 | Clipper2 2.0.1 | snake_case of upstream, complete; numpy in and out; int64 and double families; a `USINGZ` build | Linux x86_64/aarch64, macOS x86_64/arm64, Windows AMD64; CPython 3.10–3.14 | `py.typed` + stubs |
| [pyclipr](https://pypi.org/project/pyclipr/) 0.1.8 | Clipper2 2.0.1 | camelCase; numpy in and out; float coordinates scaled by a `scaleFactor` | macOS arm64, Windows AMD64; CPython 3.9–3.14 | `.pyi` stubs, no `py.typed` |
| [pyclipper](https://pypi.org/project/pyclipper/) 1.4.0 | Clipper 6.4.2 (Clipper1) | Cython wrapper keeping Clipper1's names (`Pyclipper`, `AddPaths`, `PT_SUBJECT`); lists of tuples | macOS x86_64/universal2, manylinux x86_64/aarch64, Windows 32/AMD64; CPython 3.10–3.14 including 3.14t, PyPy 3.11 | no |
| [pyclipper2](https://pypi.org/project/pyclipper2/) 0.0.8 | Clipper2 1.5.4 | nanobind; a subset (boolean ops, `inflate_paths`, `area`, `point_in_polygon`, …) | macOS arm64, CPython 3.13 | no |

File lists read from the PyPI JSON API on 2026-09-19. pyclipr publishes no Linux wheels,
so on Linux it is built from its sdist; pyclipper is the only one of the four with PyPy
and free-threaded wheels, and the only one still on Clipper1, which upstream has
superseded.

## Benchmarks

Apple M4, macOS 26.5.1, CPython 3.13, best of 5 runs. Every library is given the same
integer coordinates and the same fill rule, and every call includes the conversion from
numpy, so the numbers are comparable end to end.

| workload | clipper2-py | pyclipr | pyclipper | shapely |
| --- | --- | --- | --- | --- |
| union of 100 random 16-gons | 0.37 ms | 0.34 ms | 0.70 ms | 1.43 ms |
| union of 1000 random 16-gons | 37.7 ms | 37.3 ms | 76.4 ms | **11.8 ms** |
| intersection, 10⁵ vertices each | 5.64 ms | 6.53 ms | 31.7 ms | 9.80 ms |
| round offset, 1000-vertex rosette | 0.38 ms | 0.41 ms | 1.51 ms | **0.24 ms** |
| two squares, per call | 1.65 µs | 2.43 µs | 2.26 µs | 13.7 µs |

clipper2-py and pyclipr wrap the same upstream version and return the same areas to the
last bit, so the difference between them is binding overhead only, and it shows on small
calls. shapely (GEOS) wins two of the five: its cascaded union is three times faster on a
thousand polygons, and its buffer is faster than Clipper2's offset.

The full set, the areas used to check that the libraries agree, and the command to
reproduce: [benchmarks/RESULTS.md](benchmarks/RESULTS.md).

## Testing

```bash
pip install -e ".[test]"
pytest tests
```

- **Upstream's GoogleTest suite, ported one to one**: 256 cases, reading upstream's own
  `.txt` data files from the submodule, with the same assertions and tolerances.
- **Differential fuzzing against a C++ reference binary**: 10 372 seeded random cases over
  boolean ops, offsetting, rect clipping, Minkowski, triangulation, simplification and the
  geometry helpers, in both families, demanding exact equality — integers equal, doubles
  bit for bit. Both sides run the same upstream code on the same machine, so anything less
  is a binding bug. The reference binary is built separately, and the test skips without
  it:

  ```bash
  cmake -S tests/reference -B build/ref -DCMAKE_BUILD_TYPE=Release
  cmake --build build/ref
  pytest tests/reference
  ```

The rest of the suite covers the binding's own surface: dtype dispatch, every validation
error, empty inputs, callbacks that raise, polytree lifetimes, GIL release and the stubs.

## Versioning

clipper2-py has its own semantic version, independent of upstream's.
`clipper2.CLIPPER2_VERSION` is the bundled Clipper2 version (`"2.0.1"`) and
`clipper2.__version__` is this package's.

## License

MIT for the binding (see [LICENSE](LICENSE)). Clipper2 itself is Angus Johnson's, under
the Boost Software License 1.0; its license text ships in every wheel and sdist next to
this one.
