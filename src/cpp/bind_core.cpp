// Enums, Rect64 / RectD, Clipper2Error and the free functions of clipper.core.h + clipper.h.
// Coverage (including what is deliberately not bound) is listed in docs/api-map.md.

#include <sstream>
#include <string>
#include <vector>

#include <pybind11/operators.h>

#include "clipper2/clipper.h"
#include "convert.h"

using namespace clipper2_py;

namespace {

// Calls fn() with the path (nesting depth <= 2) or the paths (depth 3) of the right family.
// C++ picks those overloads by static type; Python has only the shape of the argument.
template <class Fn>
py::object on_path_or_paths(const py::object& x, Fn&& fn) {
  const bool many = nesting_depth(x) >= 3;
  return dispatch(
      {x},
      [&] { return many ? fn(to_paths<int64_t>(x)) : fn(to_path<int64_t>(x)); },
      [&] { return many ? fn(to_paths<double>(x)) : fn(to_path<double>(x)); });
}

template <class Fn>
py::object on_2_points(const py::object& a, const py::object& b, Fn&& fn) {
  return dispatch(
      {a, b}, [&] { return fn(to_point<int64_t>(a), to_point<int64_t>(b)); },
      [&] { return fn(to_point<double>(a), to_point<double>(b)); });
}

template <class Fn>
py::object on_3_points(const py::object& a, const py::object& b, const py::object& c, Fn&& fn) {
  return dispatch(
      {a, b, c},
      [&] { return fn(to_point<int64_t>(a), to_point<int64_t>(b), to_point<int64_t>(c)); },
      [&] { return fn(to_point<double>(a), to_point<double>(b), to_point<double>(c)); });
}

// Result of an upstream call, cast to Python with the GIL released while it runs.
template <class Fn>
py::object run(Fn&& fn) {
  return py::cast(without_gil(std::forward<Fn>(fn)));
}

template <class T>
std::string rect_str(const cl::Rect<T>& r) {
  std::ostringstream os;
  os << r;
  return os.str();
}

template <class T>
void bind_rect(py::module_& m, const char* name) {
  using R = cl::Rect<T>;
  py::class_<R>(m, name)
      .def(py::init<T, T, T, T>(), py::arg("l"), py::arg("t"), py::arg("r"), py::arg("b"))
      .def(py::init<bool>(), py::arg("is_valid") = true)
      .def_static("invalid_rect", &R::InvalidRect)
      .def_readwrite("left", &R::left)
      .def_readwrite("top", &R::top)
      .def_readwrite("right", &R::right)
      .def_readwrite("bottom", &R::bottom)
      .def("is_valid", &R::IsValid)
      .def("is_empty", &R::IsEmpty)
      .def_property("width", static_cast<T (R::*)() const>(&R::Width),
                    static_cast<void (R::*)(T)>(&R::Width))
      .def_property("height", static_cast<T (R::*)() const>(&R::Height),
                    static_cast<void (R::*)(T)>(&R::Height))
      .def("mid_point", [](const R& r) { return from_point(r.MidPoint()); })
      .def("as_path", [](const R& r) { return from_path(r.AsPath()); })
      .def("contains", [](const R& r, const R& other) { return r.Contains(other); }, py::arg("rec"))
      .def("contains", [](const R& r, const py::object& pt) { return r.Contains(to_point<T>(pt)); },
           py::arg("pt"))
      .def("scale", &R::Scale, py::arg("scale"))
      .def("intersects", &R::Intersects, py::arg("rec"))
      .def(py::self == py::self)
      .def(py::self += py::self)
      .def(py::self + py::self)
      .def("__str__", &rect_str<T>)
      .def("__repr__", [name](const R& r) {
        std::ostringstream os;
        os << name << "(" << r.left << ", " << r.top << ", " << r.right << ", " << r.bottom << ")";
        return os.str();
      });
}

}  // namespace

// Registered once, in _clipper2; _clipper2z re-exports these same objects (see module.cpp).
void bind_shared_types(py::module_& m) {
  py::register_exception<cl::Clipper2Exception>(m, "Clipper2Error");

  py::enum_<cl::FillRule>(m, "FillRule")
      .value("EVEN_ODD", cl::FillRule::EvenOdd)
      .value("NON_ZERO", cl::FillRule::NonZero)
      .value("POSITIVE", cl::FillRule::Positive)
      .value("NEGATIVE", cl::FillRule::Negative);

  py::enum_<cl::ClipType>(m, "ClipType")
      .value("NO_CLIP", cl::ClipType::NoClip)
      .value("INTERSECTION", cl::ClipType::Intersection)
      .value("UNION", cl::ClipType::Union)
      .value("DIFFERENCE", cl::ClipType::Difference)
      .value("XOR", cl::ClipType::Xor);

  py::enum_<cl::PathType>(m, "PathType")
      .value("SUBJECT", cl::PathType::Subject)
      .value("CLIP", cl::PathType::Clip);

  py::enum_<cl::PointInPolygonResult>(m, "PointInPolygonResult")
      .value("IS_ON", cl::PointInPolygonResult::IsOn)
      .value("IS_INSIDE", cl::PointInPolygonResult::IsInside)
      .value("IS_OUTSIDE", cl::PointInPolygonResult::IsOutside);

  py::enum_<cl::JoinType>(m, "JoinType")
      .value("SQUARE", cl::JoinType::Square)
      .value("BEVEL", cl::JoinType::Bevel)
      .value("ROUND", cl::JoinType::Round)
      .value("MITER", cl::JoinType::Miter);

  py::enum_<cl::EndType>(m, "EndType")
      .value("POLYGON", cl::EndType::Polygon)
      .value("JOINED", cl::EndType::Joined)
      .value("BUTT", cl::EndType::Butt)
      .value("SQUARE", cl::EndType::Square)
      .value("ROUND", cl::EndType::Round);

  py::enum_<cl::TriangulateResult>(m, "TriangulateResult")
      .value("SUCCESS", cl::TriangulateResult::success)
      .value("FAIL", cl::TriangulateResult::fail)
      .value("NO_POLYGONS", cl::TriangulateResult::no_polygons)
      .value("PATHS_INTERSECT", cl::TriangulateResult::paths_intersect);

  bind_rect<int64_t>(m, "Rect64");
  bind_rect<double>(m, "RectD");
}

const char* const* shared_type_names() {
  static const char* const names[] = {"Clipper2Error",  "FillRule",
                                      "ClipType",       "PathType",
                                      "JoinType",       "EndType",
                                      "PointInPolygonResult", "TriangulateResult",
                                      "Rect64",         "RectD",
                                      nullptr};
  return names;
}

void bind_core(py::module_& m) {
  m.attr("CLIPPER2_VERSION") = CLIPPER2_VERSION;
  m.attr("CLIPPER2_MAX_DEC_PRECISION") = cl::CLIPPER2_MAX_DEC_PRECISION;
  m.attr("MAX_COORD") = cl::MAX_COORD;
  m.attr("MIN_COORD") = cl::MIN_COORD;
  // The bits ClipperBase.error_code / ClipperOffset.error_code are made of.
  m.attr("precision_error_i") = cl::precision_error_i;
  m.attr("scale_error_i") = cl::scale_error_i;
  m.attr("non_pair_error_i") = cl::non_pair_error_i;
  m.attr("undefined_error_i") = cl::undefined_error_i;
  m.attr("range_error_i") = cl::range_error_i;

  // --- clipper.core.h ---------------------------------------------------------------

  m.def(
      "area", [](const py::object& x) {
        return on_path_or_paths(x, [](auto&& g) { return run([&] { return cl::Area(g); }); });
      },
      py::arg("path"));

  m.def(
      "is_positive",
      [](const py::object& path) {
        return dispatch(
            {path},
            [&] {
              auto p = to_path<int64_t>(path);
              return run([&] { return cl::IsPositive(p); });
            },
            [&] {
              auto p = to_path<double>(path);
              return run([&] { return cl::IsPositive(p); });
            });
      },
      py::arg("poly"));

  m.def(
      "get_bounds",
      [](const py::object& x) {
        return on_path_or_paths(x, [](auto&& g) { return run([&] { return cl::GetBounds(g); }); });
      },
      py::arg("path"));

  m.def(
      "point_in_polygon",
      [](const py::object& pt, const py::object& polygon) {
        return dispatch(
            {pt, polygon},
            [&] {
              auto p = to_point<int64_t>(pt);
              auto poly = to_path<int64_t>(polygon);
              return run([&] { return cl::PointInPolygon(p, poly); });
            },
            [&] {
              auto p = to_point<double>(pt);
              auto poly = to_path<double>(polygon);
              return run([&] { return cl::PointInPolygon(p, poly); });
            });
      },
      py::arg("pt"), py::arg("polygon"));

  m.def(
      "cross_product",
      [](const py::object& pt1, const py::object& pt2, const py::object& pt3) {
        return on_3_points(pt1, pt2, pt3, [](auto&& a, auto&& b, auto&& c) {
          return run([&] { return cl::CrossProduct(a, b, c); });
        });
      },
      py::arg("pt1"), py::arg("pt2"), py::arg("pt3"));

  m.def(
      "cross_product",
      [](const py::object& vec1, const py::object& vec2) {
        return on_2_points(vec1, vec2, [](auto&& a, auto&& b) {
          return run([&] { return cl::CrossProduct(a, b); });
        });
      },
      py::arg("vec1"), py::arg("vec2"));

  m.def(
      "dot_product",
      [](const py::object& pt1, const py::object& pt2, const py::object& pt3) {
        return on_3_points(pt1, pt2, pt3, [](auto&& a, auto&& b, auto&& c) {
          return run([&] { return cl::DotProduct(a, b, c); });
        });
      },
      py::arg("pt1"), py::arg("pt2"), py::arg("pt3"));

  m.def(
      "dot_product",
      [](const py::object& vec1, const py::object& vec2) {
        return on_2_points(vec1, vec2,
                           [](auto&& a, auto&& b) { return run([&] { return cl::DotProduct(a, b); }); });
      },
      py::arg("vec1"), py::arg("vec2"));

  m.def(
      "cross_product_sign",
      [](const py::object& pt1, const py::object& pt2, const py::object& pt3) {
        return on_3_points(pt1, pt2, pt3, [](auto&& a, auto&& b, auto&& c) {
          return run([&] { return cl::CrossProductSign(a, b, c); });
        });
      },
      py::arg("pt1"), py::arg("pt2"), py::arg("pt3"));

  m.def(
      "is_collinear",
      [](const py::object& pt1, const py::object& shared_pt, const py::object& pt2) {
        return on_3_points(pt1, shared_pt, pt2, [](auto&& a, auto&& b, auto&& c) {
          return run([&] { return cl::IsCollinear(a, b, c); });
        });
      },
      py::arg("pt1"), py::arg("shared_pt"), py::arg("pt2"));

  m.def(
      "distance_sqr",
      [](const py::object& pt1, const py::object& pt2) {
        return on_2_points(pt1, pt2, [](auto&& a, auto&& b) {
          return run([&] { return cl::DistanceSqr(a, b); });
        });
      },
      py::arg("pt1"), py::arg("pt2"));

  m.def(
      "perpendic_dist_from_line_sqrd",
      [](const py::object& pt, const py::object& line1, const py::object& line2) {
        return on_3_points(pt, line1, line2, [](auto&& p, auto&& l1, auto&& l2) {
          return run([&] { return cl::PerpendicDistFromLineSqrd(p, l1, l2); });
        });
      },
      py::arg("pt"), py::arg("line1"), py::arg("line2"));

  m.def(
      "mid_point",
      [](const py::object& p1, const py::object& p2) {
        return on_2_points(p1, p2, [](auto&& a, auto&& b) {
          return from_point(without_gil([&] { return cl::MidPoint(a, b); }));
        });
      },
      py::arg("p1"), py::arg("p2"));

  m.def(
      "near_equal",
      [](const py::object& p1, const py::object& p2, double max_dist_sqrd) {
        return on_2_points(p1, p2, [&](auto&& a, auto&& b) {
          return run([&] { return cl::NearEqual(a, b, max_dist_sqrd); });
        });
      },
      py::arg("p1"), py::arg("p2"), py::arg("max_dist_sqrd"));

  m.def(
      "strip_near_equal",
      [](const py::object& x, double max_dist_sqrd, bool is_closed_path) {
        return on_path_or_paths(x, [&](auto&& g) -> py::object {
          auto out = without_gil([&] { return cl::StripNearEqual(g, max_dist_sqrd, is_closed_path); });
          return from_geometry(out);
        });
      },
      py::arg("path"), py::arg("max_dist_sqrd"), py::arg("is_closed_path"));

  m.def(
      "strip_duplicates",
      [](const py::object& x, bool is_closed_path) {
        return on_path_or_paths(x, [&](auto&& g) -> py::object {
          auto copy = g;
          without_gil([&] {
            cl::StripDuplicates(copy, is_closed_path);
            return 0;
          });
          return from_geometry(copy);
        });
      },
      py::arg("path"), py::arg("is_closed_path"));

  m.def(
      "translate_point",
      [](const py::object& pt, double dx, double dy) {
        return dispatch(
            {pt},
            [&] {
              auto p = to_point<int64_t>(pt);
              return from_point(without_gil([&] { return cl::TranslatePoint(p, dx, dy); }));
            },
            [&] {
              auto p = to_point<double>(pt);
              return from_point(without_gil([&] { return cl::TranslatePoint(p, dx, dy); }));
            });
      },
      py::arg("pt"), py::arg("dx"), py::arg("dy"));

  m.def(
      "reflect_point",
      [](const py::object& pt, const py::object& pivot) {
        return on_2_points(pt, pivot, [](auto&& p, auto&& pv) {
          return from_point(without_gil([&] { return cl::ReflectPoint(p, pv); }));
        });
      },
      py::arg("pt"), py::arg("pivot"));

  // Upstream declares this one for Point64 only.
  m.def(
      "segments_intersect",
      [](const py::object& seg1a, const py::object& seg1b, const py::object& seg2a,
         const py::object& seg2b, bool inclusive) {
        auto a = to_point<int64_t>(seg1a);
        auto b = to_point<int64_t>(seg1b);
        auto c = to_point<int64_t>(seg2a);
        auto d = to_point<int64_t>(seg2b);
        return run([&] { return cl::SegmentsIntersect(a, b, c, d, inclusive); });
      },
      py::arg("seg1a"), py::arg("seg1b"), py::arg("seg2a"), py::arg("seg2b"),
      py::arg("inclusive") = false);

  m.def(
      "get_closest_point_on_segment",
      [](const py::object& off_pt, const py::object& seg1, const py::object& seg2) {
        return on_3_points(off_pt, seg1, seg2, [](auto&& p, auto&& s1, auto&& s2) {
          return from_point(without_gil([&] { return cl::GetClosestPointOnSegment(p, s1, s2); }));
        });
      },
      py::arg("off_pt"), py::arg("seg1"), py::arg("seg2"));

  // --- clipper.h --------------------------------------------------------------------

  m.def(
      "boolean_op",
      [](cl::ClipType cliptype, cl::FillRule fillrule, const py::object& subjects,
         const py::object& clips, const py::object& precision) {
        return dispatch(
            {subjects, clips},
            [&]() -> py::object {
              reject_precision(precision, "boolean_op", "precision");
              auto s = to_paths<int64_t>(subjects);
              auto c = to_paths<int64_t>(clips);
              return from_paths(without_gil([&] { return cl::BooleanOp(cliptype, fillrule, s, c); }));
            },
            [&]() -> py::object {
              const int p = precision_arg(precision, 2);
              auto s = to_paths<double>(subjects);
              auto c = to_paths<double>(clips);
              return from_paths(
                  without_gil([&] { return cl::BooleanOp(cliptype, fillrule, s, c, p); }));
            });
      },
      py::arg("cliptype"), py::arg("fillrule"), py::arg("subjects"), py::arg("clips"),
      py::arg("precision") = py::none());

  m.def(
      "boolean_op_tree",
      [](cl::ClipType cliptype, cl::FillRule fillrule, const py::object& subjects,
         const py::object& clips, const py::object& precision) {
        return dispatch(
            {subjects, clips},
            [&]() -> py::object {
              reject_precision(precision, "boolean_op_tree", "precision");
              auto s = to_paths<int64_t>(subjects);
              auto c = to_paths<int64_t>(clips);
              auto tree = std::unique_ptr<cl::PolyTree64>(new cl::PolyTree64());
              without_gil([&] {
                cl::BooleanOp(cliptype, fillrule, s, c, *tree);
                return 0;
              });
              return py::cast(std::move(tree));
            },
            [&]() -> py::object {
              const int p = precision_arg(precision, 2);
              auto s = to_paths<double>(subjects);
              auto c = to_paths<double>(clips);
              auto tree = std::unique_ptr<cl::PolyTreeD>(new cl::PolyTreeD());
              without_gil([&] {
                cl::BooleanOp(cliptype, fillrule, s, c, *tree, p);
                return 0;
              });
              return py::cast(std::move(tree));
            });
      },
      py::arg("cliptype"), py::arg("fillrule"), py::arg("subjects"), py::arg("clips"),
      py::arg("precision") = py::none());

  auto two_path_op = [&m](const char* name, cl::ClipType ct) {
    m.def(
        name,
        [ct, name](const py::object& subjects, const py::object& clips, cl::FillRule fillrule,
                   const py::object& decimal_prec) {
          return dispatch(
              {subjects, clips},
              [&]() -> py::object {
                reject_precision(decimal_prec, name, "decimal_prec");
                auto s = to_paths<int64_t>(subjects);
                auto c = to_paths<int64_t>(clips);
                return from_paths(without_gil([&] { return cl::BooleanOp(ct, fillrule, s, c); }));
              },
              [&]() -> py::object {
                const int p = precision_arg(decimal_prec, 2);
                auto s = to_paths<double>(subjects);
                auto c = to_paths<double>(clips);
                return from_paths(without_gil([&] { return cl::BooleanOp(ct, fillrule, s, c, p); }));
              });
        },
        py::arg("subjects"), py::arg("clips"), py::arg("fillrule"),
        py::arg("decimal_prec") = py::none());
  };

  // Union's one-argument form is registered first so that union(subjects, fillrule) matches it.
  m.def(
      "union",
      [](const py::object& subjects, cl::FillRule fillrule, const py::object& precision) {
        return dispatch(
            {subjects},
            [&]() -> py::object {
              reject_precision(precision, "union", "precision");
              auto s = to_paths<int64_t>(subjects);
              return from_paths(without_gil([&] { return cl::Union(s, fillrule); }));
            },
            [&]() -> py::object {
              const int p = precision_arg(precision, 2);
              auto s = to_paths<double>(subjects);
              return from_paths(without_gil([&] { return cl::Union(s, fillrule, p); }));
            });
      },
      py::arg("subjects"), py::arg("fillrule"), py::arg("precision") = py::none());

  two_path_op("intersect", cl::ClipType::Intersection);
  two_path_op("union", cl::ClipType::Union);
  two_path_op("difference", cl::ClipType::Difference);
  two_path_op("xor", cl::ClipType::Xor);

  m.def(
      "translate_path",
      [](const py::object& path, const py::object& dx, const py::object& dy) {
        return dispatch(
            {path},
            [&] {
              auto p = to_path<int64_t>(path);
              const int64_t x = to_int64(dx), y = to_int64(dy);
              return from_path(without_gil([&] { return cl::TranslatePath(p, x, y); }));
            },
            [&] {
              auto p = to_path<double>(path);
              const double x = to_double(dx), y = to_double(dy);
              return from_path(without_gil([&] { return cl::TranslatePath(p, x, y); }));
            });
      },
      py::arg("path"), py::arg("dx"), py::arg("dy"));

  m.def(
      "translate_paths",
      [](const py::object& paths, const py::object& dx, const py::object& dy) {
        return dispatch(
            {paths},
            [&] {
              auto p = to_paths<int64_t>(paths);
              const int64_t x = to_int64(dx), y = to_int64(dy);
              return from_paths(without_gil([&] { return cl::TranslatePaths(p, x, y); }));
            },
            [&] {
              auto p = to_paths<double>(paths);
              const double x = to_double(dx), y = to_double(dy);
              return from_paths(without_gil([&] { return cl::TranslatePaths(p, x, y); }));
            });
      },
      py::arg("paths"), py::arg("dx"), py::arg("dy"));

  m.def(
      "poly_tree_to_paths64",
      [m](const py::object& polytree) {
        const cl::PolyTree64& tree = cast_local<cl::PolyTree64>(m, "PolyPath64", polytree);
        return from_paths(without_gil([&] { return cl::PolyTreeToPaths64(tree); }));
      },
      py::arg("polytree"));

  m.def(
      "poly_tree_to_paths_d",
      [m](const py::object& polytree) {
        const cl::PolyTreeD& tree = cast_local<cl::PolyTreeD>(m, "PolyPathD", polytree);
        return from_paths(without_gil([&] { return cl::PolyTreeToPathsD(tree); }));
      },
      py::arg("polytree"));

  m.def(
      "check_polytree_fully_contains_children",
      [m](const py::object& polytree) {
        const cl::PolyTree64& tree = cast_local<cl::PolyTree64>(m, "PolyPath64", polytree);
        return run([&] { return cl::CheckPolytreeFullyContainsChildren(tree); });
      },
      py::arg("polytree"));

  m.def(
      "make_path",
      [](const py::object& values) {
        py::array a = coerce<int64_t>(values);
        if (a.ndim() != 1) throw py::value_error("expected a flat sequence of coordinates");
        const int64_t* d = static_cast<const int64_t*>(a.data());
        std::vector<int64_t> list(d, d + a.size());
        return from_path(without_gil([&] { return cl::MakePath(list); }));
      },
      py::arg("list"));

  m.def(
      "make_path_d",
      [](const py::object& values) {
        py::array a = coerce<double>(values);
        if (a.ndim() != 1) throw py::value_error("expected a flat sequence of coordinates");
        const double* d = static_cast<const double*>(a.data());
        std::vector<double> list(d, d + a.size());
        return from_path(without_gil([&] { return cl::MakePathD(list); }));
      },
      py::arg("list"));

  m.def(
      "trim_collinear",
      [](const py::object& path, const py::object& precision, bool is_open_path) {
        return dispatch(
            {path},
            [&] {
              reject_precision(precision, "trim_collinear", "precision");
              auto p = to_path<int64_t>(path);
              return from_path(without_gil([&] { return cl::TrimCollinear(p, is_open_path); }));
            },
            [&] {
              if (precision.is_none())
                throw py::type_error("trim_collinear() requires 'precision' for the D family");
              const int prec = precision_arg(precision, 0);
              auto p = to_path<double>(path);
              return from_path(
                  without_gil([&] { return cl::TrimCollinear(p, prec, is_open_path); }));
            });
      },
      py::arg("path"), py::arg("precision") = py::none(), py::arg("is_open_path") = false);

  m.def(
      "distance",
      [](const py::object& pt1, const py::object& pt2) {
        return on_2_points(pt1, pt2,
                           [](auto&& a, auto&& b) { return run([&] { return cl::Distance(a, b); }); });
      },
      py::arg("pt1"), py::arg("pt2"));

  m.def(
      "length",
      [](const py::object& path, bool is_closed_path) {
        return dispatch(
            {path},
            [&] {
              auto p = to_path<int64_t>(path);
              return run([&] { return cl::Length(p, is_closed_path); });
            },
            [&] {
              auto p = to_path<double>(path);
              return run([&] { return cl::Length(p, is_closed_path); });
            });
      },
      py::arg("path"), py::arg("is_closed_path") = false);

  m.def(
      "near_collinear",
      [](const py::object& pt1, const py::object& pt2, const py::object& pt3,
         double sin_sqrd_min_angle_rads) {
        return on_3_points(pt1, pt2, pt3, [&](auto&& a, auto&& b, auto&& c) {
          return run([&] { return cl::NearCollinear(a, b, c, sin_sqrd_min_angle_rads); });
        });
      },
      py::arg("pt1"), py::arg("pt2"), py::arg("pt3"), py::arg("sin_sqrd_min_angle_rads"));

  m.def(
      "ellipse",
      [](const cl::Rect64& rect, size_t steps) {
        return from_path(without_gil([&] { return cl::Ellipse<int64_t>(rect, steps); }));
      },
      py::arg("rect"), py::arg("steps") = 0);

  m.def(
      "ellipse",
      [](const cl::RectD& rect, size_t steps) {
        return from_path(without_gil([&] { return cl::Ellipse<double>(rect, steps); }));
      },
      py::arg("rect"), py::arg("steps") = 0);

  m.def(
      "ellipse",
      [](const py::object& center, double radius_x, double radius_y, size_t steps) {
        return dispatch(
            {center},
            [&] {
              auto c = to_point<int64_t>(center);
              return from_path(
                  without_gil([&] { return cl::Ellipse<int64_t>(c, radius_x, radius_y, steps); }));
            },
            [&] {
              auto c = to_point<double>(center);
              return from_path(
                  without_gil([&] { return cl::Ellipse<double>(c, radius_x, radius_y, steps); }));
            });
      },
      py::arg("center"), py::arg("radius_x"), py::arg("radius_y") = 0, py::arg("steps") = 0);

  m.def(
      "simplify_path",
      [](const py::object& path, double epsilon, bool is_closed_path) {
        return dispatch(
            {path},
            [&] {
              auto p = to_path<int64_t>(path);
              return from_path(
                  without_gil([&] { return cl::SimplifyPath(p, epsilon, is_closed_path); }));
            },
            [&] {
              auto p = to_path<double>(path);
              return from_path(
                  without_gil([&] { return cl::SimplifyPath(p, epsilon, is_closed_path); }));
            });
      },
      py::arg("path"), py::arg("epsilon"), py::arg("is_closed_path") = true);

  m.def(
      "simplify_paths",
      [](const py::object& paths, double epsilon, bool is_closed_path) {
        return dispatch(
            {paths},
            [&] {
              auto p = to_paths<int64_t>(paths);
              return from_paths(
                  without_gil([&] { return cl::SimplifyPaths(p, epsilon, is_closed_path); }));
            },
            [&] {
              auto p = to_paths<double>(paths);
              return from_paths(
                  without_gil([&] { return cl::SimplifyPaths(p, epsilon, is_closed_path); }));
            });
      },
      py::arg("paths"), py::arg("epsilon"), py::arg("is_closed_path") = true);

  m.def(
      "path2_contains_path1",
      [](const py::object& path1, const py::object& path2) {
        return dispatch(
            {path1, path2},
            [&] {
              auto a = to_path<int64_t>(path1);
              auto b = to_path<int64_t>(path2);
              return run([&] { return cl::Path2ContainsPath1(a, b); });
            },
            [&] {
              auto a = to_path<double>(path1);
              auto b = to_path<double>(path2);
              return run([&] { return cl::Path2ContainsPath1(a, b); });
            });
      },
      py::arg("path1"), py::arg("path2"));

  m.def(
      "ramer_douglas_peucker",
      [](const py::object& x, double epsilon) {
        return on_path_or_paths(x, [&](auto&& g) -> py::object {
          auto out = without_gil([&] { return cl::RamerDouglasPeucker(g, epsilon); });
          return from_geometry(out);
        });
      },
      py::arg("path"), py::arg("epsilon"));
}
