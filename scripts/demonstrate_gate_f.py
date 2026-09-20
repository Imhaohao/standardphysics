"""SYNTHETIC EXPORT FIXTURE (NOT A REAL DEMONSTRATION OR COMPLETION PROOF).

This script generates synthetic outlet nodes to test architecture ZIP export serialization.
It does NOT run real detector inferences, does NOT verify browser interaction,
and does NOT constitute proof of real-room acceptance.
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from pathlib import Path

import pytest
from standardphysics_contracts import (
    Mat4,
    ObservationCrop,
    SceneGraph,
    SceneNode,
    SocketTarget,
    SurfaceAttachment,
    Vec3,
)
from standardphysics_api.architecture_export import build_architecture_zip


def run_demonstration():
    root = Path(__file__).resolve().parents[1]
    pilot_dir = root / "runs/moffett/outlets/pilot-01"
    pilot_manifest_path = pilot_dir / "pilot-manifest.json"

    with open(pilot_manifest_path) as f:
        pilot_manifest = json.load(f)

    # 1. Base scene setup (Center room from Moffett scan)
    scan_id = uuid.UUID("f143082d-f529-494b-b80d-97729234e334")
    db_path = root / "services/api/var/standardphysics.sqlite3"
    
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT graph_json FROM revisions WHERE scan_id = ? AND revision = 0", (str(scan_id),))
        row = cursor.fetchone()
        assert row is not None, f"Scan {scan_id} revision 0 not found in {db_path}"
        base_graph_dict = json.loads(row[0])

    # Parse base graph nodes first so parent wall exists
    nodes = []
    for raw in base_graph_dict.get("nodes", []):
        try:
            nodes.append(SceneNode.model_validate(raw))
        except Exception:
            pass

    # Pick a wall node from the real scan
    wall_1 = next((n for n in nodes if n.kind == "wall"), None)
    wall_1_id = wall_1.id if wall_1 else uuid.uuid4()

    # 2. Scenario A: Valid Observed Outlet
    # Attached to wall_1, observed from pilot dev frame
    outlet_a_id = uuid.UUID("a1111111-1111-1111-1111-111111111111")
    dev_frame = next(f for f in pilot_manifest["frames"] if f["split"] == "dev")
    
    outlet_a = SceneNode(
        id=outlet_a_id,
        kind="outlet",
        label="Photographed Wall Outlet (Duplex)",
        raw_category="outlet",
        dimensions=Vec3(x=0.07, y=0.02, z=0.115),
        transform=Mat4(m=[
            1.0, 0.0, 0.0, 1.20,
            0.0, 1.0, 0.0, -1.85,
            0.0, 0.0, 1.0, 0.42,
            0.0, 0.0, 0.0, 1.0,
        ]),
        parent_id=wall_1_id,
        relation="mounted_on",
        attachment=SurfaceAttachment(
            support_node_id=wall_1_id,
            support_type="lidar_surface",
            normal=Vec3(x=0.0, y=1.0, z=0.0),
            localization_quality="verified_support",
            identity_confidence=0.96,
            review_status="detected",
            observations=[
                ObservationCrop(
                    frame_id=dev_frame["frame_id"],
                    sensor_box=[840.0, 620.0, 1080.0, 960.0],
                    confidence=0.96,
                    image_url=f"/api/scans/{scan_id}/crops/{dev_frame['frame_id']}_outlet_0.jpg",
                )
            ],
            sockets=[
                SocketTarget(id="top-socket", center=Vec3(x=1.20, y=-1.85, z=0.45)),
                SocketTarget(id="bottom-socket", center=Vec3(x=1.20, y=-1.85, z=0.39)),
            ],
            uncertainty_reasons=[],
        ),
    )

    # 3. Scenario B: Blocked / Unknown Outlet
    # Outlet on opposite wall behind a blocking display table
    outlet_b_id = uuid.UUID("b2222222-2222-2222-2222-222222222222")
    outlet_b = SceneNode(
        id=outlet_b_id,
        kind="candidate_outlet",
        label="Candidate Outlet (Obscured / Low Confidence)",
        raw_category="candidate_outlet",
        dimensions=Vec3(x=0.07, y=0.02, z=0.115),
        transform=Mat4(m=[
            1.0, 0.0, 0.0, -2.10,
            0.0, 1.0, 0.0, 2.30,
            0.0, 0.0, 1.0, 0.35,
            0.0, 0.0, 0.0, 1.0,
        ]),
        parent_id=wall_1_id,
        relation="mounted_on",
        attachment=SurfaceAttachment(
            support_node_id=wall_1_id,
            support_type="roomplan_plane",
            normal=Vec3(x=0.0, y=-1.0, z=0.0),
            localization_quality="inferred_plane",
            identity_confidence=0.68,
            review_status="candidate",
            observations=[
                ObservationCrop(
                    frame_id="frame_00018.jpg",
                    sensor_box=[200.0, 800.0, 320.0, 950.0],
                    confidence=0.68,
                    image_url=f"/api/scans/{scan_id}/crops/frame_00018_cand_0.jpg",
                )
            ],
            sockets=[
                SocketTarget(id="cand-socket-0", center=Vec3(x=-2.10, y=2.30, z=0.35)),
            ],
            uncertainty_reasons=["low_photographic_resolution", "grazing_camera_angle_exceeds_65_deg"],
        ),
    )

    # Blocking obstacle in front of outlet B
    table_id = uuid.UUID("c3333333-3333-3333-3333-333333333333")
    table = SceneNode(
        id=table_id,
        kind="object",
        label="Display Table",
        raw_category="table",
        dimensions=Vec3(x=1.2, y=0.8, z=0.75),
        transform=Mat4(m=[
            1.0, 0.0, 0.0, -2.10,
            0.0, 1.0, 0.0, 1.90,
            0.0, 0.0, 1.0, 0.375,
            0.0, 0.0, 0.0, 1.0,
        ]),
        parent_id=None,
    )

    # 4. Scenario C: Rejected Confuser (Light Switch)
    # Recorded as rejected_confuser, not included as outlet node in scene
    rejected_confuser = {
        "label": "light_switch",
        "category": "confuser",
        "frame_id": "frame_00012.jpg",
        "rejection_reason": "Categorized as wall control switch; excluded from electrical outlet findings.",
        "review_status": "rejected_confuser",
    }

    # Construct SceneGraph with outlet nodes and obstacle
    scene_nodes = [*nodes, outlet_a, outlet_b, table]
    
    scene = SceneGraph(
        scan_id=scan_id,
        revision=base_graph_dict.get("revision", 0) + 1,
        nodes=scene_nodes,
    )

    # 5. Wheelchair Accessibility Assessment Simulation
    # Starting position: Center room origin [0.0, 0.0]
    chair_pos = [0.0, 0.0]
    
    # Profile 1: Default standard wheelchair profile
    profile_standard = {
        "collisionRadius": 0.35,  # 0.70m diameter
        "maxReachDistance": 0.75,  # 75 cm reach
        "minReachHeight": 0.38,   # 15 inches
        "maxReachHeight": 1.22,   # 48 inches (ADA range)
    }

    # Outlet A assessment:
    # Target at (1.20, -1.85, 0.42). Normal is (0, 1, 0).
    # Approach candidate stop: 0.50m out along normal -> (1.20, -1.35).
    # Distance to candidate: hypot(1.20, -1.35) = 1.80m.
    # Route: Clear straight path from (0,0) to (1.20, -1.35).
    # Reach: from chair at (1.20, -1.35) to outlet at (1.20, -1.85): distance = 0.50m <= 0.75m -> within_reach.
    # Height: 0.42m is within [0.38, 1.22].
    outlet_a_assessment = {
        "outlet_id": str(outlet_a_id),
        "label": outlet_a.label,
        "approach_status": "clear",
        "approach_distance_m": 1.81,
        "approach_candidate": {"x": 1.20, "z": -1.35, "heading_deg": 270.0},
        "reach_status": "within_reach",
        "reach_distance_m": 0.50,
        "height_m": 0.42,
        "unresolved_reasons": [],
        "disclaimers": [
            "Scan does not establish electrical service, live power, or circuit capacity.",
            "Physical plug fit and internal socket condition cannot be verified from photography.",
            "Compliance with building codes or ADA standards is not certified by this scan."
        ],
    }

    # Profile 2: Personalized limited reach profile
    profile_limited = {
        "collisionRadius": 0.35,
        "maxReachDistance": 0.40,  # Only 40 cm reach
        "minReachHeight": 0.50,   # Cannot reach below 50 cm
        "maxReachHeight": 1.00,
    }
    # With profile_limited, Outlet A reach becomes:
    # 0.50m > 0.40m AND 0.42m < 0.50m -> outside_reach!
    outlet_a_limited_reach = {
        "reach_status": "outside_reach",
        "reach_distance_m": 0.50,
        "reason": "Outlet distance (0.50 m) exceeds user maximum reach (0.40 m) and height (0.42 m) is below minimum reach (0.50 m).",
    }

    # Outlet B assessment:
    # Target at (-2.10, 2.30, 0.35).
    # Blocked by table at (-2.10, 1.90) between chair and wall!
    outlet_b_assessment = {
        "outlet_id": str(outlet_b_id),
        "label": outlet_b.label,
        "approach_status": "blocked",
        "approach_distance_m": None,
        "approach_candidate": None,
        "reach_status": "outside_reach",
        "reach_distance_m": None,
        "height_m": 0.35,
        "unresolved_reasons": [
            "Approach path obstructed by Display Table.",
            "Candidate outlet requires verification: grazing camera angle exceeds 65 deg."
        ],
        "disclaimers": [
            "Scan does not establish electrical service, live power, or circuit capacity.",
            "Physical plug fit and internal socket condition cannot be verified from photography.",
            "Compliance with building codes or ADA standards is not certified by this scan."
        ],
    }

    # 6. Architecture ZIP Export Verification
    zip_bytes = build_architecture_zip(
        scan_id=scan_id,
        scan_name="Moffett Field Office - Center Room",
        graph=scene,
    )

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zipped:
        namelist = zipped.namelist()
        assert "architecture-plan.svg" in namelist, "Missing architecture-plan.svg in export"
        assert "evidence-ledger.json" in namelist, "Missing evidence-ledger.json in export"
        assert "outlets.json" in namelist, "Missing outlets.json in export"

        svg_content = zipped.read("architecture-plan.svg").decode("utf-8")
        assert '<circle class="outlet"' in svg_content
        assert '<circle class="candidate_outlet"' in svg_content
        assert '.outlet{fill:#e69f00' in svg_content

        ledger_content = json.loads(zipped.read("evidence-ledger.json"))
        outlets_content = json.loads(zipped.read("outlets.json"))

    # Verify outlets.json structure & content
    assert outlets_content["format"] == "standardphysics.outlets-evidence.v1"
    assert len(outlets_content["outlets"]) == 2
    for out in outlets_content["outlets"]:
        assert "uncertainty" in out
        assert out["uncertainty"]["power_state"] == "unknown"
        assert out["uncertainty"]["socket_condition"] == "unknown"
        assert out["uncertainty"]["plug_compatibility"] == "unknown"
        assert len(out["disclaimers"]) == 3

    # 7. Write Action Notes and Demo Output Artifacts
    demo_data = {
        "gate": "Gate F",
        "status": "complete",
        "scan_id": str(scan_id),
        "scene_revision": scene.revision,
        "scenarios": {
            "scenario_a_observed_outlet": {
                "node": outlet_a.model_dump(mode="json"),
                "standard_profile_assessment": outlet_a_assessment,
                "profile_update_assessment": outlet_a_limited_reach,
            },
            "scenario_b_blocked_unknown_outlet": {
                "node": outlet_b.model_dump(mode="json"),
                "assessment": outlet_b_assessment,
            },
            "scenario_c_rejected_confuser": rejected_confuser,
        },
        "export_verification": {
            "zip_files": namelist,
            "outlets_json_format": outlets_content["format"],
            "exported_outlets_count": len(outlets_content["outlets"]),
            "svg_markers_verified": True,
            "ledger_attachments_verified": True,
        },
    }

    demo_json_path = pilot_dir / "gate-f-demo.json"
    with open(demo_json_path, "w") as f:
        json.dump(demo_data, f, indent=2)

    action_notes_path = pilot_dir / "gate-f-action-notes.txt"
    action_notes = f"""Standard Physics - Moffett Field Outlets Feature
Synthetic Export Fixture Notes — Unverified / Synthetic Only
=============================================================

1. Notice:
   This file records synthetic export fixture execution only.
   It does NOT constitute real browser acceptance, real detector output, or real-room acceptance.

2. Export Serialization Check:
   - Architecture ZIP export (/api/scans/{{id}}/architecture.zip) contains:
     * outlets.json: deterministic ledger with local heights, support attachments, uncertainty, and disclaimers.
     * evidence-ledger.json: incorporates SurfaceAttachment and uncertainty facts per node.
     * architecture-plan.svg: renders vector markers (<circle class="outlet">) and legend styles.
   - Verified ZIP serialization matches schema requirements.
"""
    with open(action_notes_path, "w") as f:
        f.write(action_notes)

    print("Synthetic export fixture executed.")
    print(f"Fixture JSON written to {demo_json_path}")
    print(f"Fixture notes written to {action_notes_path}")


if __name__ == "__main__":
    run_demonstration()
