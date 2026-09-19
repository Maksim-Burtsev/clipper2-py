"""Draws the README figures with clipper2 itself: python docs/img/make_images.py"""

import math
from pathlib import Path

import clipper2
from clipper2 import ClipType, EndType, FillRule, JoinType

OUT = Path(__file__).parent
BLUE, ORANGE, GREEN, INK = "#4c8df6", "#f6a04c", "#2fbf71", "#8a8f98"
FONT = 'font-family="ui-sans-serif,system-ui,Helvetica,Arial,sans-serif"'


def d(paths):
    return " ".join("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in p) + " Z" for p in paths)


def shape(paths, fill, opacity=0.25, stroke=None, width=1.5, dx=0.0):
    stroke = stroke or fill
    return (f'<path transform="translate({dx},0)" d="{d(paths)}" fill="{fill}" '
            f'fill-opacity="{opacity}" stroke="{stroke}" stroke-width="{width}" '
            f'stroke-linejoin="round" fill-rule="evenodd"/>')


def label(text, x, y):
    return f'<text x="{x}" y="{y}" {FONT} font-size="13" fill="{INK}" text-anchor="middle">{text}</text>'


def svg(name, width, height, body):
    (OUT / name).write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}">\n' + "\n".join(body) + "\n</svg>\n")


def star(cx, cy, outer, inner, points=5):
    return [(cx + (outer if i % 2 == 0 else inner) * math.sin(i * math.pi / points),
             cy - (outer if i % 2 == 0 else inner) * math.cos(i * math.pi / points))
            for i in range(2 * points)]


def booleans():
    circle = [clipper2.ellipse((78.0, 95.0), 58.0, 58.0, 64)]
    clip = [star(122.0, 85.0, 70.0, 30.0)]
    body = []
    for i, (name, ct) in enumerate([("intersect", ClipType.INTERSECTION), ("union", ClipType.UNION),
                                    ("difference", ClipType.DIFFERENCE), ("xor", ClipType.XOR)]):
        dx = i * 210
        result = clipper2.boolean_op(ct, FillRule.NON_ZERO, circle, clip, precision=2)
        body += [shape(circle, BLUE, 0.08, width=1, dx=dx), shape(clip, ORANGE, 0.08, width=1, dx=dx),
                 shape(result, GREEN, 0.55, width=2, dx=dx), label(name, dx + 100, 182)]
    svg("booleans.svg", 830, 195, body)


def offsetting():
    glyph = [star(130.0, 120.0, 60.0, 26.0, 6)]
    body = []
    for i, (name, jt) in enumerate([("JoinType.ROUND", JoinType.ROUND), ("JoinType.MITER", JoinType.MITER),
                                    ("JoinType.BEVEL", JoinType.BEVEL)]):
        dx = i * 270
        for k, delta in enumerate((45.0, 30.0, 15.0)):
            grown = clipper2.inflate_paths(glyph, delta, jt, EndType.POLYGON, arc_tolerance=0.1)
            body.append(shape(grown, BLUE, 0.10 + 0.06 * k, width=1.2, dx=dx))
        body += [shape(glyph, ORANGE, 0.6, width=2, dx=dx),
                 shape(clipper2.inflate_paths(glyph, -9.0, jt, EndType.POLYGON), GREEN, 0.7, dx=dx),
                 label(name, dx + 130, 242)]
    svg("offsetting.svg", 800, 255, body)


def triangulation():
    outer = star(130.0, 125.0, 110.0, 62.0, 7)
    hole = clipper2.ellipse((130.0, 125.0), 30.0, 30.0, 12)[::-1]
    result, triangles = clipper2.triangulate([outer, hole], dec_places=2)
    assert result == clipper2.TriangulateResult.SUCCESS
    pattern = clipper2.ellipse((0.0, 0.0), 16.0, 16.0, 24)
    path = [(330.0, 190.0), (390.0, 70.0), (450.0, 190.0), (510.0, 70.0), (570.0, 190.0)]
    swept = clipper2.union(clipper2.minkowski_sum(pattern, path, False), FillRule.NON_ZERO)
    body = [shape(triangles, GREEN, 0.35, width=1), label("triangulate", 130, 262),
            shape(swept, BLUE, 0.3, width=2),
            f'<path d="M{" L".join(f"{x},{y}" for x, y in path)}" fill="none" stroke="{ORANGE}" stroke-width="2"/>',
            label("minkowski_sum", 450, 262)]
    svg("triangulate-minkowski.svg", 600, 275, body)


if __name__ == "__main__":
    booleans()
    offsetting()
    triangulation()
