"""ClipperOffset and inflate_paths: the binding's own surface.

Expected geometry is reasoned from what offsetting means, never read back from the binding:
a 10x10 square inflated by 1 with miter joins is the 12x12 square, and so on.  Exact equality
with upstream over random input is the differential test's job (tests/reference).
"""

import gc
import threading
import time
import traceback

import numpy as np
import pytest

import clipper2
import clipper2.z as z

SQUARE = [(0, 0), (10, 0), (10, 10), (0, 10)]
SQUARE_D = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
MITER = clipper2.JoinType.MITER
ROUND = clipper2.JoinType.ROUND
POLYGON = clipper2.EndType.POLYGON
BUTT = clipper2.EndType.BUTT
SQUARE_END = clipper2.EndType.SQUARE


def vertices(paths):
    return sorted(tuple(pt) for path in paths for pt in path.tolist())


def offsetter(paths=(SQUARE,), join=MITER, end=POLYGON, **kwargs):
    off = clipper2.ClipperOffset(**kwargs)
    off.add_paths(paths, join, end)
    return off


# --- inflate_paths ----------------------------------------------------------------------


def test_inflate_paths_miter_grows_the_square_by_delta():
    (result,) = clipper2.inflate_paths([SQUARE], 1.0, MITER, POLYGON)
    assert result.dtype == np.int64
    assert vertices([result]) == [(-1, -1), (-1, 11), (11, -1), (11, 11)]


def test_inflate_paths_negative_delta_shrinks():
    (result,) = clipper2.inflate_paths([SQUARE], -1.0, MITER, POLYGON)
    assert vertices([result]) == [(1, 1), (1, 9), (9, 1), (9, 9)]


def test_inflate_paths_zero_delta_returns_the_input():
    # upstream: "if (!delta) return paths;"
    assert vertices(clipper2.inflate_paths([SQUARE], 0.0, MITER, POLYGON)) == vertices(
        [np.asarray(SQUARE)]
    )


def test_inflate_paths_open_end_types():
    line = [(0, 0), (10, 0)]
    # BUTT offsets both sides and stops at the ends: a 10 x 2 rectangle
    assert clipper2.area(clipper2.inflate_paths([line], 1.0, MITER, BUTT)) == 20.0
    # SQUARE extends both ends by delta: 12 x 2
    assert clipper2.area(clipper2.inflate_paths([line], 1.0, MITER, SQUARE_END)) == 24.0


def test_inflate_paths_dispatches_on_dtype():
    (as_64,) = clipper2.inflate_paths([SQUARE], 1.0, MITER, POLYGON)
    (as_d,) = clipper2.inflate_paths([SQUARE_D], 1.0, MITER, POLYGON)
    assert as_64.dtype == np.int64 and as_d.dtype == np.float64
    assert vertices([as_d]) == [(-1.0, -1.0), (-1.0, 11.0), (11.0, -1.0), (11.0, 11.0)]


def test_inflate_paths_defaults_are_upstreams():
    # miter_limit 2.0, arc_tolerance 0.0, and precision 2 for the D family
    assert vertices(clipper2.inflate_paths([SQUARE], 1.0, MITER, POLYGON)) == vertices(
        clipper2.inflate_paths([SQUARE], 1.0, MITER, POLYGON, miter_limit=2.0, arc_tolerance=0.0)
    )
    assert vertices(clipper2.inflate_paths([SQUARE_D], 1.0, ROUND, POLYGON)) == vertices(
        clipper2.inflate_paths([SQUARE_D], 1.0, ROUND, POLYGON, precision=2)
    )


def test_miter_limit_default_of_two_clips_a_spike():
    # a 30 degree corner: its miter reaches 1 / sin(15 deg) = 3.9 times the offset, so a
    # miter_limit of 2 squares the join off and one of 10 lets it through
    spike = [(0, 0), (1000, -268), (1000, 268)]

    def area(**kwargs):
        return abs(clipper2.area(clipper2.inflate_paths([spike], 50.0, MITER, POLYGON, **kwargs)))

    assert area() == area(miter_limit=2.0) < area(miter_limit=10.0)


def test_arc_tolerance_controls_the_number_of_arc_steps():
    big = [(0, 0), (1000, 0), (1000, 1000), (0, 1000)]
    (fine,) = clipper2.inflate_paths([big], 100.0, ROUND, POLYGON)
    (coarse,) = clipper2.inflate_paths([big], 100.0, ROUND, POLYGON, arc_tolerance=50.0)
    assert len(coarse) < len(fine)
    # rounded corners: more than the square's 1_000_000 + 4 * 1000 * 100 of straight offset,
    # less than the 1200 x 1200 the miter join would give
    assert 1_400_000 < clipper2.area([fine]) < 1_440_000


def test_precision_belongs_to_the_d_family_only():
    with pytest.raises(TypeError, match="precision"):
        clipper2.inflate_paths([SQUARE], 1.0, MITER, POLYGON, precision=3)
    assert clipper2.inflate_paths([SQUARE_D], 1.0, MITER, POLYGON, precision=0)


def test_inflate_paths_rejects_bad_geometry():
    with pytest.raises(ValueError):
        clipper2.inflate_paths([[(0, 0, 0, 0)]], 1.0, MITER, POLYGON)
    with pytest.raises(TypeError):
        clipper2.inflate_paths([[("a", "b")]], 1.0, MITER, POLYGON)


# --- ClipperOffset ----------------------------------------------------------------------


def test_properties_default_to_upstreams_constructor_arguments():
    off = clipper2.ClipperOffset()
    assert off.miter_limit == 2.0
    assert off.arc_tolerance == 0.0
    assert off.preserve_collinear is False
    assert off.reverse_solution is False

    off = clipper2.ClipperOffset(3.0, 0.25, True, True)
    assert (off.miter_limit, off.arc_tolerance) == (3.0, 0.25)
    assert off.preserve_collinear is True and off.reverse_solution is True

    off = clipper2.ClipperOffset(miter_limit=4.0, reverse_solution=True)
    assert off.miter_limit == 4.0 and off.arc_tolerance == 0.0
    off.miter_limit = 5.0
    off.arc_tolerance = 1.0
    off.preserve_collinear = True
    off.reverse_solution = False
    assert (off.miter_limit, off.arc_tolerance) == (5.0, 1.0)
    assert off.preserve_collinear is True and off.reverse_solution is False


def test_error_code_is_read_only_and_zero_while_nothing_failed():
    off = offsetter()
    assert off.error_code == 0
    off.execute(1.0)
    assert off.error_code == 0
    with pytest.raises(AttributeError):
        off.error_code = 1


def test_add_path_and_add_paths():
    one = clipper2.ClipperOffset()
    one.add_path(SQUARE, MITER, POLYGON)
    many = offsetter([SQUARE])
    assert vertices(one.execute(1.0)) == vertices(many.execute(1.0))
    keywords = clipper2.ClipperOffset()
    keywords.add_path(path=SQUARE, jt_=MITER, et_=POLYGON)  # upstream's parameter names
    assert vertices(keywords.execute(1.0)) == vertices(one.execute(1.0))


def test_clear_forgets_the_added_paths():
    off = offsetter()
    off.clear()
    assert off.execute(1.0) == []


def test_reverse_solution_flips_the_orientation():
    assert clipper2.area(offsetter().execute(1.0)) == 144.0
    assert clipper2.area(offsetter(reverse_solution=True).execute(1.0)) == -144.0


def test_preserve_collinear_keeps_the_extra_vertex():
    path = [(0, 0), (5, 0), (10, 0), (10, 10), (0, 10)]
    assert len(offsetter([path]).execute(1.0)[0]) == 4
    assert len(offsetter([path], preserve_collinear=True).execute(1.0)[0]) == 5


def test_clipper_offset_is_64_only():
    off = clipper2.ClipperOffset()
    with pytest.raises(TypeError, match="64 family"):
        off.add_paths([SQUARE_D], MITER, POLYGON)
    with pytest.raises(TypeError, match="64 family"):
        off.add_path(SQUARE_D, MITER, POLYGON)


def test_execute_tree_returns_a_polytree():
    tree = offsetter().execute_tree(1.0)
    assert isinstance(tree, clipper2.PolyTree64)
    assert len(tree) == 1
    assert tree.area() == 144.0
    assert vertices([tree[0].polygon]) == [(-1, -1), (-1, 11), (11, -1), (11, 11)]


def test_a_child_of_an_offset_tree_keeps_the_tree_alive():
    child = offsetter().execute_tree(1.0)[0]
    gc.collect()
    assert child.area() == 144.0
    assert child.parent.area() == 144.0


def test_execute_rejects_something_that_is_neither_a_number_nor_a_callable():
    with pytest.raises(TypeError):
        offsetter().execute("1.0")


def test_execute_none_is_upstreams_execute_with_a_null_callback():
    # in C++ nullptr converts to DeltaCallback64, not to double: the callback is cleared and
    # the offset runs with a delta of 1.0
    off = offsetter()
    off.set_delta_callback(lambda *args: 5.0)
    assert vertices(off.execute(None)) == [(-1, -1), (-1, 11), (11, -1), (11, 11)]


# --- the delta callback -----------------------------------------------------------------


def test_delta_callback_receives_the_path_and_its_normals():
    seen = []

    def callback(path, path_normals, curr_idx, prev_idx):
        seen.append((path, path_normals, curr_idx, prev_idx))
        return 1.0

    result = offsetter().execute(callback)
    assert vertices(result) == [(-1, -1), (-1, 11), (11, -1), (11, 11)]

    assert seen, "the callback was never called"
    for path, normals, curr_idx, prev_idx in seen:
        assert path.dtype == np.int64 and path.tolist() == [list(pt) for pt in SQUARE]
        assert normals.dtype == np.float64 and normals.shape == path.shape
        # upstream's normals are unit vectors, one per edge
        assert np.allclose(np.hypot(normals[:, 0], normals[:, 1]), 1.0)
        assert isinstance(curr_idx, int) and isinstance(prev_idx, int)
        assert 0 <= curr_idx < len(path) and 0 <= prev_idx < len(path)


def test_the_delta_callback_stays_set_as_upstream_leaves_it():
    calls = []
    off = offsetter()
    off.execute(lambda *args: calls.append(args) or 1.0)
    before = len(calls)
    off.execute(5.0)  # upstream's Execute(cb, ...) assigns the callback for good
    assert len(calls) > before

    off.set_delta_callback(None)
    assert vertices(off.execute(5.0)) == [(-5, -5), (-5, 15), (15, -5), (15, 15)]


def test_set_delta_callback_offsets_by_the_returned_delta():
    off = offsetter()
    off.set_delta_callback(lambda path, normals, curr, prev: 2.0)
    assert vertices(off.execute(1.0)) == [(-2, -2), (-2, 12), (12, -2), (12, 12)]


def test_an_exception_in_the_delta_callback_propagates_out_of_execute():
    def boom(*args):
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        offsetter().execute(boom)


def test_the_delta_callback_must_return_a_number():
    with pytest.raises(TypeError):
        offsetter().execute(lambda *args: "wide")


# --- the z build ------------------------------------------------------------------------


def test_z_build_offsets_three_column_paths():
    off = z.ClipperOffset()
    off.add_paths([[(0, 0, 7), (10, 0, 7), (10, 10, 7), (0, 10, 7)]], MITER, POLYGON)
    (result,) = off.execute(1.0)
    assert result.shape == (4, 3)
    # upstream gives every offset point the z of the vertex it came from
    assert sorted(result[:, 2].tolist()) == [7, 7, 7, 7]
    (inflated,) = z.inflate_paths(
        [[(0, 0, 7), (10, 0, 7), (10, 10, 7), (0, 10, 7)]], 1.0, MITER, POLYGON
    )
    assert inflated.tolist() == result.tolist()


def test_z_callback_fills_in_new_points():
    # two overlapping squares with different z: where their outlines cross, upstream's
    # ClipperOffset::ZCB finds no matching z and asks the callback
    paths = [
        [(0, 0, 1), (10, 0, 1), (10, 10, 1), (0, 10, 1)],
        [(5, 5, 2), (15, 5, 2), (15, 15, 2), (5, 15, 2)],
    ]
    seen = []

    off = z.ClipperOffset()
    off.set_z_callback(lambda *args: seen.append(args) or 42)
    off.add_paths(paths, MITER, POLYGON)
    (result,) = off.execute(1.0)

    assert seen, "the callback was never called"
    assert all(len(point) == 3 for call in seen for point in call)
    assert 42 in result[:, 2].tolist()


def test_an_exception_in_the_z_callback_propagates():
    def boom(*args):
        raise ValueError("boom")

    off = z.ClipperOffset()
    off.set_z_callback(boom)
    off.add_paths(
        [
            [(0, 0, 1), (10, 0, 1), (10, 10, 1), (0, 10, 1)],
            [(5, 5, 2), (15, 5, 2), (15, 15, 2), (5, 15, 2)],
        ],
        MITER,
        POLYGON,
    )
    with pytest.raises(ValueError, match="boom"):
        off.execute(1.0)


def test_the_callback_delta_replaces_the_one_execute_was_given():
    # upstream's Execute(DeltaCallback64, ...) offsets with a delta of 1.0, which the
    # callback then overrides: a 10 x 10 square mitred out by 3 is the 16 x 16 square
    assert vertices(offsetter().execute(lambda *args: 3.0)) == [
        (-3, -3),
        (-3, 13),
        (13, -3),
        (13, 13),
    ]


def test_a_child_index_outside_an_offset_tree_is_an_index_error():
    tree = offsetter().execute_tree(1.0)
    with pytest.raises(IndexError):
        tree.child(1)
    with pytest.raises(IndexError):
        tree[-1]
    with pytest.raises(IndexError):
        tree[0].child(0)


def test_inflate_paths_precision_cannot_be_passed_by_position():
    with pytest.raises(TypeError):
        clipper2.inflate_paths(SQUARE_D, 1, MITER, POLYGON, 2.0, 2)


# --- an offsetter that is executing is off limits (no C++ equivalent) --------------------


@pytest.mark.parametrize(
    "mutate",
    [
        lambda off: off.clear(),
        lambda off: off.add_path(SQUARE, MITER, POLYGON),
        lambda off: off.add_paths([SQUARE], MITER, POLYGON),
        lambda off: off.execute(1.0),
        lambda off: off.execute_tree(1.0),
        lambda off: off.set_delta_callback(None),
        lambda off: setattr(off, "miter_limit", 3.0),
        lambda off: setattr(off, "arc_tolerance", 1.0),
        lambda off: setattr(off, "preserve_collinear", True),
        lambda off: setattr(off, "reverse_solution", True),
    ],
)
def test_the_delta_callback_may_not_touch_the_offsetter(mutate):
    off = offsetter()
    off.set_delta_callback(lambda *args: mutate(off) or 1.0)
    with pytest.raises(RuntimeError, match="ClipperOffset is executing"):
        off.execute(1.0)
    # alive and usable afterwards; reads were allowed all along
    off.set_delta_callback(lambda *args: 1.0 + off.error_code + off.arc_tolerance)
    assert clipper2.area(off.execute(1.0)) == 144.0


def test_another_thread_may_not_mutate_an_offsetter_that_is_executing():
    inside = threading.Event()
    outcome = []

    def callback(*args):
        inside.set()
        time.sleep(0.2)
        return 1.0

    off = offsetter()

    def intruder():
        inside.wait(5)
        try:
            off.add_path(SQUARE, MITER, POLYGON)
            outcome.append(None)
        except Exception as error:  # noqa: BLE001 - the point of the test
            outcome.append(error)

    thread = threading.Thread(target=intruder)
    thread.start()
    result = off.execute(callback)
    thread.join(5)

    assert clipper2.area(result) == 144.0
    assert isinstance(outcome[0], RuntimeError)


# --- an exception in a callback is held until upstream has finished (deviation 8) --------


def boom(*args):
    raise ValueError("boom")


def test_a_raising_delta_callback_leaves_a_usable_offsetter():
    off = offsetter()
    with pytest.raises(ValueError, match="boom") as raised:
        off.execute(boom)
    assert "boom" in [frame.name for frame in traceback.extract_tb(raised.value.__traceback__)]
    # upstream leaves the callback set, but the paths are still there
    off.set_delta_callback(None)
    assert clipper2.area(off.execute(1.0)) == 144.0


def test_a_raising_delta_callback_in_execute_tree():
    off = offsetter()
    off.set_delta_callback(boom)
    with pytest.raises(ValueError, match="boom"):
        off.execute_tree(1.0)
    off.set_delta_callback(None)
    assert off.execute_tree(1.0).area() == 144.0


def test_the_delta_callback_is_not_called_again_after_it_raised():
    calls = []

    def once(*args):
        calls.append(args)
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        offsetter().execute(once)
    assert len(calls) == 1  # a square asks once per vertex


def z_offsetter(callback):
    off = z.ClipperOffset()
    off.set_z_callback(callback)
    off.add_paths(
        [
            [(0, 0, 1), (10, 0, 1), (10, 10, 1), (0, 10, 1)],
            [(5, 5, 2), (15, 5, 2), (15, 15, 2), (5, 15, 2)],
        ],
        MITER,
        POLYGON,
    )
    return off


def test_a_raising_z_callback_leaves_a_usable_offsetter():
    off = z_offsetter(boom)
    with pytest.raises(ValueError, match="boom"):
        off.execute(1.0)
    with pytest.raises(ValueError, match="boom"):
        off.execute_tree(1.0)
    off.set_z_callback(None)
    assert z.area(off.execute(1.0)) > 0.0


def test_a_z_callback_may_not_touch_the_offsetter_it_runs_in():
    off = z_offsetter(None)
    off.set_z_callback(lambda *args: off.clear())
    with pytest.raises(RuntimeError, match="ClipperOffset is executing"):
        off.execute(1.0)
    off.set_z_callback(None)
    assert z.area(off.execute(1.0)) > 0.0


@pytest.mark.parametrize(
    ("returns", "error"), [(lambda *a: 2**70, OverflowError), (lambda *a: None, TypeError)]
)
def test_what_the_offsets_z_callback_returns_must_be_an_int64(returns, error):
    with pytest.raises(error):
        z_offsetter(returns).execute(1.0)


def test_the_z_callback_exists_only_in_the_z_build():
    assert not hasattr(clipper2.ClipperOffset(), "set_z_callback")
    assert hasattr(z.ClipperOffset(), "set_z_callback")
    assert clipper2.ClipperOffset is not z.ClipperOffset
