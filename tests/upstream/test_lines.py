"""Port of third_party/Clipper2/CPP/Tests/TestLines.cpp."""

import pytest

import clipper2
from clip_file_load import case_count, load_test_num

FILENAME = "Lines.txt"

CASES = list(range(1, case_count(FILENAME) + 1))


@pytest.mark.parametrize("test_number", CASES)
def test_multiple_lines(test_number):
    case = load_test_num(FILENAME, test_number)
    assert case is not None
    c = clipper2.Clipper64()
    c.add_subject(case.subj)
    c.add_open_subject(case.subj_open)
    c.add_clip(case.clip)
    # line 21: EXPECT_TRUE(c.Execute(...)); a false return raises Clipper2Error here (deviation 4)
    solution, solution_open = c.execute(case.ct, case.fr)
    count2 = len(solution) + len(solution_open)
    count_diff = abs(count2 - case.count)
    relative_count_diff = count_diff / case.count if case.count else 0

    if test_number == 1:
        assert len(solution) == 1
        if len(solution) > 0:
            assert len(solution[0]) == 6
            assert clipper2.is_positive(solution[0])
        assert len(solution_open) == 1
        if len(solution_open) > 0:
            assert len(solution_open[0]) == 2
            if len(solution_open[0]) > 0:
                # expect vertex closest to input path's start
                assert solution_open[0][0][1] == 6  # line 42: solution_open[0][0].y
    else:
        assert count_diff <= 8  # line 48
        assert relative_count_diff <= 0.1  # line 49


def test_multiple_lines_case_count():
    """line 54: EXPECT_GE(test_number, 17) after the loop, ie at least 16 cases were run."""
    assert len(CASES) + 1 >= 17
