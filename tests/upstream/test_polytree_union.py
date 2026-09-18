"""Port of third_party/Clipper2/CPP/Tests/TestPolytreeUnion.cpp."""

import clipper2


def test_polytree_union():
    subject = [
        clipper2.make_path([0, 0, 0, 5, 5, 5, 5, 0]),
        clipper2.make_path([1, 1, 1, 6, 6, 6, 6, 1]),
    ]
    clipper = clipper2.Clipper64()
    clipper.add_subject(subject)
    if clipper2.is_positive(subject[0]):
        solution, open_paths = clipper.execute_tree(clipper2.ClipType.UNION, clipper2.FillRule.POSITIVE)
    else:
        # because clipping ops normally return Positive solutions
        clipper.reverse_solution = True
        solution, open_paths = clipper.execute_tree(clipper2.ClipType.UNION, clipper2.FillRule.NEGATIVE)
    assert len(open_paths) == 0
    assert len(solution) == 1
    assert len(solution[0].polygon) == 8
    assert clipper2.is_positive(subject[0]) == clipper2.is_positive(solution[0].polygon)


def test_polytree_union2():  # line 30, #987
    subject = [
        clipper2.make_path([534, 1024, 534, -800, 1026, -800, 1026, 1024]),
        clipper2.make_path([1, 1024, 8721, 1024, 8721, 1920, 1, 1920]),
        clipper2.make_path([30, 1024, 30, -800, 70, -800, 70, 1024]),
        clipper2.make_path([1, 1024, 1, -1024, 3841, -1024, 3841, 1024]),
        clipper2.make_path([3900, -1024, 6145, -1024, 6145, 1024, 3900, 1024]),
        clipper2.make_path([5884, 1024, 5662, 1024, 5662, -1024, 5884, -1024]),
        clipper2.make_path([534, 1024, 200, 1024, 200, -800, 534, -800]),
        clipper2.make_path([200, -800, 200, 1024, 70, 1024, 70, -800]),
        clipper2.make_path([1200, 1920, 1313, 1920, 1313, -800, 1200, -800]),
        clipper2.make_path([6045, -800, 6045, 1024, 5884, 1024, 5884, -800]),
    ]
    clipper = clipper2.Clipper64()
    clipper.add_subject(subject)
    solution, _open_paths = clipper.execute_tree(clipper2.ClipType.UNION, clipper2.FillRule.EVEN_ODD)
    assert len(solution) == 1
    assert len(solution[0]) == 1


def test_polytree_union3():  # line 53; no assertion upstream either, it must simply not crash
    subject = [
        clipper2.make_path(
            [-120927680, 590077597,
             -120919386, 590077307,
             -120919432, 590077309,
             -120919451, 590077309,
             -120919455, 590077310,
             -120099297, 590048669,
             -120928004, 590077608,
             -120902794, 590076728,
             -120919444, 590077309,
             -120919450, 590077309,
             -120919842, 590077323,
             -120922852, 590077428,
             -120902452, 590076716,
             -120902455, 590076716,
             -120912590, 590077070,
             11914491, 249689797]
        )
    ]
    clipper = clipper2.Clipper64()
    clipper.add_subject(subject)
    clipper.execute_tree(clipper2.ClipType.UNION, clipper2.FillRule.EVEN_ODD)
