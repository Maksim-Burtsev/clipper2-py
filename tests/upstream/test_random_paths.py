"""Port of third_party/Clipper2/CPP/Tests/TestRandomPaths.cpp.

The generator keeps upstream's structure, bounds and counts, but a seeded Python RNG cannot
reproduce libstdc++'s default_random_engine sequence, so the actual paths differ from the
C++ run.  `random.Random.randint` is inclusive on both ends, like uniform_int_distribution.
"""

import random

import numpy as np

import clipper2


def _generate_random_int(rng, min_value, max_value):
    if min_value == max_value:
        return min_value
    return rng.randint(min_value, max_value)


def _generate_random_paths(rng, min_path_count, max_complexity):
    def first_point_coordinate():
        return rng.randint(-max_complexity, max_complexity * 2)

    def difference_to_previous_point():
        return rng.randint(-5, 5)

    path_count = _generate_random_int(rng, min_path_count, max_complexity)
    result = []
    for _path in range(path_count):
        min_point_count = 0
        path_length = _generate_random_int(rng, min_point_count, max(min_point_count, max_complexity))
        result_path = []
        for _point in range(path_length):
            if not result_path:
                result_path.append((first_point_coordinate(), first_point_coordinate()))
            else:
                previous_point = result_path[-1]
                result_path.append(
                    (
                        previous_point[0] + difference_to_previous_point(),
                        previous_point[1] + difference_to_previous_point(),
                    )
                )
        result.append(np.array(result_path, dtype=np.int64).reshape(-1, 2))
    return result


def test_random_paths():
    rng = random.Random(42)
    for i in range(750):
        max_complexity = max(1, i // 10)
        subject = _generate_random_paths(rng, 1, max_complexity)
        subject_open = _generate_random_paths(rng, 0, max_complexity)
        clip = _generate_random_paths(rng, 0, max_complexity)
        ct = clipper2.ClipType(_generate_random_int(rng, 0, 4))
        fr = clipper2.FillRule(_generate_random_int(rng, 0, 3))

        c = clipper2.Clipper64()
        c.add_subject(subject)
        c.add_open_subject(subject_open)
        c.add_clip(clip)
        solution, solution_open = c.execute(ct, fr)
        area_paths = int(clipper2.area(solution))
        _count_paths = len(solution) + len(solution_open)

        clipper_polytree = clipper2.Clipper64()
        clipper_polytree.add_subject(subject)
        clipper_polytree.add_open_subject(subject_open)
        clipper_polytree.add_clip(clip)
        solution_polytree, solution_polytree_open = clipper_polytree.execute_tree(ct, fr)
        solution_polytree_paths = clipper2.poly_tree_to_paths64(solution_polytree)
        area_polytree = int(clipper2.area(solution_polytree_paths))
        _count_polytree = len(solution_polytree_paths) + len(solution_polytree_open)

        assert area_paths == area_polytree, f"iteration {i}"
        # polytree does an additional bounds check on each path
        # and discards paths with empty bounds, so count_polytree
        # may on occasions be slightly less than count_paths even
        # though areas match
        # assert count_paths - count_polytree <= 2
