"""Conversion layer: dtype dispatch, validation, empty inputs, array shapes."""

import numpy as np
import pytest

import clipper2
import clipper2.z as z

SQUARE = [(0, 0), (10, 0), (10, 10), (0, 10)]
SQUARE_D = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
NON_ZERO = clipper2.FillRule.NON_ZERO


# --- family chosen by the dtype numpy.asarray infers (decision 4) ----------------------


@pytest.mark.parametrize(
    "paths",
    [
        [SQUARE],
        [[list(p) for p in SQUARE]],
        [np.array(SQUARE, dtype=np.int64)],
        [np.array(SQUARE, dtype=np.int32)],
        [np.array(SQUARE, dtype=np.uint16)],
        np.array([SQUARE], dtype=np.int64),
    ],
)
def test_integer_input_gives_the_64_family(paths):
    (result,) = clipper2.union(paths, NON_ZERO)
    assert result.dtype == np.int64
    assert result.shape == (4, 2)


@pytest.mark.parametrize(
    "paths",
    [
        [SQUARE_D],
        [np.array(SQUARE, dtype=np.float32)],
        [np.array(SQUARE, dtype=np.float64)],
        [[(0, 0), (10, 0), (10, 10), (0, 10.0)]],  # one float promotes the whole argument
    ],
)
def test_float_input_gives_the_d_family(paths):
    (result,) = clipper2.union(paths, NON_ZERO)
    assert result.dtype == np.float64
    assert result.shape == (4, 2)


def test_mixing_families_in_one_call_is_a_type_error():
    with pytest.raises(TypeError, match="same family"):
        clipper2.intersect([SQUARE], [SQUARE_D], NON_ZERO)
    with pytest.raises(TypeError, match="same family"):
        clipper2.point_in_polygon((0.5, 0.5), SQUARE)


def test_empty_input_takes_the_family_of_the_other_arguments():
    assert clipper2.intersect([], [], NON_ZERO) == []
    # 64 family when nothing else says otherwise
    assert clipper2.union([], NON_ZERO) == []
    (result,) = clipper2.union([SQUARE_D], [], NON_ZERO)
    assert result.dtype == np.float64
    (result,) = clipper2.union([], [SQUARE], NON_ZERO)
    assert result.dtype == np.int64


def test_empty_paths_and_empty_path():
    assert clipper2.area([]) == 0.0
    assert clipper2.length([]) == 0.0
    assert clipper2.union([[]], NON_ZERO) == []


def test_a_float_array_is_rejected_by_the_64_family():
    with pytest.raises(TypeError, match="integer coordinates"):
        clipper2.Clipper64().add_subject([SQUARE_D])
    with pytest.raises(TypeError, match="integer coordinates"):
        clipper2.make_path([0.0, 0.0, 1.0, 1.0])


def test_an_integer_array_is_accepted_by_the_d_family():
    # int -> double is the safe direction (decision 4)
    clipper = clipper2.ClipperD()
    clipper.add_subject([SQUARE])
    (result,) = clipper.execute(clipper2.ClipType.UNION, NON_ZERO)[0]
    assert result.dtype == np.float64


# --- validation C++ gets from its compiler (decision 5) -------------------------------


@pytest.mark.parametrize(
    "path",
    [
        [(0, 0, 0), (1, 1, 1), (2, 2, 2)],  # N*3 has no meaning without USINGZ
        [0, 1, 2, 3],  # flat
        np.zeros((3, 0), dtype=np.int64),
        np.zeros((3, 4), dtype=np.int64),
    ],
)
def test_wrong_shape_is_a_value_error(path):
    with pytest.raises(ValueError):
        clipper2.area(path)


def test_wrong_point_shape_is_a_value_error():
    with pytest.raises(ValueError, match="point"):
        clipper2.point_in_polygon((1, 2, 3), SQUARE)
    with pytest.raises(ValueError, match="point"):
        clipper2.distance((1,), (2,))


def test_integers_outside_int64_overflow():
    with pytest.raises(OverflowError):
        clipper2.area([(2**70, 0), (1, 1), (2, 2)])
    with pytest.raises(OverflowError):
        clipper2.area(np.array([[2**63, 0], [1, 1], [2, 2]], dtype=np.uint64))


def test_non_numeric_dtypes_are_type_errors():
    with pytest.raises(TypeError):
        clipper2.area([("a", "b"), ("c", "d")])
    with pytest.raises(TypeError):
        clipper2.area(np.array([[True, False], [True, True]]))
    with pytest.raises(TypeError):
        clipper2.area([(None, None), (1, 1)])


def test_a_float_is_refused_where_c_takes_an_integer():
    with pytest.raises(TypeError):
        clipper2.translate_path(SQUARE, 0.5, 0)
    # ... and accepted where C++ takes a double
    assert clipper2.translate_path(SQUARE_D, 1, 2)[0].tolist() == [1.0, 2.0]


# --- output shapes --------------------------------------------------------------------


def test_paths_come_out_as_a_list_of_n_by_2_arrays():
    result = clipper2.union([SQUARE], NON_ZERO)
    assert isinstance(result, list)
    assert all(isinstance(p, np.ndarray) and p.ndim == 2 and p.shape[1] == 2 for p in result)


def test_a_point_comes_out_as_a_tuple():
    assert clipper2.mid_point((0, 0), (10, 10)) == (5, 5)
    assert clipper2.Rect64(0, 0, 10, 10).mid_point() == (5, 5)
    assert clipper2.mid_point((0.0, 0.0), (5.0, 5.0)) == (2.5, 2.5)


def test_paths_of_different_lengths_are_accepted():
    triangle = [(0, 0), (20, 0), (0, 20)]
    result = clipper2.union([SQUARE, triangle], NON_ZERO)
    assert clipper2.area(result) > 0


# --- the z build ----------------------------------------------------------------------


def test_z_paths_are_n_by_3():
    (result,) = z.union([[(0, 0, 7), (10, 0, 7), (10, 10, 7), (0, 10, 7)]], NON_ZERO)
    assert result.shape == (4, 3)
    assert sorted(result[:, 2].tolist()) == [7, 7, 7, 7]


def test_z_accepts_n_by_2_and_defaults_z_to_zero():
    # upstream's Point constructor defaults z to 0
    (result,) = z.union([SQUARE], NON_ZERO)
    assert result.shape == (4, 3)
    assert result[:, 2].tolist() == [0, 0, 0, 0]


def test_z_is_an_integer_in_both_families():
    (result,) = z.union([[(0.0, 0.0, 7.0), (10.0, 0.0, 7.0), (10.0, 10.0, 7.0), (0.0, 10.0, 7.0)]], NON_ZERO)
    assert result.dtype == np.float64
    assert sorted(result[:, 2].tolist()) == [7.0, 7.0, 7.0, 7.0]
    # a fractional z is truncated towards zero, as upstream's MakePathZD does
    (result,) = z.union([[(0.0, 0.0, 7.9), (10.0, 0.0, 7.9), (10.0, 10.0, 7.9), (0.0, 10.0, 7.9)]], NON_ZERO)
    assert sorted(result[:, 2].tolist()) == [7.0, 7.0, 7.0, 7.0]


def test_z_point_tuple_has_three_items():
    # upstream's MidPoint fills x and y only, leaving z at the Point constructor's 0
    assert z.mid_point((0, 0, 4), (10, 10, 4)) == (5, 5, 0)
    assert z.translate_point((1, 2, 4), 1, 1) == (2, 3, 4)


def test_pathologically_nested_input_is_refused_not_crashed():
    recursive = []
    recursive.append(recursive)
    with pytest.raises(ValueError):
        clipper2.area(recursive)
    with pytest.raises(ValueError):
        clipper2.union(recursive, NON_ZERO)
    with pytest.raises(ValueError):
        clipper2.area([[[[0, 0], [1, 1]]]])


def test_empty_ndarray_keeps_its_dtype():
    empty_d = np.empty((0, 2), np.float64)
    assert clipper2.simplify_paths([empty_d], 1.0, True)[0].dtype == np.float64
    assert clipper2.trim_collinear(empty_d, precision=4).dtype == np.float64
    with pytest.raises(TypeError):
        clipper2.Clipper64().add_subject([empty_d])
    with pytest.raises(TypeError):
        clipper2.union([[(0, 0), (5, 0), (5, 5)]], [empty_d], clipper2.FillRule.NON_ZERO)


def test_nested_empty_sequence_is_one_empty_path():
    assert clipper2.area([[]]) == 0.0
    assert clipper2.ramer_douglas_peucker([[]], 1.0)[0].shape == (0, 2)
