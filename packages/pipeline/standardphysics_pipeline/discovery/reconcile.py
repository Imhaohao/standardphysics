"""Multi-view reconciliation of surface-attached detections.

Reconciles observations from multiple camera views without coarse distance-based
merging that would collapse adjacent outlets, duplex plates, or fixtures on
opposite sides of a wall.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Sequence

import numpy as np
from standardphysics_contracts import SceneNode, SurfaceAttachment, Vec3

from ..textures.camera import PhotoCamera

MIN_INDEPENDENT_VIEW_DISTANCE_M = 0.50
MAX_SAME_OUTLET_SURFACE_DISTANCE_M = 0.06  # 6 cm faceplate tolerance
NORMAL_ALIGNMENT_MIN_COS = 0.85


def are_compatible_observations(
    node_a: SceneNode,
    node_b: SceneNode,
    camera_a: PhotoCamera | None = None,
    camera_b: PhotoCamera | None = None,
) -> bool:
    """Checks whether two surface-attached observations represent the same physical outlet.
    
    Rejects:
    - Different support parents (different walls or furniture)
    - Opposite or tilted surface normals (e.g. opposite sides of a wall)
    - Surface distance exceeding faceplate tolerance (e.g. adjacent duplex sockets)
    - Reprojection mismatches when cameras are provided
    """
    att_a = node_a.attachment
    att_b = node_b.attachment
    if att_a is None or att_b is None:
        return False

    # Must share same support parent
    if att_a.support_node_id != att_b.support_node_id:
        return False

    # Both must have normal defined, and normals must be aligned
    if att_a.normal is None or att_b.normal is None:
        return False
    norm_a = np.array([att_a.normal.x, att_a.normal.y, att_a.normal.z], dtype=np.float64)
    norm_b = np.array([att_b.normal.x, att_b.normal.y, att_b.normal.z], dtype=np.float64)
    if float(np.dot(norm_a, norm_b)) < NORMAL_ALIGNMENT_MIN_COS:
        return False

    # Check 3D distance between centers
    pos_a = np.array([node_a.transform.m[3], node_a.transform.m[7], node_a.transform.m[11]], dtype=np.float64)
    pos_b = np.array([node_b.transform.m[3], node_b.transform.m[7], node_b.transform.m[11]], dtype=np.float64)
    dist = float(np.linalg.norm(pos_a - pos_b))
    if dist > MAX_SAME_OUTLET_SURFACE_DISTANCE_M:
        return False

    # Reprojection check if cameras available
    if camera_a is not None and len(att_b.observations) > 0:
        col, row, depth = camera_a.project(pos_b.reshape(1, 3))
        if depth[0] <= 0:
            return False

    if camera_b is not None and len(att_a.observations) > 0:
        col, row, depth = camera_b.project(pos_a.reshape(1, 3))
        if depth[0] <= 0:
            return False

    return True


def merge_two_nodes(node_a: SceneNode, node_b: SceneNode, cameras: dict[str, PhotoCamera] | None = None) -> SceneNode:
    """Merges two compatible outlet nodes, consolidating evidence and updating uncertainty."""
    att_a = node_a.attachment
    att_b = node_b.attachment
    assert att_a is not None and att_b is not None

    # Merge observations without duplicating frames
    seen_frames = {obs.frame_id for obs in att_a.observations}
    merged_obs = list(att_a.observations)
    for obs in att_b.observations:
        if obs.frame_id not in seen_frames:
            merged_obs.append(obs)
            seen_frames.add(obs.frame_id)

    # Average 3D position
    pos_a = np.array([node_a.transform.m[3], node_a.transform.m[7], node_a.transform.m[11]], dtype=np.float64)
    pos_b = np.array([node_b.transform.m[3], node_b.transform.m[7], node_b.transform.m[11]], dtype=np.float64)
    merged_pos = (pos_a + pos_b) / 2.0

    # Combine sockets
    merged_sockets = list(att_a.sockets)
    for s_b in att_b.sockets:
        # Avoid duplicate sockets if close (< 3cm)
        s_b_pt = np.array([s_b.center.x, s_b.center.y, s_b.center.z], dtype=np.float64)
        if not any(
            np.linalg.norm(s_b_pt - np.array([s_a.center.x, s_a.center.y, s_a.center.z])) < 0.03
            for s_a in att_a.sockets
        ):
            merged_sockets.append(s_b)

    # Determine viewpoint independence
    independent_views = False
    if cameras is not None and len(merged_obs) >= 2:
        obs_cams = [cameras[obs.frame_id] for obs in merged_obs if obs.frame_id in cameras]
        if len(obs_cams) >= 2:
            for i in range(len(obs_cams)):
                for j in range(i + 1, len(obs_cams)):
                    cam_dist = np.linalg.norm(obs_cams[i].position - obs_cams[j].position)
                    if cam_dist >= MIN_INDEPENDENT_VIEW_DISTANCE_M:
                        independent_views = True
                        break

    uncertainty_reasons = [
        r for r in att_a.uncertainty_reasons
        if "single viewpoint" not in r
    ]
    if not independent_views:
        if not any("single viewpoint" in r for r in uncertainty_reasons):
            uncertainty_reasons.append("single viewpoint observation; not independently verified from separate angle")

    localization_quality = "verified_support" if independent_views and att_a.support_type == "lidar_surface" else att_a.localization_quality

    merged_att = SurfaceAttachment(
        support_node_id=att_a.support_node_id,
        support_type=att_a.support_type,
        local_anchor=att_a.local_anchor,
        normal=att_a.normal,
        observed_region=att_a.observed_region,
        sockets=merged_sockets,
        observations=merged_obs,
        identity_confidence=max(att_a.identity_confidence, att_b.identity_confidence),
        localization_quality=localization_quality,
        review_status=att_a.review_status,
        uncertainty_reasons=uncertainty_reasons,
    )

    new_m = list(node_a.transform.m)
    new_m[3] = float(merged_pos[0])
    new_m[7] = float(merged_pos[1])
    new_m[11] = float(merged_pos[2])

    return node_a.model_copy(update={
        "transform": node_a.transform.model_copy(update={"m": new_m}),
        "attachment": merged_att,
    })


def reconcile_outlets(
    nodes: Sequence[SceneNode],
    cameras: dict[str, PhotoCamera] | None = None,
) -> list[SceneNode]:
    """Reconciles candidate outlet nodes, merging matching views while keeping distinct outlets separate."""
    outlets = [n for n in nodes if n.attachment is not None]
    non_outlets = [n for n in nodes if n.attachment is None]

    if not outlets:
        return list(nodes)

    clusters: list[list[SceneNode]] = []
    for node in outlets:
        matched_cluster = None
        for cluster in clusters:
            # Check compatibility against all nodes in the cluster to prevent transitive chain merging
            cam_node = cameras.get(node.attachment.observations[0].frame_id) if cameras and node.attachment.observations else None
            if all(
                are_compatible_observations(
                    node,
                    c_node,
                    cam_node,
                    cameras.get(c_node.attachment.observations[0].frame_id) if cameras and c_node.attachment.observations else None,
                )
                for c_node in cluster
            ):
                matched_cluster = cluster
                break
        if matched_cluster is not None:
            matched_cluster.append(node)
        else:
            clusters.append([node])

    reconciled_outlets: list[SceneNode] = []
    for cluster in clusters:
        current = cluster[0]
        for other in cluster[1:]:
            current = merge_two_nodes(current, other, cameras)
        reconciled_outlets.append(current)

    return non_outlets + reconciled_outlets
