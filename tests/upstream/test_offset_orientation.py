"""Port of third_party/Clipper2/CPP/Tests/TestOffsetOrientation.cpp."""

import clipper2


def test_offsetting_orientation1():
    subject = [clipper2.make_path([0, 0, 0, 5, 5, 5, 5, 0])]
    solution = clipper2.inflate_paths(subject, 1, clipper2.JoinType.ROUND, clipper2.EndType.POLYGON)
    assert len(solution) == 1
    # when offsetting, output orientation should match input
    assert clipper2.is_positive(subject[0]) == clipper2.is_positive(solution[0])


def test_offsetting_orientation2():
    subject = [
        clipper2.make_path([20, 220, 280, 220, 280, 280, 20, 280]),
        clipper2.make_path([0, 200, 0, 300, 300, 300, 300, 200]),
    ]
    co = clipper2.ClipperOffset()
    co.reverse_solution = True  # could also assign using a parameter in ClipperOffset's constructor
    co.add_paths(subject, clipper2.JoinType.ROUND, clipper2.EndType.POLYGON)
    solution = co.execute(5)
    assert len(solution) == 2
    # When offsetting, output orientation should match input EXCEPT when ReverseSolution == true
    # However, input path ORDER may not match output path order. For example, order will change
    # whenever inner paths (holes) are defined before their container outer paths (as above).
    # And when offsetting multiple outer paths, their order will likely change too. Due to the
    # sweep-line algorithm used, paths with larger Y coordinates will likely be listed first.
    assert clipper2.is_positive(subject[1]) != clipper2.is_positive(solution[0])
