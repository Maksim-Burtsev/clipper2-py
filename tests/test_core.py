"""Enums, Rect64 / RectD, Clipper2Error and the free functions of core.h / clipper.h.

Expected values are derived from the upstream headers, never from what the binding printed.
"""

import importlib.metadata

import numpy as np
import pytest

import clipper2
import clipper2.z as z

SUBJECT = [[(0, 0), (10, 0), (10, 10), (0, 10)]]
CLIP = [[(5, 5), (15, 5), (15, 15), (5, 15)]]
NON_ZERO = clipper2.FillRule.NON_ZERO


def vertices(paths):
    return sorted(tuple(pt) for path in paths for pt in path.tolist())


# --- module level ---------------------------------------------------------------------


def test_upstream_version_is_the_pinned_one():
    assert clipper2.CLIPPER2_VERSION == "2.0.1"
    assert clipper2.__version__ == importlib.metadata.version("clipper2-py")


def test_upstream_constants():
    assert clipper2.CLIPPER2_MAX_DEC_PRECISION == 8
    assert clipper2.MAX_COORD == (2**63 - 1) >> 2
    assert clipper2.MIN_COORD == -clipper2.MAX_COORD
    assert (clipper2.precision_error_i, clipper2.scale_error_i, clipper2.non_pair_error_i) == (1, 2, 4)
    assert (clipper2.undefined_error_i, clipper2.range_error_i) == (32, 64)


def test_enum_member_names():
    assert list(clipper2.FillRule.__members__) == ["EVEN_ODD", "NON_ZERO", "POSITIVE", "NEGATIVE"]
    assert list(clipper2.ClipType.__members__) == [
        "NO_CLIP",
        "INTERSECTION",
        "UNION",
        "DIFFERENCE",
        "XOR",
    ]
    assert list(clipper2.PathType.__members__) == ["SUBJECT", "CLIP"]
    assert list(clipper2.JoinType.__members__) == ["SQUARE", "BEVEL", "ROUND", "MITER"]
    assert list(clipper2.EndType.__members__) == ["POLYGON", "JOINED", "BUTT", "SQUARE", "ROUND"]
    assert list(clipper2.PointInPolygonResult.__members__) == ["IS_ON", "IS_INSIDE", "IS_OUTSIDE"]
    assert list(clipper2.TriangulateResult.__members__) == [
        "SUCCESS",
        "FAIL",
        "NO_POLYGONS",
        "PATHS_INTERSECT",
    ]


def test_enum_values_match_upstream():
    assert int(clipper2.FillRule.EVEN_ODD) == 0
    assert int(clipper2.ClipType.NO_CLIP) == 0
    assert int(clipper2.JoinType.MITER) == 3
    assert int(clipper2.EndType.POLYGON) == 0


def test_shared_types_are_the_same_objects_in_both_modules():
    for name in (
        "FillRule",
        "ClipType",
        "PathType",
        "JoinType",
        "EndType",
        "PointInPolygonResult",
        "TriangulateResult",
        "Rect64",
        "RectD",
        "Clipper2Error",
    ):
        assert getattr(clipper2, name) is getattr(z, name), name


def test_clipper2_error():
    assert issubclass(clipper2.Clipper2Error, Exception)
    with pytest.raises(clipper2.Clipper2Error, match="Precision exceeds the permitted range"):
        clipper2.boolean_op(clipper2.ClipType.UNION, NON_ZERO, [[(0.0, 0.0)]], [], precision=99)
    # the same class from the z build
    with pytest.raises(clipper2.Clipper2Error):
        z.boolean_op(z.ClipType.UNION, NON_ZERO, [[(0.0, 0.0)]], [], precision=99)


# --- Rect -----------------------------------------------------------------------------


def test_rect64_fields_and_methods():
    r = clipper2.Rect64(0, 0, 10, 20)
    assert (r.left, r.top, r.right, r.bottom) == (0, 0, 10, 20)
    assert r.width == 10 and r.height == 20
    assert r.mid_point() == (5, 10)
    assert r.as_path().tolist() == [[0, 0], [10, 0], [10, 20], [0, 20]]
    assert r.is_valid() and not r.is_empty()
    assert r.contains((5, 5)) and not r.contains((0, 0))  # strict inequalities upstream
    assert r.contains(clipper2.Rect64(1, 1, 2, 2))
    assert r.intersects(clipper2.Rect64(5, 5, 50, 50))
    assert not r.intersects(clipper2.Rect64(50, 50, 60, 60))
    r.width = 4
    assert r.right == 4
    r.height = 5
    assert r.bottom == 5


def test_rect64_operators_and_text():
    a = clipper2.Rect64(0, 0, 10, 10)
    b = clipper2.Rect64(5, 5, 20, 20)
    assert (a + b) == clipper2.Rect64(0, 0, 20, 20)
    a += b
    assert a == clipper2.Rect64(0, 0, 20, 20)
    assert str(clipper2.Rect64(0, 0, 10, 10)) == "(0,0,10,10) "  # upstream's operator<<
    assert repr(clipper2.Rect64(0, 0, 10, 10)) == "Rect64(0, 0, 10, 10)"


def test_rect_validity_and_scaling():
    assert not clipper2.Rect64(False).is_valid()
    assert clipper2.Rect64().is_valid()
    invalid = clipper2.Rect64.invalid_rect()
    assert invalid.left == 2**63 - 1 and invalid.right == -(2**63)
    assert not invalid.is_valid()
    r = clipper2.Rect64(0, 0, 10, 10)
    r.scale(2)
    assert (r.left, r.top, r.right, r.bottom) == (0, 0, 20, 20)
    assert clipper2.Rect64(0, 0, 0, 0).is_empty()


def test_rectd():
    r = clipper2.RectD(0.0, 0.0, 1.0, 2.0)
    assert r.width == 1.0 and r.height == 2.0
    assert r.mid_point() == (0.5, 1.0)
    assert str(r) == "(0,0,1,2) "
    with pytest.raises(TypeError):
        clipper2.Rect64(0.5, 0, 10, 10)  # a float where C++ takes int64_t


# --- boolean operations ---------------------------------------------------------------


def test_intersect_of_two_overlapping_squares():
    result = clipper2.intersect(SUBJECT, CLIP, NON_ZERO)
    assert len(result) == 1
    assert vertices(result) == [(5, 5), (5, 10), (10, 5), (10, 10)]
    assert clipper2.area(result) == 25.0


def test_union_difference_xor_areas():
    assert clipper2.area(clipper2.union(SUBJECT, CLIP, NON_ZERO)) == 175.0
    assert clipper2.area(clipper2.difference(SUBJECT, CLIP, NON_ZERO)) == 75.0
    assert clipper2.area(clipper2.xor(SUBJECT, CLIP, NON_ZERO)) == 150.0
    assert clipper2.area(clipper2.union(SUBJECT + CLIP, NON_ZERO)) == 175.0


def test_boolean_op_matches_the_named_operations():
    assert vertices(
        clipper2.boolean_op(clipper2.ClipType.INTERSECTION, NON_ZERO, SUBJECT, CLIP)
    ) == vertices(clipper2.intersect(SUBJECT, CLIP, NON_ZERO))


def test_boolean_op_tree():
    tree = clipper2.boolean_op_tree(clipper2.ClipType.UNION, NON_ZERO, SUBJECT, CLIP)
    assert isinstance(tree, clipper2.PolyTree64)
    assert len(tree) == 1
    assert tree.area() == 175.0
    tree_d = clipper2.boolean_op_tree(
        clipper2.ClipType.UNION, NON_ZERO, [[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]], []
    )
    assert isinstance(tree_d, clipper2.PolyTreeD)


def test_polytree_to_paths_and_containment():
    clipper = clipper2.Clipper64()
    clipper.add_subject(SUBJECT + [[(2, 2), (2, 8), (8, 8), (8, 2)]])
    tree, _ = clipper.execute_tree(clipper2.ClipType.UNION, clipper2.FillRule.EVEN_ODD)
    paths = clipper2.poly_tree_to_paths64(tree)
    assert len(paths) == 2  # the square and its hole
    assert clipper2.area(paths) == 64.0
    assert clipper2.check_polytree_fully_contains_children(tree)


def test_poly_tree_to_paths_d():
    clipper = clipper2.ClipperD()
    clipper.add_subject([[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]])
    tree, _ = clipper.execute_tree(clipper2.ClipType.UNION, NON_ZERO)
    paths = clipper2.poly_tree_to_paths_d(tree)
    assert len(paths) == 1 and paths[0].dtype == np.float64


# --- geometry helpers -----------------------------------------------------------------


def test_area_and_orientation():
    assert clipper2.area(SUBJECT[0]) == 100.0
    assert clipper2.is_positive(SUBJECT[0])
    reversed_square = SUBJECT[0][::-1]
    assert clipper2.area(reversed_square) == -100.0
    assert not clipper2.is_positive(reversed_square)
    assert clipper2.area([(0, 0), (1, 1)]) == 0.0  # fewer than 3 points


def test_get_bounds():
    assert clipper2.get_bounds(SUBJECT[0]) == clipper2.Rect64(0, 0, 10, 10)
    assert clipper2.get_bounds(SUBJECT + CLIP) == clipper2.Rect64(0, 0, 15, 15)
    assert clipper2.get_bounds([(0.0, 0.0), (1.5, 2.5)]) == clipper2.RectD(0.0, 0.0, 1.5, 2.5)


def test_point_in_polygon():
    assert clipper2.point_in_polygon((5, 5), SUBJECT[0]) == clipper2.PointInPolygonResult.IS_INSIDE
    assert clipper2.point_in_polygon((0, 0), SUBJECT[0]) == clipper2.PointInPolygonResult.IS_ON
    assert clipper2.point_in_polygon((50, 5), SUBJECT[0]) == clipper2.PointInPolygonResult.IS_OUTSIDE
    # fewer than 3 vertices is "outside" upstream
    assert clipper2.point_in_polygon((0, 0), [(0, 0), (1, 1)]) == clipper2.PointInPolygonResult.IS_OUTSIDE


def test_products_and_distances():
    assert clipper2.cross_product((0, 0), (1, 0), (1, 1)) == 1.0
    assert clipper2.cross_product((1, 0), (0, 1)) == -1.0  # vec1.y*vec2.x - vec2.y*vec1.x
    assert clipper2.dot_product((0, 0), (1, 0), (2, 0)) == 1.0
    assert clipper2.dot_product((1, 2), (3, 4)) == 11.0
    assert clipper2.cross_product_sign((0, 0), (1, 0), (1, 1)) == 1
    assert clipper2.distance((0, 0), (3, 4)) == 5.0
    assert clipper2.distance_sqr((0, 0), (3, 4)) == 25.0
    assert clipper2.perpendic_dist_from_line_sqrd((0, 5), (0, 0), (10, 0)) == 25.0
    assert clipper2.length(SUBJECT[0]) == 30.0
    assert clipper2.length(SUBJECT[0], is_closed_path=True) == 40.0


def test_point_helpers():
    assert clipper2.mid_point((0, 0), (10, 10)) == (5, 5)
    assert clipper2.near_equal((0, 0), (1, 1), 4.0)
    assert not clipper2.near_equal((0, 0), (1, 1), 1.0)
    assert clipper2.is_collinear((0, 0), (5, 0), (10, 0))
    assert not clipper2.is_collinear((0, 0), (5, 1), (10, 0))
    assert clipper2.translate_point((1, 2), 3, 4) == (4, 6)
    assert clipper2.reflect_point((1, 1), (0, 0)) == (-1, -1)
    assert clipper2.get_closest_point_on_segment((5, 5), (0, 0), (10, 0)) == (5, 0)


def test_segments_intersect_is_64_only():
    assert clipper2.segments_intersect((0, 0), (10, 0), (5, -5), (5, 5))
    assert not clipper2.segments_intersect((0, 0), (10, 0), (0, 5), (10, 5))
    # touching at an end point is excluded unless `inclusive`
    assert not clipper2.segments_intersect((0, 0), (10, 0), (0, 0), (0, 10))
    assert clipper2.segments_intersect((0, 0), (10, 0), (0, 0), (0, 10), inclusive=True)
    with pytest.raises(TypeError):
        clipper2.segments_intersect((0.0, 0.0), (10.0, 0.0), (5.0, -5.0), (5.0, 5.0))


def test_strip_helpers():
    assert clipper2.strip_duplicates([(0, 0), (0, 0), (10, 0), (10, 10)], True).tolist() == [
        [0, 0],
        [10, 0],
        [10, 10],
    ]
    assert clipper2.strip_near_equal([(0, 0), (1, 1), (10, 0)], 4.0, False).tolist() == [
        [0, 0],
        [10, 0],
    ]


def test_make_path():
    assert clipper2.make_path([0, 0, 10, 0, 10, 10]).tolist() == [[0, 0], [10, 0], [10, 10]]
    assert clipper2.make_path_d([0.5, 0.5, 1.5, 1.5]).tolist() == [[0.5, 0.5], [1.5, 1.5]]
    assert clipper2.make_path_d([1, 2, 3, 4]).dtype == np.float64  # int -> double is safe
    with pytest.raises(clipper2.Clipper2Error, match="2 values for each coordinate"):
        clipper2.make_path([0, 0, 10])


def test_trim_collinear():
    path = [(0, 0), (5, 0), (10, 0), (10, 10), (0, 10)]
    assert clipper2.trim_collinear(path).tolist() == [[0, 0], [10, 0], [10, 10], [0, 10]]
    assert len(clipper2.trim_collinear([(0, 0), (5, 0), (10, 0)], is_open_path=True)) == 2
    assert clipper2.trim_collinear(
        [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (10.0, 10.0)], precision=2
    ).tolist() == [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]]


def test_trim_collinear_d_requires_upstreams_precision():
    # upstream's D overload declares precision without a default
    with pytest.raises(TypeError, match="requires"):
        clipper2.trim_collinear([(0.0, 0.0), (5.0, 0.0), (10.0, 0.0)])


def test_simplify_and_rdp():
    path = [(0, 0), (5, 0), (10, 0), (10, 10), (0, 10)]
    square = [[0, 0], [10, 0], [10, 10], [0, 10]]
    assert clipper2.simplify_path(path, 1.0).tolist() == square
    assert [p.tolist() for p in clipper2.simplify_paths([path], 1.0)] == [square]
    assert clipper2.ramer_douglas_peucker(path, 1.0).tolist() == square
    assert [p.tolist() for p in clipper2.ramer_douglas_peucker([path], 1.0)] == [square]
    # fewer than 5 points is returned unchanged
    assert clipper2.ramer_douglas_peucker([(0, 0), (1, 1)], 100.0).tolist() == [[0, 0], [1, 1]]


def test_ellipse():
    # steps defaults to size_t(PI * sqrt((rx + ry) / 2)) == 7 for a radius of 5
    path = clipper2.ellipse(clipper2.Rect64(0, 0, 10, 10))
    assert path.shape == (7, 2)
    assert tuple(path[0]) == (10, 5)  # (center.x + radius_x, center.y)
    assert clipper2.ellipse((0, 0), 5.0, steps=4).shape == (4, 2)
    assert clipper2.ellipse(clipper2.RectD(0.0, 0.0, 10.0, 10.0)).dtype == np.float64
    assert len(clipper2.ellipse((0, 0), 0)) == 0  # radius_x <= 0 gives an empty path


def test_path2_contains_path1():
    assert clipper2.path2_contains_path1([(2, 2), (3, 3), (2, 3)], SUBJECT[0])
    assert not clipper2.path2_contains_path1([(20, 20), (30, 30), (20, 30)], SUBJECT[0])


def test_near_collinear():
    assert clipper2.near_collinear((0, 0), (5, 0), (10, 0), 0.1)
    assert not clipper2.near_collinear((0, 0), (5, 5), (10, 0), 0.1)


def test_translate():
    assert clipper2.translate_path(SUBJECT[0], 5, 5).tolist() == [
        [5, 5],
        [15, 5],
        [15, 15],
        [5, 15],
    ]
    assert clipper2.translate_paths(SUBJECT, 1, 2)[0].tolist()[0] == [1, 2]
    assert clipper2.translate_path([(0.0, 0.0)], 0.5, 0.5).tolist() == [[0.5, 0.5]]


def test_d_family_keeps_upstreams_precision_argument():
    subject = [[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]]
    clip = [[(5.0, 5.0), (15.0, 5.0), (15.0, 15.0), (5.0, 15.0)]]
    assert clipper2.area(clipper2.intersect(subject, clip, NON_ZERO)) == 25.0
    assert clipper2.area(clipper2.intersect(subject, clip, NON_ZERO, 0)) == 25.0
    with pytest.raises(TypeError, match="64 family"):
        clipper2.intersect(SUBJECT, CLIP, NON_ZERO, 2)


def test_precision_is_refused_by_every_64_family_call():
    with pytest.raises(TypeError, match="boolean_op"):
        clipper2.boolean_op(clipper2.ClipType.UNION, NON_ZERO, SUBJECT, CLIP, precision=2)
    with pytest.raises(TypeError, match="boolean_op_tree"):
        clipper2.boolean_op_tree(clipper2.ClipType.UNION, NON_ZERO, SUBJECT, CLIP, precision=2)
    with pytest.raises(TypeError, match="union"):
        clipper2.union(SUBJECT, NON_ZERO, 2)
    with pytest.raises(TypeError, match="trim_collinear"):
        clipper2.trim_collinear(SUBJECT[0], precision=2)


def test_precision_must_be_an_integer():
    subject = [[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]]
    with pytest.raises(TypeError):
        clipper2.intersect(subject, subject, NON_ZERO, 2.5)
    with pytest.raises(OverflowError):
        clipper2.intersect(subject, subject, NON_ZERO, 2**40)


def test_clipperd_precision_follows_the_same_rule():
    with pytest.raises(TypeError, match="bool"):
        clipper2.ClipperD(True)
    with pytest.raises(TypeError):
        clipper2.ClipperD(2.0)
    with pytest.raises(OverflowError):
        clipper2.ClipperD(2**40)


# --- make_path ---------------------------------------------------------------------------


def test_make_path_takes_a_flat_sequence_only():
    with pytest.raises(ValueError, match="flat"):
        clipper2.make_path([[0, 0], [1, 1]])
    with pytest.raises(TypeError):
        clipper2.make_path(np.array([1, 0.5], dtype=object))
    with pytest.raises(ValueError, match="flat"):
        clipper2.make_path_d([[0.0, 0.0], [1.0, 1.0]])


# --- path or paths by nesting depth (deviation 2) ----------------------------------------


def test_strip_helpers_take_a_path_or_paths():
    path = [(0, 0), (1, 1), (10, 0)]
    stripped = clipper2.strip_near_equal(path, 4.0, False)
    (as_paths,) = clipper2.strip_near_equal([path], 4.0, False)
    assert stripped.tolist() == as_paths.tolist() == [[0, 0], [10, 0]]

    duplicated = [(0, 0), (0, 0), (10, 0), (10, 10)]
    stripped = clipper2.strip_duplicates(duplicated, True)
    (as_paths,) = clipper2.strip_duplicates([duplicated], True)
    assert stripped.tolist() == as_paths.tolist() == [[0, 0], [10, 0], [10, 10]]


def test_strip_duplicates_leaves_its_argument_alone():
    # C++ strips in place; the binding works on a copy (deviation 4)
    array = np.array([[0, 0], [0, 0], [10, 0]], dtype=np.int64)
    assert clipper2.strip_duplicates(array, True).tolist() == [[0, 0], [10, 0]]
    assert array.tolist() == [[0, 0], [0, 0], [10, 0]]


# --- RectD ------------------------------------------------------------------------------


def test_rectd_fields_and_methods():
    r = clipper2.RectD(0.0, 0.0, 10.0, 20.0)
    assert (r.left, r.top, r.right, r.bottom) == (0.0, 0.0, 10.0, 20.0)
    assert r.width == 10.0 and r.height == 20.0
    assert r.mid_point() == (5.0, 10.0)
    assert r.as_path().tolist() == [[0.0, 0.0], [10.0, 0.0], [10.0, 20.0], [0.0, 20.0]]
    assert r.is_valid() and not r.is_empty()
    assert r.contains((5.0, 5.0)) and not r.contains((0.0, 0.0))  # strict inequalities
    assert r.contains(clipper2.RectD(1.0, 1.0, 2.0, 2.0))
    assert r.intersects(clipper2.RectD(5.0, 5.0, 50.0, 50.0))
    assert not r.intersects(clipper2.RectD(50.0, 50.0, 60.0, 60.0))
    r.width = 4.0
    assert r.right == 4.0
    r.height = 5.0
    assert r.bottom == 5.0
    r.left, r.top, r.right, r.bottom = -1.0, -2.0, 3.0, 4.0
    assert (r.left, r.top, r.right, r.bottom) == (-1.0, -2.0, 3.0, 4.0)


def test_rectd_operators_validity_and_scaling():
    a = clipper2.RectD(0.0, 0.0, 10.0, 10.0)
    b = clipper2.RectD(5.0, 5.0, 20.0, 20.0)
    assert (a + b) == clipper2.RectD(0.0, 0.0, 20.0, 20.0)
    a += b
    assert a == clipper2.RectD(0.0, 0.0, 20.0, 20.0)
    assert not clipper2.RectD(False).is_valid()
    assert clipper2.RectD(True).is_valid()
    invalid = clipper2.RectD.invalid_rect()
    assert not invalid.is_valid()
    assert invalid.left > invalid.right
    r = clipper2.RectD(0.0, 0.0, 10.0, 10.0)
    r.scale(2.0)
    assert (r.left, r.top, r.right, r.bottom) == (0.0, 0.0, 20.0, 20.0)
    assert clipper2.RectD(0.0, 0.0, 0.0, 0.0).is_empty()
    assert repr(clipper2.RectD(0.0, 0.0, 1.0, 2.0)) == "RectD(0, 0, 1, 2)"


# --- the D overloads of the scalar helpers ------------------------------------------------


def test_d_overloads_of_the_point_helpers():
    assert clipper2.cross_product_sign((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)) == 1
    assert clipper2.is_collinear((0.0, 0.0), (5.0, 0.0), (10.0, 0.0))
    assert not clipper2.is_collinear((0.0, 0.0), (5.0, 1.0), (10.0, 0.0))
    assert clipper2.reflect_point((1.0, 1.0), (0.0, 0.0)) == (-1.0, -1.0)
    assert clipper2.translate_point((1.0, 2.0), 0.5, 0.5) == (1.5, 2.5)
    assert clipper2.get_closest_point_on_segment((5.0, 5.0), (0.0, 0.0), (10.0, 0.0)) == (5.0, 0.0)


def test_d_overloads_of_the_path_helpers():
    square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    assert clipper2.is_positive(square)
    assert not clipper2.is_positive(square[::-1])
    assert clipper2.path2_contains_path1([(2.0, 2.0), (3.0, 3.0), (2.0, 3.0)], square)
    assert not clipper2.path2_contains_path1([(20.0, 20.0), (30.0, 30.0), (20.0, 30.0)], square)
    (moved,) = clipper2.translate_paths([square], 0.5, 1.5)
    assert moved.tolist()[0] == [0.5, 1.5]
    assert moved.dtype == np.float64


# --- z through the free functions (deviation 7) -------------------------------------------

Z_PATH = [(0, 0, 1), (5, 0, 1), (10, 0, 2), (10, 10, 3), (0, 10, 4)]
Z_SQUARE = [[0, 0, 1], [10, 0, 2], [10, 10, 3], [0, 10, 4]]


@pytest.mark.parametrize(
    "call",
    [
        lambda path: z.simplify_path(path, 1.0),
        lambda path: z.trim_collinear(path),
        lambda path: z.ramer_douglas_peucker(path, 1.0),
    ],
)
def test_the_simplifiers_keep_the_z_of_the_points_they_keep(call):
    # each of them drops the collinear (5, 0) and keeps the other four points untouched
    assert call(Z_PATH).tolist() == Z_SQUARE


def test_strip_helpers_keep_the_z_of_the_surviving_point():
    # upstream keeps the first of a run, with its own z
    assert z.strip_duplicates([(0, 0, 1), (0, 0, 9), (10, 0, 2)], True).tolist() == [
        [0, 0, 1],
        [10, 0, 2],
    ]
    assert z.strip_near_equal([(0, 0, 1), (1, 1, 9), (10, 0, 2)], 4.0, False).tolist() == [
        [0, 0, 1],
        [10, 0, 2],
    ]


def test_translate_paths_drops_z_because_upstream_does():
    # upstream's TranslatePath builds Point<T>(pt.x + dx, pt.y + dy), so z falls back to the
    # constructor's 0 -- unlike TranslatePoint, which passes pt.z on
    (moved,) = z.translate_paths([Z_PATH], 1, 2)
    assert moved[:, 2].tolist() == [0] * len(Z_PATH)
    assert z.translate_path(Z_PATH, 1, 2)[:, 2].tolist() == [0] * len(Z_PATH)
    assert z.translate_point((1, 2, 4), 1, 1) == (2, 3, 4)


def test_make_path_and_ellipse_give_z_zero():
    # neither has a z to work from: upstream's Point constructor defaults it to 0
    assert z.make_path([0, 0, 10, 0, 10, 10]).tolist() == [[0, 0, 0], [10, 0, 0], [10, 10, 0]]
    assert z.ellipse(z.Rect64(0, 0, 10, 10)).shape == (7, 3)
    assert z.ellipse((0, 0, 7), 5.0, 5.0, 4).tolist() == [
        [5, 0, 0],
        [0, 5, 0],
        [-5, 0, 0],
        [0, -5, 0],
    ]


def test_the_point_helpers_take_two_and_three_element_points():
    assert z.distance((0, 0, 4), (3, 4, 9)) == z.distance((0, 0), (3, 4)) == 5.0
    assert z.length(Z_PATH) == 30.0
    assert z.area(Z_PATH) == 100.0
    assert z.get_bounds(Z_PATH) == z.Rect64(0, 0, 10, 10)
    # ReflectPoint passes pt.z on, GetClosestPointOnSegment builds a fresh point
    assert z.reflect_point((1, 1, 7), (0, 0, 0)) == (-1, -1, 7)
    assert z.reflect_point((1, 1), (0, 0)) == (-1, -1, 0)
    assert z.get_closest_point_on_segment((5, 5, 3), (0, 0, 1), (10, 0, 2)) == (5, 0, 0)
    assert z.mid_point((0, 0), (10, 10)) == (5, 5, 0)


def test_rect64_stays_two_dimensional_in_the_z_build():
    # Rect64 and RectD are registered once, in the non-USINGZ extension (deviation 7)
    rect = z.Rect64(0, 0, 10, 10)
    assert rect.mid_point() == (5, 5)
    assert rect.as_path().shape == (4, 2)
    assert rect.contains((5, 5))
    with pytest.raises(ValueError, match="point"):
        rect.contains((5, 5, 1))
    rect_d = z.RectD(0.0, 0.0, 10.0, 10.0)
    assert rect_d.mid_point() == (5.0, 5.0)
    assert rect_d.as_path().shape == (4, 2)
    with pytest.raises(ValueError, match="point"):
        rect_d.contains((5.0, 5.0, 1.0))


def test_ellipse_with_two_radii():
    # steps defaults to size_t(PI * sqrt((rx + ry) / 2)) == 8 for radii 10 and 5
    path = clipper2.ellipse((0.0, 0.0), 10.0, 5.0)
    assert path.shape == (8, 2)
    assert tuple(path[0]) == (10.0, 0.0)  # (center.x + radius_x, center.y)
    assert max(abs(path[:, 0])) == pytest.approx(10.0)
    assert max(abs(path[:, 1])) == pytest.approx(5.0)
    # radius_y defaults to radius_x: a circle, and 7 steps for a radius of 5
    circle = clipper2.ellipse((0.0, 0.0), 5.0)
    assert circle.shape == (7, 2)
    assert np.allclose(np.hypot(circle[:, 0], circle[:, 1]), 5.0)


def test_get_line_intersect_pt_returns_the_point_or_none():
    assert clipper2.get_line_intersect_pt((0, 0), (10, 10), (0, 10), (10, 0)) == (5, 5)
    assert clipper2.get_line_intersect_pt((0.0, 0.0), (1.0, 1.0), (0.0, 1.0), (1.0, 0.0)) == (0.5, 0.5)
    # parallel lines: upstream returns false and leaves its out-parameter untouched
    assert clipper2.get_line_intersect_pt((0, 0), (10, 0), (0, 5), (10, 5)) is None
    # upstream constrains the point to the first segment
    assert clipper2.get_line_intersect_pt((0, 0), (2, 2), (0, 10), (10, 0)) == (2, 2)
    with pytest.raises(TypeError):
        clipper2.get_line_intersect_pt((0, 0), (10, 10), (0.0, 10.0), (10.0, 0.0))
    assert z.get_line_intersect_pt((0, 0, 7), (10, 10, 7), (0, 10, 7), (10, 0, 7))[:2] == (5, 5)
