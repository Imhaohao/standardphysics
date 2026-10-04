"""A Blender run that outlives its time limit fails the way every other Blender failure does.

Callers that can do without Blender's output catch BlenderError, or the
RuntimeError it extends, and carry on without it. The timeout that
subprocess.run raises is neither, so a hung Blender used to fail the whole job.
"""

from __future__ import annotations

import stat

import pytest
from standardphysics_fixtures import build_graph
from standardphysics_pipeline import blender


def _a_blender_that_hangs(tmp_path):
    """Write a stand-in for the Blender binary that prints one line and then sleeps far past the time limit."""
    stand_in = tmp_path / "blender"
    stand_in.write_text("#!/bin/sh\necho 'Read prefs: /tmp/userpref.blend' >&2\nexec sleep 30\n")
    stand_in.chmod(stand_in.stat().st_mode | stat.S_IXUSR)
    return stand_in


def test_a_run_past_the_time_limit_is_a_blender_error_that_keeps_what_blender_printed(tmp_path, monkeypatch):
    monkeypatch.setenv("BLENDER", str(_a_blender_that_hangs(tmp_path)))
    monkeypatch.setattr(blender, "TIMEOUT_SECONDS", 1.5)
    with pytest.raises(blender.BlenderError, match="timed out after 1.5 seconds") as raised:
        blender.export_glb(build_graph(), tmp_path / "scene.glb")
    assert "Read prefs: /tmp/userpref.blend" in str(raised.value)
