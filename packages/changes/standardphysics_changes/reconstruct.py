"""One MapAnything pass over the frames of both videos, so they land in one metric frame together."""

from __future__ import annotations

import os

import numpy as np

from .video import DETAIL_SCALE, Frame, fit_to, model_size
from .views import View

MODEL_ID = "facebook/map-anything"


def _device():
    import torch

    if torch.cuda.is_available():
        return "cuda"
    return "mps" if torch.backends.mps.is_available() else "cpu"


def intrinsics_for(width: int, height: int, size: tuple[int, int], fov_deg: float) -> np.ndarray:
    """The pinhole matrix of a frame `width` wide with this horizontal field of view, after `fit_to(size)`."""
    focal = width / 2 / np.tan(np.radians(fov_deg) / 2)
    scale = max(size[0] / width, size[1] / height)
    return np.array([[focal * scale, 0, size[0] / 2], [0, focal * scale, size[1] / 2], [0, 0, 1]], dtype=np.float32)


def reconstruct(before: list[Frame], after: list[Frame], fov_deg: float | None = None) -> list[View]:
    """Depth, intrinsics and camera poses for every frame, all in the first frame's world.

    The background that did not change is what ties the two recordings together; the
    model sees all frames at once, so nothing has to be registered afterwards. A known
    horizontal field of view pins the focal length, which the model otherwise guesses.
    """
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    import torch
    from mapanything.models import MapAnything
    from mapanything.utils.image import preprocess_inputs

    frames = [(0, f) for f in before] + [(1, f) for f in after]
    height, width = frames[0][1].rgb.shape[:2]
    size = model_size(width, height)
    images = [fit_to(f.rgb, *size) for _, f in frames]
    details = [fit_to(f.rgb, size[0] * DETAIL_SCALE, size[1] * DETAIL_SCALE) for _, f in frames]
    model = MapAnything.from_pretrained(MODEL_ID).to(_device()).eval()
    known = {} if fov_deg is None else {"intrinsics": intrinsics_for(width, height, size, fov_deg)}
    inputs = preprocess_inputs([{"img": image, **known} for image in images], resize_mode="fixed_size", size=size)
    with torch.no_grad():
        predictions = model.infer(inputs, memory_efficient_inference=True, use_amp=True, amp_dtype="bf16",
                                  apply_mask=True, mask_edges=True, apply_confidence_mask=False)
    views = [
        _view(epoch, frame, image, detail, prediction)
        for (epoch, frame), image, detail, prediction in zip(frames, images, details, predictions)
    ]
    del model
    return views


def _view(epoch: int, frame: Frame, image: np.ndarray, detail: np.ndarray, prediction: dict) -> View:
    depth = prediction["depth_z"][0, ..., 0].float().cpu().numpy()
    mask = prediction["mask"][0, ..., 0].float().cpu().numpy() > 0.5
    if depth.shape != image.shape[:2]:
        raise ValueError(f"depth {depth.shape} does not match the frame {image.shape[:2]}")
    return View(
        epoch=epoch, frame_index=frame.index, time_s=frame.time_s, image=image, detail=detail,
        depth=np.where(mask, depth, 0.0).astype(np.float32),
        confidence=prediction["conf"][0].float().cpu().numpy().astype(np.float32),
        intrinsics=prediction["intrinsics"][0].float().cpu().numpy().astype(np.float64),
        cam_to_world=prediction["camera_poses"][0].float().cpu().numpy().astype(np.float64),
    )
