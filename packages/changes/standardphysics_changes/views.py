"""One reconstructed camera view: the picture, its metric depth and where the camera stood."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

BEFORE, AFTER = 0, 1
EPOCH_NAMES = ("before", "after")


@dataclass
class View:
    epoch: int
    frame_index: int
    time_s: float
    image: np.ndarray
    """H x W x 3 uint8, pixel-aligned with `depth`."""
    detail: np.ndarray
    """The same framing at a higher resolution, for crops a person or a model looks at."""
    depth: np.ndarray
    """H x W float32 metres along the optical axis, 0 where the reconstruction has no answer."""
    confidence: np.ndarray
    intrinsics: np.ndarray
    cam_to_world: np.ndarray
    """4 x 4, OpenCV axes: x right, y down, z forward."""

    @property
    def shape(self) -> tuple[int, int]:
        return self.depth.shape[0], self.depth.shape[1]

    @property
    def position(self) -> np.ndarray:
        return self.cam_to_world[:3, 3]

    def moved_by(self, transform: np.ndarray) -> View:
        return View(
            epoch=self.epoch, frame_index=self.frame_index, time_s=self.time_s, image=self.image,
            detail=self.detail, depth=self.depth, confidence=self.confidence, intrinsics=self.intrinsics,
            cam_to_world=transform @ self.cam_to_world,
        )

    def scaled(self, factor: float) -> View:
        """The same view in a world `factor` times larger: depth and camera position grow, the picture does not."""
        pose = self.cam_to_world.copy()
        pose[:3, 3] *= factor
        return View(
            epoch=self.epoch, frame_index=self.frame_index, time_s=self.time_s, image=self.image,
            detail=self.detail, depth=self.depth * factor, confidence=self.confidence, intrinsics=self.intrinsics,
            cam_to_world=pose,
        )


def of_epoch(views: list[View], epoch: int) -> list[View]:
    return [view for view in views if view.epoch == epoch]


def save_views(views: list[View], path) -> None:
    np.savez_compressed(
        path,
        epoch=np.array([v.epoch for v in views]),
        frame_index=np.array([v.frame_index for v in views]),
        time_s=np.array([v.time_s for v in views]),
        image=np.stack([v.image for v in views]),
        detail=np.stack([v.detail for v in views]),
        depth=np.stack([v.depth for v in views]),
        confidence=np.stack([v.confidence for v in views]),
        intrinsics=np.stack([v.intrinsics for v in views]),
        cam_to_world=np.stack([v.cam_to_world for v in views]),
    )


def load_views(path) -> list[View]:
    data = np.load(path)
    return [
        View(
            epoch=int(data["epoch"][i]), frame_index=int(data["frame_index"][i]), time_s=float(data["time_s"][i]),
            image=data["image"][i], detail=data["detail"][i], depth=data["depth"][i],
            confidence=data["confidence"][i], intrinsics=data["intrinsics"][i], cam_to_world=data["cam_to_world"][i],
        )
        for i in range(len(data["epoch"]))
    ]
