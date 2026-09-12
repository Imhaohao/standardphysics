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


def test_stops_and_widths_without_the_new_fields_still_validate():
    from standardphysics_contracts import Stop, WidthResult

    stop = Stop.model_validate({"name": "Entrance", "position": {"x": 0, "y": 0, "z": 0}})
    assert stop.anchor_node_id is None
    width = WidthResult.model_validate(
        {"inches": 31.0, "pinch_point": {"x": 0, "y": 0, "z": 0}, "blocking_node_ids": []}
    )
    assert width.needs_measurement is False


def test_graph_hash_ignores_node_order_and_revision():
    from standardphysics_contracts import graph_hash
    from standardphysics_fixtures import build_graph

    graph = build_graph()
    reordered = graph.model_copy(update={"nodes": list(reversed(graph.nodes)), "revision": 7})
    assert graph_hash(reordered) == graph_hash(graph)


def test_graph_hash_changes_when_a_node_moves():
    from standardphysics_contracts import graph_hash
    from standardphysics_fixtures import build_graph, node_id

    graph = build_graph()
    before = graph_hash(graph)
    graph.by_id(node_id("case_east")).transform.m[3] += 0.01
    assert graph_hash(graph) != before
