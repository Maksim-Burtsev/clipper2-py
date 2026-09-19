# Deviations

The algorithms are upstream Clipper2's, untouched: the same input produces the same result
as the C++ library. What follows is everything a C++ user would notice when moving to
Python. Nothing here changes what the library computes.

`docs/api-map.md` lists every upstream symbol with its Python name or the reason it is not
bound.

## 1. Names

`InflatePaths` → `inflate_paths`, `Clipper64.AddSubject` → `add_subject`. Getter/setter
pairs such as `MiterLimit()` / `MiterLimit(v)` are properties (`miter_limit`); a plain
getter stays a method (`is_valid()`, `mid_point()`), except on the `PolyPath` tree, where
`level`, `is_hole`, `parent`, `polygon`, `scale` are attributes and `area()` is a method.
Class names keep their CamelCase, enum members are UPPER_SNAKE (`FillRule.NON_ZERO`).

Keyword-argument names are upstream's parameter names, snake_cased. Upstream is not always
consistent, and neither are we: `boolean_op(..., precision=...)` but
`intersect(..., decimal_prec=...)`, `Clipper64.execute(clip_type=..., fill_rule=...)` but
`boolean_op(cliptype=..., fillrule=...)`, `minkowski_sum(..., decimal_places=...)` but
`triangulate(..., dec_places=...)`, and `ClipperOffset.add_path(path, jt_, et_)` with the
trailing underscores upstream's parameters carry.

## 2. Points, paths and the two families

A point goes in as any pair `(x, y)` and comes back as a tuple. A path goes in as any
sequence of points or an N×2 array and comes back as an N×2 numpy array (`int64` for the 64
family, `float64` for D); paths come back as a list of such arrays.

Which family runs is decided by the dtype `numpy.asarray` infers for the point and path
arguments: integer → 64, float → D. Mixing families in one call is a `TypeError` (in C++ it
would not compile). An empty input has no dtype: it takes the family of the other
arguments, and the 64 family if there are none. An integer array is accepted by a D
function (C++ converts `int` to `double` implicitly); a float array is refused by a 64
function.

C++ picks between `Area(Path)` and `Area(Paths)` by static type. Python has only the shape
of the argument, so `area`, `get_bounds`, `ramer_douglas_peucker`, `strip_near_equal`,
`strip_duplicates`, `rect_clip` and `rect_clip_lines` choose by nesting depth: a sequence of
points is a path, a sequence of those is paths. An empty sequence cannot be a point, so it is
an empty path: `[[]]` is paths holding one empty path, and a bare `[]` is an empty path.

`rect_clip` and `rect_clip_lines` take the family from the rect as well, because that is what
picks the overload in C++: a `Rect64` with float paths, or a `RectD` with integer ones, is a
`TypeError`. `ClipperOffset` and the `RectClip64` / `RectClipLines64` classes are 64-only
upstream, so float input is a `TypeError` there too.

## 3. Validation the C++ compiler does for free

* A wrong shape is a `ValueError`.
* An integer that does not fit `int64` is an `OverflowError`; a `uint64` array above
  `INT64_MAX` too. Nothing is ever truncated silently.
* Anything that is not an integer or float dtype is a `TypeError` — including `bool`
  arrays, string arrays and numpy `object` arrays.
* A float where C++ takes `int64_t` (`translate_path(path, 0.5, 0)` on the 64 family) is a
  `TypeError`; an int where C++ takes `double` is fine.
* An index outside a `PolyPath`'s children raises `IndexError`; C++ has undefined behaviour
  there. Negative indices are not accepted: upstream has no such concept.

## 4. Out-parameters became return values

* `Clipper64.execute(clip_type, fill_rule)` returns `(closed_paths, open_paths)`;
  `execute_tree` returns `(tree, open_paths)`. Same for `ClipperD`.
* The `BooleanOp` overload that fills a `PolyTree` is `boolean_op_tree`.
* `ClipperOffset.execute(delta)` returns the paths and `execute_tree(delta)` the tree. The
  `Execute` overload that takes a `DeltaCallback64` is `execute(callable)`: as upstream, it
  offsets with a delta of 1.0 and leaves the callback set on the object afterwards.
* `triangulate(...)` returns `(TriangulateResult, paths)`.
* `strip_duplicates(path, is_closed_path)` returns the stripped path; C++ edits its
  argument in place.
* Upstream's `Execute` returning `false` (an internal inconsistency it reports through the
  return value) raises `Clipper2Error` with upstream's own "There is an undefined error in
  Clipper2" text.

## 5. `precision` / `decimal_prec`

Only the D family has these parameters upstream, so they default to `None`: passing one to
a 64-family call is a `TypeError`. `trim_collinear` (`precision`) and `triangulate`
(`dec_places`) are the two whose D overload has no default upstream, so they require the
argument for float input.

In three functions upstream's D overload inserts this parameter in the middle of the list:
`InflatePaths(…, miter_limit, precision, arc_tolerance)`, `TrimCollinear(path, precision,
is_open_path)`, `Triangulate(pp, decPlaces, solution, useDelaunay)`. One Python function
serves both families, so a call written by position would change meaning with the input's
dtype. There the parameter and everything after it are keyword-only:
`inflate_paths(paths, delta, jt, et, miter_limit=2.0, *, precision=None, arc_tolerance=0.0)`,
`trim_collinear(path, *, precision=None, is_open_path=False)`,
`triangulate(pp, *, dec_places=None, use_delaunay=True)`.

## 6. Errors

`Clipper2Lib::Clipper2Exception` becomes `clipper2.Clipper2Error` (a subclass of
`Exception`) with upstream's message. Where C++ silently returns an empty result, so do we.
`clipper2.z.Clipper2Error` is the very same class, as are the enums, `Rect64` and `RectD`.

## 7. The z build

`clipper2.z` is the same library compiled with `USINGZ`. Points are `(x, y, z)` and paths
are N×3 arrays. Upstream's `z` is `int64_t` in **both** families (`z_type` in
clipper.core.h), so in the D family the third column is an integer value carried in a
`float64` array, and a fractional z on the way in is truncated towards zero — exactly what
upstream's own `MakePathZD` does. An N×2 path is also accepted and gets z = 0, which is
what upstream's `Point` constructor does.

`Rect64` and `RectD` are among the types registered once, in the non-USINGZ extension
(deviation 6), so in `clipper2.z` they stay two-dimensional: `mid_point()` returns
`(x, y)`, `as_path()` an N×2 array, and `contains(pt)` wants a plain `(x, y)` — a
three-element point is a `ValueError` there. Everything compiled into both modules
(`clipper2.z.mid_point`, `clipper2.z.ellipse`, …) does use three-element points.

`set_z_callback(fn)` takes `fn(e1bot, e1top, e2bot, e2top, pt)` and uses its **return
value** as the z of `pt`; upstream's callback writes `pt.z` through a reference, which
Python cannot do. `set_z_callback(None)` removes the callback.

Objects must not be passed between `clipper2` and `clipper2.z`: the two builds lay points
out differently, so a `clipper2.PolyPath64` is not a `clipper2.z.PolyPath64`. Where such an
object is a function argument (`poly_tree_to_paths64`, `poly_tree_to_paths_d`,
`check_polytree_fully_contains_children`, `add_reuseable_data`) the binding checks and
raises `TypeError`. Reaching an unbound method of one module's class with the other
module's instance (`clipper2.Clipper64.clear(z_clipper)`) is not guarded.

## 8. Callbacks and the GIL

The GIL is released while upstream code runs and re-acquired for callbacks, so two threads
clip in parallel. An exception raised inside a callback — a z callback, or `ClipperOffset`'s
delta callback — propagates out of `execute()`. It unwinds through upstream's C++ and
would skip the clean-up `Execute` ends with, so the binding runs that same clean-up
(`ClipperBase::CleanUp`) before re-raising: the clipper is left as after a normal `execute`,
with its paths still added. `ClipperOffset` keeps no such state.

`ClipperOffset`'s delta callback is upstream's `DeltaCallback64`:
`fn(path, path_normals, curr_idx, prev_idx)` returns the delta to use, with `path` as an
int64 array and `path_normals` as a float64 one.

## 9. What is not bound

`clipper.export.h` (a C ABI for DLL users) and, per the coverage table in
`docs/api-map.md`, upstream's C++-only plumbing: the type-conversion templates
(`ScalePath`, `TransformPaths`, …) — use the D functions' `precision` or numpy's `astype` —
the engine-internal structs, and the scalar helpers whose Python equivalent is exact
(`Sqr` is `x * x`, `ProductsAreEqual` is `a * b == c * d` on Python's arbitrary-precision
ints).

`MakePath` and `MakePathD` are bound because upstream's documentation uses them; templates
are instantiated for the 64 and D families only.
