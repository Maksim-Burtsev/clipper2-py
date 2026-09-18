// Conversion layer: Python sequences / numpy arrays <-> Clipper2 points, paths and paths-of-paths.
//
// Family (64 vs D) is inferred from the dtype numpy.asarray would give the input
// (spec decision 4); validation that C++ gets from its compiler is done here (decision 5).

#ifndef CLIPPER2_PY_CONVERT_H
#define CLIPPER2_PY_CONVERT_H

#include <cstdint>
#include <initializer_list>
#include <limits>
#include <string>
#include <type_traits>
#include <utility>

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include "clipper2/clipper.core.h"

namespace py = pybind11;
namespace cl = Clipper2Lib;

namespace clipper2_py {

#ifdef USINGZ
// Point64::z and PointD::z are both z_type == int64_t, so a D point's z is an integer
// value carried in a float64 column (and truncated on the way in, as MakePathZD does).
inline constexpr py::ssize_t kPointLen = 3;
#else
inline constexpr py::ssize_t kPointLen = 2;
#endif

enum class Family { Empty, Int64, Double };

// --- numpy plumbing -------------------------------------------------------------------

// The handles are leaked on purpose: they must stay valid for the module's whole life.
inline py::handle np_function(const char* name) {
  return py::object(py::module_::import("numpy").attr(name)).release();
}

inline py::handle np_asarray_fn() {
  static const py::handle fn = np_function("asarray");
  return fn;
}

inline py::handle np_ascontiguousarray_fn() {
  static const py::handle fn = np_function("ascontiguousarray");
  return fn;
}

[[noreturn]] inline void raise_overflow(const char* what) {
  PyErr_SetString(PyExc_OverflowError, what);
  throw py::error_already_set();
}

inline std::string dtype_name(const py::array& a) { return py::str(a.dtype()).cast<std::string>(); }

// --- family detection -----------------------------------------------------------------

inline Family combine(Family a, Family b) {
  if (a == Family::Empty) return b;
  if (b == Family::Empty) return a;
  return (a == Family::Double || b == Family::Double) ? Family::Double : Family::Int64;
}

// Paths are the deepest thing any argument can be, so recursion stops there: without a
// limit, a self-referential sequence would recurse until the C stack runs out.
inline constexpr int kMaxNesting = 3;

// The family numpy.asarray would infer for a point / path / paths argument.
// An input without values (spec: "an empty input has no dtype") is Family::Empty.
inline Family family_of(py::handle obj, int depth = 0) {
  if (depth > kMaxNesting)
    throw py::value_error("input nested deeper than paths: expected a point, a path or paths");
  // Python scalars first: an int too large for numpy still belongs to the 64 family
  // (it is the conversion that then reports the overflow).
  if (py::isinstance<py::bool_>(obj)) throw py::type_error("coordinates must be integer or float, got bool");
  if (py::isinstance<py::int_>(obj)) return Family::Int64;
  if (py::isinstance<py::float_>(obj)) return Family::Double;

  py::object arr;
  bool inhomogeneous = false;
  try {
    arr = np_asarray_fn()(obj);
  } catch (py::error_already_set& e) {
    // Paths of different lengths are legal input but not a rectangular array.
    if (!e.matches(PyExc_ValueError)) throw;
    inhomogeneous = true;
  }
  if (!inhomogeneous) {
    py::array a(arr);
    // A sequence without values has no dtype (numpy calls it float64), so look inside it:
    // `[]` is Empty, `[np.empty((0, 2))]` is Double. An ndarray keeps the dtype it was given.
    if (a.size() != 0 || py::isinstance<py::array>(obj)) {
      const char kind = a.dtype().kind();
      if (kind == 'i' || kind == 'u') return Family::Int64;
      if (kind == 'f') return Family::Double;
      if (kind != 'O')
        throw py::type_error("coordinates must be of integer or float dtype, got " + dtype_name(a));
    }
  }
  Family fam = Family::Empty;
  for (py::handle item : py::reinterpret_borrow<py::object>(obj))
    fam = combine(fam, family_of(item, depth + 1));
  return fam;
}

// Nesting depth: 1 == point, 2 == path, 3 == paths. Used where C++ picks an overload
// by static type (GetBounds, Area, RamerDouglasPeucker).
inline int nesting_depth(py::handle obj, int depth = 0) {
  if (py::isinstance<py::array>(obj)) return static_cast<int>(py::array(py::reinterpret_borrow<py::object>(obj)).ndim());
  if (py::isinstance<py::str>(obj) || py::isinstance<py::bytes>(obj)) return 0;
  if (!PySequence_Check(obj.ptr())) return 0;
  if (depth > kMaxNesting) return depth;  // too deep to be geometry; conversion reports it
  const py::ssize_t n = PySequence_Size(obj.ptr());
  if (n < 0) throw py::error_already_set();
  if (n == 0) return 2;  // an empty sequence cannot be a point: it is an empty path
  py::object first = py::reinterpret_steal<py::object>(PySequence_GetItem(obj.ptr(), 0));
  if (!first) throw py::error_already_set();
  return 1 + nesting_depth(first, depth + 1);
}

// --- scalars --------------------------------------------------------------------------

// int64_t where C++ takes int64_t: a float is a compile error in C++, so a TypeError here.
inline int64_t to_int64(py::handle obj) {
  py::object idx = py::reinterpret_steal<py::object>(PyNumber_Index(obj.ptr()));
  if (!idx) throw py::error_already_set();
  const long long v = PyLong_AsLongLong(idx.ptr());
  if (v == -1 && PyErr_Occurred()) throw py::error_already_set();
  return static_cast<int64_t>(v);
}

inline double to_double(py::handle obj) {
  const double v = PyFloat_AsDouble(obj.ptr());
  if (v == -1.0 && PyErr_Occurred()) throw py::error_already_set();
  return v;
}

// --- input conversion -----------------------------------------------------------------

template <class T>
py::array coerce(py::handle obj) {
  static_assert(std::is_same<T, int64_t>::value || std::is_same<T, double>::value, "");
  py::array a(np_asarray_fn()(obj));
  // A sequence without values has no dtype of its own (numpy calls it float64).
  const char kind = (a.size() == 0 && !py::isinstance<py::array>(obj)) ? '\0' : a.dtype().kind();
  if (std::is_same<T, int64_t>::value) {
    if (kind == 'f')
      throw py::type_error("the 64 family takes integer coordinates, got " + dtype_name(a));
    if (kind != '\0' && kind != 'i' && kind != 'u' && kind != 'O')
      throw py::type_error("coordinates must be of integer or float dtype, got " + dtype_name(a));
    // numpy would wrap uint64 values above INT64_MAX silently.
    if (kind == 'u' && a.dtype().itemsize() == 8 &&
        py::cast<uint64_t>(a.attr("max")()) > static_cast<uint64_t>(INT64_MAX))
      raise_overflow("coordinate does not fit in int64");
  } else if (kind != '\0' && kind != 'f' && kind != 'i' && kind != 'u' && kind != 'O') {
    throw py::type_error("coordinates must be of integer or float dtype, got " + dtype_name(a));
  }
  // An object array is what numpy makes of ints that do not fit int64; converting it
  // raises OverflowError. Anything that survives the conversion but is not equal to the
  // input (a float in an object array) would be a silent truncation.
  py::array out(np_ascontiguousarray_fn()(a, py::dtype::of<T>()));
  if (kind == 'O' && std::is_same<T, int64_t>::value &&
      !py::cast<bool>(out.attr("__eq__")(a).attr("all")()))
    throw py::type_error("the 64 family takes integer coordinates, got " + dtype_name(a));
  return out;
}

template <class T>
cl::Path<T> to_path(py::handle obj) {
  py::array a = coerce<T>(obj);
  if (a.ndim() == 1 && a.size() == 0) return cl::Path<T>();  // `[]` is an empty path
  const char* expected =
      kPointLen == 3 ? "expected a sequence of (x, y[, z]) points or an N*2 / N*3 array"
                     : "expected a sequence of (x, y) points or an N*2 array";
  if (a.ndim() != 2) throw py::value_error(expected);
  const py::ssize_t cols = a.shape(1);
  if (cols != 2 && cols != kPointLen) throw py::value_error(expected);

  const py::ssize_t n = a.shape(0);
  const T* d = static_cast<const T*>(a.data());
  cl::Path<T> out;
  out.reserve(static_cast<size_t>(n));
  for (py::ssize_t i = 0; i < n; ++i) {
#ifdef USINGZ
    out.emplace_back(d[i * cols], d[i * cols + 1],
                     cols == 3 ? static_cast<cl::z_type>(d[i * cols + 2]) : cl::z_type(0));
#else
    out.emplace_back(d[i * cols], d[i * cols + 1]);
#endif
  }
  return out;
}

template <class T>
cl::Paths<T> to_paths(py::handle obj) {
  // Element by element: paths of different lengths are not a rectangular array.
  cl::Paths<T> out;
  for (py::handle item : py::reinterpret_borrow<py::object>(obj)) out.push_back(to_path<T>(item));
  return out;
}

template <class T>
cl::Point<T> to_point(py::handle obj) {
  py::array a = coerce<T>(obj);
  const py::ssize_t n = a.ndim() == 1 ? a.shape(0) : -1;
  if (n != 2 && n != kPointLen)
    throw py::value_error(kPointLen == 3 ? "expected a point (x, y) or (x, y, z)"
                                         : "expected a point (x, y)");
  const T* d = static_cast<const T*>(a.data());
#ifdef USINGZ
  return cl::Point<T>(d[0], d[1], n == 3 ? static_cast<cl::z_type>(d[2]) : cl::z_type(0));
#else
  return cl::Point<T>(d[0], d[1]);
#endif
}

// --- output conversion ----------------------------------------------------------------

template <class T>
py::object from_point(const cl::Point<T>& pt) {
#ifdef USINGZ
  return py::make_tuple(pt.x, pt.y, pt.z);
#else
  return py::make_tuple(pt.x, pt.y);
#endif
}

template <class T>
py::array from_path(const cl::Path<T>& path) {
  py::array_t<T> out({static_cast<py::ssize_t>(path.size()), kPointLen});
  T* d = out.mutable_data();
  for (size_t i = 0; i < path.size(); ++i) {
    d[i * kPointLen] = path[i].x;
    d[i * kPointLen + 1] = path[i].y;
#ifdef USINGZ
    d[i * kPointLen + 2] = static_cast<T>(path[i].z);
#endif
  }
  return out;
}

// For call sites that are generic over "a path or paths" (see bind_core.cpp).
template <class T>
py::object from_geometry(const cl::Path<T>& path) {
  return from_path(path);
}

template <class T>
py::list from_paths(const cl::Paths<T>& paths) {
  py::list out(paths.size());
  for (size_t i = 0; i < paths.size(); ++i) out[i] = from_path(paths[i]);
  return out;
}

template <class T>
py::object from_geometry(const cl::Paths<T>& paths) {
  return from_paths(paths);
}

#ifdef USINGZ
// Upstream's callback writes pt.z by reference; in Python the callback returns it.
// Shared by Clipper64 / ClipperD (bind_engine.cpp) and ClipperOffset (bind_offset.cpp).
template <class T, class Callback, class Setter>
void set_z_callback(const py::object& fn, Setter&& setter) {
  if (fn.is_none()) {
    setter(Callback(nullptr));
    return;
  }
  setter(Callback([fn](const cl::Point<T>& e1bot, const cl::Point<T>& e1top,
                       const cl::Point<T>& e2bot, const cl::Point<T>& e2top, cl::Point<T>& pt) {
    py::gil_scoped_acquire gil;
    py::object z = fn(from_point(e1bot), from_point(e1top), from_point(e2bot), from_point(e2top),
                      from_point(pt));
    pt.z = to_int64(z);
  }));
}
#endif

// --- dispatch -------------------------------------------------------------------------

// Runs f64() or fd() depending on the family of the geometry arguments (spec decision 4).
template <class F64, class FD>
py::object dispatch(std::initializer_list<py::handle> geometry, F64&& f64, FD&& fd) {
  Family fam = Family::Empty;
  for (py::handle h : geometry) {
    const Family f = family_of(h);
    if (f == Family::Empty) continue;
    if (fam != Family::Empty && f != fam)
      throw py::type_error(
          "integer and float coordinates in one call: every point and path argument must "
          "be of the same family");
    fam = f;
  }
  return fam == Family::Double ? fd() : f64();
}

template <class F>
auto without_gil(F&& f) -> decltype(f()) {
  py::gil_scoped_release release;
  return f();
}

// pybind11 lets a py::module_local() class be loaded from another module as long as the C++
// type name matches. _clipper2 and _clipper2z have different Point layouts, so accepting the
// other module's object would reinterpret its memory: check the Python type first.
template <class T>
const T& cast_local(const py::module_& m, const char* name, const py::handle& obj) {
  if (!py::isinstance(obj, m.attr(name)))
    throw py::type_error(std::string("expected a ") + py::cast<std::string>(m.attr("__name__")) +
                         "." + name);
  return py::cast<const T&>(obj);
}

// D-family functions keep upstream's precision argument; the 64 family has none.
inline void reject_precision(const py::object& precision, const char* name, const char* arg) {
  if (!precision.is_none())
    throw py::type_error(std::string(name) + "() takes no '" + arg + "' for the 64 family");
}

inline int precision_arg(const py::object& precision, int fallback) {
  if (precision.is_none()) return fallback;
  if (py::isinstance<py::bool_>(precision)) throw py::type_error("precision must be an int, got bool");
  const int64_t value = to_int64(precision);  // a float is a TypeError, as in C++
  if (value < (std::numeric_limits<int>::min)() || value > (std::numeric_limits<int>::max)())
    raise_overflow("precision does not fit in an int");
  return static_cast<int>(value);
}

}  // namespace clipper2_py

#endif  // CLIPPER2_PY_CONVERT_H
