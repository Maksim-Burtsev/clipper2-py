"""A cross-section of the API, checked by `mypy --strict` in test_stubs.py.

Every `assert_type` here pins a return type the stubs promise; a wrong overload order or
a wrong element dtype in src/clipper2/*.pyi makes mypy fail on this file.
"""

from typing import assert_type

import numpy as np
from numpy.typing import NDArray

import clipper2 as cl
import clipper2.z as clz

SQUARE = [[0, 0], [100, 0], [100, 100], [0, 100]]
SQUARE_D = [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]
DIAMOND = [[50, -50], [150, 50], [50, 150], [-50, 50]]
DIAMOND_D = [[50.0, -50.0], [150.0, 50.0], [50.0, 150.0], [-50.0, 50.0]]


def boolean_ops() -> None:
    both = cl.intersect([SQUARE], [DIAMOND], cl.FillRule.NON_ZERO)
    assert_type(both, list[NDArray[np.int64]])
    assert_type(cl.union([SQUARE], cl.FillRule.NON_ZERO), list[NDArray[np.int64]])
    assert_type(cl.union([SQUARE], [DIAMOND], cl.FillRule.NON_ZERO), list[NDArray[np.int64]])
    assert_type(cl.difference([SQUARE], [DIAMOND], cl.FillRule.EVEN_ODD), list[NDArray[np.int64]])
    assert_type(cl.xor([SQUARE], [DIAMOND], cl.FillRule.EVEN_ODD), list[NDArray[np.int64]])
    assert_type(
        cl.boolean_op(cl.ClipType.INTERSECTION, cl.FillRule.NON_ZERO, [SQUARE], [DIAMOND]),
        list[NDArray[np.int64]],
    )

    assert_type(
        cl.intersect([SQUARE_D], [DIAMOND_D], cl.FillRule.NON_ZERO, 4),
        list[NDArray[np.float64]],
    )
    assert_type(
        cl.boolean_op(
            cl.ClipType.UNION, cl.FillRule.NON_ZERO, [SQUARE_D], [DIAMOND_D], precision=3
        ),
        list[NDArray[np.float64]],
    )
    assert_type(
        cl.boolean_op_tree(cl.ClipType.UNION, cl.FillRule.NON_ZERO, [SQUARE], [DIAMOND]),
        cl.PolyPath64,
    )
    assert_type(
        cl.boolean_op_tree(cl.ClipType.UNION, cl.FillRule.NON_ZERO, [SQUARE_D], [DIAMOND_D]),
        cl.PolyPathD,
    )

    # numpy input keeps the family of its dtype.
    arr = np.asarray(SQUARE_D, dtype=np.float64)
    assert_type(cl.union([arr], cl.FillRule.NON_ZERO), list[NDArray[np.float64]])


def engine() -> None:
    c64 = cl.Clipper64()
    c64.preserve_collinear = True
    c64.reverse_solution = False
    c64.add_subject([SQUARE])
    c64.add_open_subject([[[0, 0], [200, 200]]])
    c64.add_clip([DIAMOND])
    closed, open_paths = c64.execute(cl.ClipType.INTERSECTION, cl.FillRule.NON_ZERO)
    assert_type(closed, list[NDArray[np.int64]])
    assert_type(open_paths, list[NDArray[np.int64]])
    assert_type(c64.error_code, int)

    reuse = cl.ReuseableDataContainer64()
    reuse.add_paths([SQUARE], cl.PathType.CLIP, False)
    c64.clear()
    c64.add_reuseable_data(reuse)

    cd = cl.ClipperD(precision=4)
    cd.add_subject([SQUARE_D])
    cd.add_clip([DIAMOND_D])
    closed_d, open_d = cd.execute(cl.ClipType.UNION, cl.FillRule.NON_ZERO)
    assert_type(closed_d, list[NDArray[np.float64]])
    assert_type(open_d, list[NDArray[np.float64]])

    tree, open_from_tree = c64.execute_tree(cl.ClipType.UNION, cl.FillRule.NON_ZERO)
    assert_type(tree, cl.PolyPath64)
    assert_type(open_from_tree, list[NDArray[np.int64]])
    assert_type(walk(tree), float)

    tree_d, _ = cd.execute_tree(cl.ClipType.UNION, cl.FillRule.NON_ZERO)
    assert_type(tree_d, cl.PolyPathD)
    assert_type(tree_d.polygon, NDArray[np.float64])
    assert_type(tree_d.scale, float)
    assert_type(cl.poly_tree_to_paths_d(tree_d), list[NDArray[np.float64]])
    assert_type(cl.poly_tree_to_paths64(tree), list[NDArray[np.int64]])
    assert_type(cl.check_polytree_fully_contains_children(tree), bool)


def walk(node: cl.PolyPath64) -> float:
    """Depth-first over the tree: `child`, `[i]`, iteration and the read-only attributes."""
    assert_type(node.polygon, NDArray[np.int64])
    assert_type(node.is_hole, bool)
    assert_type(node.level, int)
    parent = node.parent
    assert_type(parent, cl.PolyPath64 | None)
    total = node.area()
    for i in range(len(node)):
        total += walk(node.child(i)) + node[i].area()
    for child in node:
        total += child.area()
    return total


def offsetting() -> None:
    off = cl.ClipperOffset(miter_limit=3.0, arc_tolerance=0.25)
    off.add_path(SQUARE, cl.JoinType.MITER, cl.EndType.POLYGON)
    off.add_paths([DIAMOND], cl.JoinType.ROUND, cl.EndType.POLYGON)
    assert_type(off.execute(5.0), list[NDArray[np.int64]])
    assert_type(off.execute_tree(5.0), cl.PolyPath64)
    assert_type(off.miter_limit, float)

    def delta(
        path: NDArray[np.int64], normals: NDArray[np.float64], curr: int, prev: int
    ) -> float:
        return float(len(path) + len(normals) + curr + prev)

    off.set_delta_callback(delta)
    assert_type(off.execute(delta), list[NDArray[np.int64]])
    off.set_delta_callback(None)

    assert_type(
        cl.inflate_paths([SQUARE], 5.0, cl.JoinType.ROUND, cl.EndType.POLYGON),
        list[NDArray[np.int64]],
    )
    assert_type(
        cl.inflate_paths(
            [SQUARE_D], 5.0, cl.JoinType.ROUND, cl.EndType.POLYGON, 2.0, precision=4
        ),
        list[NDArray[np.float64]],
    )


def rect_and_misc() -> None:
    r64 = cl.Rect64(0, 0, 100, 100)
    assert_type(r64.mid_point(), tuple[int, int])
    assert_type(r64.as_path(), NDArray[np.int64])
    assert_type(r64.width, int)
    assert_type(r64.contains(cl.Rect64(1, 1, 2, 2)), bool)
    assert_type(r64.contains((1, 1)), bool)
    assert_type(cl.Rect64.invalid_rect(), cl.Rect64)
    assert_type(cl.rect_clip(r64, [SQUARE]), list[NDArray[np.int64]])
    assert_type(cl.rect_clip_lines(r64, [[[0, 0], [200, 200]]]), list[NDArray[np.int64]])
    assert_type(cl.RectClip64(r64).execute([SQUARE]), list[NDArray[np.int64]])
    assert_type(cl.RectClipLines64(r64).execute([[[0, 0], [200, 200]]]), list[NDArray[np.int64]])

    rd = cl.RectD(0.0, 0.0, 100.0, 100.0)
    assert_type(rd.mid_point(), tuple[float, float])
    assert_type(cl.rect_clip(rd, [SQUARE_D], 4), list[NDArray[np.float64]])
    assert_type(cl.get_bounds([SQUARE]), cl.Rect64)
    assert_type(cl.get_bounds([SQUARE_D]), cl.RectD)

    assert_type(cl.minkowski_sum(SQUARE, DIAMOND, True), list[NDArray[np.int64]])
    assert_type(
        cl.minkowski_diff(SQUARE_D, DIAMOND_D, True, decimal_places=3),
        list[NDArray[np.float64]],
    )

    ok, triangles = cl.triangulate([SQUARE])
    assert_type(ok, cl.TriangulateResult)
    assert_type(triangles, list[NDArray[np.int64]])
    ok_d, triangles_d = cl.triangulate([SQUARE_D], dec_places=2, use_delaunay=False)
    assert_type(ok_d, cl.TriangulateResult)
    assert_type(triangles_d, list[NDArray[np.float64]])

    assert_type(cl.area([SQUARE]), float)
    assert_type(cl.is_positive(SQUARE), bool)
    assert_type(cl.point_in_polygon((1, 1), SQUARE), cl.PointInPolygonResult)
    assert_type(cl.mid_point((0, 0), (4, 4)), tuple[int, int])
    assert_type(cl.mid_point((0.0, 0.0), (4.0, 4.0)), tuple[float, float])
    assert_type(cl.make_path([0, 0, 1, 1]), NDArray[np.int64])
    assert_type(cl.make_path_d([0.0, 0.0, 1.0, 1.0]), NDArray[np.float64])
    assert_type(cl.translate_path(SQUARE, 1, 2), NDArray[np.int64])
    assert_type(cl.translate_paths([SQUARE_D], 1.5, 2.5), list[NDArray[np.float64]])
    assert_type(cl.simplify_path(SQUARE, 1.0), NDArray[np.int64])
    assert_type(cl.simplify_paths([SQUARE_D], 1.0), list[NDArray[np.float64]])
    assert_type(cl.trim_collinear(SQUARE), NDArray[np.int64])
    assert_type(cl.trim_collinear(SQUARE_D, precision=2), NDArray[np.float64])
    assert_type(cl.ramer_douglas_peucker(SQUARE, 1.0), NDArray[np.int64])
    assert_type(cl.ramer_douglas_peucker([SQUARE_D], 1.0), list[NDArray[np.float64]])
    assert_type(cl.ellipse(r64, 16), NDArray[np.int64])
    assert_type(cl.ellipse(rd, 16), NDArray[np.float64])
    assert_type(cl.ellipse((0, 0), 5.0, 3.0, 16), NDArray[np.int64])
    assert_type(cl.ellipse((0.0, 0.0), 5.0), NDArray[np.float64])
    assert_type(cl.cross_product((0, 0), (1, 0), (1, 1)), float)
    assert_type(cl.cross_product((1, 0), (1, 1)), float)
    assert_type(cl.segments_intersect((0, 0), (2, 2), (0, 2), (2, 0)), bool)
    assert_type(cl.strip_duplicates(SQUARE, True), NDArray[np.int64])
    assert_type(cl.strip_near_equal([SQUARE_D], 0.1, True), list[NDArray[np.float64]])
    assert_type(cl.length(SQUARE), float)
    assert_type(cl.CLIPPER2_VERSION, str)
    assert_type(cl.__version__, str)
    assert_type(cl.MAX_COORD, int)


def z_module() -> None:
    subject = [[[0, 0, 1], [100, 0, 2], [100, 100, 3], [0, 100, 4]]]
    clip = [[[50, 50, 5], [150, 50, 6], [150, 150, 7], [50, 150, 8]]]

    def on_z(
        e1bot: tuple[int, int, int],
        e1top: tuple[int, int, int],
        e2bot: tuple[int, int, int],
        e2top: tuple[int, int, int],
        pt: tuple[int, int, int],
    ) -> int:
        return e1bot[2] + e1top[2] + e2bot[2] + e2top[2] + pt[2]

    c = clz.Clipper64()
    c.set_z_callback(on_z)
    c.default_z = 99
    c.add_subject(subject)
    c.add_clip(clip)
    solution, _open = c.execute(clz.ClipType.INTERSECTION, clz.FillRule.NON_ZERO)
    assert_type(solution, list[NDArray[np.int64]])
    assert_type(clz.mid_point((0, 0, 1), (4, 4, 3)), tuple[int, int, int])

    def on_z_d(
        e1bot: tuple[float, float, int],
        e1top: tuple[float, float, int],
        e2bot: tuple[float, float, int],
        e2top: tuple[float, float, int],
        pt: tuple[float, float, int],
    ) -> int:
        return pt[2]

    cd = clz.ClipperD(2)
    cd.set_z_callback(on_z_d)
    cd.add_subject([[[0.0, 0.0, 1], [10.0, 0.0, 2], [10.0, 10.0, 3]]])
    assert_type(cd.execute(clz.ClipType.UNION, clz.FillRule.NON_ZERO)[0], list[NDArray[np.float64]])
    assert_type(clz.mid_point((0.0, 0.0, 1), (4.0, 4.0, 3)), tuple[float, float, int])

    offset = clz.ClipperOffset()
    offset.set_z_callback(on_z)
    offset.add_paths(subject, clz.JoinType.ROUND, clz.EndType.POLYGON)
    assert_type(offset.execute(2.0), list[NDArray[np.int64]])

    # The shared Rect64 comes from the non-USINGZ build, so it stays two-dimensional.
    assert_type(clz.Rect64(0, 0, 10, 10).mid_point(), tuple[int, int])
    assert_type(clz.get_bounds(subject), clz.Rect64)
