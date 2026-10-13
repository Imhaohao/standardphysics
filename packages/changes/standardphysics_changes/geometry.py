"""Points from depth, pixels from points, and a room frame with the floor at z = 0."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .views import View


@dataclass
class Cloud:
    points: np.ndarray
    colors: np.ndarray
    epoch: np.ndarray

    def __len__(self) -> int:
        return len(self.points)

    def subset(self, mask: np.ndarray) -> Cloud:
        return Cloud(self.points[mask], self.colors[mask], self.epoch[mask])


@dataclass(frozen=True)
class Sampling:
    """Which pixels become points. Depth is least reliable at the frame's edge and right in front of the lens."""

    stride: int = 2
    border_px: int = 10
    min_depth_m: float = 0.4
    min_confidence: float = 0.0


def backproject(view: View, sampling: Sampling = Sampling()) -> tuple[np.ndarray, np.ndarray]:
    """World points and colours for the trusted pixels of one view, every `stride` pixels."""
    edge = sampling.border_px
    rows, cols = np.mgrid[edge:view.shape[0] - edge:sampling.stride, edge:view.shape[1] - edge:sampling.stride]
    depth = view.depth[rows, cols]
    keep = (depth > sampling.min_depth_m) & (view.confidence[rows, cols] > sampling.min_confidence)
    z = depth[keep]
    fx, fy = view.intrinsics[0, 0], view.intrinsics[1, 1]
    cx, cy = view.intrinsics[0, 2], view.intrinsics[1, 2]
    camera = np.stack([(cols[keep] + 0.5 - cx) / fx * z, (rows[keep] + 0.5 - cy) / fy * z, z], axis=1)
    world = camera @ view.cam_to_world[:3, :3].T + view.cam_to_world[:3, 3]
    return world.astype(np.float32), view.image[rows[keep], cols[keep]]


def project(points: np.ndarray, view: View) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pixel column, pixel row and depth of world points in one view."""
    world_to_cam = np.linalg.inv(view.cam_to_world)
    camera = points @ world_to_cam[:3, :3].T + world_to_cam[:3, 3]
    z = camera[:, 2]
    safe = np.where(z > 1e-6, z, 1e-6)
    u = camera[:, 0] / safe * view.intrinsics[0, 0] + view.intrinsics[0, 2]
    v = camera[:, 1] / safe * view.intrinsics[1, 1] + view.intrinsics[1, 2]
    return u, v, z


def voxel_downsample(points: np.ndarray, colors: np.ndarray, size: float) -> tuple[np.ndarray, np.ndarray]:
    """One averaged point per occupied voxel."""
    if len(points) == 0:
        return points, colors
    keys = np.floor(points / size).astype(np.int64)
    _, inverse, counts = np.unique(keys, axis=0, return_inverse=True, return_counts=True)
    inverse = inverse.reshape(-1)
    mean_points = np.zeros((len(counts), 3))
    mean_colors = np.zeros((len(counts), 3))
    np.add.at(mean_points, inverse, points)
    np.add.at(mean_colors, inverse, colors.astype(np.float64))
    return (mean_points / counts[:, None]).astype(np.float32), (mean_colors / counts[:, None]).astype(np.uint8)


def build_cloud(views: list[View], voxel: float, sampling: Sampling = Sampling()) -> Cloud:
    """Each recording's surfaces as its own voxelised cloud, so the two never blend."""
    parts = []
    for epoch in sorted({view.epoch for view in views}):
        pairs = [backproject(view, sampling) for view in views if view.epoch == epoch]
        points, colors = voxel_downsample(np.concatenate([p for p, _ in pairs]), np.concatenate([c for _, c in pairs]),
                                          voxel)
        parts.append(Cloud(points, colors, np.full(len(points), epoch, dtype=np.uint8)))
    return Cloud(
        np.concatenate([p.points for p in parts]),
        np.concatenate([p.colors for p in parts]),
        np.concatenate([p.epoch for p in parts]),
    )


def rough_up(views: list[View]) -> np.ndarray:
    """People hold phones roughly upright, so the cameras' negative y axes average to up."""
    up = -np.mean([view.cam_to_world[:3, 1] for view in views], axis=0)
    return up / np.linalg.norm(up)


def _plane_candidates(points: np.ndarray, up: np.ndarray, rng: np.random.Generator, tries: int,
                      max_tilt_deg: float, inlier_m: float) -> list[tuple[int, np.ndarray, float]]:
    """Random three-point planes that face roughly up, with how many points lie on each."""
    found = []
    for _ in range(tries):
        a, b, c = points[rng.choice(len(points), 3, replace=False)]
        normal = np.cross(b - a, c - a)
        if np.linalg.norm(normal) < 1e-9:
            continue
        normal /= np.linalg.norm(normal)
        normal = normal if normal @ up > 0 else -normal
        if normal @ up < np.cos(np.radians(max_tilt_deg)):
            continue
        offset = float(a @ normal)
        found.append((int(np.sum(np.abs(points @ normal - offset) < inlier_m)), normal, offset))
    return found


def _lowest_broad_plane(points: np.ndarray, up: np.ndarray, tries: int = 400, max_tilt_deg: float = 35.0,
                        inlier_m: float = 0.02, broad_share: float = 0.4) -> tuple[np.ndarray, float]:
    """Among planes holding at least `broad_share` of the best plane's support, the lowest one.

    The cameras' average up is only rough: a phone pitched down while walking tilts it
    by tens of degrees. So the search accepts tilted planes and lets support decide,
    and picks the lowest broad one because a big tabletop can rival the floor.
    """
    rng = np.random.default_rng(0)
    sample = points[rng.choice(len(points), min(len(points), 40000), replace=False)]
    found = _plane_candidates(sample, up, rng, tries, max_tilt_deg, inlier_m)
    if not found:
        return up, float(np.percentile(points @ up, 2))
    best = max(count for count, _, _ in found)
    broad = [(count, normal, offset) for count, normal, offset in found if count >= broad_share * best]
    centre = sample.mean(axis=0)
    _, normal, offset = min(broad, key=lambda item: _height_under(centre, item[1], item[2], up))
    return normal, offset


def _height_under(centre: np.ndarray, normal: np.ndarray, offset: float, up: np.ndarray) -> float:
    """How high a plane is straight below the middle of the room, along one shared up.

    Offsets along two different normals measure different things: a plane tilted 30 degrees
    can have the smaller offset and still pass well above the floor in the middle of the room.
    """
    return float(centre @ up + (offset - normal @ centre) / (normal @ up))


def fit_floor(points: np.ndarray, up: np.ndarray, rounds: int = 3) -> tuple[np.ndarray, float]:
    """Normal and height of the floor: the lowest flat surface holding a real share of the points."""
    normal, height = _lowest_broad_plane(points, up)
    for _ in range(rounds):
        near = points[np.abs(points @ normal - height) < 0.04]
        if len(near) < 50:
            break
        centred = near - near.mean(axis=0)
        candidate = np.linalg.svd(centred, full_matrices=False)[2][-1]
        normal = candidate if candidate @ up > 0 else -candidate
        height = float(near.mean(axis=0) @ normal)
    return normal, height


def _histogram_sharpness(xy: np.ndarray, angle: float, bin_m: float = 0.05) -> float:
    c, s = np.cos(angle), np.sin(angle)
    total = 0.0
    for axis in (xy @ np.array([c, s]), xy @ np.array([-s, c])):
        counts, _ = np.histogram(axis, bins=max(int(np.ptp(axis) / bin_m), 1))
        total += float(np.sum(counts.astype(np.float64) ** 2))
    return total


def wall_angle(xy: np.ndarray) -> float:
    """The yaw that lines the walls up with the axes: walls are long straight runs of points."""
    angles = np.radians(np.arange(0, 90, 1.0))
    return float(angles[int(np.argmax([_histogram_sharpness(xy, a) for a in angles]))])


def room_frame(views: list[View], points: np.ndarray) -> np.ndarray:
    """A world-to-room transform: z up, floor at z = 0, walls along x and y."""
    up = rough_up(views)
    normal, height = fit_floor(points, up)
    forward = views[0].cam_to_world[:3, 2]
    y_axis = forward - (forward @ normal) * normal
    y_axis /= np.linalg.norm(y_axis)
    x_axis = np.cross(y_axis, normal)
    rotation = np.stack([x_axis, y_axis, normal])
    origin = views[0].position - (views[0].position @ normal - height) * normal
    transform = np.eye(4)
    transform[:3, :3] = rotation
    transform[:3, 3] = -rotation @ origin
    in_room = points @ rotation.T + transform[:3, 3]
    upright = in_room[(in_room[:, 2] > 0.3) & (in_room[:, 2] < 2.0)]
    if len(upright) > 100:
        yaw = wall_angle(upright[:, :2])
        c, s = np.cos(-yaw), np.sin(-yaw)
        spin = np.eye(4)
        spin[:2, :2] = [[c, -s], [s, c]]
        transform = spin @ transform
    return transform


def apply(transform: np.ndarray, points: np.ndarray) -> np.ndarray:
    return (points @ transform[:3, :3].T + transform[:3, 3]).astype(np.float32)
