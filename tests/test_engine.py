"""Clipper64 / ClipperD, the PolyPath tree, GIL release and the z build's callbacks."""

import gc
import threading
import time

import numpy as np
import pytest

import clipper2
import clipper2.z as z

SQUARE = [(0, 0), (10, 0), (10, 10), (0, 10)]
HOLE = [(2, 2), (2, 8), (8, 8), (8, 2)]
NON_ZERO = clipper2.FillRule.NON_ZERO
EVEN_ODD = clipper2.FillRule.EVEN_ODD


def vertices(paths):
    return sorted(tuple(pt) for path in paths for pt in path.tolist())


# --- Clipper64 / ClipperD -------------------------------------------------------------


def test_execute_returns_closed_and_open_paths():
    clipper = clipper2.Clipper64()
    clipper.add_subject([SQUARE])
    clipper.add_clip([[(5, 5), (15, 5), (15, 15), (5, 15)]])
    closed, open_paths = clipper.execute(clipper2.ClipType.INTERSECTION, NON_ZERO)
    assert open_paths == []
    assert vertices(closed) == [(5, 5), (5, 10), (10, 5), (10, 10)]


def test_open_subjects_come_back_as_open_paths():
    clipper = clipper2.Clipper64()
    clipper.add_open_subject([[(-5, 5), (15, 5)]])
    clipper.add_clip([SQUARE])
    closed, open_paths = clipper.execute(clipper2.ClipType.INTERSECTION, NON_ZERO)
    assert closed == []
    assert vertices(open_paths) == [(0, 5), (10, 5)]


def test_clear_forgets_the_added_paths():
    clipper = clipper2.Clipper64()
    clipper.add_subject([SQUARE])
    clipper.clear()
    assert clipper.execute(clipper2.ClipType.UNION, NON_ZERO) == ([], [])


def test_preserve_collinear_property():
    path = [(0, 0), (5, 0), (10, 0), (10, 10), (0, 10)]
    clipper = clipper2.Clipper64()
    assert clipper.preserve_collinear is True  # upstream's default
    clipper.add_subject([path])
    assert len(clipper.execute(clipper2.ClipType.UNION, NON_ZERO)[0][0]) == 5

    clipper = clipper2.Clipper64()
    clipper.preserve_collinear = False
    clipper.add_subject([path])
    assert len(clipper.execute(clipper2.ClipType.UNION, NON_ZERO)[0][0]) == 4


def test_reverse_solution_property():
    clipper = clipper2.Clipper64()
    assert clipper.reverse_solution is False
    clipper.reverse_solution = True
    clipper.add_subject([SQUARE])
    assert clipper2.area(clipper.execute(clipper2.ClipType.UNION, NON_ZERO)[0]) == -100.0


def test_error_code_is_zero_while_nothing_failed():
    clipper = clipper2.Clipper64()
    assert clipper.error_code == 0
    clipper.add_subject([SQUARE])
    clipper.execute(clipper2.ClipType.UNION, NON_ZERO)
    assert clipper.error_code == 0
    with pytest.raises(AttributeError):
        clipper.error_code = 1


def test_clipperd_precision():
    # upstream rounds to a power of two: precision 0 gives a scale of 2
    clipper = clipper2.ClipperD(0)
    clipper.add_subject([[(0.4, 0.4), (10.6, 0.4), (10.6, 10.6), (0.4, 10.6)]])
    (result,) = clipper.execute(clipper2.ClipType.UNION, NON_ZERO)[0]
    assert vertices([result]) == [(0.5, 0.5), (0.5, 10.5), (10.5, 0.5), (10.5, 10.5)]
    with pytest.raises(clipper2.Clipper2Error, match="Precision"):
        clipper2.ClipperD(99)


def test_reuseable_data_container():
    data = clipper2.ReuseableDataContainer64()
    data.add_paths([SQUARE], clipper2.PathType.SUBJECT, False)
    clipper = clipper2.Clipper64()
    clipper.add_reuseable_data(data)
    assert clipper2.area(clipper.execute(clipper2.ClipType.UNION, NON_ZERO)[0]) == 100.0
    data.clear()
    clipper = clipper2.Clipper64()
    clipper.add_reuseable_data(data)
    assert clipper.execute(clipper2.ClipType.UNION, NON_ZERO) == ([], [])


# --- PolyPath / PolyTree ---------------------------------------------------------------


def square_with_hole_tree():
    clipper = clipper2.Clipper64()
    clipper.add_subject([SQUARE, HOLE])
    tree, open_paths = clipper.execute_tree(clipper2.ClipType.UNION, EVEN_ODD)
    assert open_paths == []
    return tree


def test_polytree_structure():
    tree = square_with_hole_tree()
    assert len(tree) == 1
    assert tree.level == 0
    assert tree.is_hole is False
    assert tree.parent is None
    assert tree.polygon.shape == (0, 2)  # the root holds no polygon
    assert tree.area() == 64.0  # 100 - 36

    outer = tree.child(0)
    assert outer is tree[0]
    assert outer.level == 1 and outer.is_hole is False
    assert vertices([outer.polygon]) == [(0, 0), (0, 10), (10, 0), (10, 10)]
    assert outer.area() == 64.0

    hole = outer[0]
    assert hole.level == 2 and hole.is_hole is True
    assert hole.area() == -36.0
    assert hole.parent is outer


def test_polytree_iteration_and_indexing():
    tree = square_with_hole_tree()
    assert [child.is_hole for child in tree] == [False]
    assert [grandchild.is_hole for grandchild in tree[0]] == [True]
    assert len(list(tree)) == 1
    with pytest.raises(IndexError):
        tree.child(1)
    with pytest.raises(IndexError):
        tree[-1]  # upstream has no negative indexing


def test_polytree_text():
    tree = square_with_hole_tree()
    assert str(tree) == (
        "\nPolytree with 1 polygon.\n  +- Polygon (0) contains 1 hole.\n\n\n"
    )
    assert repr(tree).startswith("<PolyPath64 with 1 child(ren)")


def test_a_child_keeps_the_tree_alive():
    child = square_with_hole_tree()[0]
    gc.collect()
    assert vertices([child.polygon]) == [(0, 0), (0, 10), (10, 0), (10, 10)]
    grandchild = child[0]
    del child
    gc.collect()
    assert grandchild.area() == -36.0
    assert grandchild.parent.area() == 64.0


def test_polytree_d_scale():
    clipper = clipper2.ClipperD(2)
    clipper.add_subject([[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]])
    tree, _ = clipper.execute_tree(clipper2.ClipType.UNION, NON_ZERO)
    assert isinstance(tree, clipper2.PolyPathD)
    # ClipperD's scale is a power of two: 2 ** (ilogb(10 ** 2) + 1) == 128
    assert tree.scale == 1 / 128
    assert tree[0].polygon.dtype == np.float64
    assert tree.area() == 100.0


def test_polytree_is_read_only():
    tree = square_with_hole_tree()
    for name in ("add_child", "set_scale", "Clear"):
        assert not hasattr(tree, name)
    with pytest.raises(AttributeError):
        tree.polygon = np.zeros((1, 2))


# --- the GIL (decision 12) -------------------------------------------------------------


def test_execute_releases_the_gil():
    rng = np.random.default_rng(0)
    subjects = [rng.integers(-1000, 1000, size=(100, 2)) for _ in range(12)]
    clips = [rng.integers(-1000, 1000, size=(100, 2)) for _ in range(12)]

    def work():
        clipper = clipper2.Clipper64()
        clipper.add_subject(subjects)
        clipper.add_clip(clips)
        clipper.execute(clipper2.ClipType.INTERSECTION, NON_ZERO)

    work()  # warm up
    start = time.perf_counter()
    work()
    work()
    serial = time.perf_counter() - start

    threads = [threading.Thread(target=work) for _ in range(2)]
    start = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    parallel = time.perf_counter() - start

    assert parallel < serial * 0.75, f"serial {serial:.3f}s, parallel {parallel:.3f}s"


# --- the z build ------------------------------------------------------------------------


def test_z_callback_sets_z_on_new_points():
    seen = []

    def callback(e1bot, e1top, e2bot, e2top, pt):
        seen.append((e1bot, e1top, e2bot, e2top, pt))
        return 99

    clipper = z.Clipper64()
    clipper.set_z_callback(callback)
    clipper.add_subject([[(0, 0, 1), (10, 0, 1), (10, 10, 1), (0, 10, 1)]])
    clipper.add_clip([[(5, 5, 2), (15, 5, 2), (15, 15, 2), (5, 15, 2)]])
    (result,) = clipper.execute(z.ClipType.INTERSECTION, NON_ZERO)[0]

    assert seen, "the callback was never called"
    assert all(len(point) == 3 for call in seen for point in call)
    by_xy = {(x, y): zz for x, y, zz in result.tolist()}
    assert by_xy[(10, 10)] == 1  # an original subject vertex keeps its z
    assert by_xy[(5, 5)] == 2  # an original clip vertex keeps its z
    assert by_xy[(5, 10)] == 99  # a new intersection point gets the callback's value
    assert by_xy[(10, 5)] == 99


def test_z_callback_on_clipperd_gets_descaled_points():
    def callback(e1bot, e1top, e2bot, e2top, pt):
        assert all(isinstance(coordinate, float) for coordinate in pt[:2])
        assert isinstance(pt[2], int)
        return 77

    clipper = z.ClipperD(2)
    clipper.set_z_callback(callback)
    clipper.add_subject([[(0.0, 0.0, 1), (10.0, 0.0, 1), (10.0, 10.0, 1), (0.0, 10.0, 1)]])
    clipper.add_clip([[(5.0, 5.0, 2), (15.0, 5.0, 2), (15.0, 15.0, 2), (5.0, 15.0, 2)]])
    (result,) = clipper.execute(z.ClipType.INTERSECTION, NON_ZERO)[0]
    assert result.dtype == np.float64
    assert {(x, y): zz for x, y, zz in result.tolist()}[(5.0, 10.0)] == 77.0


def test_an_exception_in_a_callback_propagates_out_of_execute():
    def boom(*args):
        raise ValueError("boom")

    clipper = z.Clipper64()
    clipper.set_z_callback(boom)
    clipper.add_subject([[(0, 0, 1), (10, 0, 1), (10, 10, 1), (0, 10, 1)]])
    clipper.add_clip([[(5, 5, 2), (15, 5, 2), (15, 15, 2), (5, 15, 2)]])
    with pytest.raises(ValueError, match="boom"):
        clipper.execute(z.ClipType.INTERSECTION, NON_ZERO)

    # the clipper is left as after a normal execute: usable, its paths still added
    clipper.set_z_callback(None)
    assert z.area(clipper.execute(z.ClipType.INTERSECTION, NON_ZERO)[0]) == 25.0


def test_z_callback_must_return_an_integer():
    clipper = z.Clipper64()
    clipper.set_z_callback(lambda *args: 1.5)
    clipper.add_subject([[(0, 0, 1), (10, 0, 1), (10, 10, 1), (0, 10, 1)]])
    clipper.add_clip([[(5, 5, 2), (15, 5, 2), (15, 15, 2), (5, 15, 2)]])
    with pytest.raises(TypeError):
        clipper.execute(z.ClipType.INTERSECTION, NON_ZERO)


def test_default_z_is_exposed_only_in_the_z_build():
    assert z.Clipper64().default_z == 0
    clipper = z.Clipper64()
    clipper.default_z = 5
    assert clipper.default_z == 5
    assert not hasattr(clipper2.Clipper64(), "default_z")
    assert not hasattr(clipper2.Clipper64(), "set_z_callback")


def test_the_two_modules_have_separate_classes():
    # Clipper64 has a different Point layout in each build, so the classes are module-local
    assert clipper2.Clipper64 is not z.Clipper64
    with pytest.raises(TypeError):
        z.poly_tree_to_paths64(square_with_hole_tree())
