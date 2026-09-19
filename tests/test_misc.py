"""rect_clip, rect_clip_lines, minkowski and triangulate: the binding's own surface.

Expected geometry is reasoned, not read back from the binding: clipping the 10x10 square
with the rect (0, 0, 5, 5) gives that rect, the Minkowski sum of two axis-aligned squares is
their side-wise sum, and any triangulation of a square is two triangles of total area 100.
"""

import numpy as np
import pytest

import clipper2
import clipper2.z as z

SQUARE = [(0, 0), (10, 0), (10, 10), (0, 10)]
SQUARE_D = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
CROSSING = [(-5, 5), (15, 5)]  # an open line straight through the square


def vertices(paths):
    return sorted(tuple(pt) for path in paths for pt in path.tolist())


# --- rect_clip / rect_clip_lines --------------------------------------------------------


def test_rect_clip_keeps_the_part_inside_the_rect():
    (result,) = clipper2.rect_clip(clipper2.Rect64(0, 0, 5, 5), [SQUARE])
    assert result.dtype == np.int64
    assert vertices([result]) == [(0, 0), (0, 5), (5, 0), (5, 5)]


def test_rect_clip_d_family():
    (result,) = clipper2.rect_clip(clipper2.RectD(0.0, 0.0, 5.0, 5.0), [SQUARE_D])
    assert result.dtype == np.float64
    assert vertices([result]) == [(0.0, 0.0), (0.0, 5.0), (5.0, 0.0), (5.0, 5.0)]


def test_rect_clip_takes_a_path_or_paths_by_nesting_depth():
    rect = clipper2.Rect64(0, 0, 5, 5)
    assert vertices(clipper2.rect_clip(rect, SQUARE)) == vertices(clipper2.rect_clip(rect, [SQUARE]))
    assert clipper2.rect_clip(rect, []) == []


def test_rect_clip_of_an_empty_rect_is_empty():
    assert clipper2.rect_clip(clipper2.Rect64(5, 5, 5, 5), [SQUARE]) == []
    assert clipper2.rect_clip_lines(clipper2.Rect64(5, 5, 5, 5), [CROSSING]) == []


def test_rect_clip_lines_clips_an_open_line():
    (result,) = clipper2.rect_clip_lines(clipper2.Rect64(0, 0, 10, 10), [CROSSING])
    assert result.tolist() == [[0, 5], [10, 5]]
    # a closed polygon handed to rect_clip_lines stays open: its outline is cut, not filled
    assert clipper2.area(clipper2.rect_clip_lines(clipper2.Rect64(0, 0, 5, 5), [SQUARE])) != 25.0


def test_the_rect_type_picks_the_family():
    with pytest.raises(TypeError, match="same family"):
        clipper2.rect_clip(clipper2.Rect64(0, 0, 5, 5), [SQUARE_D])
    with pytest.raises(TypeError, match="same family"):
        clipper2.rect_clip(clipper2.RectD(0.0, 0.0, 5.0, 5.0), [SQUARE])
    with pytest.raises(TypeError, match="same family"):
        clipper2.rect_clip_lines(clipper2.Rect64(0, 0, 5, 5), [CROSSING[0], (1.5, 2.5)])


def test_rect_clip_precision_belongs_to_the_d_family_only():
    with pytest.raises(TypeError, match="precision"):
        clipper2.rect_clip(clipper2.Rect64(0, 0, 5, 5), [SQUARE], precision=3)
    with pytest.raises(TypeError, match="precision"):
        clipper2.rect_clip_lines(clipper2.Rect64(0, 0, 5, 5), [CROSSING], precision=3)
    # precision 0 scales by 1: the clipped corner lands on whole numbers
    (result,) = clipper2.rect_clip(
        clipper2.RectD(0.0, 0.0, 5.4, 5.4), [SQUARE_D], precision=0
    )
    assert vertices([result]) == [(0.0, 0.0), (0.0, 5.0), (5.0, 0.0), (5.0, 5.0)]


def test_rect_clip_classes():
    rect = clipper2.Rect64(0, 0, 5, 5)
    clipper = clipper2.RectClip64(rect)
    assert vertices(clipper.execute([SQUARE])) == vertices(clipper2.rect_clip(rect, [SQUARE]))
    # upstream cleans up after every path, so the object can be executed again
    assert vertices(clipper.execute([SQUARE])) == [(0, 0), (0, 5), (5, 0), (5, 5)]

    lines = clipper2.RectClipLines64(clipper2.Rect64(0, 0, 10, 10))
    assert lines.execute([CROSSING])[0].tolist() == [[0, 5], [10, 5]]
    # upstream: class RectClipLines64 : public RectClip64
    assert issubclass(clipper2.RectClipLines64, clipper2.RectClip64)


def test_rect_clip_classes_are_64_only():
    with pytest.raises(TypeError, match="64 family"):
        clipper2.RectClip64(clipper2.Rect64(0, 0, 5, 5)).execute([SQUARE_D])
    with pytest.raises(TypeError):
        clipper2.RectClip64(clipper2.RectD(0.0, 0.0, 5.0, 5.0))


def test_rect_clip_in_the_z_build():
    rect = z.Rect64(0, 0, 5, 5)
    (result,) = z.rect_clip(rect, [[(0, 0, 3), (10, 0, 3), (10, 10, 3), (0, 10, 3)]])
    assert result.shape == (4, 3)
    assert sorted(tuple(pt[:2]) for pt in result.tolist()) == [(0, 0), (0, 5), (5, 0), (5, 5)]
    assert clipper2.Rect64 is z.Rect64  # Rect64 is shared by the two modules


# --- minkowski --------------------------------------------------------------------------

# Upstream sweeps the pattern along the path, so a closed path gives a band, not a filled
# shape: this 2x2 pattern swept along the 10x10 square covers [-1, 11]^2 minus [1, 9]^2.
PATTERN = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
PATTERN_D = [(-0.25, -0.25), (0.25, -0.25), (0.25, 0.25), (-0.25, 0.25)]


def test_minkowski_sum_of_two_squares():
    result = clipper2.minkowski_sum(PATTERN, SQUARE, True)
    assert len(result) == 2  # the outer ring and the hole
    assert all(path.dtype == np.int64 for path in result)
    assert clipper2.area(result) == 144.0 - 64.0
    assert str(clipper2.get_bounds(result)) == str(clipper2.Rect64(-1, -1, 11, 11))


def test_minkowski_diff_mirrors_the_pattern():
    # MinkowskiDiff subtracts the pattern, and this pattern is symmetric about the origin
    assert vertices(clipper2.minkowski_diff(PATTERN, SQUARE, True)) == vertices(
        clipper2.minkowski_sum(PATTERN, SQUARE, True)
    )


def test_minkowski_open_path_leaves_out_the_closing_edge():
    closed = clipper2.area(clipper2.minkowski_sum(PATTERN, SQUARE, True))
    open_path = clipper2.area(clipper2.minkowski_sum(PATTERN, SQUARE, False))
    assert abs(open_path) < abs(closed)


def test_minkowski_dispatches_on_dtype_and_rounds_at_decimal_places():
    result = clipper2.minkowski_sum(PATTERN_D, SQUARE_D, True)
    assert all(path.dtype == np.float64 for path in result)
    assert clipper2.area(result) == 10.5**2 - 9.5**2
    # decimal_places 0 scales by 1, so the whole pattern rounds onto a single point and
    # sweeping it leaves nothing behind
    assert clipper2.minkowski_sum(PATTERN_D, SQUARE_D, True, decimal_places=0) == []
    # the default is upstream's 2
    assert vertices(clipper2.minkowski_sum(PATTERN_D, SQUARE_D, True, decimal_places=2)) == (
        vertices(result)
    )


def test_minkowski_decimal_places_belongs_to_the_d_family_only():
    with pytest.raises(TypeError, match="decimal_places"):
        clipper2.minkowski_sum(PATTERN, SQUARE, True, decimal_places=3)
    with pytest.raises(TypeError, match="decimal_places"):
        clipper2.minkowski_diff(PATTERN, SQUARE, True, decimal_places=3)
    assert clipper2.minkowski_sum(PATTERN_D, SQUARE_D, True, decimal_places=3)


def test_minkowski_refuses_mixed_families():
    with pytest.raises(TypeError, match="same family"):
        clipper2.minkowski_sum(PATTERN, SQUARE_D, True)
    with pytest.raises(TypeError, match="same family"):
        clipper2.minkowski_diff(PATTERN_D, SQUARE, True)


def test_minkowski_of_an_empty_path_is_empty():
    assert clipper2.minkowski_sum([], SQUARE, True) == []
    assert clipper2.minkowski_sum(PATTERN, [], True) == []


# --- triangulate ------------------------------------------------------------------------


def test_triangulate_a_square_gives_two_triangles():
    result, solution = clipper2.triangulate([SQUARE])
    assert result == clipper2.TriangulateResult.SUCCESS
    assert len(solution) == 2
    assert all(triangle.shape == (3, 2) for triangle in solution)
    assert sum(abs(clipper2.area(triangle)) for triangle in solution) == 100.0


def test_triangulate_use_delaunay_defaults_to_true():
    assert vertices(clipper2.triangulate([SQUARE])[1]) == vertices(
        clipper2.triangulate([SQUARE], use_delaunay=True)[1]
    )
    result, solution = clipper2.triangulate([SQUARE], use_delaunay=False)
    assert result == clipper2.TriangulateResult.SUCCESS
    assert sum(abs(clipper2.area(triangle)) for triangle in solution) == 100.0


def test_triangulate_reports_upstreams_failures():
    assert clipper2.triangulate([]) == (clipper2.TriangulateResult.NO_POLYGONS, [])
    assert clipper2.triangulate([[(0, 0), (10, 0)]])[0] == clipper2.TriangulateResult.NO_POLYGONS
    crossing = [SQUARE, [(5, 5), (15, 5), (15, 15), (5, 15)]]
    assert clipper2.triangulate(crossing)[0] == clipper2.TriangulateResult.PATHS_INTERSECT


def test_triangulate_d_requires_dec_places_as_upstream_does():
    # upstream's D overload declares decPlaces without a default
    with pytest.raises(TypeError, match="dec_places"):
        clipper2.triangulate([SQUARE_D])
    result, solution = clipper2.triangulate([SQUARE_D], dec_places=2)
    assert result == clipper2.TriangulateResult.SUCCESS
    assert all(triangle.dtype == np.float64 for triangle in solution)
    assert sum(abs(clipper2.area(triangle)) for triangle in solution) == 100.0
    # keyword-only: upstream puts decPlaces before useDelaunay in the D overload only
    assert vertices(clipper2.triangulate([SQUARE_D], dec_places=2, use_delaunay=True)[1]) == (
        vertices(solution)
    )


def test_triangulate_dec_places_belongs_to_the_d_family_only():
    with pytest.raises(TypeError, match="takes no 'dec_places'"):
        clipper2.triangulate([SQUARE], dec_places=2)


def test_triangulate_in_the_z_build():
    result, solution = z.triangulate([[(0, 0, 4), (10, 0, 4), (10, 10, 4), (0, 10, 4)]])
    assert result == clipper2.TriangulateResult.SUCCESS  # the enums are shared
    assert all(triangle.shape == (3, 3) for triangle in solution)


def test_rect_clip_lines_takes_a_path_or_paths_by_nesting_depth():
    rect = clipper2.Rect64(0, 0, 10, 10)
    (single,) = clipper2.rect_clip_lines(rect, CROSSING)
    (many,) = clipper2.rect_clip_lines(rect, [CROSSING])
    assert single.tolist() == many.tolist() == [[0, 5], [10, 5]]


# --- the z build ---------------------------------------------------------------------------


def test_rect_clip_keeps_the_z_of_the_vertices_it_keeps():
    square = [(0, 0, 3), (10, 0, 4), (10, 10, 5), (0, 10, 6)]
    (result,) = z.rect_clip(z.Rect64(0, 0, 5, 5), [square])
    # (0, 0) is a corner of both, so it keeps its z; the three others are new points
    assert sorted(tuple(point) for point in result.tolist()) == [
        (0, 0, 3),
        (0, 5, 0),
        (5, 0, 0),
        (5, 5, 0),
    ]
    (line,) = z.rect_clip_lines(z.Rect64(0, 0, 10, 10), [[(-5, 5, 8), (15, 5, 9)]])
    assert line.tolist() == [[0, 5, 0], [10, 5, 0]]  # both ends are new points


def test_triangulate_keeps_the_z_of_the_corners():
    square = [(0, 0, 1), (10, 0, 2), (10, 10, 3), (0, 10, 4)]
    result, solution = z.triangulate([square])
    assert result == clipper2.TriangulateResult.SUCCESS
    assert all(triangle.shape == (3, 3) for triangle in solution)
    # a square is cut into two triangles along a diagonal: every corner is an input vertex
    corners = {tuple(point) for triangle in solution for point in triangle.tolist()}
    assert corners == {(0, 0, 1), (10, 0, 2), (10, 10, 3), (0, 10, 4)}


def test_minkowski_carries_z_through():
    pattern = [(-1, -1, 7), (1, -1, 7), (1, 1, 7), (-1, 1, 7)]
    square = [(0, 0, 3), (10, 0, 3), (10, 10, 3), (0, 10, 3)]
    result = z.minkowski_sum(pattern, square, True)
    assert all(path.shape[1] == 3 for path in result)
    # upstream sums the two points, and its MinkowskiInternal keeps neither z: they are new
    assert {point[2] for path in result for point in path.tolist()} == {0}


def test_family_dependent_arguments_are_keyword_only():
    # Upstream's D overloads insert precision mid-list; a positional call would change meaning.
    square = [[(0, 0), (10, 0), (10, 10), (0, 10)]]
    with pytest.raises(TypeError):
        clipper2.inflate_paths(square, 1, clipper2.JoinType.MITER, clipper2.EndType.POLYGON, 2, 100)
    with pytest.raises(TypeError):
        clipper2.triangulate(square, True)
    with pytest.raises(TypeError):
        clipper2.trim_collinear(square[0], True)
    with pytest.raises(TypeError):
        clipper2.trim_collinear([(0.0, 0.0), (5.0, 0.0), (9.0, 9.0)], precision=True)
