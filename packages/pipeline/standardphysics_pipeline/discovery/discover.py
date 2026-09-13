"""Finding the objects the scan measured but never named.

RoomPlan boxes the categories Apple ships, which are the furniture of a home.
A shop is full of things outside that list: the card reader on the counter, the
monitor behind it, the laptop on the desk, the kettle, the sign. Those arrive
as LiDAR and nothing else, so a check cannot reason about them and the owner
cannot move them.

This walks the capture once and gives them boxes.

    frames        photos, evenly spread across the walk
    detections    one vision pass per frame: what is here, and where in the picture
    people        every person's surface taken out of the mesh first
    carving       each rectangle plus the mesh becomes one measured box
    merging       the same object seen from several places becomes one object
    nodes         a SceneNode per object, sized by LiDAR and named by the photo

The photo only ever supplies a name and a rectangle. Every number comes from
the mesh, so a confident wrong label produces a mislabelled box rather than a
wrong measurement.
"""

from __future__ import annotations

import concurrent.futures
import logging
import pathlib
import uuid
from dataclasses import dataclass, field

import numpy as np
from standardphysics_contracts import SceneGraph, SceneNode

from ..lidar import LidarMeshError, room_cloud
from ..textures.camera import CameraMetadataError, PhotoCamera, load_cameras
from ..textures.project import depth_buffer
from .boxes import claimed_by_any, contained_fraction, resting_parent
from .carve import FrameView, carve
from .detect import Detection, DetectionError, Transport, detect_objects
from .merge import Candidate, DiscoveredObject, merge_candidates
from .people import without_people

log = logging.getLogger(__name__)

FRAME_LIMIT = 400
"""Every keyframe of a normal walk. A frame nobody reads is a person left in
the mesh and an object that was never there: on a real 110-second capture,
sampling 24 of 218 frames found half the laptops and a quarter of the people."""
DETECTION_WORKERS = 6
MIN_VOLUME = 0.0004
"""Forty cubic centimetres, about a card reader lying flat. Smaller is noise."""
MAX_FLOOR_CLEARANCE = 2.4
CONFIDENT_VIEWS = 4
"""Views that make a box worth trusting without a second look."""
MIN_VIEWS = 2
"""An object one frame saw once is usually a fragment of something else. Two
frames from different places agreeing is the cheapest evidence that it is real."""
ALREADY_MEASURED = 0.6
"""A carved object mostly inside a node RoomPlan already boxed is that node, not a new one."""
DISCOVERY_NAMESPACE = uuid.UUID("6f1f6a2e-9a5f-5f77-9a0c-8b6f1b0d4a10")


class DiscoveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class DiscoveryInputs:
    graph: SceneGraph
    poses_path: pathlib.Path
    frame_paths: dict[str, pathlib.Path]
    """Stored JPEG for each frame id, as the photo manifest lists them."""
    lidar_mesh_path: pathlib.Path


@dataclass
class DiscoveryResult:
    nodes: list[SceneNode] = field(default_factory=list)
    objects: list[DiscoveredObject] = field(default_factory=list)
    frames_read: int = 0
    people_points_removed: int = 0
    frames_with_people: int = 0
    failures: list[str] = field(default_factory=list)
    """Frames the vision model could not read. Never silent: a dropped frame is a smaller answer."""

    @property
    def mesh_points(self) -> int:
        return sum(len(object_.box.points) for object_ in self.objects)


def discover_objects(inputs: DiscoveryInputs, *, transport: Transport | None = None) -> DiscoveryResult:
    """Every object in the photos that the measured model does not already hold."""
    graph = inputs.graph
    if graph.capture_to_room is None:
        raise DiscoveryError("the scan has no capture_to_room transform, so photos cannot be projected")
    points = _mesh_points(inputs)
    cameras = _cameras(inputs, graph)
    detections, failures = _detect_all(cameras, inputs.frame_paths, transport)
    buffers = {camera.frame_id: depth_buffer(camera, points) for camera in cameras}
    removal = without_people(
        points, graph,
        [(camera, detections.get(camera.frame_id, []), buffers[camera.frame_id]) for camera in cameras],
    )
    unclaimed = removal.points[~claimed_by_any(removal.points, graph)]
    candidates = _carve_all(cameras, detections, unclaimed, buffers)
    objects = [
        object_ for object_ in merge_candidates(candidates)
        if _worth_keeping(object_, graph)
    ]
    return DiscoveryResult(
        nodes=[_node_for(object_, graph) for object_ in objects],
        objects=objects,
        frames_read=len(cameras) - len(failures),
        people_points_removed=removal.removed,
        frames_with_people=removal.frames_with_people,
        failures=failures,
    )


def _mesh_points(inputs: DiscoveryInputs) -> np.ndarray:
    try:
        points = room_cloud(inputs.lidar_mesh_path, inputs.graph.capture_to_room)
    except (LidarMeshError, OSError) as error:
        raise DiscoveryError(f"could not read the LiDAR mesh: {error}") from error
    if not len(points):
        raise DiscoveryError("the LiDAR mesh is empty")
    return points


def _cameras(inputs: DiscoveryInputs, graph: SceneGraph) -> list[PhotoCamera]:
    try:
        cameras = load_cameras(inputs.poses_path, inputs.frame_paths, graph.capture_to_room)
    except CameraMetadataError as error:
        raise DiscoveryError(f"the photos carry no usable camera metadata: {error}") from error
    stored = [camera for camera in cameras if inputs.frame_paths.get(camera.frame_id, pathlib.Path()).is_file()]
    if not stored:
        raise DiscoveryError("no stored photo has a matching camera pose")
    return _evenly_spread(stored, FRAME_LIMIT)


def _evenly_spread(cameras: list[PhotoCamera], limit: int) -> list[PhotoCamera]:
    if len(cameras) <= limit:
        return cameras
    picks = np.linspace(0, len(cameras) - 1, limit).round().astype(int)
    return [cameras[index] for index in dict.fromkeys(picks.tolist())]


def _detect_all(
    cameras: list[PhotoCamera],
    frame_paths: dict[str, pathlib.Path],
    transport: Transport | None,
) -> tuple[dict[str, list[Detection]], list[str]]:
    detections: dict[str, list[Detection]] = {}
    failures: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=DETECTION_WORKERS) as pool:
        futures = {
            pool.submit(detect_objects, frame_paths[camera.frame_id], camera.frame_id, transport=transport): camera
            for camera in cameras
        }
        for future in concurrent.futures.as_completed(futures):
            frame_id = futures[future].frame_id
            try:
                detections[frame_id] = future.result()
            except DetectionError as error:
                log.warning("no objects read from %s: %s", frame_id, error)
                failures.append(f"{frame_id}: {error}")
    return detections, failures


def _carve_all(
    cameras: list[PhotoCamera],
    detections: dict[str, list[Detection]],
    points: np.ndarray,
    buffers: dict[str, np.ndarray],
) -> list[Candidate]:
    candidates = []
    for camera in cameras:
        wanted = [one for one in detections.get(camera.frame_id, []) if not one.is_person]
        if not wanted:
            continue
        view = FrameView.of(points, camera, buffers[camera.frame_id])
        for detection in wanted:
            box = carve(view, detection)
            if box is not None and box.volume >= MIN_VOLUME:
                candidates.append(Candidate(detection=detection, box=box))
    return candidates


def _worth_keeping(object_: DiscoveredObject, graph: SceneGraph) -> bool:
    if object_.views < MIN_VIEWS:
        return False
    if object_.box.volume < MIN_VOLUME or object_.box.floor_clearance > MAX_FLOOR_CLEARANCE:
        return False
    return not any(
        contained_fraction(object_.box, node) >= ALREADY_MEASURED
        for node in graph.nodes
        if node.kind == "object"
    )


def _node_for(object_: DiscoveredObject, graph: SceneGraph) -> SceneNode:
    return SceneNode(
        id=_stable_id(graph.scan_id, object_),
        kind="object",
        label=object_.name.capitalize(),
        raw_category=object_.name.replace(" ", "_"),
        dimensions=object_.box.as_vec3(),
        transform=object_.box.as_transform(),
        quality="measured" if object_.views >= CONFIDENT_VIEWS else "needs_another_look",
        movable=object_.movable,
        labeled_by="discovery",
        parent_id=resting_parent(object_.box, graph),
    )


def _stable_id(scan_id: uuid.UUID, object_: DiscoveredObject) -> uuid.UUID:
    """The same object in the same place keeps its id, so a rebuild does not orphan a move."""
    where = ",".join(f"{value:.2f}" for value in object_.box.centre)
    return uuid.uuid5(DISCOVERY_NAMESPACE, f"{scan_id}|{object_.name}|{where}")
