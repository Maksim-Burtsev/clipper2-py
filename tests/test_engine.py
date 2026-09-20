"""Clipper64 / ClipperD, the PolyPath tree, GIL release and the z build's callbacks."""

import gc
import threading
import time
import traceback

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


def test_error_code_keeps_the_bit_upstream_set():
    # ScalePaths sets range_error_i on the clipper and then throws: the object survives
    # the exception and still reports what went wrong
    clipper = clipper2.ClipperD(2)
    with pytest.raises(clipper2.Clipper2Error, match="range"):
        clipper.add_subject([[(1e18, 1e18), (2e18, 1e18), (2e18, 2e18)]])
    assert clipper.error_code == clipper2.range_error_i == 64


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

    def serial_once():
        start = time.perf_counter()
        work()
        work()
        return time.perf_counter() - start

    def parallel_once():
        threads = [threading.Thread(target=work) for _ in range(2)]
        start = time.perf_counter()
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return time.perf_counter() - start

    work()  # warm up
    # Best of three: a loaded CI runner once put the ratio at 0.76 with the GIL released.
    serial = min(serial_once() for _ in range(3))
    parallel = min(parallel_once() for _ in range(3))

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


def test_every_cross_module_argument_is_guarded_in_both_directions():
    tree_64 = square_with_hole_tree()
    tree_d = clipper2.ClipperD().execute_tree(clipper2.ClipType.UNION, NON_ZERO)[0]
    z_tree_64 = z_square_tree()
    z_tree_d = z.ClipperD().execute_tree(z.ClipType.UNION, NON_ZERO)[0]
    for module, ours, theirs in ((clipper2, tree_64, z_tree_64), (z, z_tree_64, tree_64)):
        assert module.poly_tree_to_paths64(ours) is not None
        with pytest.raises(TypeError, match="PolyPath64"):
            module.poly_tree_to_paths64(theirs)
        assert module.check_polytree_fully_contains_children(ours) is not None
        with pytest.raises(TypeError, match="PolyPath64"):
            module.check_polytree_fully_contains_children(theirs)
    for module, ours, theirs in ((clipper2, tree_d, z_tree_d), (z, z_tree_d, tree_d)):
        assert module.poly_tree_to_paths_d(ours) == []
        with pytest.raises(TypeError, match="PolyPathD"):
            module.poly_tree_to_paths_d(theirs)
    for module, other in ((clipper2, z), (z, clipper2)):
        with pytest.raises(TypeError, match="ReuseableDataContainer64"):
            module.Clipper64().add_reuseable_data(other.ReuseableDataContainer64())


def z_square_tree():
    clipper = z.Clipper64()
    clipper.add_subject([[(0, 0, 1), (10, 0, 1), (10, 10, 1), (0, 10, 1)]])
    return clipper.execute_tree(z.ClipType.UNION, NON_ZERO)[0]


def test_polytree_d_is_a_polypath_like_the_64_one():
    clipper = clipper2.ClipperD(2)
    clipper.add_subject([[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]])
    clipper.add_subject([[(2.0, 2.0), (2.0, 8.0), (8.0, 8.0), (8.0, 2.0)]])
    tree, _ = clipper.execute_tree(clipper2.ClipType.UNION, EVEN_ODD)
    # upstream's PolyTreeD operator<< ends with one more endl than the 64 one, at level 0
    assert str(tree) == "\nPolytree with 1 polygon.\n  +- Polygon (0) contains 1 hole.\n\n\n\n"
    assert tree.parent is None and tree.level == 0 and tree.is_hole is False
    assert tree.scale == 1 / 128  # 2 ** (ilogb(10 ** 2) + 1)
    outer = tree.child(0)
    assert outer.level == 1 and outer.is_hole is False and outer.parent is tree
    assert outer.area() == 100.0 - 36.0
    hole = outer.child(0)
    assert hole.level == 2 and hole.is_hole is True and hole.area() == -36.0
    assert hole.scale == tree.scale
    with pytest.raises(IndexError):
        hole.child(0)
    with pytest.raises(IndexError):
        tree.child(1)


# --- the reuseable data container --------------------------------------------------------


def make_reuseable(paths=([SQUARE]), polytype=clipper2.PathType.SUBJECT, is_open=False):
    data = clipper2.ReuseableDataContainer64()
    data.add_paths(paths, polytype, is_open)
    return data


def test_a_container_that_python_no_longer_holds_stays_alive():
    # upstream keeps raw Vertex pointers into the container until the clipper is cleared
    clipper = clipper2.Clipper64()
    clipper.add_reuseable_data(make_reuseable())
    gc.collect()
    assert clipper2.area(clipper.execute(clipper2.ClipType.UNION, NON_ZERO)[0]) == 100.0
    clipper.clear()
    assert clipper.execute(clipper2.ClipType.UNION, NON_ZERO) == ([], [])


def test_reuseable_data_as_the_clip():
    # the 20 x 20 clip overlaps the 10 x 10 subject in a quarter of it: 100 - 25 one way
    # round, 400 - 25 the other, so this fails if subject and clip were swapped
    big = [(5, 5), (25, 5), (25, 25), (5, 25)]
    clipper = clipper2.Clipper64()
    clipper.add_subject([SQUARE])
    clipper.add_reuseable_data(make_reuseable([big], clipper2.PathType.CLIP))
    closed, _ = clipper.execute(clipper2.ClipType.DIFFERENCE, NON_ZERO)
    assert clipper2.area(closed) == 75.0


def test_reuseable_data_with_an_open_subject():
    clipper = clipper2.Clipper64()
    clipper.add_reuseable_data(
        make_reuseable([[(-5, 5), (15, 5)]], clipper2.PathType.SUBJECT, True)
    )
    clipper.add_clip([SQUARE])
    closed, open_paths = clipper.execute(clipper2.ClipType.INTERSECTION, NON_ZERO)
    assert closed == []
    assert vertices(open_paths) == [(0, 5), (10, 5)]


def test_reuseable_data_through_clipperd():
    # the container holds the scaled int64 vertices ClipperD works in, so its coordinates
    # come back divided by the clipper's scale of 128
    clipper = clipper2.ClipperD(2)
    clipper.add_reuseable_data(make_reuseable())
    (result,) = clipper.execute(clipper2.ClipType.UNION, NON_ZERO)[0]
    assert result.dtype == np.float64
    assert clipper2.area([result]) == 100.0 / 128**2


# --- an object that is executing is off limits (no C++ equivalent) -----------------------


def z_clipper_ready(callback):
    clipper = z.Clipper64()
    clipper.set_z_callback(callback)
    clipper.add_subject([[(0, 0, 1), (10, 0, 1), (10, 10, 1), (0, 10, 1)]])
    clipper.add_clip([[(5, 5, 2), (15, 5, 2), (15, 15, 2), (5, 15, 2)]])
    return clipper


def test_a_callback_may_not_touch_the_clipper_it_runs_in():
    clipper = z_clipper_ready(lambda *args: clipper.clear())
    with pytest.raises(RuntimeError, match="Clipper64 is executing"):
        clipper.execute(z.ClipType.INTERSECTION, NON_ZERO)
    # still alive and usable, with its paths still added
    clipper.set_z_callback(None)
    assert z.area(clipper.execute(z.ClipType.INTERSECTION, NON_ZERO)[0]) == 25.0


def test_a_callback_may_not_execute_the_clipper_again():
    clipper = z_clipper_ready(lambda *args: clipper.execute(z.ClipType.UNION, NON_ZERO))
    with pytest.raises(RuntimeError, match="Clipper64 is executing"):
        clipper.execute(z.ClipType.INTERSECTION, NON_ZERO)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c.add_subject([[(0, 0, 0), (1, 0, 0), (1, 1, 0)]]),
        lambda c: c.add_open_subject([[(0, 0, 0), (1, 1, 0)]]),
        lambda c: c.add_clip([[(0, 0, 0), (1, 0, 0), (1, 1, 0)]]),
        lambda c: c.add_reuseable_data(z.ReuseableDataContainer64()),
        lambda c: c.clear(),
        lambda c: c.set_z_callback(None),
        lambda c: setattr(c, "preserve_collinear", False),
        lambda c: setattr(c, "reverse_solution", True),
        lambda c: setattr(c, "default_z", 3),
        lambda c: c.execute_tree(z.ClipType.UNION, NON_ZERO),
    ],
)
def test_every_mutating_call_is_refused_while_executing(mutate):
    clipper = z_clipper_ready(lambda *args: mutate(clipper))
    with pytest.raises(RuntimeError, match="Clipper64 is executing"):
        clipper.execute(z.ClipType.INTERSECTION, NON_ZERO)
    # reads are still allowed
    clipper.set_z_callback(lambda *args: clipper.error_code + clipper.preserve_collinear)
    assert clipper.execute(z.ClipType.INTERSECTION, NON_ZERO)[0]


def test_another_thread_may_not_mutate_a_clipper_that_is_executing():
    inside = threading.Event()
    outcome = []

    def callback(*args):
        inside.set()
        time.sleep(0.2)  # the GIL is released around this, so the other thread runs
        return 7

    clipper = z_clipper_ready(callback)

    def intruder():
        inside.wait(5)
        try:
            clipper.add_subject([[(0, 0, 0), (1, 0, 0), (1, 1, 0)]])
            outcome.append(None)
        except Exception as error:  # noqa: BLE001 - the point of the test
            outcome.append(error)

    thread = threading.Thread(target=intruder)
    thread.start()
    result = clipper.execute(z.ClipType.INTERSECTION, NON_ZERO)[0]
    thread.join(5)

    assert z.area(result) == 25.0
    assert isinstance(outcome[0], RuntimeError) and "Clipper64 is executing" in str(outcome[0])


def test_clipperd_names_itself_in_the_message():
    clipper = z.ClipperD(2)
    clipper.set_z_callback(lambda *args: clipper.clear())
    clipper.add_subject([[(0.0, 0.0, 1), (10.0, 0.0, 1), (10.0, 10.0, 1), (0.0, 10.0, 1)]])
    clipper.add_clip([[(5.0, 5.0, 2), (15.0, 5.0, 2), (15.0, 15.0, 2), (5.0, 15.0, 2)]])
    with pytest.raises(RuntimeError, match="ClipperD is executing"):
        clipper.execute(z.ClipType.INTERSECTION, NON_ZERO)


# --- an exception in a callback is held until upstream has finished (deviation 8) --------


def boom(*args):
    raise ValueError("boom")


@pytest.mark.parametrize("method", ["execute", "execute_tree"])
def test_a_raising_z_callback_keeps_its_type_message_and_traceback(method):
    clipper = z_clipper_ready(boom)
    with pytest.raises(ValueError, match="boom") as raised:
        getattr(clipper, method)(z.ClipType.INTERSECTION, NON_ZERO)
    assert "boom" in [frame.name for frame in traceback.extract_tb(raised.value.__traceback__)]

    # reusable without clear(), with the paths still added
    clipper.set_z_callback(None)
    assert z.area(clipper.execute(z.ClipType.INTERSECTION, NON_ZERO)[0]) == 25.0


@pytest.mark.parametrize("method", ["execute", "execute_tree"])
def test_a_raising_z_callback_on_clipperd(method):
    clipper = z.ClipperD(2)
    clipper.set_z_callback(boom)
    clipper.add_subject([[(0.0, 0.0, 1), (10.0, 0.0, 1), (10.0, 10.0, 1), (0.0, 10.0, 1)]])
    clipper.add_clip([[(5.0, 5.0, 2), (15.0, 5.0, 2), (15.0, 15.0, 2), (5.0, 15.0, 2)]])
    with pytest.raises(ValueError, match="boom"):
        getattr(clipper, method)(z.ClipType.INTERSECTION, NON_ZERO)
    clipper.set_z_callback(None)
    assert z.area(clipper.execute(z.ClipType.INTERSECTION, NON_ZERO)[0]) == 25.0


def test_the_callback_is_not_called_again_after_it_raised():
    calls = []

    def once(*args):
        calls.append(args)
        raise ValueError("boom")

    clipper = z_clipper_ready(once)
    with pytest.raises(ValueError, match="boom"):
        clipper.execute(z.ClipType.INTERSECTION, NON_ZERO)
    assert len(calls) == 1  # the two crossings would both ask, were it still asked


@pytest.mark.parametrize(
    ("returns", "error"), [(lambda *a: 2**70, OverflowError), (lambda *a: None, TypeError)]
)
def test_what_the_z_callback_returns_must_be_an_int64(returns, error):
    clipper = z_clipper_ready(returns)
    with pytest.raises(error):
        clipper.execute(z.ClipType.INTERSECTION, NON_ZERO)
    clipper_d = z.ClipperD(2)
    clipper_d.set_z_callback(returns)
    clipper_d.add_subject([[(0.0, 0.0, 1), (10.0, 0.0, 1), (10.0, 10.0, 1), (0.0, 10.0, 1)]])
    clipper_d.add_clip([[(5.0, 5.0, 2), (15.0, 5.0, 2), (15.0, 15.0, 2), (5.0, 15.0, 2)]])
    with pytest.raises(error):
        clipper_d.execute(z.ClipType.INTERSECTION, NON_ZERO)


def test_default_z_is_what_the_callback_finds_on_the_new_point():
    seen = []
    clipper = z.Clipper64()
    clipper.default_z = 9
    clipper.set_z_callback(lambda e1b, e1t, e2b, e2t, pt: seen.append(pt[2]) or 42)
    clipper.add_subject([[(0, 0, 1), (10, 0, 1), (10, 10, 1), (0, 10, 1)]])
    clipper.add_clip([[(5, 5, 2), (15, 5, 2), (15, 15, 2), (5, 15, 2)]])
    (result,) = clipper.execute(z.ClipType.INTERSECTION, NON_ZERO)[0]
    assert seen == [9] * len(seen) and seen
    assert 42 in result[:, 2].tolist()


# --- z through the clipper (deviation 7) -------------------------------------------------


def test_z_survives_execute_tree_and_open_subjects():
    clipper = z.Clipper64()
    clipper.add_subject([[(0, 0, 5), (10, 0, 5), (10, 10, 5), (0, 10, 5)]])
    tree, open_paths = clipper.execute_tree(z.ClipType.UNION, NON_ZERO)
    assert open_paths == []
    assert tree[0].polygon.shape == (4, 3)
    assert sorted(tree[0].polygon[:, 2].tolist()) == [5, 5, 5, 5]

    clipper = z.Clipper64()
    clipper.add_open_subject([[(-5, 5, 3), (15, 5, 3)]])
    clipper.add_clip([[(0, 0, 4), (10, 0, 4), (10, 10, 4), (0, 10, 4)]])
    closed, open_paths = clipper.execute(z.ClipType.INTERSECTION, NON_ZERO)
    assert closed == []
    # the two ends are new points: without a callback upstream leaves them at default_z
    assert open_paths[0].shape == (2, 3)
    assert open_paths[0][:, 2].tolist() == [0, 0]


def test_z_survives_the_named_boolean_operations():
    subject = [[(0, 0, 1), (10, 0, 1), (10, 10, 1), (0, 10, 1)]]
    clip = [[(5, 5, 2), (15, 5, 2), (15, 15, 2), (5, 15, 2)]]
    # the overlap is the square (5, 5) - (10, 10): (5, 5) is a clip vertex, (10, 10) a
    # subject one, and the two crossings are new points, left at default_z 0
    assert vertices(z.intersect(subject, clip, NON_ZERO)) == [
        (5, 5, 2),
        (5, 10, 0),
        (10, 5, 0),
        (10, 10, 1),
    ]
    # the subject with that corner taken out
    assert vertices(z.difference(subject, clip, NON_ZERO)) == [
        (0, 0, 1),
        (0, 10, 1),
        (5, 5, 2),
        (5, 10, 0),
        (10, 0, 1),
        (10, 5, 0),
    ]
    for operation in (z.xor, z.union):
        result = operation(subject, clip, NON_ZERO)
        assert all(path.shape[1] == 3 for path in result)
        kept = {tuple(point) for path in result for point in path.tolist()}
        assert {(0, 0, 1), (15, 15, 2)} <= kept
    tree = z.boolean_op_tree(z.ClipType.UNION, NON_ZERO, subject, clip)
    assert tree[0].polygon.shape[1] == 3
    assert 1 in tree[0].polygon[:, 2].tolist()
