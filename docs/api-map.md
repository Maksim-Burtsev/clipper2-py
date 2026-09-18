# API map

Every namespace-scope symbol of the upstream headers (outside `namespace detail` /
`namespace details`) with its Python name, or the reason it is not bound. Upstream is
`third_party/Clipper2` at tag `Clipper2_2.0.1`.

Conventions used below:

* Names are the mechanical snake_case of upstream's (spec decision 2); keyword-argument
  names are upstream's parameter names, snake_cased, so they differ between functions that
  upstream spells differently (`precision` vs `decimal_prec`).
* "a point" is a tuple `(x, y)` in, any sequence of two numbers out; "a path" is an N×2
  numpy array; "paths" is a list of those. In `clipper2.z` the arrays are N×3.
* A getter/setter pair is a property; a lone getter stays a method, except on `PolyPath`
  where spec decision 9 fixes the surface.

## clipper.version.h

| C++ | Python |
| --- | --- |
| `CLIPPER2_VERSION` | `clipper2.CLIPPER2_VERSION` (`clipper2.__version__` is this package's own) |

## clipper.core.h

| C++ | Python |
| --- | --- |
| `Clipper2Exception` | `Clipper2Error` (subclass of `Exception`, upstream's message) |
| `precision_error`, `range_error`, `scale_error`, `non_pair_error`, `undefined_error` | not bound: the message strings of `Clipper2Error` |
| `precision_error_i`, `scale_error_i`, `non_pair_error_i`, `undefined_error_i`, `range_error_i` | same names; the bits of `error_code` |
| `PI` | not bound: `math.pi` |
| `CLIPPER2_MAX_DEC_PRECISION` | same name |
| `MAX_COORD`, `MIN_COORD` | same names |
| `INVALID` | not bound: engine-internal sentinel |
| `max_coord`, `min_coord` | not bound: `MAX_COORD` / `MIN_COORD` as doubles |
| `MAX_DBL` | not bound: `sys.float_info.max` |
| `DoError` | not bound: internal, raises `Clipper2Error` from an error code |
| `is_round_invocable` | not bound: C++ type trait |
| `FillRule` | `FillRule.EVEN_ODD / NON_ZERO / POSITIVE / NEGATIVE` |
| `z_type` (USINGZ) | not bound: the C++ type of a point's z (`int64_t`); see the z build section |
| `Point<T>`, `Point64`, `PointD` | a tuple `(x, y)` (`(x, y, z)` in `clipper2.z`), or one row of a path array |
| `Point::Init`, `SetZ`, `operator*`, `==`, `!=`, unary `-`, `+`, `-`, `Negate`, `operator<<` | not bound: points are plain tuples / array rows, arithmetic is numpy's |
| `Path<T>`, `Paths<T>`, `Path64`, `PathD`, `Paths64`, `PathsD` | an N×2 numpy array / a list of them |
| `operator<<(Path&, Point&)`, `operator<<(Paths&, Path&)` | not bound: C++ list-building sugar (`list.append`) |
| `operator<<(ostream&, Path/Paths)` | not bound: paths are numpy arrays, they print as arrays |
| `InvalidPoint64`, `InvalidPointD` | not bound: C++ sentinels, no bound function returns them |
| `MidPoint(p1, p2)` | `mid_point(p1, p2)` |
| `Rect<T>`, `Rect64`, `RectD` | `Rect64`, `RectD` (shared by both modules) |
| `Rect(T l, T t, T r, T b)`, `Rect(bool is_valid = true)` | `Rect64(l, t, r, b)`, `Rect64(is_valid=True)` |
| `Rect::left / top / right / bottom` | read/write attributes |
| `Rect::InvalidRect()` | `Rect64.invalid_rect()` (static) |
| `Rect::IsValid`, `IsEmpty` | `is_valid()`, `is_empty()` |
| `Rect::Width()/Width(v)`, `Height()/Height(v)` | `width`, `height` properties |
| `Rect::MidPoint`, `AsPath` | `mid_point()`, `as_path()` |
| `Rect::Contains(Point)`, `Contains(Rect)` | `contains(pt)` / `contains(rec)` |
| `Rect::Scale`, `Intersects` | `scale(scale)`, `intersects(rec)` |
| `Rect::operator==`, `operator+=`, `operator+`, `operator<<` | `__eq__`, `__iadd__`, `__add__`, `__str__` (upstream's exact text) |
| `ScaleRect<T1,T2>` | not bound: C++-only type conversion |
| `InvalidRect64`, `InvalidRectD` | not bound: the value of `Rect64.invalid_rect()` |
| `GetBounds(Path)`, `GetBounds(Paths)` | `get_bounds(path)` — a path or paths, by nesting depth |
| `GetBounds<T,T2>(Path/Paths)` | not bound: C++-only type conversion |
| `ScalePath`, `ScalePaths` (2 overloads each) | not bound: C++-only type conversion with an `int&` error out-parameter; use the D functions' `precision`, or numpy's `astype` |
| `TransformPath`, `TransformPaths` | not bound: C++-only type conversion |
| `Sqr` | not bound: `x * x` |
| `NearEqual` | `near_equal(p1, p2, max_dist_sqrd)` |
| `StripNearEqual(Path/Paths)` | `strip_near_equal(path, max_dist_sqrd, is_closed_path)` |
| `StripDuplicates(Path/Paths)` | `strip_duplicates(path, is_closed_path)` — returns the result, C++ edits in place |
| `CheckPrecisionRange` (2 overloads) | not bound: internal validation, applied by every D function |
| `TriSign`, `GetSign` | not bound: scalar helpers, `(x > 0) - (x < 0)` |
| `UInt128Struct`, `MultiplyUInt64`, `ProductsAreEqual` | not bound: 128-bit arithmetic helpers; Python's `int` is exact (`a * b == c * d`) |
| `CrossProductSign` | `cross_product_sign(pt1, pt2, pt3)` |
| `IsCollinear` | `is_collinear(pt1, shared_pt, pt2)` |
| `CrossProduct(pt1,pt2,pt3)`, `CrossProduct(vec1,vec2)` | `cross_product` (both overloads) |
| `DotProduct(pt1,pt2,pt3)`, `DotProduct(vec1,vec2)` | `dot_product` (both overloads) |
| `DistanceSqr` | `distance_sqr(pt1, pt2)` |
| `PerpendicDistFromLineSqrd` | `perpendic_dist_from_line_sqrd(pt, line1, line2)` |
| `Area(Path)`, `Area(Paths)` | `area(path)` — a path or paths, by nesting depth |
| `IsPositive` | `is_positive(poly)` |
| `GetLineIntersectPt` | **not bound** — see OPEN QUESTIONS in the phase report: `bool` plus an out-parameter that upstream leaves untouched when it returns false |
| `TranslatePoint` | `translate_point(pt, dx, dy)` |
| `ReflectPoint` | `reflect_point(pt, pivot)` |
| `SegmentsIntersect` | `segments_intersect(seg1a, seg1b, seg2a, seg2b, inclusive=False)` — 64 family only, as upstream declares it |
| `GetClosestPointOnSegment` | `get_closest_point_on_segment(off_pt, seg1, seg2)` |
| `PointInPolygonResult` | `PointInPolygonResult.IS_ON / IS_INSIDE / IS_OUTSIDE` |
| `PointInPolygon` | `point_in_polygon(pt, polygon)` |

`IsCollinear` and `CrossProductSign` are instantiated for both families, as upstream does
(`PointInPolygon<double>` uses `CrossProductSign<double>`). Note that upstream's integer
arithmetic inside them converts double coordinates to `int64_t`: the D family results are
upstream's, quirk included.

## clipper.engine.h

| C++ | Python |
| --- | --- |
| `ClipType` | `ClipType.NO_CLIP / INTERSECTION / UNION / DIFFERENCE / XOR` |
| `PathType` | `PathType.SUBJECT / CLIP` |
| `JoinWith`, `VertexFlags` (+ its `&`, `|` operators) | not bound: engine-internal |
| `Scanline`, `IntersectNode`, `Active`, `Vertex`, `LocalMinima`, `OutRec`, `OutPt`, `HorzSegment`, `HorzJoin`, `OutRecList`, `LocalMinima_ptr`, `LocalMinimaList`, `IntersectNodeList`, `HorzSegmentList` | not bound: engine-internal types |
| `ZCallback64`, `ZCallbackD` (USINGZ) | `Clipper64.set_z_callback(fn)` / `ClipperD.set_z_callback(fn)`; `fn(e1bot, e1top, e2bot, e2top, pt)` **returns** the z of `pt` |
| `ReuseableDataContainer64` | `ReuseableDataContainer64()` |
| `ReuseableDataContainer64::Clear`, `AddPaths` | `clear()`, `add_paths(paths, polytype, is_open)` |
| `ReuseableDataContainer64::AddLocMin` | not bound: private |
| `ClipperBase` | not bound as a class; its public members are on `Clipper64` and `ClipperD` |
| `ClipperBase::ErrorCode` | `error_code` (read-only property) |
| `ClipperBase::PreserveCollinear`, `ReverseSolution` | `preserve_collinear`, `reverse_solution` properties |
| `ClipperBase::Clear`, `AddReuseableData` | `clear()`, `add_reuseable_data(reuseable_data)` |
| `ClipperBase::DefaultZ` (USINGZ) | `default_z` attribute |
| `ClipperBase` protected/private members | not bound: internal |
| `PolyPath` | not bound as a class; its members appear on `PolyPath64` / `PolyPathD` |
| `PolyPath::Level`, `Parent`, `IsHole`, `Count` | `level`, `parent`, `is_hole`, `len(tree)` |
| `PolyPath::AddChild`, `Clear` | not bound: the tree is read-only from Python (decision 9) |
| `PolyPath64List`, `PolyPathDList` | not bound: C++ container types |
| `PolyPath64`, `PolyPathD` | `PolyPath64`, `PolyPathD` (module-local: the Point layout differs per module) |
| `PolyPath64::operator[]`, `Child` | `tree[i]`, `tree.child(i)` — bounds-checked, no negative indices |
| `PolyPath64::begin/end` | iteration over children (sequence protocol) |
| `PolyPath64::Polygon`, `Area` | `polygon` (property), `area()` |
| `PolyPathD::Scale` | `scale` (read-only property) |
| `PolyPathD::SetScale` | not bound: read-only tree |
| `PolyTree64`, `PolyTreeD` | `PolyTree64 is PolyPath64`, `PolyTreeD is PolyPathD`, as upstream |
| `Clipper64` | `Clipper64()` |
| `Clipper64::AddSubject`, `AddOpenSubject`, `AddClip` | `add_subject`, `add_open_subject`, `add_clip` |
| `Clipper64::Execute` (4 overloads) | `execute(clip_type, fill_rule) -> (closed, open)`, `execute_tree(clip_type, fill_rule) -> (tree, open)` |
| `Clipper64::SetZCallback` (USINGZ) | `set_z_callback(callback)` |
| `Clipper64::BuildPaths64`, `BuildTree64` | not bound: private |
| `ClipperD` | `ClipperD(precision=2)` |
| `ClipperD::AddSubject`, `AddOpenSubject`, `AddClip`, `Execute`, `SetZCallback` | as `Clipper64` |
| `ClipperD::ZCB`, `CheckCallback` | not bound: internal proxies for the D z-callback |

## clipper.h

| C++ | Python |
| --- | --- |
| `BooleanOp(ct, fr, subjects, clips[, precision])` | `boolean_op(cliptype, fillrule, subjects, clips, precision=None)` |
| `BooleanOp(..., PolyTree&[, precision])` | `boolean_op_tree(cliptype, fillrule, subjects, clips, precision=None)` |
| `Intersect` (2) | `intersect(subjects, clips, fillrule, decimal_prec=None)` |
| `Union(subjects, clips, fillrule[, decimal_prec])` | `union(subjects, clips, fillrule, decimal_prec=None)` |
| `Union(subjects, fillrule[, precision])` | `union(subjects, fillrule, precision=None)` |
| `Difference` (2) | `difference(subjects, clips, fillrule, decimal_prec=None)` |
| `Xor` (2) | `xor(subjects, clips, fillrule, decimal_prec=None)` |
| `InflatePaths(Paths64, delta, jt, et, miter_limit, arc_tolerance)` | `inflate_paths(paths, delta, jt, et, miter_limit=2.0, precision=None, arc_tolerance=0.0)` |
| `InflatePaths(PathsD, delta, jt, et, miter_limit, precision, arc_tolerance)` | same function; `precision` sits where the D overload declares it |
| `TranslatePath` (template + 2 overloads) | `translate_path(path, dx, dy)` |
| `TranslatePaths` (template + 2 overloads) | `translate_paths(paths, dx, dy)` |
| `RectClip(Rect64, Path64)`, `RectClip(Rect64, Paths64)` | `rect_clip(rect, path)` — a path or paths, by nesting depth |
| `RectClip(RectD, PathD, precision)`, `RectClip(RectD, PathsD, precision)` | `rect_clip(rect, path, precision=None)` — the `RectD` overloads, chosen by the rect |
| `RectClipLines(Rect64, Path64)`, `(Rect64, Paths64)` | `rect_clip_lines(rect, line)` |
| `RectClipLines(RectD, PathD, precision)`, `(RectD, PathsD, precision)` | `rect_clip_lines(rect, line, precision=None)` |
| `namespace details` (`PolyPathToPaths64/D`, `PolyPath64ContainsChildren`, `OutlinePolyPath*`, `MakePathGeneric`, `GetNext`, `GetPrior`) | not bound: upstream's internal namespace |
| `operator<<(ostream&, PolyTree64/PolyTreeD)` | `str(tree)` — upstream's exact text |
| `PolyTreeToPaths64` | `poly_tree_to_paths64(polytree)` |
| `PolyTreeToPathsD` | `poly_tree_to_paths_d(polytree)` |
| `CheckPolytreeFullyContainsChildren` | `check_polytree_fully_contains_children(polytree)` |
| `MakePath` (vector and C-array overloads) | `make_path(list)` — a flat sequence of integers |
| `MakePathD` (vector and C-array overloads) | `make_path_d(list)` — a flat sequence of numbers |
| `MakePathZ`, `MakePathZD` (USINGZ) | not bound: compile-time-sized C-array templates with no runtime form; pass an N×3 array, or `make_path` for z = 0 |
| `TrimCollinear(Path64, is_open)` / `(PathD, precision, is_open)` | `trim_collinear(path, precision=None, is_open_path=False)` |
| `Distance` | `distance(pt1, pt2)` |
| `Length` | `length(path, is_closed_path=False)` |
| `NearCollinear` | `near_collinear(pt1, pt2, pt3, sin_sqrd_min_angle_rads)` |
| `Ellipse(Rect, steps)` | `ellipse(rect, steps=0)` |
| `Ellipse(center, radiusX, radiusY, steps)` | `ellipse(center, radius_x, radius_y=0, steps=0)` |
| `SimplifyPath` | `simplify_path(path, epsilon, is_closed_path=True)` |
| `SimplifyPaths` | `simplify_paths(paths, epsilon, is_closed_path=True)` |
| `Path2ContainsPath1` | `path2_contains_path1(path1, path2)` |
| `RDP` | not bound: the recursive helper of `ramer_douglas_peucker` (mutable flags out-parameter) |
| `RamerDouglasPeucker(Path)`, `(Paths)` | `ramer_douglas_peucker(path, epsilon)` — a path or paths, by nesting depth |

## clipper.offset.h

The enums are registered once, in `_clipper2`, so they are bound with the other shared types.

| C++ | Python |
| --- | --- |
| `JoinType` | `JoinType.SQUARE / BEVEL / ROUND / MITER` |
| `EndType` | `EndType.POLYGON / JOINED / BUTT / SQUARE / ROUND` |
| `DeltaCallback64` | any callable `(path, path_normals, curr_idx, prev_idx) -> float`; `path` is an int64 array, `path_normals` a float64 one |
| `ClipperOffset` | `ClipperOffset(miter_limit=2.0, arc_tolerance=0.0, preserve_collinear=False, reverse_solution=False)` — 64 only, as upstream; module-local (its points depend on `USINGZ`) |
| `ClipperOffset::Group` and the other private members (`ExecuteInternal`, `DoGroupOffset`, `DoBevel`, `DoSquare`, `DoMiter`, `DoRound`, `BuildNormals`, `OffsetPolygon`, `OffsetOpenJoined`, `OffsetOpenPath`, `OffsetPoint`, `CalcSolutionCapacity`, `CheckReverseOrientation`, `ZCB`, the data members) | not bound: private |
| `ClipperOffset::ErrorCode` | `error_code` (read-only property) |
| `ClipperOffset::AddPath`, `AddPaths` | `add_path(path, jt_, et_)`, `add_paths(paths, jt_, et_)` — upstream's parameter names, trailing underscore included |
| `ClipperOffset::Clear` | `clear()` |
| `ClipperOffset::Execute(delta, Paths64&)` | `execute(delta) -> paths` |
| `ClipperOffset::Execute(delta, PolyTree64&)` | `execute_tree(delta) -> PolyTree64` |
| `ClipperOffset::Execute(DeltaCallback64, Paths64&)` | `execute(callable) -> paths`; like upstream it sets the callback and offsets with delta 1.0, and the callback stays set |
| `ClipperOffset::MiterLimit`, `ArcTolerance`, `PreserveCollinear`, `ReverseSolution` | `miter_limit`, `arc_tolerance`, `preserve_collinear`, `reverse_solution` properties |
| `ClipperOffset::SetZCallback` (USINGZ) | `set_z_callback(callback)`, as on `Clipper64` |
| `ClipperOffset::SetDeltaCallback` | `set_delta_callback(callback)`; `None` removes it |

## clipper.rectclip.h

| C++ | Python |
| --- | --- |
| `Location`, `OutPt2`, `OutPt2List` | not bound: rectclip-internal types |
| `RectClip64` | `RectClip64(rect)` — module-local (it holds `Point64`s) |
| `RectClip64::Execute` | `execute(paths)` |
| `RectClip64` private / protected members (`ExecuteInternal`, `GetPath`, `CheckEdges`, `TidyEdges`, `GetNextLocation`, `Add`, `AddCorner`, the data members) | not bound: internal |
| `RectClipLines64` | `RectClipLines64(rect)`, a subclass of `RectClip64` as upstream |
| `RectClipLines64::Execute` | `execute(paths)` |
| `RectClipLines64::ExecuteInternal`, `GetPath` | not bound: private |

The `RectClip` / `RectClipLines` free functions are in the clipper.h table above. They pick
the family from the rect: a `Rect64` with float paths, or a `RectD` with integer ones, is a
`TypeError`, because neither combination compiles in C++. `precision` is upstream's, so it
defaults to 2 for a `RectD` and is refused for a `Rect64`.

## clipper.minkowski.h

| C++ | Python |
| --- | --- |
| `namespace detail` (`Minkowski`, `Union`) | not bound: upstream's internal namespace |
| `MinkowskiSum(Path64, Path64, isClosed)` | `minkowski_sum(pattern, path, is_closed, decimal_places=None)` |
| `MinkowskiSum(PathD, PathD, isClosed, decimalPlaces)` | same function; `decimal_places` defaults to upstream's 2 for the D family |
| `MinkowskiDiff` (both overloads) | `minkowski_diff(pattern, path, is_closed, decimal_places=None)` |

## clipper.triangulation.h

| C++ | Python |
| --- | --- |
| `TriangulateResult` | `TriangulateResult.SUCCESS / FAIL / NO_POLYGONS / PATHS_INTERSECT` (registered once, in `_clipper2`) |
| `Triangulate(Paths64, Paths64& solution, useDelaunay)` | `triangulate(pp, dec_places=None, use_delaunay=True) -> (TriangulateResult, paths)` |
| `Triangulate(PathsD, decPlaces, PathsD& solution, useDelaunay)` | same function; `dec_places` sits where upstream declares it and, like upstream, has no default: the D family requires it |

## clipper.export.h

Not bound: a C ABI for DLL consumers (spec decision 11).
