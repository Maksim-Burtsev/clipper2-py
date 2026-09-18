"""Port of third_party/Clipper2/CPP/Tests/TestPolytreeIntersection.cpp."""

import clipper2


def test_poly_tree_intersection():
    clipper = clipper2.Clipper64()
    subject = [clipper2.make_path([0, 0, 0, 5, 5, 5, 5, 0])]
    clipper.add_subject(subject)
    clip = [clipper2.make_path([1, 1, 1, 6, 6, 6, 6, 1])]
    clipper.add_clip(clip)
    if clipper2.is_positive(subject[0]):
        solution, open_paths = clipper.execute_tree(
            clipper2.ClipType.INTERSECTION, clipper2.FillRule.POSITIVE
        )
    else:
        solution, open_paths = clipper.execute_tree(
            clipper2.ClipType.INTERSECTION, clipper2.FillRule.NEGATIVE
        )
    assert len(open_paths) == 0
    assert len(solution) == 1
    assert len(solution[0].polygon) == 4
