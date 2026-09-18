"""Port of third_party/Clipper2/CPP/Tests/TestRectClip.cpp."""

import clipper2


def test_rect_clip():
    rect = clipper2.Rect64(100, 100, 700, 500)
    clp = [rect.as_path()]
    sub = [clipper2.make_path([100, 100, 700, 100, 700, 500, 100, 500])]
    sol = clipper2.rect_clip(rect, sub)
    assert clipper2.area(sol) == clipper2.area(sub)

    sub = [clipper2.make_path([110, 110, 700, 100, 700, 500, 100, 500])]
    sol = clipper2.rect_clip(rect, sub)
    assert clipper2.area(sol) == clipper2.area(sub)

    sub = [clipper2.make_path([90, 90, 700, 100, 700, 500, 100, 500])]
    sol = clipper2.rect_clip(rect, sub)
    assert clipper2.area(sol) == clipper2.area(clp)

    sub = [clipper2.make_path([110, 110, 690, 110, 690, 490, 110, 490])]
    sol = clipper2.rect_clip(rect, sub)
    assert clipper2.area(sol) == clipper2.area(sub)

    rect = clipper2.Rect64(390, 290, 410, 310)
    clp = [rect.as_path()]
    sub = [clipper2.make_path([410, 290, 500, 290, 500, 310, 410, 310])]
    sol = clipper2.rect_clip(rect, sub)
    assert len(sol) == 0

    sub = [clipper2.make_path([430, 290, 470, 330, 390, 330])]
    sol = clipper2.rect_clip(rect, sub)
    assert len(sol) == 0

    sub = [clipper2.make_path([450, 290, 480, 330, 450, 330])]
    sol = clipper2.rect_clip(rect, sub)
    assert len(sol) == 0

    sub = [clipper2.make_path([208, 66, 366, 112, 402, 303, 234, 332, 233, 262, 243, 140, 215, 126, 40, 172])]
    rect = clipper2.Rect64(237, 164, 322, 248)
    sol = clipper2.rect_clip(rect, sub)
    sol_bounds = clipper2.get_bounds(sol)
    assert sol_bounds.width == rect.width
    assert sol_bounds.height == rect.height


def test_rect_clip2():  # line 48, #597
    rect = clipper2.Rect64(54690, 0, 65628, 6000)
    subject = [[(700000, 6000), (0, 6000), (0, 5925), (700000, 5925)]]
    solution = clipper2.rect_clip(rect, subject)
    assert len(solution) == 1 and len(solution[0]) == 4


def test_rect_clip3():  # line 56, #637
    r = clipper2.Rect64(-1800000000, -137573171, -1741475021, 3355443)
    subject = [
        clipper2.make_path(
            [-1800000000, 10005000, -1800000000, -5000, -1789994999, -5000, -1789994999, 10005000]
        )
    ]
    _clip = [r.as_path()]
    solution = clipper2.rect_clip(r, subject)
    assert len(solution) == 1


def test_rect_clip_orientation():  # line 68, #864
    rect = clipper2.Rect64(1222, 1323, 3247, 3348)
    subject = clipper2.make_path([375, 1680, 1915, 4716, 5943, 586, 3987, 152])
    clip = clipper2.RectClip64(rect)
    solution = clip.execute([subject])
    assert len(solution) == 1
    assert clipper2.is_positive(subject) == clipper2.is_positive(solution[0])
