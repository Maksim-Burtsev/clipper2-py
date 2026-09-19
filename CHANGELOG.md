# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This package
has its own [semantic version](https://semver.org/spec/v2.0.0.html), independent of the
Clipper2 version it bundles; `clipper2.CLIPPER2_VERSION` tells the latter.

## 0.1.0 — unreleased

First release. Bundles Clipper2 2.0.1 (upstream tag `Clipper2_2.0.1`).

### Added

- The complete public Clipper2 API as `clipper2`: the boolean operations (`union`,
  `intersect`, `difference`, `xor`, `boolean_op`, `boolean_op_tree`) and the `Clipper64` /
  `ClipperD` engine classes with open subjects, `execute`, `execute_tree` and
  `ReuseableDataContainer64`.
- Offsetting: `inflate_paths` and `ClipperOffset`, including upstream's variable-offset
  delta callback.
- `rect_clip`, `rect_clip_lines` and the `RectClip64` / `RectClipLines64` classes;
  `minkowski_sum` and `minkowski_diff`; `triangulate`.
- The read-only `PolyPath64` / `PolyPathD` tree, `Rect64` / `RectD`, the enums, and the
  geometry helpers of `clipper.core.h` and `clipper.h` (`area`, `get_bounds`,
  `point_in_polygon`, `simplify_path`, `ramer_douglas_peucker`, `ellipse`, `distance`,
  `length`, `make_path`, …).
- `clipper2.z`: the same library built with `USINGZ`, with N×3 paths and a z callback that
  returns the z of each new point.
- numpy arrays in and out: a path is an N×2 array, paths are a list of them, and the
  input's dtype picks upstream's 64 or D family.
- `Clipper2Error` for `Clipper2Lib::Clipper2Exception`, with upstream's message.
- Type stubs and a `py.typed` marker.
- Wheels for Linux x86_64 and aarch64 (manylinux_2_28), macOS x86_64 and arm64, and
  Windows AMD64, on CPython 3.10–3.14.

### Known issues

- Upstream's `ClipperOffset` segfaults on an empty path with an open end type, and
  upstream's `Triangulate` does not return on some degenerate inputs. The binding adds no
  guard against either
  ([#1](https://github.com/Maksim-Burtsev/clipper2-py/issues/1),
  [#2](https://github.com/Maksim-Burtsev/clipper2-py/issues/2)).
- `GetLineIntersectPt` is not bound
  ([#3](https://github.com/Maksim-Burtsev/clipper2-py/issues/3)); neither is
  `clipper.export.h`, upstream's C ABI for DLL users. See [DEVIATIONS.md](DEVIATIONS.md)
  and [docs/api-map.md](docs/api-map.md).
