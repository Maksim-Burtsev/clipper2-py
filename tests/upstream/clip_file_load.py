"""Port of third_party/Clipper2/CPP/Utils/ClipFileLoad.cpp — the test-data parser.

The data files are read straight from the submodule (third_party/Clipper2/Tests), never
copied.  `load_test_num` mirrors the C++ function of the same name: it returns `None`
where C++ returns `false`, and the out-parameters as a named tuple (spec deviation 4).
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import NamedTuple

import numpy as np

import clipper2

TESTS_DIR = Path(__file__).resolve().parents[2] / "third_party" / "Clipper2" / "Tests"


class TestCase(NamedTuple):
    subj: list[np.ndarray]
    subj_open: list[np.ndarray]
    clip: list[np.ndarray]
    area: int
    count: int
    ct: clipper2.ClipType
    fr: clipper2.FillRule


def _get_int(line: str, i: int) -> tuple[int | None, int]:
    """ClipFileLoad.cpp GetInt (line 11): value and the new position, or None on failure."""
    n = len(line)
    while i < n and line[i] == " ":
        i += 1
    if i >= n:
        return None, i
    is_neg = line[i] == "-"
    if is_neg:
        i += 1
    start = i
    value = 0
    while i < n and "0" <= line[i] <= "9":
        value = value * 10 + ord(line[i]) - 48
        i += 1
    if i == start:
        return None, i  # no value
    # trim trailing space and a comma if present
    while i < n and line[i] == " ":
        i += 1
    if i < n and line[i] == ",":
        i += 1
    return (-value if is_neg else value), i


def _get_path(line: str) -> np.ndarray | None:
    """ClipFileLoad.cpp GetPath (line 33). None where C++ returns false."""
    points = []
    i = 0
    while True:
        x, i = _get_int(line, i)
        if x is None:
            break
        y, i = _get_int(line, i)
        if y is None:
            break
        points.append((x, y))
    if not points:
        return None
    return np.array(points, dtype=np.int64)


def _get_paths(lines: list[str], i: int, paths: list[np.ndarray]) -> int:
    """ClipFileLoad.cpp GetPaths (line 45). Returns the index of the first unparsed line.

    C++ rewinds the stream by one byte past the failed line (its LF/CRLF workaround), so
    the caller's next getline yields an empty string and then re-reads that line; reading
    by index has the same effect, an ignored empty line less.
    """
    while i < len(lines):
        path = _get_path(lines[i])
        if path is None:
            break
        paths.append(path)
        i += 1
    return i


@functools.lru_cache(maxsize=None)
def _lines(filename: str) -> list[str]:
    path = TESTS_DIR / filename
    assert path.is_file(), f"missing upstream test data: {path}"  # ASSERT_TRUE(ifs.good())
    return path.read_text().splitlines()


def load_test_num(
    filename: str,
    test_num: int,
    ct: clipper2.ClipType = clipper2.ClipType.NO_CLIP,
    fr: clipper2.FillRule = clipper2.FillRule.EVEN_ODD,
) -> TestCase | None:
    """ClipFileLoad.cpp LoadTestNum (line 59). `ct` / `fr` are the caller's initial values."""
    lines = _lines(filename)
    area = 0
    count = 0
    if test_num <= 0:
        test_num = 1
    subj: list[np.ndarray] = []
    subj_open: list[np.ndarray] = []
    clip: list[np.ndarray] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if test_num:
            if "CAPTION:" in line:
                test_num -= 1
            continue

        if "CAPTION:" in line:
            break  # ie don't go beyond current test

        elif "INTERSECTION" in line:
            ct = clipper2.ClipType.INTERSECTION
        elif "UNION" in line:
            ct = clipper2.ClipType.UNION
        elif "DIFFERENCE" in line:
            ct = clipper2.ClipType.DIFFERENCE
        elif "XOR" in line:
            ct = clipper2.ClipType.XOR
        elif "EVENODD" in line:
            fr = clipper2.FillRule.EVEN_ODD
        elif "NONZERO" in line:
            fr = clipper2.FillRule.NON_ZERO
        elif "POSITIVE" in line:
            fr = clipper2.FillRule.POSITIVE
        elif "NEGATIVE" in line:
            fr = clipper2.FillRule.NEGATIVE
        elif "SOL_AREA" in line:
            value, _ = _get_int(line, 10)
            area = value if value is not None else 0
        elif "SOL_COUNT" in line:
            value, _ = _get_int(line, 11)
            count = value if value is not None else 0
        elif "SUBJECTS_OPEN" in line:
            i = _get_paths(lines, i, subj_open)
        elif "SUBJECTS" in line:
            i = _get_paths(lines, i, subj)
        elif "CLIPS" in line:
            i = _get_paths(lines, i, clip)

    if test_num:
        return None
    return TestCase(subj, subj_open, clip, area, count, ct, fr)


@functools.lru_cache(maxsize=None)
def case_count(filename: str) -> int:
    """Number of test cases in a data file; the C++ loops just run until LoadTestNum fails."""
    return sum(1 for line in _lines(filename) if "CAPTION:" in line)
