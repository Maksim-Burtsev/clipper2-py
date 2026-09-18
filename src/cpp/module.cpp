// The extension module. Built twice from the same sources: _clipper2 and, with USINGZ,
// _clipper2z. Types whose layout depends on USINGZ are module-local; the rest is registered
// once in _clipper2 and re-exported here, so that clipper2.FillRule is clipper2.z.FillRule.

#include <exception>

#include <pybind11/pybind11.h>

#include "clipper2/clipper.core.h"
#include "clipper2/clipper.version.h"

namespace py = pybind11;
namespace cl = Clipper2Lib;

void bind_shared_types(py::module_&);
const char* const* shared_type_names();
void bind_core(py::module_&);
void bind_engine(py::module_&);
void bind_offset(py::module_&);
void bind_misc(py::module_&);

#ifdef USINGZ
namespace {

// Borrowed from _clipper2 and kept for the module's lifetime; the translator below is a
// plain function pointer, so it cannot capture it.
PyObject* g_clipper2_error = nullptr;

void translate_clipper2_exception(std::exception_ptr p) {
  try {
    if (p) std::rethrow_exception(p);
  } catch (const cl::Clipper2Exception& e) {
    PyErr_SetString(g_clipper2_error, e.what());
  }
}

}  // namespace
#endif

PYBIND11_MODULE(CLIPPER2_PY_MODULE_NAME, m) {
  m.doc() = "Python bindings for the Clipper2 C++ library.";

#ifdef USINGZ
  py::module_ base = py::module_::import("clipper2._clipper2");
  for (const char* const* name = shared_type_names(); *name != nullptr; ++name)
    m.attr(*name) = base.attr(*name);
  g_clipper2_error = py::object(base.attr("Clipper2Error")).release().ptr();
  py::register_exception_translator(&translate_clipper2_exception);
#else
  bind_shared_types(m);
#endif

  bind_core(m);
  bind_engine(m);
  bind_offset(m);
  bind_misc(m);
}
