"""Port of third_party/Clipper2/CPP/Tests/TestSimplifyPath.cpp."""

import clipper2


def test_simplify_path():
    input1 = clipper2.make_path([0, 0, 1, 1, 0, 20, 0, 21, 1, 40, 0, 41, 0, 60, 0, 61, 0, 80, 1, 81, 0, 100])
    output1 = clipper2.simplify_path(input1, 2, False)
    assert clipper2.length(output1) == 100
    assert len(output1) == 2
