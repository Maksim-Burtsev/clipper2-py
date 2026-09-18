# clipper2-py — specification

Python bindings for [Clipper2](https://github.com/AngusJohnson/Clipper2) (C++), pinned to tag
`Clipper2_2.0.1` in `third_party/Clipper2`. PyPI name `clipper2-py`, import name `clipper2`,
own versioning starting at 0.1.0.

## Prime rule

The algorithms are upstream's, untouched. The binding adds **no** behaviour: no limits, no
clamping, no "fixes", no convenience helpers that upstream does not have. Every place where the
Python surface differs from C++ is one of the numbered deviations below and is recorded in
`DEVIATIONS.md`. A fork not covered here is resolved by doing what C++ does. If C++ gives no
answer, stop and report it to the orchestrator — do not pick.

## Decisions locked with the owner

1. pybind11 binding of the C++ sources (not a rewrite). scikit-build-core, cibuildwheel,
   CPython 3.10–3.14, Linux x86_64/aarch64 (manylinux_2_28), macOS x86_64/arm64, Windows AMD64.
2. Names: mechanical snake_case. `InflatePaths` → `inflate_paths`, `Clipper64.AddSubject` →
   `add_subject`, C++ getter/setter pairs (`MiterLimit()` / `MiterLimit(v)`) → a Python property
   `miter_limit`. Class names stay CamelCase (`Clipper64`, `ClipperD`, `ClipperOffset`,
   `PolyPath64`, `Rect64`). Enum members UPPER_SNAKE: `FillRule.NON_ZERO`, `ClipType.INTERSECTION`,
   `JoinType.MITER`, `EndType.POLYGON`, `PointInPolygonResult.IS_ON`, `TriangulateResult.SUCCESS`.
3. Data. A point is a pair `(x, y)`. A path goes in as any sequence of pairs or an N×2 numpy
   array; paths go in as any sequence of paths or an M×N×2 array. A path comes out as an N×2
   numpy array (`int64` for the 64 family, `float64` for D); paths come out as a `list` of such
   arrays. A point comes out as a `tuple`. `Rect64` / `RectD` are classes with upstream's fields
   and methods. numpy is a hard runtime dependency.
4. 64 vs D is chosen by the input's dtype as `numpy.asarray` infers it: integer kind → 64,
   float kind → D; anything else → `TypeError`. All point/path arguments of one call must be of
   the same family; mixing → `TypeError` (in C++ it would not compile). Scalar arguments follow
   C++ implicit conversion in the safe direction only: an `int` is accepted where C++ takes
   `double`; a `float` where C++ takes `int64_t` → `TypeError`. D-family functions keep
   upstream's `precision` / `decimal_places` parameter with upstream's default.
   An empty input (`[]`) has no dtype: it takes the family of the other arguments, and the 64
   family if there are none.
5. Input validation that C++ gets from the compiler: wrong shape → `ValueError`; integer outside
   int64 → `OverflowError`; a float array handed to `Clipper64` / `ClipperOffset` → `TypeError`.
   Never truncate silently. Value-range checks are upstream's only.
6. Errors: a thrown `Clipper2Lib::Clipper2Exception` becomes `clipper2.Clipper2Error`
   (subclass of `Exception`) with upstream's message. Where C++ silently returns an empty result,
   so do we. `error_code` getters are bound as upstream has them.
7. Out-parameters become return values.
   `Clipper64.execute(clip_type, fill_rule) -> (closed_paths, open_paths)`;
   `Clipper64.execute_tree(clip_type, fill_rule) -> (PolyTree64, open_paths)`; same for `ClipperD`.
   C++ `Execute` returning `false` → `Clipper2Error`.
   `ClipperOffset.execute(delta) -> paths`, `execute_tree(delta) -> PolyTree64`;
   `execute(delta)` also accepts a callable (upstream's `DeltaCallback64`:
   `(path, path_normals, curr_idx, prev_idx) -> float`).
   `triangulate(pp, *, dec_places=None, use_delaunay=True) -> (TriangulateResult, paths)`
   (`dec_places` is upstream's name; required for D, as upstream has no default). Where a D
   overload inserts its precision parameter mid-list (`inflate_paths`, `trim_collinear`,
   `triangulate`), it and everything after it are keyword-only. Free `boolean_op` with a polytree out-param →
   `boolean_op_tree`.
8. `operator<<` overloads → `__str__` producing upstream's exact text; `__repr__` is a short
   Python-style repr.
9. PolyTree is read-only from Python: `polygon`, `is_hole`, `level`, `parent`, `len()`,
   iteration over children, `child(i)` (upstream `Child`), `[i]`, `area()`, and for D `scale`.
   `PolyTree64` is `PolyPath64` as upstream (`using PolyTree64 = PolyPath64`). A child keeps its
   tree alive (`py::keep_alive` / shared ownership).
10. Z support is a second extension, `clipper2.z`, compiled from the same binding sources with
    `USINGZ`. There paths are N×3 (`x, y, z`; z is `int64` in the 64 family and, per upstream,
    `int64` in D too — check `clipper.core.h` and follow it). `set_z_callback(fn)`:
    upstream's callback mutates `pt.z` by reference; in Python `fn(e1bot, e1top, e2bot, e2top, pt)`
    **returns** the z for `pt`. An exception raised in any Python callback propagates out of
    `execute`. `clipper2.z` exposes the same names as `clipper2`.
11. Not bound: `clipper.export.h` (a C ABI for DLL users). C++ templates are instantiated for the
    64 and D families only. `MakePath` / `MakePathD` **are** bound (`make_path`, `make_path_d`:
    flat list → path) because upstream's docs use them.
12. The GIL is released while upstream code runs (`execute`, the free functions) and re-acquired
    for callbacks.

## Shared vs per-module types

`clipper2._clipper2` and `clipper2._clipper2z` are two extensions with different `Point` layouts.
- Registered once, in `_clipper2`, and reused by `_clipper2z` (which imports `_clipper2` first):
  all enums, `Rect64`, `RectD`, `Clipper2Error`.
- Registered in both with `py::module_local()`: `Clipper64`, `ClipperD`, `ClipperOffset`,
  `PolyPath64`, `PolyPathD`, `ReuseableDataContainer64`.
- Upstream `.cpp` files are compiled straight into each extension with hidden symbol visibility;
  upstream's own CMake is not used.

## Coverage contract

`docs/api-map.md` lists **every** namespace-scope symbol of `clipper.h`, `clipper.core.h`,
`clipper.engine.h`, `clipper.offset.h`, `clipper.rectclip.h`, `clipper.minkowski.h`,
`clipper.triangulation.h`, `clipper.version.h` outside `namespace detail`, each with either its
Python name or the reason it is not bound (e.g. "C++-only type conversion", "internal, used only
by the engine"). Nothing is dropped silently. `clipper2.CLIPPER2_VERSION` exposes upstream's
version string; `clipper2.__version__` is ours.

## Layout

```
CMakeLists.txt  pyproject.toml  LICENSE  README.md  DEVIATIONS.md
src/clipper2/__init__.py        re-exports _clipper2, __version__
src/clipper2/z.py               re-exports _clipper2z
src/clipper2/__init__.pyi, z.pyi, py.typed
src/cpp/convert.h               numpy/sequence <-> Path/Paths/Point/Rect, dtype dispatch, validation
src/cpp/module.cpp              PYBIND11_MODULE (name from CLIPPER2_PY_MODULE_NAME macro)
src/cpp/bind_core.cpp           enums, Rect, error, core + clipper.h free functions
src/cpp/bind_engine.cpp         Clipper64, ClipperD, PolyPath, ReuseableDataContainer64
src/cpp/bind_offset.cpp         ClipperOffset, inflate_paths
src/cpp/bind_misc.cpp           rectclip, minkowski, triangulation
tests/                          pytest
tests/upstream/                 ports of third_party/Clipper2/CPP/Tests/*.cpp, reading ../Tests/*.txt
tests/reference/                C++ reference CLI + differential fuzz test
benchmarks/
```

## Tests

1. Every upstream GoogleTest file is ported to pytest one-to-one (same cases, same data files,
   same assertions and tolerances). `TestExportHeaders.cpp` is skipped with a note (deviation 11).
2. Differential fuzz: `tests/reference/ref_cli.cpp` links upstream directly, reads operations from
   a text file, prints results (`%.17g` for doubles). A seeded pytest generates ≥10 000 random
   cases over boolean ops (all clip types × fill rules, open paths, polytree), offset (all join ×
   end types), rectclip, rectclip lines, minkowski, triangulation, simplify/RDP/trim_collinear,
   64 and D, and demands exact equality with the binding's output. Built by the standalone
   `tests/reference/CMakeLists.txt` into `build/ref/ref_cli`; the test skips if the binary is absent.
3. Binding-specific tests: dtype dispatch, every validation error, empty inputs, callbacks
   (including ones that raise), PolyTree lifetime (child outlives tree variable), GIL release
   (two threads run concurrently), no leaks over 10⁵ calls (`tracemalloc` / RSS bound),
   `mypy --strict` on a sample against the stubs.

## Out of scope for 0.1.0

Free-threaded wheels, PyPy, 32-bit, musllinux (add musllinux only if it builds with no extra work).
No tag, no release, no PRs to other repos until the owner says so.
