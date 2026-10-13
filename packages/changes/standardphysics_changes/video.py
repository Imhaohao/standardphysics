"""Pick the sharpest frame from each stretch of a phone video."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

PATCH = 14
MODEL_LONG_SIDE = 518
DETAIL_SCALE = 2


@dataclass
class Frame:
    index: int
    time_s: float
    rgb: np.ndarray


def model_size(width: int, height: int, long_side: int = MODEL_LONG_SIDE) -> tuple[int, int]:
    """Width and height for the reconstruction model: the long side fixed, both multiples of the patch."""
    if width >= height:
        return long_side, max(PATCH, round(long_side * height / width / PATCH) * PATCH)
    return max(PATCH, round(long_side * width / height / PATCH) * PATCH), long_side


def sharpness(gray: np.ndarray) -> float:
    """Variance of the Laplacian: high for crisp frames, low for motion blur."""
    lap = gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:] - 4 * gray[1:-1, 1:-1]
    return float(lap.var())


TURNS = {90: "ROTATE_90_CLOCKWISE", 180: "ROTATE_180", 270: "ROTATE_90_COUNTERCLOCKWISE"}


def sample_frames(path: Path, count: int, rotate_cw: int = 0) -> list[Frame]:
    """`count` frames spread evenly through the video, each the sharpest of its stretch.

    Phone videos usually say which way is up and OpenCV turns them; `rotate_cw` is for the
    ones that don't, turning every frame clockwise by that many degrees.
    """
    import cv2

    turn = getattr(cv2, TURNS[rotate_cw]) if rotate_cw else None
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise FileNotFoundError(f"cannot open video {path}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    edges = np.linspace(0, total, count + 1).astype(int)
    best: dict[int, tuple[float, int, np.ndarray]] = {}
    index = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        window = min(int(np.searchsorted(edges, index, side="right")) - 1, count - 1)
        small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (320, 240)).astype(np.float32)
        score = sharpness(small)
        if window not in best or score > best[window][0]:
            best[window] = (score, index, frame)
        index += 1
    capture.release()
    frames = [(i, f if turn is None else cv2.rotate(f, turn)) for _, (_, i, f) in sorted(best.items())]
    return [Frame(i, i / fps, cv2.cvtColor(f, cv2.COLOR_BGR2RGB)) for i, f in frames]


def fit_to(rgb: np.ndarray, width: int, height: int) -> np.ndarray:
    """Centre-crop to the target aspect ratio, then resize."""
    from PIL import Image

    h, w = rgb.shape[:2]
    scale = max(width / w, height / h)
    crop_w, crop_h = round(width / scale), round(height / scale)
    left, top = (w - crop_w) // 2, (h - crop_h) // 2
    cropped = rgb[top:top + crop_h, left:left + crop_w]
    return np.asarray(Image.fromarray(cropped).resize((width, height), Image.Resampling.LANCZOS))
