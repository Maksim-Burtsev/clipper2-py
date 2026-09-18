// ClipperOffset and inflate_paths.

#include <memory>
#include <utility>

#include "clipper2/clipper.h"
#include "convert.h"

using namespace clipper2_py;

namespace {

using CO = cl::ClipperOffset;

// Upstream's DeltaCallback64: (path, path_normals, curr_idx, prev_idx) -> delta.
cl::DeltaCallback64 delta_callback(const py::object& fn) {
  if (fn.is_none()) return nullptr;
  return [fn](const cl::Path64& path, const cl::PathD& path_normals, size_t curr_idx,
              size_t prev_idx) {
    py::gil_scoped_acquire gil;
    return to_double(fn(from_path(path), from_path(path_normals), curr_idx, prev_idx));
  };
}

}  // namespace

void bind_offset(py::module_& m) {
  py::class_<CO> co(m, "ClipperOffset", py::module_local());
  co.def(py::init<double, double, bool, bool>(), py::arg("miter_limit") = 2.0,
         py::arg("arc_tolerance") = 0.0, py::arg("preserve_collinear") = false,
         py::arg("reverse_solution") = false)
      .def_property("miter_limit", static_cast<double (CO::*)() const>(&CO::MiterLimit),
                    static_cast<void (CO::*)(double)>(&CO::MiterLimit))
      .def_property("arc_tolerance", static_cast<double (CO::*)() const>(&CO::ArcTolerance),
                    static_cast<void (CO::*)(double)>(&CO::ArcTolerance))
      .def_property("preserve_collinear",
                    static_cast<bool (CO::*)() const>(&CO::PreserveCollinear),
                    static_cast<void (CO::*)(bool)>(&CO::PreserveCollinear))
      .def_property("reverse_solution", static_cast<bool (CO::*)() const>(&CO::ReverseSolution),
                    static_cast<void (CO::*)(bool)>(&CO::ReverseSolution))
      .def_property_readonly("error_code", &CO::ErrorCode)
      .def("clear", &CO::Clear)
      // Upstream names these parameters jt_ / et_; keyword names are upstream's (deviation 1).
      .def(
          "add_path",
          [](CO& self, const py::object& path, cl::JoinType jt, cl::EndType et) {
            self.AddPath(to_path<int64_t>(path), jt, et);
          },
          py::arg("path"), py::arg("jt_"), py::arg("et_"))
      .def(
          "add_paths",
          [](CO& self, const py::object& paths, cl::JoinType jt, cl::EndType et) {
            self.AddPaths(to_paths<int64_t>(paths), jt, et);
          },
          py::arg("paths"), py::arg("jt_"), py::arg("et_"))
      .def(
          "execute",
          [](CO& self, const py::object& delta) {
            cl::Paths64 solution;
            // None is C++'s Execute(nullptr, paths): a delta callback that clears the
            // callback, since nullptr converts to DeltaCallback64 and not to double.
            if (delta.is_none() || PyCallable_Check(delta.ptr())) {
              // Upstream's Execute(DeltaCallback64, Paths64&) is exactly these two lines, and
              // it likewise leaves the callback set on the object.
              self.SetDeltaCallback(delta_callback(delta));
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
            return from_paths(solution);
          },
          py::arg("delta"))
      .def(
          "execute_tree",
          [](CO& self, double delta) {
            std::unique_ptr<cl::PolyTree64> tree(new cl::PolyTree64());
            without_gil([&] {
              self.Execute(delta, *tree);
              return 0;
            });
            return tree;
          },
          py::arg("delta"))
      .def(
          "set_delta_callback",
          [](CO& self, const py::object& callback) {
            self.SetDeltaCallback(delta_callback(callback));
          },
          py::arg("callback"));

#ifdef USINGZ
  co.def(
      "set_z_callback",
      [](CO& self, const py::object& callback) {
        set_z_callback<int64_t, cl::ZCallback64>(
            callback, [&self](cl::ZCallback64 cb) { self.SetZCallback(std::move(cb)); });
      },
      py::arg("callback"));
#endif

  // Upstream's D overload puts precision between miter_limit and arc_tolerance, so a call
  // written by position would change meaning with the family: keyword-only from there on.
  m.def(
      "inflate_paths",
      [](const py::object& paths, double delta, cl::JoinType jt, cl::EndType et,
         double miter_limit, const py::object& precision, double arc_tolerance) {
        return dispatch(
            {paths},
            [&]() -> py::object {
              reject_precision(precision, "inflate_paths", "precision");
              auto p = to_paths<int64_t>(paths);
              return from_paths(without_gil([&] {
                return cl::InflatePaths(p, delta, jt, et, miter_limit, arc_tolerance);
              }));
            },
            [&]() -> py::object {
              const int prec = precision_arg(precision, 2);
              auto p = to_paths<double>(paths);
              return from_paths(without_gil([&] {
                return cl::InflatePaths(p, delta, jt, et, miter_limit, prec, arc_tolerance);
              }));
            });
      },
      py::arg("paths"), py::arg("delta"), py::arg("jt"), py::arg("et"),
      py::arg("miter_limit") = 2.0, py::kw_only(), py::arg("precision") = py::none(),
      py::arg("arc_tolerance") = 0.0);
}
