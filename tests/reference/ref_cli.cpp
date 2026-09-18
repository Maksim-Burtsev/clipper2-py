/*
 * Reference CLI for the differential test.  It calls the public upstream Clipper2 API
 * exactly the way a C++ user would, so test_differential.py can demand that the Python
 * binding returns the very same numbers.
 *
 * RECORD FORMAT (one record per line, whitespace-separated tokens; blank lines and lines
 * starting with '#' are skipped).
 *   request := <op> <arg>...      int64 and enums in decimal, bool as 0/1,
 *                                 double in any strtod form (the test writes repr()).
 *   path    := <n> x0 y0 x1 y1 ... (2*n coordinates)
 *   paths   := <m> <path>...
 *   tree    := <is_hole> <level> <polygon:path> <child_count> <tree>...   (root included)
 * Replies, one line per request, in order:
 *   "OK" <result>...   results in the same encoding, doubles as %.17g (exact round-trip)
 *   "ERROR <what>"     a Clipper2Exception escaped upstream
 *   "FAILED"           Clipper64/ClipperD::Execute returned false
 *   "EXCEPTION <what>" any other std::exception (a bug here or upstream)
 */

#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>

#include "clipper2/clipper.h"

using namespace Clipper2Lib;

namespace {

// ---------------------------------------------------------------- reading

void ReadNum(std::istream& is, int64_t& v) { is >> v; }

// strtod rather than operator>>: num_get sets failbit on a denormal (strtod's ERANGE),
// and a denormal is a perfectly good double for the test to send.
void ReadNum(std::istream& is, double& v)
{
  std::string token;
  is >> token;
  v = std::strtod(token.c_str(), nullptr);
}

double ReadDouble(std::istream& is)
{
  double v = 0;
  ReadNum(is, v);
  return v;
}

template <typename T>
Path<T> ReadPath(std::istream& is)
{
  size_t n = 0;
  is >> n;
  Path<T> path;
  path.reserve(n);
  for (size_t i = 0; i < n; ++i)
  {
    T x, y;
    ReadNum(is, x);
    ReadNum(is, y);
    path.emplace_back(x, y);
  }
  return path;
}

template <typename T>
Paths<T> ReadPaths(std::istream& is)
{
  size_t m = 0;
  is >> m;
  Paths<T> paths;
  paths.reserve(m);
  for (size_t i = 0; i < m; ++i) paths.emplace_back(ReadPath<T>(is));
  return paths;
}

bool ReadBool(std::istream& is)
{
  int v = 0;
  is >> v;
  return v != 0;
}

template <typename T>
Rect<T> ReadRect(std::istream& is)
{
  T l, t, r, b;
  ReadNum(is, l);
  ReadNum(is, t);
  ReadNum(is, r);
  ReadNum(is, b);
  return Rect<T>(l, t, r, b);
}

// ---------------------------------------------------------------- writing

void WNum(std::ostream& os, int64_t v) { os << ' ' << v; }

void WNum(std::ostream& os, double v)
{
  char buf[40];
  std::snprintf(buf, sizeof(buf), " %.17g", v);
  os << buf;
}

template <typename T>
void WPath(std::ostream& os, const Path<T>& path)
{
  os << ' ' << path.size();
  for (const auto& pt : path) { WNum(os, pt.x); WNum(os, pt.y); }
}

template <typename T>
void WPaths(std::ostream& os, const Paths<T>& paths)
{
  os << ' ' << paths.size();
  for (const auto& path : paths) WPath(os, path);
}

template <typename PolyPathT>
void WTree(std::ostream& os, const PolyPathT& pp)
{
  os << ' ' << (pp.IsHole() ? 1 : 0) << ' ' << pp.Level();
  WPath(os, pp.Polygon());
  os << ' ' << pp.Count();
  for (size_t i = 0; i < pp.Count(); ++i) WTree(os, *pp.Child(i));
}

// Thrown when Execute() reports failure; the test only checks that Python raises too.
struct ExecuteFailed {};

// ---------------------------------------------------------------- ops

void Run(const std::string& line, std::ostream& os)
{
  std::istringstream is(line);
  std::string op;
  is >> op;

  if (op == "boolean_op64" || op == "boolean_op_tree64")
  {
    int ct, fr;
    is >> ct >> fr;
    Paths64 subj = ReadPaths<int64_t>(is), clip = ReadPaths<int64_t>(is);
    if (op == "boolean_op64")
      WPaths(os, BooleanOp(static_cast<ClipType>(ct), static_cast<FillRule>(fr), subj, clip));
    else
    {
      PolyTree64 tree;
      BooleanOp(static_cast<ClipType>(ct), static_cast<FillRule>(fr), subj, clip, tree);
      WTree(os, tree);
    }
  }
  else if (op == "boolean_opd" || op == "boolean_op_treed")
  {
    int precision, ct, fr;
    is >> precision >> ct >> fr;
    PathsD subj = ReadPaths<double>(is), clip = ReadPaths<double>(is);
    if (op == "boolean_opd")
      WPaths(os, BooleanOp(static_cast<ClipType>(ct), static_cast<FillRule>(fr),
                           subj, clip, precision));
    else
    {
      PolyTreeD tree;
      BooleanOp(static_cast<ClipType>(ct), static_cast<FillRule>(fr),
                subj, clip, tree, precision);
      WTree(os, tree);
    }
  }
  else if (op == "clipper64")
  {
    int ct, fr;
    is >> ct >> fr;
    bool as_tree = ReadBool(is), pc = ReadBool(is), rs = ReadBool(is);
    Paths64 subj = ReadPaths<int64_t>(is);
    Paths64 open_subj = ReadPaths<int64_t>(is);
    Paths64 clip = ReadPaths<int64_t>(is);
    Clipper64 c;
    c.PreserveCollinear(pc);
    c.ReverseSolution(rs);
    c.AddSubject(subj);
    c.AddOpenSubject(open_subj);
    c.AddClip(clip);
    Paths64 open_sol;
    if (as_tree)
    {
      PolyTree64 tree;
      if (!c.Execute(static_cast<ClipType>(ct), static_cast<FillRule>(fr), tree, open_sol))
        throw ExecuteFailed{};
      WTree(os, tree);
    }
    else
    {
      Paths64 closed_sol;
      if (!c.Execute(static_cast<ClipType>(ct), static_cast<FillRule>(fr), closed_sol, open_sol))
        throw ExecuteFailed{};
      WPaths(os, closed_sol);
    }
    WPaths(os, open_sol);
  }
  else if (op == "clipperd")
  {
    int precision, ct, fr;
    is >> precision >> ct >> fr;
    bool as_tree = ReadBool(is), pc = ReadBool(is), rs = ReadBool(is);
    PathsD subj = ReadPaths<double>(is);
    PathsD open_subj = ReadPaths<double>(is);
    PathsD clip = ReadPaths<double>(is);
    ClipperD c(precision);
    c.PreserveCollinear(pc);
    c.ReverseSolution(rs);
    c.AddSubject(subj);
    c.AddOpenSubject(open_subj);
    c.AddClip(clip);
    PathsD open_sol;
    if (as_tree)
    {
      PolyTreeD tree;
      if (!c.Execute(static_cast<ClipType>(ct), static_cast<FillRule>(fr), tree, open_sol))
        throw ExecuteFailed{};
      WTree(os, tree);
    }
    else
    {
      PathsD closed_sol;
      if (!c.Execute(static_cast<ClipType>(ct), static_cast<FillRule>(fr), closed_sol, open_sol))
        throw ExecuteFailed{};
      WPaths(os, closed_sol);
    }
    WPaths(os, open_sol);
  }
  else if (op == "inflate64")
  {
    int jt, et;
    double delta = ReadDouble(is);
    is >> jt >> et;
    double miter_limit = ReadDouble(is), arc_tolerance = ReadDouble(is);
    Paths64 paths = ReadPaths<int64_t>(is);
    WPaths(os, InflatePaths(paths, delta, static_cast<JoinType>(jt),
                            static_cast<EndType>(et), miter_limit, arc_tolerance));
  }
  else if (op == "inflated")
  {
    int jt, et, precision;
    double delta = ReadDouble(is);
    is >> jt >> et;
    double miter_limit = ReadDouble(is);
    is >> precision;
    double arc_tolerance = ReadDouble(is);
    PathsD paths = ReadPaths<double>(is);
    WPaths(os, InflatePaths(paths, delta, static_cast<JoinType>(jt),
                            static_cast<EndType>(et), miter_limit, precision, arc_tolerance));
  }
  else if (op == "offset64")
  {
    size_t group_count;
    double miter_limit = ReadDouble(is), arc_tolerance = ReadDouble(is);
    bool pc = ReadBool(is), rs = ReadBool(is);
    double delta = ReadDouble(is);
    bool as_tree = ReadBool(is);
    is >> group_count;
    ClipperOffset co(miter_limit, arc_tolerance, pc, rs);
    for (size_t i = 0; i < group_count; ++i)
    {
      int jt, et;
      is >> jt >> et;
      Paths64 paths = ReadPaths<int64_t>(is);
      co.AddPaths(paths, static_cast<JoinType>(jt), static_cast<EndType>(et));
    }
    if (as_tree)
    {
      PolyTree64 tree;
      co.Execute(delta, tree);
      WTree(os, tree);
    }
    else
    {
      Paths64 solution;
      co.Execute(delta, solution);
      WPaths(os, solution);
    }
  }
  else if (op == "rect_clip64" || op == "rect_clip_lines64")
  {
    Rect64 rect = ReadRect<int64_t>(is);
    Paths64 paths = ReadPaths<int64_t>(is);
    WPaths(os, op == "rect_clip64" ? RectClip(rect, paths) : RectClipLines(rect, paths));
  }
  else if (op == "rect_clipd" || op == "rect_clip_linesd")
  {
    int precision;
    is >> precision;
    RectD rect = ReadRect<double>(is);
    PathsD paths = ReadPaths<double>(is);
    WPaths(os, op == "rect_clipd" ? RectClip(rect, paths, precision)
                                  : RectClipLines(rect, paths, precision));
  }
  else if (op == "minkowski_sum64" || op == "minkowski_diff64")
  {
    bool is_closed = ReadBool(is);
    Path64 pattern = ReadPath<int64_t>(is), path = ReadPath<int64_t>(is);
    WPaths(os, op == "minkowski_sum64" ? MinkowskiSum(pattern, path, is_closed)
                                       : MinkowskiDiff(pattern, path, is_closed));
  }
  else if (op == "minkowski_sumd" || op == "minkowski_diffd")
  {
    int decimal_places;
    is >> decimal_places;
    bool is_closed = ReadBool(is);
    PathD pattern = ReadPath<double>(is), path = ReadPath<double>(is);
    WPaths(os, op == "minkowski_sumd"
                   ? MinkowskiSum(pattern, path, is_closed, decimal_places)
                   : MinkowskiDiff(pattern, path, is_closed, decimal_places));
  }
  else if (op == "triangulate64")
  {
    bool use_delaunay = ReadBool(is);
    Paths64 paths = ReadPaths<int64_t>(is);
    Paths64 solution;
    TriangulateResult result = Triangulate(paths, solution, use_delaunay);
    os << ' ' << static_cast<int>(result);
    WPaths(os, solution);
  }
  else if (op == "triangulated")
  {
    int decimal_places;
    is >> decimal_places;
    bool use_delaunay = ReadBool(is);
    PathsD paths = ReadPaths<double>(is);
    PathsD solution;
    TriangulateResult result = Triangulate(paths, decimal_places, solution, use_delaunay);
    os << ' ' << static_cast<int>(result);
    WPaths(os, solution);
  }
  else if (op == "simplify_paths64")
  {
    double epsilon = ReadDouble(is);
    bool is_closed = ReadBool(is);
    Paths64 paths = ReadPaths<int64_t>(is);
    WPaths(os, SimplifyPaths(paths, epsilon, is_closed));
  }
  else if (op == "simplify_pathsd")
  {
    double epsilon = ReadDouble(is);
    bool is_closed = ReadBool(is);
    PathsD paths = ReadPaths<double>(is);
    WPaths(os, SimplifyPaths(paths, epsilon, is_closed));
  }
  else if (op == "rdp64")
  {
    double epsilon = ReadDouble(is);
    Paths64 paths = ReadPaths<int64_t>(is);
    WPaths(os, RamerDouglasPeucker(paths, epsilon));
  }
  else if (op == "rdpd")
  {
    double epsilon = ReadDouble(is);
    PathsD paths = ReadPaths<double>(is);
    WPaths(os, RamerDouglasPeucker(paths, epsilon));
  }
  else if (op == "trim_collinear64")
  {
    bool is_open = ReadBool(is);
    Path64 path = ReadPath<int64_t>(is);
    WPath(os, TrimCollinear(path, is_open));
  }
  else if (op == "trim_collineard")
  {
    int precision;
    is >> precision;
    bool is_open = ReadBool(is);
    PathD path = ReadPath<double>(is);
    WPath(os, TrimCollinear(path, precision, is_open));
  }
  else if (op == "area64")
  {
    WNum(os, Area(ReadPath<int64_t>(is)));
  }
  else if (op == "aread")
  {
    WNum(os, Area(ReadPath<double>(is)));
  }
  else if (op == "pip64")
  {
    int64_t x, y;
    is >> x >> y;
    Path64 polygon = ReadPath<int64_t>(is);
    os << ' ' << static_cast<int>(PointInPolygon(Point64(x, y), polygon));
  }
  else if (op == "pipd")
  {
    double x = ReadDouble(is), y = ReadDouble(is);
    PathD polygon = ReadPath<double>(is);
    os << ' ' << static_cast<int>(PointInPolygon(PointD(x, y), polygon));
  }
  else
    throw std::runtime_error("unknown op: " + op);

  if (is.fail()) throw std::runtime_error("malformed record: " + line);
}

}  // namespace

int main(int argc, char* argv[])
{
  std::ios_base::sync_with_stdio(false);
  if (argc < 2)
  {
    std::cerr << "usage: ref_cli <input file> [output file]\n";
    return 2;
  }
  std::ifstream in(argv[1]);
  if (!in)
  {
    std::cerr << "ref_cli: cannot read " << argv[1] << '\n';
    return 2;
  }
  std::ofstream file_out;
  if (argc > 2)
  {
    file_out.open(argv[2]);
    if (!file_out)
    {
      std::cerr << "ref_cli: cannot write " << argv[2] << '\n';
      return 2;
    }
  }
  std::ostream& out = (argc > 2) ? static_cast<std::ostream&>(file_out) : std::cout;

  std::string line;
  while (std::getline(in, line))
  {
    if (line.empty() || line[0] == '#') continue;
    std::ostringstream record;
    try
    {
      Run(line, record);
      out << "OK" << record.str() << '\n';
    }
    catch (const Clipper2Exception& e)
    {
      out << "ERROR " << e.what() << '\n';
    }
    catch (const ExecuteFailed&)
    {
      out << "FAILED\n";
    }
    catch (const std::exception& e)
    {
      out << "EXCEPTION " << e.what() << '\n';
    }
    out.flush();  // a reader that times out still learns which record did not return
  }
  return 0;
}
