// Clipper64, ClipperD, ReuseableDataContainer64 and the read-only PolyPath tree.

#include <memory>
#include <sstream>
#include <string>

#include "clipper2/clipper.h"
#include "convert.h"

using namespace clipper2_py;

namespace {

// Upstream's Execute returns false without raising; spec decision 7 turns that into an error.
[[noreturn]] void raise_execute_failed() { throw cl::Clipper2Exception(cl::undefined_error); }

// What Python needs on top of upstream's clipper: see ExecState in convert.h.
template <class C>
struct Holder : C {
  using C::C;
  ExecState state;
};

using PyClipper64 = Holder<cl::Clipper64>;
using PyClipperD = Holder<cl::ClipperD>;

template <class C>
void add_clipper_base(const py::module_& m, py::class_<C>& c, const char* name) {
  c.def_property(
       "preserve_collinear",
       static_cast<bool (cl::ClipperBase::*)() const>(&cl::ClipperBase::PreserveCollinear),
       [name](C& self, bool value) {
         check_idle(self.state, name);
         self.PreserveCollinear(value);
       })
      .def_property(
          "reverse_solution",
          static_cast<bool (cl::ClipperBase::*)() const>(&cl::ClipperBase::ReverseSolution),
          [name](C& self, bool value) {
            check_idle(self.state, name);
            self.ReverseSolution(value);
          })
      .def_property_readonly("error_code", &cl::ClipperBase::ErrorCode)
      .def("clear",
           [name](C& self) {
             check_idle(self.state, name);
             self.Clear();
             self.state.kept.clear();
           })
      .def(
          "add_reuseable_data",
          [m, name](C& self, const py::object& reuseable_data) {
            check_idle(self.state, name);
            self.AddReuseableData(cast_local<cl::ReuseableDataContainer64>(
                m, "ReuseableDataContainer64", reuseable_data));
            // Upstream keeps raw Vertex pointers into the container until Clear().
            self.state.kept.push_back(reuseable_data);
          },
          py::arg("reuseable_data"));
#ifdef USINGZ
  c.def_property(
      "default_z", [](const C& self) { return self.DefaultZ; },
      [name](C& self, int64_t value) {
        check_idle(self.state, name);
        self.DefaultZ = value;
      });
#endif
}

template <class P>
py::class_<P> bind_polypath(py::module_& m, const char* name) {
  py::class_<P> c(m, name, py::module_local());
  c.def_property_readonly("polygon", [](const P& p) { return from_path(p.Polygon()); })
      .def_property_readonly("is_hole", &P::IsHole)
      .def_property_readonly("level", &P::Level)
      .def_property_readonly(
          "parent", [](const P& p) { return static_cast<const P*>(p.Parent()); },
          py::return_value_policy::reference_internal)
      .def("__len__", &P::Count)
      .def("area", &P::Area)
      .def("__str__",
           [](const P& p) {
             std::ostringstream os;
             os << p;
             return os.str();
           })
      .def("__repr__", [name](const P& p) {
        std::ostringstream os;
        os << "<" << name << " with " << p.Count() << " child(ren), "
           << p.Polygon().size() << " vertices>";
        return os.str();
      });

  auto child = [](const P& p, py::ssize_t index) -> const P* {
    if (index < 0 || static_cast<size_t>(index) >= p.Count())
      throw py::index_error("PolyPath index out of range");
    return p.Child(static_cast<size_t>(index));
  };
  c.def("child", child, py::arg("index"), py::return_value_policy::reference_internal);
  // Defining __getitem__ also gives iteration over the children (sequence protocol).
  c.def("__getitem__", child, py::arg("index"), py::return_value_policy::reference_internal);
  return c;
}

}  // namespace

void bind_engine(py::module_& m) {
  py::class_<cl::ReuseableDataContainer64> reuseable(m, "ReuseableDataContainer64",
                                                     py::module_local());
  reuseable.def(py::init<>())
      .def("clear", &cl::ReuseableDataContainer64::Clear)
      .def(
          "add_paths",
          [](cl::ReuseableDataContainer64& self, const Geometry& paths, cl::PathType polytype,
             bool is_open) { self.AddPaths(to_paths<int64_t>(paths), polytype, is_open); },
          py::arg("paths"), py::arg("polytype"), py::arg("is_open"));

  bind_polypath<cl::PolyPath64>(m, "PolyPath64");
  bind_polypath<cl::PolyPathD>(m, "PolyPathD").def_property_readonly("scale", &cl::PolyPathD::Scale);
  m.attr("PolyTree64") = m.attr("PolyPath64");  // upstream: using PolyTree64 = PolyPath64
  m.attr("PolyTreeD") = m.attr("PolyPathD");

  py::class_<PyClipper64> c64(m, "Clipper64", py::module_local());
  add_clipper_base(m, c64, "Clipper64");
  c64.def(py::init<>())
      .def(
          "add_subject",
          [](PyClipper64& self, const Geometry& subjects) {
            check_idle(self.state, "Clipper64");
            self.AddSubject(to_paths<int64_t>(subjects));
          },
          py::arg("subjects"))
      .def(
          "add_open_subject",
          [](PyClipper64& self, const Geometry& open_subjects) {
            check_idle(self.state, "Clipper64");
            self.AddOpenSubject(to_paths<int64_t>(open_subjects));
          },
          py::arg("open_subjects"))
      .def(
          "add_clip",
          [](PyClipper64& self, const Geometry& clips) {
            check_idle(self.state, "Clipper64");
            self.AddClip(to_paths<int64_t>(clips));
          },
          py::arg("clips"))
      .def(
          "execute",
          [](PyClipper64& self, cl::ClipType clip_type, cl::FillRule fill_rule) {
            ExecGuard guard(self.state, "Clipper64");
            cl::Paths64 closed, open;
            const bool ok =
                without_gil([&] { return self.Execute(clip_type, fill_rule, closed, open); });
            guard.rethrow_pending();
            if (!ok) raise_execute_failed();
            return py::make_tuple(from_paths(closed), from_paths(open));
          },
          py::arg("clip_type"), py::arg("fill_rule"))
      .def(
          "execute_tree",
          [](PyClipper64& self, cl::ClipType clip_type, cl::FillRule fill_rule) {
            ExecGuard guard(self.state, "Clipper64");
            std::unique_ptr<cl::PolyTree64> tree(new cl::PolyTree64());
            cl::Paths64 open;
            const bool ok =
                without_gil([&] { return self.Execute(clip_type, fill_rule, *tree, open); });
            guard.rethrow_pending();
            if (!ok) raise_execute_failed();
            return py::make_tuple(py::cast(std::move(tree)), from_paths(open));
          },
          py::arg("clip_type"), py::arg("fill_rule"));

  py::class_<PyClipperD> cd(m, "ClipperD", py::module_local());
  add_clipper_base(m, cd, "ClipperD");
  // precision goes through the same rule as every other one: a bool or a float is a
  // TypeError, as it is for the free functions.
  cd.def(py::init([](const py::object& precision) {
           return new PyClipperD(precision_arg(precision, 2));
         }),
         py::arg("precision") = 2)
      .def(
          "add_subject",
          [](PyClipperD& self, const Geometry& subjects) {
            check_idle(self.state, "ClipperD");
            self.AddSubject(to_paths<double>(subjects));
          },
          py::arg("subjects"))
      .def(
          "add_open_subject",
          [](PyClipperD& self, const Geometry& open_subjects) {
            check_idle(self.state, "ClipperD");
            self.AddOpenSubject(to_paths<double>(open_subjects));
          },
          py::arg("open_subjects"))
      .def(
          "add_clip",
          [](PyClipperD& self, const Geometry& clips) {
            check_idle(self.state, "ClipperD");
            self.AddClip(to_paths<double>(clips));
          },
          py::arg("clips"))
      .def(
          "execute",
          [](PyClipperD& self, cl::ClipType clip_type, cl::FillRule fill_rule) {
            ExecGuard guard(self.state, "ClipperD");
            cl::PathsD closed, open;
            const bool ok =
                without_gil([&] { return self.Execute(clip_type, fill_rule, closed, open); });
            guard.rethrow_pending();
            if (!ok) raise_execute_failed();
            return py::make_tuple(from_paths(closed), from_paths(open));
          },
          py::arg("clip_type"), py::arg("fill_rule"))
      .def(
          "execute_tree",
          [](PyClipperD& self, cl::ClipType clip_type, cl::FillRule fill_rule) {
            ExecGuard guard(self.state, "ClipperD");
            std::unique_ptr<cl::PolyTreeD> tree(new cl::PolyTreeD());
            cl::PathsD open;
            const bool ok =
                without_gil([&] { return self.Execute(clip_type, fill_rule, *tree, open); });
            guard.rethrow_pending();
            if (!ok) raise_execute_failed();
            return py::make_tuple(py::cast(std::move(tree)), from_paths(open));
          },
          py::arg("clip_type"), py::arg("fill_rule"));

#ifdef USINGZ
  c64.def(
      "set_z_callback",
      [](PyClipper64& self, const py::object& callback) {
        check_idle(self.state, "Clipper64");
        set_z_callback<int64_t, cl::ZCallback64>(
            callback, self.state, [&self](cl::ZCallback64 cb) { self.SetZCallback(std::move(cb)); });
      },
      py::arg("callback"));
  cd.def(
      "set_z_callback",
      [](PyClipperD& self, const py::object& callback) {
        check_idle(self.state, "ClipperD");
        set_z_callback<double, cl::ZCallbackD>(
            callback, self.state, [&self](cl::ZCallbackD cb) { self.SetZCallback(std::move(cb)); });
      },
      py::arg("callback"));
#endif
}
