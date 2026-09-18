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

template <class C>
void add_clipper_base(const py::module_& m, py::class_<C>& c) {
  c.def_property("preserve_collinear",
                 static_cast<bool (cl::ClipperBase::*)() const>(&cl::ClipperBase::PreserveCollinear),
                 static_cast<void (cl::ClipperBase::*)(bool)>(&cl::ClipperBase::PreserveCollinear))
      .def_property("reverse_solution",
                    static_cast<bool (cl::ClipperBase::*)() const>(&cl::ClipperBase::ReverseSolution),
                    static_cast<void (cl::ClipperBase::*)(bool)>(&cl::ClipperBase::ReverseSolution))
      .def_property_readonly("error_code", &cl::ClipperBase::ErrorCode)
      .def("clear", &cl::ClipperBase::Clear)
      .def(
          "add_reuseable_data",
          [m](C& self, const py::object& reuseable_data) {
            self.AddReuseableData(cast_local<cl::ReuseableDataContainer64>(
                m, "ReuseableDataContainer64", reuseable_data));
          },
          py::arg("reuseable_data"));
#ifdef USINGZ
  c.def_readwrite("default_z", &cl::ClipperBase::DefaultZ);
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
          [](cl::ReuseableDataContainer64& self, const py::object& paths, cl::PathType polytype,
             bool is_open) { self.AddPaths(to_paths<int64_t>(paths), polytype, is_open); },
          py::arg("paths"), py::arg("polytype"), py::arg("is_open"));

  bind_polypath<cl::PolyPath64>(m, "PolyPath64");
  bind_polypath<cl::PolyPathD>(m, "PolyPathD").def_property_readonly("scale", &cl::PolyPathD::Scale);
  m.attr("PolyTree64") = m.attr("PolyPath64");  // upstream: using PolyTree64 = PolyPath64
  m.attr("PolyTreeD") = m.attr("PolyPathD");

  py::class_<cl::Clipper64> c64(m, "Clipper64", py::module_local());
  add_clipper_base(m, c64);
  c64.def(py::init<>())
      .def(
          "add_subject",
          [](cl::Clipper64& self, const py::object& subjects) {
            self.AddSubject(to_paths<int64_t>(subjects));
          },
          py::arg("subjects"))
      .def(
          "add_open_subject",
          [](cl::Clipper64& self, const py::object& open_subjects) {
            self.AddOpenSubject(to_paths<int64_t>(open_subjects));
          },
          py::arg("open_subjects"))
      .def(
          "add_clip",
          [](cl::Clipper64& self, const py::object& clips) {
            self.AddClip(to_paths<int64_t>(clips));
          },
          py::arg("clips"))
      .def(
          "execute",
          [](cl::Clipper64& self, cl::ClipType clip_type, cl::FillRule fill_rule) {
            cl::Paths64 closed, open;
            if (!without_gil([&] { return self.Execute(clip_type, fill_rule, closed, open); }))
              raise_execute_failed();
            return py::make_tuple(from_paths(closed), from_paths(open));
          },
          py::arg("clip_type"), py::arg("fill_rule"))
      .def(
          "execute_tree",
          [](cl::Clipper64& self, cl::ClipType clip_type, cl::FillRule fill_rule) {
            std::unique_ptr<cl::PolyTree64> tree(new cl::PolyTree64());
            cl::Paths64 open;
            if (!without_gil([&] { return self.Execute(clip_type, fill_rule, *tree, open); }))
              raise_execute_failed();
            return py::make_tuple(py::cast(std::move(tree)), from_paths(open));
          },
          py::arg("clip_type"), py::arg("fill_rule"));

  py::class_<cl::ClipperD> cd(m, "ClipperD", py::module_local());
  add_clipper_base(m, cd);
  cd.def(py::init<int>(), py::arg("precision") = 2)
      .def(
          "add_subject",
          [](cl::ClipperD& self, const py::object& subjects) {
            self.AddSubject(to_paths<double>(subjects));
          },
          py::arg("subjects"))
      .def(
          "add_open_subject",
          [](cl::ClipperD& self, const py::object& open_subjects) {
            self.AddOpenSubject(to_paths<double>(open_subjects));
          },
          py::arg("open_subjects"))
      .def(
          "add_clip",
          [](cl::ClipperD& self, const py::object& clips) {
            self.AddClip(to_paths<double>(clips));
          },
          py::arg("clips"))
      .def(
          "execute",
          [](cl::ClipperD& self, cl::ClipType clip_type, cl::FillRule fill_rule) {
            cl::PathsD closed, open;
            if (!without_gil([&] { return self.Execute(clip_type, fill_rule, closed, open); }))
              raise_execute_failed();
            return py::make_tuple(from_paths(closed), from_paths(open));
          },
          py::arg("clip_type"), py::arg("fill_rule"))
      .def(
          "execute_tree",
          [](cl::ClipperD& self, cl::ClipType clip_type, cl::FillRule fill_rule) {
            std::unique_ptr<cl::PolyTreeD> tree(new cl::PolyTreeD());
            cl::PathsD open;
            if (!without_gil([&] { return self.Execute(clip_type, fill_rule, *tree, open); }))
              raise_execute_failed();
            return py::make_tuple(py::cast(std::move(tree)), from_paths(open));
          },
          py::arg("clip_type"), py::arg("fill_rule"));

#ifdef USINGZ
  c64.def(
      "set_z_callback",
      [](cl::Clipper64& self, const py::object& callback) {
        set_z_callback<int64_t, cl::ZCallback64>(
            callback, [&self](cl::ZCallback64 cb) { self.SetZCallback(std::move(cb)); });
      },
      py::arg("callback"));
  cd.def(
      "set_z_callback",
      [](cl::ClipperD& self, const py::object& callback) {
        set_z_callback<double, cl::ZCallbackD>(
            callback, [&self](cl::ZCallbackD cb) { self.SetZCallback(std::move(cb)); });
      },
      py::arg("callback"));
#endif
}
