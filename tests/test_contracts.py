from standardphysics_contracts import Mat4, Vec3, to_inches, to_meters


def test_inch_conversion_round_trips():
    assert to_inches(to_meters(36.0)) == 36.0


def test_thirty_six_inches_is_the_ada_route_width():
    assert round(to_meters(36.0), 4) == 0.9144


def test_translation_exposes_position():
    p = Mat4.translation(1.5, -2.0, 0.25).position
    assert (p.x, p.y, p.z) == (1.5, -2.0, 0.25)


def test_vec3_tuple():
    assert Vec3(x=1, y=2, z=3).as_tuple() == (1, 2, 3)
