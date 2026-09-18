"""Port of third_party/Clipper2/CPP/Tests/TestPolygons.cpp.

MakeRandomPath (line 4) is unused by every TEST in that file and is not ported.
"""

import pytest

import clipper2
from clip_file_load import case_count, load_test_num

FILENAME = "Polygons.txt"

# line 24: start_num = 1, end_num = 1000; the loop stops when LoadTestNum runs out of cases.
CASES = list(range(1, min(case_count(FILENAME), 1000) + 1))


@pytest.mark.parametrize("test_number", CASES)
def test_multiple_polygons(test_number):
    case = load_test_num(FILENAME, test_number)
    assert case is not None
    stored_area, stored_count, ct, fr = case.area, case.count, case.ct, case.fr

    # check Paths64 solutions
    c = clipper2.Clipper64()
    c.add_subject(case.subj)
    c.add_open_subject(case.subj_open)
    c.add_clip(case.clip)
    solution, solution_open = c.execute(ct, fr)
    measured_area = int(clipper2.area(solution))
    measured_count = len(solution) + len(solution_open)

    # check the polytree variant too
    clipper_polytree = clipper2.Clipper64()
    clipper_polytree.add_subject(case.subj)
    clipper_polytree.add_open_subject(case.subj_open)
    clipper_polytree.add_clip(case.clip)
    solution_polytree, solution_polytree_open = clipper_polytree.execute_tree(ct, fr)
    measured_area_polytree = int(solution_polytree.area())
    solution_polytree_paths = clipper2.poly_tree_to_paths64(solution_polytree)
    measured_count_polytree = len(solution_polytree_paths)

    # check polygon counts (lines 58-72)
    if stored_count <= 0:
        pass  # skip count
    elif test_number in {120, 121, 130, 138, 140, 148, 163, 165, 166, 167, 168, 172, 173, 175, 178, 180}:
        assert abs(measured_count - stored_count) <= 5  # line 62
    elif test_number in {126}:
        assert abs(measured_count - stored_count) <= 3  # line 64
    elif test_number in {16, 27, 181}:
        assert abs(measured_count - stored_count) <= 2  # line 66
    elif 120 <= test_number <= 184:
        assert abs(measured_count - stored_count) <= 2  # line 68
    elif test_number in {23, 45, 87, 102, 111, 113, 191}:
        assert abs(measured_count - stored_count) <= 1  # line 70
    else:
        assert measured_count == stored_count  # line 72

    # check polygon areas (lines 74-89)
    if stored_area <= 0:
        pass  # skip area
    elif test_number in {19, 22, 23, 24}:
        assert abs(measured_area - stored_area) <= 0.5 * measured_area  # line 77
    elif test_number == 193:
        assert abs(measured_area - stored_area) <= 0.2 * measured_area  # line 79
    elif test_number == 63:
        assert abs(measured_area - stored_area) <= 0.1 * measured_area  # line 81
    elif test_number == 16:
        assert abs(measured_area - stored_area) <= 0.075 * measured_area  # line 83
    elif test_number == 26:
        assert abs(measured_area - stored_area) <= 0.05 * measured_area  # line 85
    elif test_number in {15, 52, 53, 54, 59, 60, 64, 117, 119, 184}:
        assert abs(measured_area - stored_area) <= 0.02 * measured_area  # line 87
    else:
        assert abs(measured_area - stored_area) <= 0.01 * measured_area  # line 89

    assert measured_count == measured_count_polytree  # line 90
    assert measured_area == measured_area_polytree  # line 92


def test_horz_spikes():  # line 100, #720
    paths = [
        clipper2.make_path([1600, 0, 1600, 100, 2050, 100, 2050, 300, 450, 300, 450, 0]),
        clipper2.make_path([1800, 200, 1800, 100, 1600, 100, 2000, 100, 2000, 200]),
    ]
    c = clipper2.Clipper64()
    c.add_subject(paths)
    paths, _ = c.execute(clipper2.ClipType.UNION, clipper2.FillRule.NON_ZERO)
    assert len(paths) >= 1


def test_collinear_on_mac_os():  # line 112, #777
    subject = [
        clipper2.make_path([0, -453054451, 0, -433253797, -455550000, 0]),
        clipper2.make_path([0, -433253797, 0, 0, -455550000, 0]),
    ]
    clipper = clipper2.Clipper64()
    clipper.preserve_collinear = False
    clipper.add_subject(subject)
    solution, _ = clipper.execute(clipper2.ClipType.UNION, clipper2.FillRule.NON_ZERO)
    assert len(solution) == 1
    assert len(solution[0]) == 3
    assert clipper2.is_positive(subject[0]) == clipper2.is_positive(solution[0])
