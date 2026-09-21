"""Multi-view reconciliation of surface-attached detections.

Reconciles observations from multiple camera views without coarse distance-based
merging that would collapse adjacent outlets, duplex plates, or fixtures on
opposite sides of a wall.
"""

from __future__ import annotations

import uuid
from typing import Sequence

import numpy as np
from standardphysics_contracts import ObservationCrop, SceneNode, SurfaceAttachment

from ..textures.camera import PhotoCamera

MIN_INDEPENDENT_VIEW_DISTANCE_M = 0.50
MAX_SAME_OUTLET_SURFACE_DISTANCE_M = 0.06  # 6 cm faceplate tolerance
NORMAL_ALIGNMENT_MIN_COS = 0.85


CROP_PADDING = 0.20
"""How far outside a recorded crop a reprojected point may land and still be it."""


def _centre(node: SceneNode) -> np.ndarray:
    return np.array([node.transform.m[3], node.transform.m[7], node.transform.m[11]], dtype=np.float64)


def _normals_point_the_same_way(a: SurfaceAttachment, b: SurfaceAttachment) -> bool:
    """Two faceplates on opposite sides of one wall share a parent but not a direction."""
    if a.normal is None or b.normal is None:
        return False
    facing_a = np.array([a.normal.x, a.normal.y, a.normal.z], dtype=np.float64)
    facing_b = np.array([b.normal.x, b.normal.y, b.normal.z], dtype=np.float64)
    return float(np.dot(facing_a, facing_b)) >= NORMAL_ALIGNMENT_MIN_COS


def _lands_in_the_crop(
    camera: PhotoCamera | None, attachment: SurfaceAttachment, point: np.ndarray
) -> bool:
    """Where this camera saw its own outlet, the other's centre should appear too.

    Without a camera or a recorded crop there is nothing to disagree with, so
    the check passes rather than inventing a disagreement.
    """
    if camera is None or not attachment.observations:
        return True
    col, row, depth = camera.project(point.reshape(1, 3))
    if depth[0] <= 0:
        return False
    left, top, right, bottom = attachment.observations[0].sensor_box
    pad_x = (right - left) * CROP_PADDING
    pad_y = (bottom - top) * CROP_PADDING
    return left - pad_x <= col[0] <= right + pad_x and top - pad_y <= row[0] <= bottom + pad_y


def are_compatible_observations(
    node_a: SceneNode,
    node_b: SceneNode,
    camera_a: PhotoCamera | None = None,
    camera_b: PhotoCamera | None = None,
) -> bool:
    """Whether two surface-attached observations are one physical outlet.

    Distance alone would collapse the two halves of a duplex plate, a pair of
    outlets a hand's width apart, and two fixtures back to back through one
    wall. So sharing a support, facing the same way and reprojecting into each
    other's crop all have to hold as well.
    """
    att_a = node_a.attachment
    att_b = node_b.attachment
    if att_a is None or att_b is None:
        return False
    if att_a.support_node_id != att_b.support_node_id:
        return False
    if not _normals_point_the_same_way(att_a, att_b):
        return False

    here, there = _centre(node_a), _centre(node_b)
    if float(np.linalg.norm(here - there)) > MAX_SAME_OUTLET_SURFACE_DISTANCE_M:
        return False

    return _lands_in_the_crop(camera_a, att_a, there) and _lands_in_the_crop(camera_b, att_b, here)


def _attachments(cluster: Sequence[SceneNode]) -> list[SurfaceAttachment]:
    return [node.attachment for node in cluster if node.attachment]


def _observations_once_per_frame(cluster: Sequence[SceneNode]) -> list[ObservationCrop]:
    """Every frame that saw this thing, each counted once."""
    seen: set[str] = set()
    merged = []
    for attachment in _attachments(cluster):
        for obs in attachment.observations:
            if obs.frame_id not in seen:
                merged.append(obs)
                seen.add(obs.frame_id)
    return merged


def _averaged_position(cluster: Sequence[SceneNode]) -> np.ndarray:
    return np.mean(
        [
            np.array([n.transform.m[3], n.transform.m[7], n.transform.m[11]], dtype=np.float64)
            for n in cluster
        ],
        axis=0,
    )


def _sockets_without_repeats(cluster: Sequence[SceneNode]) -> list:
    """Sockets closer than 3 cm are the same socket seen twice."""
    merged: list = []
    for attachment in _attachments(cluster):
        for socket in attachment.sockets:
            here = np.array([socket.center.x, socket.center.y, socket.center.z], dtype=np.float64)
            already = any(
                np.linalg.norm(here - np.array([m.center.x, m.center.y, m.center.z])) < 0.03
                for m in merged
            )
            if not already:
                merged.append(socket)
    return merged


def _seen_from_separate_places(
    observations: Sequence[ObservationCrop], cameras: dict[str, PhotoCamera] | None
) -> bool:
    """Two cameras half a metre apart make a second look, rather than a second frame."""
    if cameras is None:
        return False
    positions = [cameras[obs.frame_id].position for obs in observations if obs.frame_id in cameras]
    return any(
        np.linalg.norm(positions[i] - positions[j]) >= MIN_INDEPENDENT_VIEW_DISTANCE_M
        for i in range(len(positions))
        for j in range(i + 1, len(positions))
    )


def _review_status(cluster: Sequence[SceneNode], fallback: str) -> str:
    """What an owner said outlives what a detector found, and a rejection outranks a confirmation."""
    said = {attachment.review_status for attachment in _attachments(cluster)}
    if "rejected_by_user" in said:
        return "rejected_by_user"
    if "confirmed_by_user" in said:
        return "confirmed_by_user"
    return fallback


def _uncertainty_reasons(cluster: Sequence[SceneNode], independent_views: bool) -> list[str]:
    reasons: list[str] = []
    for attachment in _attachments(cluster):
        for reason in attachment.uncertainty_reasons:
            if "single viewpoint" not in reason and reason not in reasons:
                reasons.append(reason)
    if not independent_views:
        reasons.append(
            "single viewpoint observation; not independently verified from separate angle"
        )
    return reasons


def _localization_quality(
    cluster: Sequence[SceneNode], first: SurfaceAttachment, independent_views: bool
) -> str:
    unsure = any(
        attachment.localization_quality == "needs_verification"
        for attachment in _attachments(cluster)
    )
    if not independent_views or unsure or first.support_type != "lidar_surface":
        return "needs_verification"
    return "verified_support"


def merge_cluster(cluster: Sequence[SceneNode], cameras: dict[str, PhotoCamera] | None = None) -> SceneNode:
    """Merges a cluster of compatible outlet nodes, consolidating evidence and updating uncertainty."""
    first = cluster[0].attachment
    assert first is not None

    observations = _observations_once_per_frame(cluster)
    position = _averaged_position(cluster)
    independent_views = _seen_from_separate_places(observations, cameras)

    merged_att = SurfaceAttachment(
        support_node_id=first.support_node_id,
        support_type=first.support_type,
        local_anchor=first.local_anchor,
        normal=first.normal,
        observed_region=first.observed_region,
        sockets=_sockets_without_repeats(cluster),
        observations=observations,
        identity_confidence=max(
            (attachment.identity_confidence for attachment in _attachments(cluster)),
            default=first.identity_confidence,
        ),
        localization_quality=_localization_quality(cluster, first, independent_views),
        review_status=_review_status(cluster, first.review_status),
        uncertainty_reasons=_uncertainty_reasons(cluster, independent_views),
    )

    placed = list(cluster[0].transform.m)
    placed[3], placed[7], placed[11] = (float(value) for value in position)

    seed = "_".join(
        [str(merged_att.support_node_id)] + [str(round(float(value), 2)) for value in position]
    )
    return cluster[0].model_copy(update={
        "id": uuid.uuid5(uuid.NAMESPACE_OID, seed),
        "transform": cluster[0].transform.model_copy(update={"m": placed}),
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

