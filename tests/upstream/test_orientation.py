"""Port of third_party/Clipper2/CPP/Tests/TestOrientation.cpp."""

import clipper2


def test_negative_orientation():
    subjects = [
        clipper2.make_path([0, 0, 0, 100, 100, 100, 100, 0]),
        clipper2.make_path([10, 10, 10, 110, 110, 110, 110, 10]),
    ]
    assert not clipper2.is_positive(subjects[0])
    assert not clipper2.is_positive(subjects[1])
    clips = [clipper2.make_path([50, 50, 50, 150, 150, 150, 150, 50])]
    assert not clipper2.is_positive(clips[0])
    solution = clipper2.union(subjects, clips, clipper2.FillRule.NEGATIVE)
    assert len(solution) == 1
    assert len(solution[0]) == 12
