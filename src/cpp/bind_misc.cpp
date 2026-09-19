// rectclip, minkowski and triangulation.

#include <cstdint>

#include "clipper2/clipper.h"
#include "convert.h"

using namespace clipper2_py;

namespace {

// The rect's type picks the C++ overload, so it also picks the family: RectClip(Rect64, PathsD)
// compiles no better than RectClip(RectD, Paths64) does.
void check_family(const Geometry& geometry, Family family) {
  const Family found = family_of(geometry);
  if (found != Family::Empty && found != family)
    throw py::type_error(
        "integer and float coordinates in one call: every point and path argument must "
        "be of the same family");
}

// C++ picks RectClip(rect, Path) or RectClip(rect, Paths) by static type; Python has only the
// nesting depth of the argument, as in area() / get_bounds(). The two are not quite the same
// call upstream, so both are kept.
template <class T, class FPath, class FPaths>
py::object rect_op(const Geometry& geometry, FPath&& on_path, FPaths&& on_paths) {
  if (nesting_depth(geometry) >= 3) {
    auto paths = to_paths<T>(geometry);
    return from_paths(without_gil([&] { return on_paths(paths); }));
  }
  auto path = to_path<T>(geometry);
  return from_paths(without_gil([&] { return on_path(path); }));
}

// Base is upstream's base class, if any: RectClipLines64 publicly derives from RectClip64.
template <class R, class... Base>
void bind_rect_clip_class(py::module_& m, const char* name) {
  py::class_<R, Base...>(m, name, py::module_local())
      .def(py::init<const cl::Rect64&>(), py::arg("rect"))
      .def(
          "execute",
          [](R& self, const Geometry& paths) {
            auto p = to_paths<int64_t>(paths);
            return from_paths(without_gil([&] { return self.Execute(p); }));
          },
          py::arg("paths"));
}

}  // namespace

void bind_misc(py::module_& m) {
  // --- clipper.rectclip.h -----------------------------------------------------------

  m.def(
      "rect_clip",
      [](const cl::Rect64& rect, const Geometry& path, const py::object& precision) {
        reject_precision(precision, "rect_clip", "precision");
        check_family(path, Family::Int64);
        return rect_op<int64_t>(
            path, [&](const cl::Path64& p) { return cl::RectClip(rect, p); },
            [&](const cl::Paths64& p) { return cl::RectClip(rect, p); });
      },
      py::arg("rect"), py::arg("path"), py::arg("precision") = py::none());

  m.def(
      "rect_clip",
      [](const cl::RectD& rect, const Geometry& path, const py::object& precision) {
        const int prec = precision_arg(precision, 2);
        check_family(path, Family::Double);
        return rect_op<double>(
            path, [&](const cl::PathD& p) { return cl::RectClip(rect, p, prec); },
            [&](const cl::PathsD& p) { return cl::RectClip(rect, p, prec); });
      },
      py::arg("rect"), py::arg("path"), py::arg("precision") = py::none());

  m.def(
      "rect_clip_lines",
      [](const cl::Rect64& rect, const Geometry& line, const py::object& precision) {
        reject_precision(precision, "rect_clip_lines", "precision");
        check_family(line, Family::Int64);
        return rect_op<int64_t>(
            line, [&](const cl::Path64& p) { return cl::RectClipLines(rect, p); },
            [&](const cl::Paths64& p) { return cl::RectClipLines(rect, p); });
      },
      py::arg("rect"), py::arg("line"), py::arg("precision") = py::none());

  m.def(
      "rect_clip_lines",
      [](const cl::RectD& rect, const Geometry& line, const py::object& precision) {
        const int prec = precision_arg(precision, 2);
        check_family(line, Family::Double);
        return rect_op<double>(
            line, [&](const cl::PathD& p) { return cl::RectClipLines(rect, p, prec); },
            [&](const cl::PathsD& p) { return cl::RectClipLines(rect, p, prec); });
      },
      py::arg("rect"), py::arg("line"), py::arg("precision") = py::none());

  // Both classes are 64-only upstream and hold Point64s, so they are module-local.
  bind_rect_clip_class<cl::RectClip64>(m, "RectClip64");
  bind_rect_clip_class<cl::RectClipLines64, cl::RectClip64>(m, "RectClipLines64");

  // --- clipper.minkowski.h ----------------------------------------------------------

  auto minkowski_op = [&m](const char* name, bool is_sum) {
    m.def(
        name,
        [name, is_sum](const Geometry& pattern, const Geometry& path, bool is_closed,
                       const py::object& decimal_places) {
          return dispatch(
              {pattern, path},
              [&]() -> py::object {
                reject_precision(decimal_places, name, "decimal_places");
                auto pat = to_path<int64_t>(pattern);
                auto p = to_path<int64_t>(path);
                return from_paths(without_gil([&] {
                  return is_sum ? cl::MinkowskiSum(pat, p, is_closed)
                                : cl::MinkowskiDiff(pat, p, is_closed);
                }));
              },
              [&]() -> py::object {
                const int places = precision_arg(decimal_places, 2);
                auto pat = to_path<double>(pattern);
                auto p = to_path<double>(path);
                return from_paths(without_gil([&] {
                  return is_sum ? cl::MinkowskiSum(pat, p, is_closed, places)
                                : cl::MinkowskiDiff(pat, p, is_closed, places);
                }));
              });
        },
        py::arg("pattern"), py::arg("path"), py::arg("is_closed"),
        py::arg("decimal_places") = py::none());
  };
  minkowski_op("minkowski_sum", true);
  minkowski_op("minkowski_diff", false);

  // --- clipper.triangulation.h ------------------------------------------------------

  // dec_places sits where upstream's D overload has it, and like upstream it has no default.
  m.def(
      "triangulate",
      [](const Geometry& pp, const py::object& dec_places, bool use_delaunay) {
        return dispatch(
            {pp},
            [&]() -> py::object {
              reject_precision(dec_places, "triangulate", "dec_places");
              auto paths = to_paths<int64_t>(pp);
              cl::Paths64 solution;
              auto result = without_gil(
                  [&] { return cl::Triangulate(paths, solution, use_delaunay); });
              return py::make_tuple(result, from_paths(solution));
            },
            [&]() -> py::object {
              if (dec_places.is_none())
                throw py::type_error("triangulate() requires 'dec_places' for the D family");
              const int places = precision_arg(dec_places, 0);
              auto paths = to_paths<double>(pp);
              cl::PathsD solution;
              auto result = without_gil(
                  [&] { return cl::Triangulate(paths, places, solution, use_delaunay); });
              return py::make_tuple(result, from_paths(solution));
            });
      },
      py::arg("pp"), py::kw_only(), py::arg("dec_places") = py::none(),
      py::arg("use_delaunay") = true);
}
