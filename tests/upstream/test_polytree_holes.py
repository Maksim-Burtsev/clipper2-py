"""Port of third_party/Clipper2/CPP/Tests/TestPolytreeHoles.cpp."""

import clipper2
from clip_file_load import load_test_num


def test_polytree_holes1():
    case = load_test_num("PolytreeHoleOwner.txt", 1)
    assert case is not None
    c = clipper2.Clipper64()
    c.add_subject(case.subj)
    c.add_open_subject(case.subj_open)
    c.add_clip(case.clip)
    solution, _solution_open = c.execute_tree(case.ct, case.fr)
    assert clipper2.check_polytree_fully_contains_children(solution)


def _poly_path_contains_point(pp, pt):
    """line 25: PolyPathContainsPoint; the `int& counter` out-parameter is the return value."""
    counter = 0
    if len(pp.polygon) > 0:
        if clipper2.point_in_polygon(pt, pp.polygon) != clipper2.PointInPolygonResult.IS_OUTSIDE:
            counter += -1 if pp.is_hole else 1
    for child in pp:
        counter += _poly_path_contains_point(child, pt)
    return counter


def _polytree_contains_point(pp, pt):  # line 39
    counter = sum(_poly_path_contains_point(child, pt) for child in pp)
    assert counter >= 0  # line 44: ie 'pt' can't be inside more holes than outers
    return counter != 0


def _get_poly_path_area(pp):  # line 48: GetPolyPathArea
    return clipper2.area(pp.polygon) + sum(_get_poly_path_area(child) for child in pp)


def _get_polytree_area(pp):  # line 54
    return sum(_get_poly_path_area(child) for child in pp)


def test_polytree_holes2():
    case = load_test_num("PolytreeHoleOwner2.txt", 1)
    assert case is not None
    subject = case.subj
    points_of_interest_outside = [(21887, 10420), (21726, 10825), (21662, 10845), (21617, 10890)]
    # confirm that each 'points_of_interest_outside' is outside every subject,
    for poi_outside in points_of_interest_outside:
        outside_subject_count = 0
        for path in subject:
            if clipper2.point_in_polygon(poi_outside, path) != clipper2.PointInPolygonResult.IS_OUTSIDE:
                outside_subject_count += 1
        assert outside_subject_count == 0

    points_of_interest_inside = [(21887, 10430), (21843, 10520), (21810, 10686), (21900, 10461)]
    # confirm that each 'points_of_interest_inside' is inside a subject,
    # and inside only one subject (to exclude possible subject holes)
    for poi_inside in points_of_interest_inside:
        inside_subject_count = 0
        for path in subject:
            if clipper2.point_in_polygon(poi_inside, path) != clipper2.PointInPolygonResult.IS_OUTSIDE:
                inside_subject_count += 1
        assert inside_subject_count == 1

    c = clipper2.Clipper64()
    c.add_subject(subject)
    c.add_open_subject(case.subj_open)
    c.add_clip(case.clip)
    solution_tree, _solution_open = c.execute_tree(case.ct, clipper2.FillRule.NEGATIVE)
    solution_paths = clipper2.poly_tree_to_paths64(solution_tree)
    assert solution_paths
    subject_area = -clipper2.area(subject)  # negate (see fillrule)
    solution_tree_area = _get_polytree_area(solution_tree)
    solution_paths_area = clipper2.area(solution_paths)
    # 1a. check solution_paths_area  is smaller than subject_area
    assert solution_paths_area < subject_area
    # 1b. but not too much smaller
    assert solution_paths_area > subject_area * 0.92
    # 2. check solution_tree's area matches solution_paths' area
    assert abs(solution_tree_area - solution_paths_area) <= 0.0001  # line 122
    # 3. check that all children are inside their parents
    assert clipper2.check_polytree_fully_contains_children(solution_tree)
    # 4. confirm all 'point_of_interest_outside' are outside polytree
    for poi_outside in points_of_interest_outside:
        assert not _polytree_contains_point(solution_tree, poi_outside)
    # 5. confirm all 'point_of_interest_inside' are inside polytree
    for poi_inside in points_of_interest_inside:
        assert _polytree_contains_point(solution_tree, poi_inside)


def test_polytree_holes3():
    subject = [
        clipper2.make_path(
            [1072, 501, 1072, 501, 1072, 539, 1072, 539, 1072, 539, 870, 539,
             870, 539, 870, 539, 870, 520, 894, 520, 898, 524, 911, 524, 915, 520, 915, 520, 936, 520,
             940, 524, 953, 524, 957, 520, 957, 520, 978, 520, 983, 524, 995, 524, 1000, 520, 1021, 520,
             1025, 524, 1038, 524, 1042, 520, 1038, 516, 1025, 516, 1021, 520, 1000, 520, 995, 516,
             983, 516, 978, 520, 957, 520, 953, 516, 940, 516, 936, 520, 915, 520, 911, 516, 898, 516,
             894, 520, 870, 520, 870, 516, 870, 501, 870, 501, 870, 501, 1072, 501]
        )
    ]
    clip = [clipper2.make_path([870, 501, 971, 501, 971, 539, 870, 539])]
    c = clipper2.Clipper64()
    c.add_subject(subject)
    c.add_clip(clip)
    solution, _ = c.execute_tree(clipper2.ClipType.INTERSECTION, clipper2.FillRule.NON_ZERO)
    assert len(solution) == 1 and len(solution[0]) == 2


def test_polytree_holes4():  # line 151, #618
    subject = [
        clipper2.make_path(
            [50, 500, 50, 300, 100, 300, 100, 350, 150, 350,
             150, 250, 200, 250, 200, 450, 350, 450, 350, 200, 400, 200, 400, 225, 450, 225,
             450, 175, 400, 175, 400, 200, 350, 200, 350, 175, 200, 175, 200, 250, 150, 250,
             150, 200, 100, 200, 100, 300, 50, 300, 50, 125, 500, 125, 500, 500]
        ),
        clipper2.make_path([250, 425, 250, 375, 300, 375, 300, 425]),
    ]
    c = clipper2.Clipper64()
    c.add_subject(subject)
    solution, _ = c.execute_tree(clipper2.ClipType.UNION, clipper2.FillRule.NON_ZERO)
    # Polytree root
    #   +- Polygon with 3 holes.
    #      +- Hole with 1 nested polygon.
    #         +-Polygon
    #      +- Hole
    #      +- Hole
    assert len(solution) == 1 and len(solution[0]) == 3


def test_polytree_holes5():
    subject = [clipper2.make_path([0, 30, 400, 30, 400, 100, 0, 100])]
    clip = [
        clipper2.make_path([20, 30, 30, 30, 30, 150, 20, 150]),
        clipper2.make_path([200, 0, 300, 0, 300, 30, 280, 30, 280, 20, 220, 20, 220, 30, 200, 30]),
        clipper2.make_path([200, 50, 300, 50, 300, 80, 200, 80]),
    ]
    c = clipper2.Clipper64()
    c.add_subject(subject)
    c.add_clip(clip)
    tree, _ = c.execute_tree(clipper2.ClipType.XOR, clipper2.FillRule.NON_ZERO)
    # Polytree with 3 polygons.
    #   + -Polygon (2) contains 2 holes.
    assert len(tree) == 3 and len(tree[2]) == 2


def test_polytree_holes6():  # line 190, #618
    subject = [
        clipper2.make_path([150, 50, 200, 50, 200, 100, 150, 100]),
        clipper2.make_path([125, 100, 150, 100, 150, 150, 125, 150]),
        clipper2.make_path([225, 50, 300, 50, 300, 80, 225, 80]),
        clipper2.make_path(
            [225, 100, 300, 100, 300, 150, 275, 150, 275, 175, 260, 175,
             260, 250, 235, 250, 235, 300, 275, 300, 275, 275, 300, 275, 300, 350, 225, 350]
        ),
        clipper2.make_path([300, 150, 350, 150, 350, 175, 300, 175]),
    ]
    clip = [
        clipper2.make_path([0, 0, 400, 0, 400, 50, 0, 50]),
        clipper2.make_path([0, 100, 400, 100, 400, 150, 0, 150]),
        clipper2.make_path([260, 175, 325, 175, 325, 275, 260, 275]),
    ]
    c = clipper2.Clipper64()
    c.add_subject(subject)
    c.add_clip(clip)
    tree, _ = c.execute_tree(clipper2.ClipType.XOR, clipper2.FillRule.NON_ZERO)
    # Polytree with 3 polygons.
    #   + -Polygon (2) contains 1 holes.
    assert len(tree) == 3 and len(tree[2]) == 1


def test_polytree_holes7():  # line 213, #618
    subject = [
        clipper2.make_path(
            [0, 0, 100000, 0, 100000, 100000, 200000, 100000,
             200000, 0, 300000, 0, 300000, 200000, 0, 200000]
        ),
        clipper2.make_path([0, 0, 0, -100000, 250000, -100000, 250000, 0]),
    ]
    c = clipper2.Clipper64()
    c.add_subject(subject)
    polytree, _ = c.execute_tree(clipper2.ClipType.UNION, clipper2.FillRule.NON_ZERO)
    assert len(polytree) == 1 and len(polytree[0]) == 1


def test_polytree_holes8():  # line 227, #942
    subject = [
        clipper2.make_path([1588700, -8717600, 1616200, -8474800, 1588700, -8474800]),
        clipper2.make_path(
            [13583800, -15601600, 13582800, -15508500,
             13555300, -15508500, 13555500, -15182200, 13010900, -15185400]
        ),
        clipper2.make_path([956700, -3092300, 1152600, 3147400, 25600, 3151700]),
        clipper2.make_path(
            [22575900, -16604000, 31286800, -12171900,
             31110200, 4882800, 30996200, 4826300, 30414400, 5447400, 30260000, 5391500,
             29662200, 5805400, 28844500, 5337900, 28435000, 5789300, 27721400, 5026400,
             22876300, 5034300, 21977700, 4414900, 21148000, 4654700, 20917600, 4653400,
             19334300, 12411000, -2591700, 12177200, 53200, 3151100, -2564300, 12149800,
             7819400, 4692400, 10116000, 5228600, 6975500, 3120100, 7379700, 3124700,
             11037900, 596200, 12257000, 2587800, 12257000, 596200, 15227300, 2352700,
             18444400, 1112100, 19961100, 5549400, 20173200, 5078600, 20330000, 5079300,
             20970200, 4544300, 20989600, 4563700, 19465500, 1112100, 21611600, 4182100,
             22925100, 1112200, 22952700, 1637200, 23059000, 1112200, 24908100, 4181200,
             27070100, 3800600, 27238000, 3800700, 28582200, 520300, 29367800, 1050100,
             29291400, 179400, 29133700, 360700, 29056700, 312600, 29121900, 332500,
             29269900, 162300, 28941400, 213100, 27491300, -3041500, 27588700, -2997800,
             22104900, -16142800, 13010900, -15603000, 13555500, -15182200,
             13555300, -15508500, 13582800, -15508500, 13583100, -15154700,
             1588700, -8822800, 1588700, -8379900, 1588700, -8474800, 1616200, -8474800,
             1003900, -630100, 1253300, -12284500, 12983400, -16239900]
        ),
        clipper2.make_path([198200, 12149800, 1010600, 12149800, 1011500, 11859600]),
        clipper2.make_path([21996700, -7432000, 22096700, -7432000, 22096700, -7332000]),
    ]
    c = clipper2.Clipper64()
    c.add_subject(subject)
    solution, _ = c.execute_tree(clipper2.ClipType.UNION, clipper2.FillRule.NON_ZERO)
    assert len(solution) == 1 and len(solution[0]) == 2 and len(solution[0][1]) == 1


def test_polytree_holes9():  # line 261, #957
    subject = [
        clipper2.make_path([77910, 46865, 78720, 46865, 78720, 48000, 77910, 48000, 77910, 46865]),
        clipper2.make_path([82780, 53015, 93600, 53015, 93600, 54335, 82780, 54335, 82780, 53015]),
        clipper2.make_path([82780, 48975, 84080, 48975, 84080, 53015, 82780, 53015, 82780, 48975]),
        clipper2.make_path([77910, 48000, 84080, 48000, 84080, 48975, 77910, 48975, 77910, 48000]),
        clipper2.make_path([89880, 40615, 90700, 40615, 90700, 46865, 89880, 46865, 89880, 40615]),
        clipper2.make_path([92700, 54335, 93600, 54335, 93600, 61420, 92700, 61420, 92700, 54335]),
        clipper2.make_path([78950, 47425, 84080, 47425, 84080, 47770, 78950, 47770, 78950, 47425]),
        clipper2.make_path([82780, 61420, 93600, 61420, 93600, 62435, 82780, 62435, 82780, 61420]),
        clipper2.make_path(
            [101680, 63085, 100675, 63085, 100675, 47770, 100680, 47770, 100680, 40615, 101680, 40615, 101680, 63085]
        ),
        clipper2.make_path([76195, 39880, 89880, 39880, 89880, 41045, 76195, 41045, 76195, 39880]),
        clipper2.make_path([85490, 56145, 90520, 56145, 90520, 59235, 85490, 59235, 85490, 56145]),
        clipper2.make_path([89880, 39880, 101680, 39880, 101680, 40615, 89880, 40615, 89880, 39880]),
        clipper2.make_path([89880, 46865, 100680, 46865, 100680, 47770, 89880, 47770, 89880, 46865]),
        clipper2.make_path([82780, 54335, 83280, 54335, 83280, 61420, 82780, 61420, 82780, 54335]),
        clipper2.make_path([76195, 41045, 76855, 41045, 76855, 62665, 76195, 62665, 76195, 41045]),
        clipper2.make_path([76195, 62665, 100675, 62665, 100675, 63085, 76195, 63085, 76195, 62665]),
        clipper2.make_path([82780, 41045, 84080, 41045, 84080, 47425, 82780, 47425, 82780, 41045]),
    ]
    c = clipper2.Clipper64()
    c.add_subject(subject)
    solution, _ = c.execute_tree(clipper2.ClipType.UNION, clipper2.FillRule.NON_ZERO)

    #  Polytree with 1 polygon.
    #    + -Polygon(0) contains 2 holes.
    #    + -Hole(0) contains 1 nested polygon.
    #    + -Polygon(0) contains 1 hole.
    #    + -Hole(0) contains 1 nested polygon.
    assert len(solution) == 1 and len(solution[0]) == 2 and len(solution[0][0]) == 1


def test_polytree_holes10():  # line 297, #973
    subject = [
        clipper2.make_path([0, 0, 79530, 0, 79530, 940, 0, 940, 0, 0]),
        clipper2.make_path([0, 33360, 79530, 33360, 79530, 34300, 0, 34300, 0, 33360]),
        clipper2.make_path([78470, 940, 79530, 940, 79530, 33360, 78470, 33360, 78470, 940]),
        clipper2.make_path([0, 940, 940, 940, 940, 33360, 0, 33360, 0, 940]),
        clipper2.make_path([29290, 940, 30350, 940, 30350, 33360, 29290, 33360, 29290, 940]),
    ]
    c = clipper2.Clipper64()
    c.add_subject(subject)
    solution, _ = c.execute_tree(clipper2.ClipType.UNION, clipper2.FillRule.NON_ZERO)

    #  Polytree with 1 polygon.
    #    + -Polygon(0) contains 2 holes.
    assert len(solution) == 1 and len(solution[0]) == 2
