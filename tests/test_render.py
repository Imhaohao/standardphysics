"""Blender-backed output. Skipped where Blender is not installed."""

import pathlib

import pytest

from standardphysics_fixtures import build_graph, build_scenario
from standardphysics_pipeline.blender import export_glb, glb_node_names, render_finding
from standardphysics_pipeline.check_blender import blender_path
from standardphysics_pipeline.locus import width_locus
from standardphysics_pipeline.measure import PipelineMeasurements


def blender_missing() -> bool:
    try:
        blender_path()
    except FileNotFoundError:
        return True
    return False


needs_blender = pytest.mark.skipif(blender_missing(), reason="Blender not installed")


@pytest.fixture
def finding_locus():
    graph, scenario = build_graph(), build_scenario()
    result = PipelineMeasurements().route_clear_width(graph, scenario, 0)
    return graph, width_locus(graph, result)


@needs_blender
def test_a_finding_renders(tmp_path, finding_locus):
    graph, locus = finding_locus
    out = render_finding(graph, locus, tmp_path / "finding.png", size=(400, 300))
    assert out.exists()
    assert out.stat().st_size > 5_000


@needs_blender
def test_glb_names_every_node_by_id(tmp_path):
    graph = build_graph()
    names = set(glb_node_names(export_glb(graph, tmp_path / "scene.glb")))
    assert {str(node.id) for node in graph.nodes} <= names


def test_the_camera_stays_inside_the_room(finding_locus):
    """A low camera puts the near wall between the lens and the subject, and
    spends half the frame outside the building."""
    graph, locus = finding_locus
    floor = next(node for node in graph.nodes if node.kind == "floor")
    half_depth = floor.dimensions.y / 2
    assert abs(locus.camera.position.y) < half_depth


def test_the_camera_clears_the_walls(finding_locus):
    graph, locus = finding_locus
    tallest = max(
        node.transform.position.z + node.dimensions.z / 2
        for node in graph.nodes
        if node.kind == "wall"
    )
    assert locus.camera.position.z > tallest * 0.8


def test_framing_includes_the_objects_causing_the_pinch(finding_locus):
    """A tight crop on the gap alone is two coloured shapes and no shop."""
    _, locus = finding_locus
    width = locus.bbox_max.x - locus.bbox_min.x
    assert width > 1.5
