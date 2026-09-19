// Conversion layer: Python sequences / numpy arrays <-> Clipper2 points, paths and paths-of-paths.
//
// Family (64 vs D) is inferred from the dtype numpy.asarray would give the input
// (spec decision 4); validation that C++ gets from its compiler is done here (decision 5).

#ifndef CLIPPER2_PY_CONVERT_H
#define CLIPPER2_PY_CONVERT_H

#include <atomic>
#include <cmath>
#include <cstdint>
#include <exception>
#include <initializer_list>
#include <limits>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

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

inline int nesting_depth(py::handle obj, int depth = 0);

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

  // A list of paths is walked path by path: paths of different lengths are legal input but
  // not a rectangular array (numpy < 1.24 warns about them, later ones raise).
  if (py::isinstance<py::array>(obj) || nesting_depth(obj) <= 2) {
    py::array a(np_asarray_fn()(obj));
    // A sequence without values has no dtype (numpy calls it float64): `[]` is Empty.
    // An ndarray keeps the dtype it was given even when it is empty.
    if (a.size() == 0 && !py::isinstance<py::array>(obj)) return Family::Empty;
    const char kind = a.dtype().kind();
    if (kind == 'i' || kind == 'u') return Family::Int64;
    if (kind == 'f') return Family::Double;
    if (kind != 'O')
      throw py::type_error("coordinates must be of integer or float dtype, got " + dtype_name(a));
  }
  Family fam = Family::Empty;
  for (py::handle item : py::reinterpret_borrow<py::object>(obj))
    fam = combine(fam, family_of(item, depth + 1));
  return fam;
}

// Nesting depth: 1 == point, 2 == path, 3 == paths. Used where C++ picks an overload
// by static type (GetBounds, Area, RamerDouglasPeucker).
inline int nesting_depth(py::handle obj, int depth) {
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

// --- geometry arguments ---------------------------------------------------------------

// One walk over a pure-Python point / path / paths argument does three things that all
// need the Python objects themselves rather than the array numpy makes of them:
//
// * generators and other one-shot iterables are materialised, since family detection and
//   the conversion each iterate the argument (a generator would be empty the second time);
// * the family is taken from the objects, so an integer numpy has to promote to float64
//   (anything from 2**63 up) stays in the 64 family and is reported as an OverflowError;
// * a bool is refused as a coordinate wherever it appears.
//
// `hinted` goes false where numpy knows better -- an ndarray of an exotic dtype, a string,
// anything that is not a number -- and the caller falls back to asarray, as before.
inline py::object scan_geometry(py::handle obj, int depth, Family& fam, bool& hinted,
                                bool& overflow) {
  py::object self = py::reinterpret_borrow<py::object>(obj);
  if (depth > kMaxNesting) {  // too deep to be geometry; family_of reports it
    hinted = false;
    return self;
  }
  if (py::isinstance<py::bool_>(obj))
    throw py::type_error("coordinates must be integer or float, got bool");
  if (py::isinstance<py::int_>(obj)) {
    fam = combine(fam, Family::Int64);
    const long long value = PyLong_AsLongLong(obj.ptr());
    if (value == -1 && PyErr_Occurred()) {
      if (!PyErr_ExceptionMatches(PyExc_OverflowError)) throw py::error_already_set();
      PyErr_Clear();
      overflow = true;
    }
    return self;
  }
  if (py::isinstance<py::float_>(obj)) {
    fam = combine(fam, Family::Double);
    return self;
  }
  if (py::isinstance<py::array>(obj)) {
    const char kind = py::array(self).dtype().kind();
    if (kind == 'i' || kind == 'u')
      fam = combine(fam, Family::Int64);
    else if (kind == 'f')
      fam = combine(fam, Family::Double);
    else
      hinted = false;
    return self;
  }
  if (py::isinstance<py::str>(obj) || py::isinstance<py::bytes>(obj)) {
    hinted = false;
    return self;
  }
  if (PySequence_Check(obj.ptr())) {
    const py::ssize_t n = PySequence_Size(obj.ptr());
    if (n < 0) throw py::error_already_set();
    auto item_at = [&](py::ssize_t i) {
      py::object item = py::reinterpret_steal<py::object>(PySequence_GetItem(obj.ptr(), i));
      if (!item) throw py::error_already_set();
      return item;
    };
    py::list copy;  // built only once an element has to be replaced, which is rare
    bool replaced = false;
    for (py::ssize_t i = 0; i < n; ++i) {
      py::object item = item_at(i);
      py::object converted = scan_geometry(item, depth + 1, fam, hinted, overflow);
      if (!replaced && !converted.is(item)) {
        replaced = true;
        for (py::ssize_t j = 0; j < i; ++j) copy.append(item_at(j));
      }
      if (replaced) copy.append(converted);
    }
    return replaced ? py::object(std::move(copy)) : self;
  }
  py::object iterator = py::reinterpret_steal<py::object>(PyObject_GetIter(obj.ptr()));
  if (!iterator) {  // not a number and not iterable: let numpy have its say
    PyErr_Clear();
    hinted = false;
    return self;
  }
  py::list out;
  for (py::handle item : iterator) out.append(scan_geometry(item, depth + 1, fam, hinted, overflow));
  return out;
}

// A point / path / paths argument, scanned once on the way in (see scan_geometry).
class Geometry {
 public:
  Geometry() = default;
  explicit Geometry(py::handle obj) { obj_ = scan_geometry(obj, 0, hint_, hinted_, overflow_); }

  operator py::handle() const { return obj_; }
  const py::object& obj() const { return obj_; }
  bool hinted() const { return hinted_; }
  Family hint() const { return hint_; }
  // An integer in the argument that does not fit int64: only the 64 family cares.
  bool overflows_int64() const { return overflow_; }

 private:
  py::object obj_;
  Family hint_ = Family::Empty;
  bool hinted_ = true;
  bool overflow_ = false;
};

inline Family family_of(const Geometry& g) { return g.hinted() ? g.hint() : family_of(g.obj()); }

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
    // numpy would wrap uint64 values above INT64_MAX silently (max() needs a value).
    if (kind == 'u' && a.dtype().itemsize() == 8 && a.size() != 0 &&
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

#ifdef USINGZ
// z is int64_t upstream in both families, so in D it arrives in the float64 column: a
// value C++ would static_cast (undefined for nan/inf and out of range) is refused here.
inline cl::z_type to_z(double value) {
  if (!std::isfinite(value)) throw py::value_error("z must be a finite number");
  if (!(value >= -9223372036854775808.0 && value < 9223372036854775808.0))
    raise_overflow("z does not fit in int64");
  return static_cast<cl::z_type>(value);  // truncates towards zero, as MakePathZD does
}

inline cl::z_type to_z(int64_t value) { return static_cast<cl::z_type>(value); }
#endif

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
                     cols == 3 ? to_z(d[i * cols + 2]) : cl::z_type(0));
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
  return cl::Point<T>(d[0], d[1], n == 3 ? to_z(d[2]) : cl::z_type(0));
#else
  return cl::Point<T>(d[0], d[1]);
#endif
}

// Every conversion of a whole argument goes through one of these, so an integer outside
// int64 is reported wherever the 64 family runs -- free function or class method.
template <class T>
void check_int64_range(const Geometry& g) {
  if (std::is_same<T, int64_t>::value && g.overflows_int64())
    raise_overflow("coordinate does not fit in int64");
}

template <class T>
py::array coerce(const Geometry& g) {
  check_int64_range<T>(g);
  return coerce<T>(g.obj());
}

template <class T>
cl::Path<T> to_path(const Geometry& g) {
  check_int64_range<T>(g);
  return to_path<T>(g.obj());
}

template <class T>
cl::Paths<T> to_paths(const Geometry& g) {
  check_int64_range<T>(g);
  return to_paths<T>(g.obj());
}

template <class T>
cl::Point<T> to_point(const Geometry& g) {
  check_int64_range<T>(g);
  return to_point<T>(g.obj());
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

// --- state a Python-driven clipper needs on top of upstream's ---------------------------

// Upstream's Execute runs Python code (the z and delta callbacks) and keeps raw pointers
// into what was added to it, two things a C++ caller cannot do wrong. Every class that
// executes -- Clipper64, ClipperD, ClipperOffset -- is bound through a small derived
// holder carrying this, so the extra state lives and dies with the object.
struct ExecState {
  // Set while Execute runs. Any other call that would mutate or execute the same object,
  // from a callback or from another thread, is refused: in C++ it is undefined behaviour.
  std::atomic<bool> executing{false};
  // The first exception a Python callback raised during this Execute. It is not allowed
  // to unwind through upstream (which would leak the memory Execute frees on its way
  // out); the binding re-raises it once Execute has returned.
  std::exception_ptr callback_error;
  // Containers handed to add_reuseable_data: upstream keeps raw Vertex pointers into them.
  std::vector<py::object> kept;

  // Only the thread inside Execute stores, and it holds the GIL while it does.
  void store_error() {
    if (!callback_error) callback_error = std::current_exception();
  }
  bool failed() const { return callback_error != nullptr; }
};

[[noreturn]] inline void raise_executing(const char* class_name) {
  throw std::runtime_error(std::string(class_name) + " is executing");
}

// Every method that mutates or executes the object starts here.
inline void check_idle(const ExecState& state, const char* class_name) {
  if (state.executing.load(std::memory_order_acquire)) raise_executing(class_name);
}

// Holds `executing` for one Execute and makes sure nothing outlives it.
class ExecGuard {
 public:
  ExecGuard(ExecState& state, const char* class_name) : state_(state) {
    bool idle = false;
    if (!state.executing.compare_exchange_strong(idle, true, std::memory_order_acq_rel))
      raise_executing(class_name);
    state.callback_error = nullptr;
  }
  ExecGuard(const ExecGuard&) = delete;
  ExecGuard& operator=(const ExecGuard&) = delete;
  // The GIL is held here, as it is in the callback that stored the exception.
  ~ExecGuard() {
    state_.callback_error = nullptr;
    state_.executing.store(false, std::memory_order_release);
  }

  // Called once Execute has returned and done its own clean-up.
  void rethrow_pending() const {
    if (state_.callback_error) std::rethrow_exception(state_.callback_error);
  }

 private:
  ExecState& state_;
};

#ifdef USINGZ
// Upstream's callback writes pt.z by reference; in Python the callback returns it.
// Shared by Clipper64 / ClipperD (bind_engine.cpp) and ClipperOffset (bind_offset.cpp).
// `state` belongs to the object that owns the std::function, so it cannot dangle.
template <class T, class Callback, class Setter>
void set_z_callback(const py::object& fn, ExecState& state, Setter&& setter) {
  if (fn.is_none()) {
    setter(Callback(nullptr));
    return;
  }
  setter(Callback([fn, &state](const cl::Point<T>& e1bot, const cl::Point<T>& e1top,
                               const cl::Point<T>& e2bot, const cl::Point<T>& e2top,
                               cl::Point<T>& pt) {
    py::gil_scoped_acquire gil;
    if (state.failed()) return;  // an earlier call raised: leave pt.z as upstream set it
    try {
      pt.z = to_int64(fn(from_point(e1bot), from_point(e1top), from_point(e2bot),
                         from_point(e2top), from_point(pt)));
    } catch (...) {
      state.store_error();
    }
  }));
}
#endif

// --- dispatch -------------------------------------------------------------------------

// Runs f64() or fd() depending on the family of the geometry arguments (spec decision 4).
template <class F64, class FD>
py::object dispatch(std::initializer_list<Geometry> geometry, F64&& f64, FD&& fd) {
  Family fam = Family::Empty;
  for (const Geometry& g : geometry) {
    const Family f = family_of(g);
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

namespace pybind11 {
namespace detail {

// Geometry arguments are plain Python objects, scanned as they are loaded; the name keeps
// pybind11's signatures reading "object", as they do for py::object.
template <>
struct type_caster<clipper2_py::Geometry> {
 public:
  PYBIND11_TYPE_CASTER(clipper2_py::Geometry, const_name("object"));

  bool load(handle src, bool) {
    if (!src) return false;
    value = clipper2_py::Geometry(src);
    return true;
  }
};

}  // namespace detail
}  // namespace pybind11

#endif  // CLIPPER2_PY_CONVERT_H
