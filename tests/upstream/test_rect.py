"""Port of third_party/Clipper2/CPP/Tests/TestRect.cpp."""

import clipper2


def test_rect_op_plus():
    lhs = clipper2.Rect64.invalid_rect()
    rhs = clipper2.Rect64(-1, -1, 10, 10)
    assert rhs == lhs + rhs
    lhs, rhs = rhs, lhs
    assert lhs == lhs + rhs

    lhs = clipper2.Rect64.invalid_rect()
    rhs = clipper2.Rect64(1, 1, 10, 10)
    assert rhs == lhs + rhs
    lhs, rhs = rhs, lhs
    assert lhs == lhs + rhs

    lhs = clipper2.Rect64(0, 0, 1, 1)
    rhs = clipper2.Rect64(-1, -1, 0, 0)
    expected = clipper2.Rect64(-1, -1, 1, 1)
    assert expected == lhs + rhs
    lhs, rhs = rhs, lhs
    assert expected == lhs + rhs

    lhs = clipper2.Rect64(-10, -10, -1, -1)
    rhs = clipper2.Rect64(1, 1, 10, 10)
    expected = clipper2.Rect64(-10, -10, 10, 10)
    assert expected == lhs + rhs
    lhs, rhs = rhs, lhs
    assert expected == lhs + rhs
