"""Port of third_party/Clipper2/CPP/Tests/TestIsCollinear.cpp."""

import clipper2

# TesthiCalculation cannot keep upstream's spelling: pytest only collects names that start
# with "test_", so "TesthiCalculation" becomes test_hi_calculation.
# MultiplyUInt64 is not bound (docs/api-map.md: "128-bit arithmetic helpers; Python's int is
# exact"), so `.hi` is the documented substitute, (a * b) >> 64 on Python ints. This exercises
# the substitute rather than the binding, but the values and expectations are upstream's.


def _hi(a, b):
    return (a * b) >> 64


def test_hi_calculation():
    assert _hi(0x51EAED81157DE061, 0x3A271FB2745B6FE9) == 0x129BBEBDFAE0464E
    assert _hi(0x3A271FB2745B6FE9, 0x51EAED81157DE061) == 0x129BBEBDFAE0464E
    assert _hi(0xC2055706A62883FA, 0x26C78BC79C2322CC) == 0x1D640701D192519B
    assert _hi(0xC2055706A62883FA, 0x26C78BC79C2322CC) == 0x1D640701D192519B
    assert _hi(0x26C78BC79C2322CC, 0xC2055706A62883FA) == 0x1D640701D192519B
    assert _hi(0x874DDAE32094B0DE, 0x9B1559A06FDF83E0) == 0x51F76C49563E5BFE
    assert _hi(0x9B1559A06FDF83E0, 0x874DDAE32094B0DE) == 0x51F76C49563E5BFE
    assert _hi(0x81FB3AD3636CA900, 0x239C000A982A8DA4) == 0x12148E28207B83A3
    assert _hi(0x239C000A982A8DA4, 0x81FB3AD3636CA900) == 0x12148E28207B83A3
    assert _hi(0x4BE0B4C5D2725C44, 0x990CD6DB34A04C30) == 0x2D5D1A4183FD6165
    assert _hi(0x990CD6DB34A04C30, 0x4BE0B4C5D2725C44) == 0x2D5D1A4183FD6165
    assert _hi(0x978EC0C0433C01F6, 0x2DF03D097966B536) == 0x1B3251D91FE272A5
    assert _hi(0x2DF03D097966B536, 0x978EC0C0433C01F6) == 0x1B3251D91FE272A5
    assert _hi(0x49C5CBBCFD716344, 0xC489E3B34B007AD3) == 0x38A32C74C8C191A4
    assert _hi(0xC489E3B34B007AD3, 0x49C5CBBCFD716344) == 0x38A32C74C8C191A4
    assert _hi(0xD3361CDBEED655D5, 0x1240DA41E324953A) == 0x0F0F4FA11E7E8F2A
    assert _hi(0x1240DA41E324953A, 0xD3361CDBEED655D5) == 0x0F0F4FA11E7E8F2A
    assert _hi(0x51B854F8E71B0AE0, 0x6F8D438AAE530AF5) == 0x239C04EE3C8CC248
    assert _hi(0x6F8D438AAE530AF5, 0x51B854F8E71B0AE0) == 0x239C04EE3C8CC248
    assert _hi(0xBBECF7DBC6147480, 0xBB0F73D0F82E2236) == 0x895170F4E9A216A7
    assert _hi(0xBB0F73D0F82E2236, 0xBBECF7DBC6147480) == 0x895170F4E9A216A7


def test_is_collinear():
    # a large integer not representable by double
    i = 9007199254740993

    pt1 = (0, 0)
    shared_pt = (i, i * 10)
    pt2 = (i * 10, i * 100)

    assert clipper2.is_collinear(pt1, shared_pt, pt2)


def test_is_collinear2():
    # see https://github.com/AngusJohnson/Clipper2/issues/831
    i = 0x4000000000000
    subject = [(-i, -i), (i, -i), (-i, i), (i, i)]
    clipper = clipper2.Clipper64()
    clipper.add_subject([subject])
    solution, _ = clipper.execute(clipper2.ClipType.UNION, clipper2.FillRule.EVEN_ODD)
    assert len(solution) == 2
