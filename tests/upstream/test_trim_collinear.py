"""Port of third_party/Clipper2/CPP/Tests/TestTrimCollinear.cpp."""

import clipper2


def test_trim_collinear():
    input1 = clipper2.make_path([10, 10, 10, 10, 50, 10, 100, 10, 100, 100, 10, 100, 10, 10, 20, 10])
    output1 = clipper2.trim_collinear(input1, is_open_path=False)
    assert len(output1) == 4

    input2 = clipper2.make_path([10, 10, 10, 10, 100, 10, 100, 100, 10, 100, 10, 10, 10, 10])
    output2 = clipper2.trim_collinear(input2, is_open_path=True)
    assert len(output2) == 5

    input3 = clipper2.make_path(
        [10, 10, 10, 50, 10, 10, 50, 10, 50, 50, 50, 10, 70, 10, 70, 50, 70, 10, 50, 10, 100, 10, 100, 50, 100, 10]
    )
    output3 = clipper2.trim_collinear(input3)
    assert len(output3) == 0

    input4 = clipper2.make_path(
        [2, 3, 3, 4, 4, 4, 4, 5, 7, 5, 8, 4, 8, 3, 9, 3, 8, 3, 7, 3, 6, 3, 5, 3, 4, 3, 3, 3, 2, 3]
    )
    output4a = clipper2.trim_collinear(input4)
    output4b = clipper2.trim_collinear(output4a)
    area4a = int(clipper2.area(output4a))
    area4b = int(clipper2.area(output4b))
    assert len(output4a) == 7
    assert area4a == -9
    assert len(output4a) == len(output4b)
    assert area4a == area4b
