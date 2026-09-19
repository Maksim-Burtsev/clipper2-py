"""Nothing may accumulate over 10^5 calls (spec, Tests 3).

Both sides are watched: `tracemalloc` sees what the binding allocates on the Python heap
(a callback it forgets to release, a tuple it never frees), `resource.getrusage` sees the
native heap through the process's peak RSS.

The bound is measured, not guessed: each workload first runs a tenth of the iterations to
settle the allocator, and the growth that warm-up shows sets the ceiling for the real run
(a genuine leak would make the warm-up grow a tenth as much as the measured run, so a
ceiling of four warm-ups still fails). A floor keeps it meaningful when the warm-up shows
nothing at all: 2 MiB of RSS over 10^5 calls is 21 bytes per call.
"""

from __future__ import annotations

import gc
import sys
import tracemalloc
from collections.abc import Callable

import pytest

import clipper2 as cl
import clipper2.z as clz

resource = pytest.importorskip("resource", reason="no getrusage on Windows")

# 10^5 everywhere, including the tree traversal, which allocates a numpy array per node
# per call and costs about half of this file's ~10 s.
CALLS = 100_000

RSS_FLOOR = 2 * 1024 * 1024
HEAP_FLOOR = 256 * 1024
# ru_maxrss is bytes on macOS and kibibytes everywhere else.
RSS_UNIT = 1 if sys.platform == "darwin" else 1024

SQUARE = [[0, 0], [100, 0], [100, 100], [0, 100]]
DIAMOND = [[50, -50], [150, 50], [50, 150], [-50, 50]]
SQUARE_Z = [[0, 0, 1], [100, 0, 2], [100, 100, 3], [0, 100, 4]]
DIAMOND_Z = [[50, -50, 5], [150, 50, 6], [50, 150, 7], [-50, 50, 8]]


def _rss() -> int:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * RSS_UNIT


def _measure(work: Callable[[int], None], calls: int) -> tuple[int, int]:
    """Python-heap and RSS growth over `calls` iterations, in bytes."""
    gc.collect()
    tracemalloc.start()
    heap_before = tracemalloc.get_traced_memory()[0]
    rss_before = _rss()
    work(calls)
    gc.collect()
    heap_after = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()
    return heap_after - heap_before, _rss() - rss_before


def assert_no_leak(work: Callable[[int], None], calls: int = CALLS) -> None:
    work(calls // 100)  # first-touch costs (numpy's caches, arenas) out of the way
    warm_heap, warm_rss = _measure(work, calls // 10)
    heap, rss = _measure(work, calls)
    assert heap <= max(HEAP_FLOOR, 4 * warm_heap), (
        f"Python heap grew {heap} bytes over {calls} calls (warm-up {warm_heap})"
    )
    assert rss <= max(RSS_FLOOR, 4 * warm_rss), (
        f"RSS grew {rss} bytes over {calls} calls (warm-up {warm_rss})"
    )


def test_free_function() -> None:
    def work(n: int) -> None:
        for _ in range(n):
            cl.intersect([SQUARE], [DIAMOND], cl.FillRule.NON_ZERO)

    assert_no_leak(work)


def test_clipper64_execute() -> None:
    def work(n: int) -> None:
        for _ in range(n):
            clipper = cl.Clipper64()
            clipper.add_subject([SQUARE])
            clipper.add_clip([DIAMOND])
            clipper.execute(cl.ClipType.INTERSECTION, cl.FillRule.NON_ZERO)

    assert_no_leak(work)


def test_execute_tree_and_traversal() -> None:
    """A child holds its tree alive (py::keep_alive); neither may outlive the loop."""

    def work(n: int) -> None:
        for _ in range(n):
            clipper = cl.Clipper64()
            clipper.add_subject([SQUARE])
            clipper.add_clip([DIAMOND])
            tree, _open = clipper.execute_tree(cl.ClipType.UNION, cl.FillRule.NON_ZERO)
            pending = [tree]
            while pending:
                node = pending.pop()
                assert node.polygon.ndim == 2
                node.area(), node.is_hole, node.level, node.parent
                pending.extend(node)

    assert_no_leak(work)


def test_offset_with_delta_callback() -> None:
    def delta(path: object, normals: object, curr: int, prev: int) -> float:
        return 5.0

    def work(n: int) -> None:
        for _ in range(n):
            offset = cl.ClipperOffset()
            offset.add_path(SQUARE, cl.JoinType.ROUND, cl.EndType.POLYGON)
            offset.execute(delta)

    assert_no_leak(work)


def test_a_raising_callback_leaks_nothing() -> None:
    """Deviation 8: the exception waits until upstream's Execute has cleaned up.

    `ClipperOffset::Execute(double, PolyTree64&)` is `solution = new Paths64();
    ExecuteInternal(delta); delete solution;` -- an exception thrown from the delta
    callback used to unwind straight past that `delete`, losing the whole solution.
    """
    big = [
        [(x * 100, y * 100), (x * 100 + 80, y * 100), (x * 100 + 80, y * 100 + 80)]
        for x in range(40)
        for y in range(40)
    ]

    def boom(path: object, normals: object, curr: int, prev: int) -> float:
        raise ValueError("boom")

    def work(n: int) -> None:
        for _ in range(n):
            offset = cl.ClipperOffset()
            offset.add_paths(big, cl.JoinType.ROUND, cl.EndType.POLYGON)
            offset.set_delta_callback(boom)
            with pytest.raises(ValueError):
                offset.execute_tree(10.0)

    assert_no_leak(work, calls=50)


def test_z_callback() -> None:
    def on_z(e1bot: object, e1top: object, e2bot: object, e2top: object, pt: object) -> int:
        return 42

    def work(n: int) -> None:
        for _ in range(n):
            clipper = clz.Clipper64()
            clipper.set_z_callback(on_z)
            clipper.add_subject([SQUARE_Z])
            clipper.add_clip([DIAMOND_Z])
            clipper.execute(clz.ClipType.INTERSECTION, clz.FillRule.NON_ZERO)

    assert_no_leak(work)
