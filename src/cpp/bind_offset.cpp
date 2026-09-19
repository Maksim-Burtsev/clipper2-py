// ClipperOffset and inflate_paths.

#include <algorithm>
#include <memory>
#include <utility>

#include "clipper2/clipper.h"
#include "convert.h"

using namespace clipper2_py;

namespace {

// What Python needs on top of upstream's offsetter: see ExecState in convert.h.
struct CO : cl::ClipperOffset {
  using ClipperOffset::ClipperOffset;
  ExecState state;
};

// Upstream's DeltaCallback64: (path, path_normals, curr_idx, prev_idx) -> delta.
// `state` belongs to the object that owns the std::function, so it cannot dangle.
cl::DeltaCallback64 delta_callback(const py::object& fn, ExecState& state) {
  if (fn.is_none()) return nullptr;
  return [fn, &state](const cl::Path64& path, const cl::PathD& path_normals, size_t curr_idx,
                      size_t prev_idx) {
    py::gil_scoped_acquire gil;
    if (state.failed()) return 0.0;  // an earlier call raised: offset by nothing
    try {
      return to_double(fn(from_path(path), from_path(path_normals), curr_idx, prev_idx));
    } catch (...) {
      state.store_error();
      return 0.0;
    }
  };
}

}  // namespace

// Upstream 2.0.1 indexes path.size() - 1 of an empty path when the end type is an open one and
// crashes (issue #1). Such a path has nothing to offset, so it is dropped before upstream sees
// it, which is what upstream itself does with it for EndType::Polygon.
template <class T>
void drop_empty_open_paths(cl::Paths<T>& paths, cl::EndType et) {
  if (et == cl::EndType::Polygon) return;
  paths.erase(std::remove_if(paths.begin(), paths.end(),
                             [](const cl::Path<T>& p) { return p.empty(); }),
              paths.end());
}

void bind_offset(py::module_& m) {
  py::class_<CO> co(m, "ClipperOffset", py::module_local());
  co.def(py::init<double, double, bool, bool>(), py::arg("miter_limit") = 2.0,
         py::arg("arc_tolerance") = 0.0, py::arg("preserve_collinear") = false,
         py::arg("reverse_solution") = false)
      .def_property("miter_limit", static_cast<double (cl::ClipperOffset::*)() const>(&CO::MiterLimit),
                    [](CO& self, double value) {
                      check_idle(self.state, "ClipperOffset");
                      self.MiterLimit(value);
                    })
      .def_property("arc_tolerance", static_cast<double (cl::ClipperOffset::*)() const>(&CO::ArcTolerance),
                    [](CO& self, double value) {
                      check_idle(self.state, "ClipperOffset");
                      self.ArcTolerance(value);
                    })
      .def_property("preserve_collinear",
                    static_cast<bool (cl::ClipperOffset::*)() const>(&CO::PreserveCollinear),
                    [](CO& self, bool value) {
                      check_idle(self.state, "ClipperOffset");
                      self.PreserveCollinear(value);
                    })
      .def_property("reverse_solution", static_cast<bool (cl::ClipperOffset::*)() const>(&CO::ReverseSolution),
                    [](CO& self, bool value) {
                      check_idle(self.state, "ClipperOffset");
                      self.ReverseSolution(value);
                    })
      .def_property_readonly("error_code", &CO::ErrorCode)
      .def("clear",
           [](CO& self) {
             check_idle(self.state, "ClipperOffset");
             self.Clear();
           })
      // Upstream names these parameters jt_ / et_; keyword names are upstream's (deviation 1).
      .def(
          "add_path",
          [](CO& self, const Geometry& path, cl::JoinType jt, cl::EndType et) {
            check_idle(self.state, "ClipperOffset");
            cl::Paths64 one{to_path<int64_t>(path)};
            drop_empty_open_paths(one, et);
            if (!one.empty()) self.AddPath(one[0], jt, et);
          },
          py::arg("path"), py::arg("jt_"), py::arg("et_"))
      .def(
          "add_paths",
          [](CO& self, const Geometry& paths, cl::JoinType jt, cl::EndType et) {
            check_idle(self.state, "ClipperOffset");
            auto p = to_paths<int64_t>(paths);
            drop_empty_open_paths(p, et);
            self.AddPaths(p, jt, et);
          },
          py::arg("paths"), py::arg("jt_"), py::arg("et_"))
      .def(
          "execute",
          [](CO& self, const py::object& delta) {
            ExecGuard guard(self.state, "ClipperOffset");
            cl::Paths64 solution;
            // None is C++'s Execute(nullptr, paths): a delta callback that clears the
            // callback, since nullptr converts to DeltaCallback64 and not to double.
            if (delta.is_none() || PyCallable_Check(delta.ptr())) {
              // Upstream's Execute(DeltaCallback64, Paths64&) is exactly these two lines, and
              // it likewise leaves the callback set on the object.
              self.SetDeltaCallback(delta_callback(delta, self.state));
              without_gil([&] {
                self.Execute(1.0, solution);
                return 0;
              });
            } else {
              const double d = to_double(delta);
              without_gil([&] {
                self.Execute(d, solution);
                return 0;
              });
            }
            guard.rethrow_pending();
            return from_paths(solution);
          },
          py::arg("delta"))
      .def(
          "execute_tree",
          [](CO& self, double delta) {
            ExecGuard guard(self.state, "ClipperOffset");
            std::unique_ptr<cl::PolyTree64> tree(new cl::PolyTree64());
            without_gil([&] {
              self.Execute(delta, *tree);
              return 0;
            });
            guard.rethrow_pending();
            return tree;
          },
          py::arg("delta"))
      .def(
          "set_delta_callback",
          [](CO& self, const py::object& callback) {
            check_idle(self.state, "ClipperOffset");
            self.SetDeltaCallback(delta_callback(callback, self.state));
          },
          py::arg("callback"));

#ifdef USINGZ
  co.def(
      "set_z_callback",
      [](CO& self, const py::object& callback) {
        check_idle(self.state, "ClipperOffset");
        set_z_callback<int64_t, cl::ZCallback64>(
            callback, self.state, [&self](cl::ZCallback64 cb) { self.SetZCallback(std::move(cb)); });
      },
      py::arg("callback"));
#endif

  // Upstream's D overload puts precision between miter_limit and arc_tolerance, so a call
  // written by position would change meaning with the family: keyword-only from there on.
  m.def(
      "inflate_paths",
      [](const Geometry& paths, double delta, cl::JoinType jt, cl::EndType et,
         double miter_limit, const py::object& precision, double arc_tolerance) {
        return dispatch(
            {paths},
            [&]() -> py::object {
              reject_precision(precision, "inflate_paths", "precision");
              auto p = to_paths<int64_t>(paths);
              if (delta != 0.0) drop_empty_open_paths(p, et);  // delta 0 returns the input as is
              return from_paths(without_gil([&] {
                return cl::InflatePaths(p, delta, jt, et, miter_limit, arc_tolerance);
              }));
            },
            [&]() -> py::object {
              const int prec = precision_arg(precision, 2);
              auto p = to_paths<double>(paths);
              if (delta != 0.0) drop_empty_open_paths(p, et);
              return from_paths(without_gil([&] {
                return cl::InflatePaths(p, delta, jt, et, miter_limit, prec, arc_tolerance);
              }));
            });
      },
      py::arg("paths"), py::arg("delta"), py::arg("jt"), py::arg("et"),
      py::arg("miter_limit") = 2.0, py::kw_only(), py::arg("precision") = py::none(),
      py::arg("arc_tolerance") = 0.0);
}
