"""Multi-view reconciliation of surface-attached detections.

Reconciles observations from multiple camera views, and refuses to merge
anything without agreeing visual evidence: proximity alone never collapses
two adjacent outlets into one, because the count of nearby devices is unknown
until their photos actually show the same device.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
from standardphysics_contracts import SceneNode, SurfaceAttachment

from ..textures.camera import PhotoCamera
from .detect import box_iou

MIN_INDEPENDENT_VIEW_DISTANCE_M = 0.50
MAX_SAME_OUTLET_SURFACE_DISTANCE_M = 0.06  # 6 cm faceplate tolerance
NORMAL_ALIGNMENT_MIN_COS = 0.85
VISUAL_AGREEMENT_IOU = 0.30
"""How much two boxes in the same photo must overlap to count as one detection."""


def _visually_agree(att_a: SurfaceAttachment, att_b: SurfaceAttachment) -> bool:
    """Whether some single photo shows both crops overlapping substantially.

    Two detections in the same frame that cover the same region are strong
    evidence of one device read twice. Detections from different frames carry
    no such evidence without a camera to verify against.
    """
    for obs_a in att_a.observations:
        for obs_b in att_b.observations:
            if obs_a.frame_id != obs_b.frame_id:
                continue
            if box_iou(tuple(obs_a.sensor_box), tuple(obs_b.sensor_box)) >= VISUAL_AGREEMENT_IOU:
                return True
    return False


def _reprojection_agrees(
    att: SurfaceAttachment,
    pos_other: np.ndarray,
    camera: PhotoCamera,
) -> bool:
    """Whether the other node's 3D centre lands inside this observation's padded photo box."""
    if not att.observations:
        return False
    col, row, depth = camera.project(pos_other.reshape(1, 3))
    if depth[0] <= 0:
        return False
    obs_box = att.observations[0].sensor_box
    pad_x = (obs_box[2] - obs_box[0]) * 0.20
    pad_y = (obs_box[3] - obs_box[1]) * 0.20
    return obs_box[0] - pad_x <= col[0] <= obs_box[2] + pad_x and obs_box[1] - pad_y <= row[0] <= obs_box[3] + pad_y


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
    - Any pair with neither camera nor shared-photo visual agreement:
      distance on its own never proves one device, so adjacent outlets stay
      separate and the count stays unknown
    """
    att_a = node_a.attachment
    att_b = node_b.attachment
    if att_a is None or att_b is None:
        return False
    if att_a.support_node_id != att_b.support_node_id or att_a.normal is None or att_b.normal is None:
        return False
    norm_a = np.array([att_a.normal.x, att_a.normal.y, att_a.normal.z], dtype=np.float64)
    norm_b = np.array([att_b.normal.x, att_b.normal.y, att_b.normal.z], dtype=np.float64)
    if float(np.dot(norm_a, norm_b)) < NORMAL_ALIGNMENT_MIN_COS:
        return False
    pos_a = np.array([node_a.transform.m[3], node_a.transform.m[7], node_a.transform.m[11]], dtype=np.float64)
    pos_b = np.array([node_b.transform.m[3], node_b.transform.m[7], node_b.transform.m[11]], dtype=np.float64)
    if float(np.linalg.norm(pos_a - pos_b)) > MAX_SAME_OUTLET_SURFACE_DISTANCE_M:
        return False

    verified = False
    if camera_a is not None:
        if not _reprojection_agrees(att_a, pos_b, camera_a):
            return False
        verified = True
    if camera_b is not None:
        if not _reprojection_agrees(att_b, pos_a, camera_b):
            return False
        verified = True

    if verified:
        return True
    return _visually_agree(att_a, att_b)


def _merged_observations(cluster: Sequence[SceneNode]) -> list:
    """Every observation in the cluster, one per frame."""
    seen_frames: set[str] = set()
    merged = []
    for node in cluster:
        if not node.attachment:
            continue
        for obs in node.attachment.observations:
            if obs.frame_id not in seen_frames:
                merged.append(obs)
                seen_frames.add(obs.frame_id)
    return merged


def _merged_sockets(cluster: Sequence[SceneNode]) -> list:
    """Every socket in the cluster, with ones within 3cm treated as the same socket."""
    merged: list = []
    for node in cluster:
        if not node.attachment:
            continue
        for socket in node.attachment.sockets:
            point = np.array([socket.center.x, socket.center.y, socket.center.z], dtype=np.float64)
            if not any(
                np.linalg.norm(point - np.array([m.center.x, m.center.y, m.center.z])) < 0.03
                for m in merged
            ):
                merged.append(socket)
    return merged


def _seen_from_independent_views(
    cameras: dict[str, PhotoCamera] | None, observations: Sequence
) -> bool:
    """Whether two of the observing cameras stood far enough apart to corroborate.

    Two frames taken from the same spot are one viewpoint twice, however many
    of them there are, so the test is distance between cameras rather than a
    count of observations.
    """
    if cameras is None or len(observations) < 2:
        return False
    observing = [cameras[obs.frame_id] for obs in observations if obs.frame_id in cameras]
    return any(
        np.linalg.norm(observing[i].position - observing[j].position) >= MIN_INDEPENDENT_VIEW_DISTANCE_M
        for i in range(len(observing))
        for j in range(i + 1, len(observing))
    )


def _merged_review_status(cluster: Sequence[SceneNode], first_att) -> str:
    """An owner's decision survives the merge, and a rejection outranks a confirmation."""
    if any(n.attachment and n.attachment.review_status == "rejected_by_user" for n in cluster):
        return "rejected_by_user"
    if any(n.attachment and n.attachment.review_status == "confirmed_by_user" for n in cluster):
        return "confirmed_by_user"
    return first_att.review_status


def _merged_uncertainty_reasons(cluster: Sequence[SceneNode], independent_views: bool) -> list[str]:
    """Each node's reasons, minus the single-viewpoint note, which is re-decided here.

    A cluster can be corroborated even when none of its members was, so the old
    note is dropped and re-added only if the merged evidence still stands on one
    viewpoint.
    """
    reasons: list[str] = []
    for node in cluster:
        if not node.attachment:
            continue
        for reason in node.attachment.uncertainty_reasons:
            if "single viewpoint" not in reason and reason not in reasons:
                reasons.append(reason)
    if not independent_views:
        reasons.append("single viewpoint observation; not independently verified from separate angle")
    return reasons


def merge_cluster(cluster: Sequence[SceneNode], cameras: dict[str, PhotoCamera] | None = None) -> SceneNode:
    """Merges a cluster of compatible outlet nodes, consolidating evidence and updating uncertainty."""
    import uuid

    first_att = cluster[0].attachment
    assert first_att is not None

    merged_obs = _merged_observations(cluster)
    merged_sockets = _merged_sockets(cluster)
    independent_views = _seen_from_independent_views(cameras, merged_obs)
    merged_review_status = _merged_review_status(cluster, first_att)
    uncertainty_reasons = _merged_uncertainty_reasons(cluster, independent_views)

    all_pos = [
        np.array([n.transform.m[3], n.transform.m[7], n.transform.m[11]], dtype=np.float64)
        for n in cluster
    ]
    merged_pos = np.mean(all_pos, axis=0)

    needs_verification = any(
        n.attachment and n.attachment.localization_quality == "needs_verification"
        for n in cluster
    )
    if not independent_views or needs_verification or first_att.support_type != "lidar_surface":
        localization_quality = "needs_verification"
    else:
        localization_quality = "verified_support"

    max_confidence = max(
        (n.attachment.identity_confidence for n in cluster if n.attachment),
        default=first_att.identity_confidence,
    )

    merged_att = SurfaceAttachment(
        support_node_id=first_att.support_node_id,
        support_type=first_att.support_type,
        local_anchor=first_att.local_anchor,
        normal=first_att.normal,
        observed_region=first_att.observed_region,
        sockets=merged_sockets,
        observations=merged_obs,
        identity_confidence=max_confidence,
        localization_quality=localization_quality,
        review_status=merged_review_status,
        uncertainty_reasons=uncertainty_reasons,
    )

    new_m = list(cluster[0].transform.m)
    new_m[3] = float(merged_pos[0])
    new_m[7] = float(merged_pos[1])
    new_m[11] = float(merged_pos[2])

    stable_seed = f"{merged_att.support_node_id}_{round(float(merged_pos[0]), 2)}_{round(float(merged_pos[1]), 2)}_{round(float(merged_pos[2]), 2)}"
    merged_id = uuid.uuid5(uuid.NAMESPACE_OID, stable_seed)

    return cluster[0].model_copy(update={
        "id": merged_id,
        "transform": cluster[0].transform.model_copy(update={"m": new_m}),
        "attachment": merged_att,
    })


def merge_two_nodes(node_a: SceneNode, node_b: SceneNode, cameras: dict[str, PhotoCamera] | None = None) -> SceneNode:
    """Merges two compatible outlet nodes, consolidating evidence and updating uncertainty."""
    return merge_cluster([node_a, node_b], cameras)


def reconcile_outlets(
    nodes: Sequence[SceneNode],
    cameras: dict[str, PhotoCamera] | None = None,
) -> list[SceneNode]:
    """Reconciles candidate outlet nodes, merging matching views while keeping distinct outlets separate."""
    outlets = [n for n in nodes if n.attachment is not None]
    non_outlets = [n for n in nodes if n.attachment is None]

    if not outlets:
        return list(nodes)

    # Sort outlets deterministically by ID string to ensure reproducible clustering
    sorted_outlets = sorted(outlets, key=lambda n: str(n.id))

    clusters: list[list[SceneNode]] = []
    for node in sorted_outlets:
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

    reconciled_outlets = [merge_cluster(cluster, cameras) for cluster in clusters]
    return non_outlets + reconciled_outlets

