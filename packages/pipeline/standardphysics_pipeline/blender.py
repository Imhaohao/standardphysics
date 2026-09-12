"""Driving Blender from the pipeline.

Blender runs as a subprocess because `bpy` as a library pins a Python version
we do not control. Every script lives in `blender_scripts/` and takes its
arguments after a bare `--`.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import tempfile

from standardphysics_contracts import SceneGraph

from .check_blender import blender_path

SCRIPTS = pathlib.Path(__file__).parent / "blender_scripts"

TIMEOUT_SECONDS = 300


class BlenderError(RuntimeError):
    pass


def _run(script: str, args: list[str]) -> str:
    result = subprocess.run(
        [blender_path(), "--background", "--python", str(SCRIPTS / script), "--", *args],
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise BlenderError(result.stderr[-2000:] or result.stdout[-2000:])
    return result.stdout


def export_glb(graph: SceneGraph, out_path: pathlib.Path) -> pathlib.Path:
    """Display geometry for the viewer, named by node ID.

    glTF node names take a UUID directly, so the viewer selects by the same ID
    the checks reason about with no mapping file in between.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        handle.write(graph.model_dump_json())
        graph_path = handle.name

    output = _run("build_glb.py", ["--graph", graph_path, "--out", str(out_path)])
    pathlib.Path(graph_path).unlink(missing_ok=True)

    if "GLB_WRITTEN" not in output:
        raise BlenderError(f"export did not report success:\n{output[-2000:]}")
    return out_path


def glb_node_names(path: pathlib.Path) -> list[str]:
    """Read the node names back out of a GLB, without Blender.

    A GLB is a 12 byte header then length-prefixed chunks; the first chunk is
    the JSON scene description.
    """
    data = path.read_bytes()
    if data[:4] != b"glTF":
        raise BlenderError(f"{path} is not a GLB")
    chunk_length = int.from_bytes(data[12:16], "little")
    scene = json.loads(data[20 : 20 + chunk_length].decode("utf-8"))
    return [node.get("name", "") for node in scene.get("nodes", [])]
