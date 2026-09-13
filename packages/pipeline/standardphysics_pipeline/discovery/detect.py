"""What a vision model sees in one captured frame, in that frame's own pixels.

RoomPlan only boxes the furniture categories Apple ships, so a payment
terminal, a monitor or a laptop reaches us as unclaimed LiDAR and nothing
else. This asks a grounding model what is in the picture and where, and the
answer is a pixel rectangle we can turn back into mesh points.

**Pixels are sensor pixels.** Frames are stored exactly as the camera
delivered them and the pose intrinsics describe that same grid, so the image
goes to the model unrotated and every box comes back scaled to the stored
resolution. Rotating here would silently shear every box against the camera.

**Boxes arrive as Gemini writes them**: `[ymin, xmin, ymax, xmax]`, each value
0-1000 of the image's height or width. Asking for the convention the model was
trained on gets better corners than asking it to translate.

A request that fails raises. Nothing here returns an empty list to mean the
network was down, because a silent fallback reads downstream as a room with
nothing in it.
"""

from __future__ import annotations

import base64
import io
import json
import os
import pathlib
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

MODEL_ENV = "DISCOVERY_MODEL"
API_KEY_ENV = "OPENROUTER_API_KEY"
BASE_URL_ENV = "OPENROUTER_BASE_URL"
DEFAULT_MODEL = "google/gemini-3.8-flash"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
PROVIDER_ROUTING = {"data_collection": "deny"}
REQUEST_TIMEOUT_SECONDS = 120.0
MAX_OUTPUT_TOKENS = 8_192
MAX_RESPONSE_BYTES = 4_000_000
MAX_DETECTIONS = 40

MAX_IMAGE_EDGE = 1024
MAX_IMAGE_BYTES = 3_000_000
MAX_SOURCE_BYTES = 16_000_000
MAX_SOURCE_PIXELS = 40_000_000
JPEG_QUALITIES = (85, 75, 65, 55)

BOX_SCALE = 1000.0
MIN_BOX_FRACTION = 0.0015
"""A box thinner than this share of the frame carries too few mesh points to fit."""

PERSON_NAMES = frozenset({
    "person", "people", "human", "man", "woman", "child", "customer",
    "shopper", "employee", "staff", "worker", "hand", "arm", "leg", "face",
})

FIXED_NAMES = frozenset({
    "wall", "floor", "ceiling", "window", "door", "doorway", "column",
    "pillar", "staircase", "stairs", "railing", "sink", "toilet", "radiator",
    "built-in counter", "built-in shelving", "fireplace",
})

INSTRUCTION = (
    "You look at one photo of a shop or workplace interior and list the objects in it. "
    "Include anything a person uses or that takes up floor or counter space: payment terminals, "
    "card readers, cash registers, monitors, laptops, tablets, printers, phones, kettles, "
    "espresso machines, blenders, microwaves, refrigerators, display cases, shelving, signage, "
    "boxes, bins, chairs, stools, tables, counters, planters, fans, speakers, lamps. "
    "Also list every person you see, named exactly 'person'. "
    "Give each object a short lowercase name a shop owner would use. "
    "Set movable to true when one or two people could pick the object up and set it down "
    "somewhere else, and false when it is built in, plumbed in, or too heavy to move. "
    "Box every object separately: a laptop sitting on a desk is its own object, not part of the desk. "
    "Report the box as [ymin, xmin, ymax, xmax] with each number between 0 and 1000, "
    "measured against the image height for y and the image width for x."
)

DETECTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["objects"],
    "properties": {
        "objects": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "box_2d", "movable", "confidence"],
                "properties": {
                    "name": {"type": "string"},
                    "box_2d": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 4,
                        "maxItems": 4,
                    },
                    "movable": {"type": "boolean"},
                    "confidence": {"type": "number"},
                },
            },
        }
    },
}

Transport = Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]


class DetectionError(RuntimeError):
    """The frame could not be read, or the model did not answer."""


@dataclass(frozen=True)
class Detection:
    frame_id: str
    name: str
    box: tuple[float, float, float, float]
    """left, top, right, bottom in stored sensor pixels."""
    movable: bool
    confidence: float

    @property
    def is_person(self) -> bool:
        return self.name.strip().lower() in PERSON_NAMES

    @property
    def width(self) -> float:
        return self.box[2] - self.box[0]

    @property
    def height(self) -> float:
        return self.box[3] - self.box[1]

    def contains(self, columns, rows):
        left, top, right, bottom = self.box
        return (columns >= left) & (columns <= right) & (rows >= top) & (rows <= bottom)


@dataclass(frozen=True)
class EncodedFrame:
    jpeg: bytes
    width: int
    height: int
    """The stored sensor resolution the boxes are scaled back to."""


def detect_objects(
    image_path: pathlib.Path,
    frame_id: str,
    *,
    transport: Transport | None = None,
) -> list[Detection]:
    """Every object the model finds in one frame, boxed in that frame's stored pixels."""
    frame = encode_frame(image_path)
    api_key = os.environ.get(API_KEY_ENV, "")
    if transport is None and not api_key:
        raise DetectionError(f"{API_KEY_ENV} is not set, so no frame can be read")
    payload = _post(transport, _request_body(frame), api_key)
    return _detections_from(payload, frame, frame_id)


def encode_frame(image_path: pathlib.Path) -> EncodedFrame:
    """The frame as JPEG under the size cap, never rotated, with its stored resolution kept."""
    from PIL import Image

    source = pathlib.Path(image_path)
    try:
        if source.stat().st_size > MAX_SOURCE_BYTES:
            raise DetectionError(f"{source.name} is too large to read")
        with Image.open(source) as opened:
            if opened.width * opened.height > MAX_SOURCE_PIXELS:
                raise DetectionError(f"{source.name} has too many pixels to read")
            image = opened.convert("RGB")
    except (OSError, ValueError) as error:
        raise DetectionError(f"unreadable frame {source.name}: {error}") from error
    stored_width, stored_height = image.width, image.height
    image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)
    return EncodedFrame(_compressed(image), stored_width, stored_height)


def _compressed(image) -> bytes:
    encoded = b""
    for quality in JPEG_QUALITIES:
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=quality, optimize=True)
        encoded = buffer.getvalue()
        if len(encoded) <= MAX_IMAGE_BYTES:
            return encoded
    raise DetectionError("frame will not compress under the size limit")


def _request_body(frame: EncodedFrame) -> dict[str, Any]:
    data_url = "data:image/jpeg;base64," + base64.b64encode(frame.jpeg).decode("ascii")
    return {
        "model": os.environ.get(MODEL_ENV) or DEFAULT_MODEL,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "messages": [
            {"role": "system", "content": INSTRUCTION},
            {"role": "user", "content": [
                {"type": "text", "text": "List every object in this photo with its box."},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]},
        ],
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "detections", "strict": True, "schema": DETECTION_SCHEMA,
        }},
        "provider": PROVIDER_ROUTING,
    }


def _post(transport: Transport | None, body: dict[str, Any], api_key: str) -> dict[str, Any]:
    url = f"{(os.environ.get(BASE_URL_ENV) or DEFAULT_BASE_URL).rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        return (transport or _openrouter_post)(url, body, headers)
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as error:
        raise DetectionError(f"the vision model did not answer: {error}") from error


def _openrouter_post(url: str, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read(MAX_RESPONSE_BYTES))


def _detections_from(payload: dict[str, Any], frame: EncodedFrame, frame_id: str) -> list[Detection]:
    objects = _objects_in(payload)
    detections = []
    for item in objects[:MAX_DETECTIONS]:
        detection = _one_detection(item, frame, frame_id)
        if detection is not None:
            detections.append(detection)
    return detections


def _objects_in(payload: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise DetectionError(f"the vision model returned no message: {error}") from error
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    try:
        objects = json.loads(content)["objects"]
    except (ValueError, KeyError, TypeError) as error:
        raise DetectionError(f"the vision model returned unreadable objects: {error}") from error
    return objects if isinstance(objects, list) else []


def _one_detection(item: dict[str, Any], frame: EncodedFrame, frame_id: str) -> Detection | None:
    name = str(item.get("name", "")).strip().lower()
    box = _pixel_box(item.get("box_2d"), frame)
    if not name or box is None:
        return None
    return Detection(
        frame_id=frame_id,
        name=name,
        box=box,
        movable=bool(item.get("movable", True)) and name not in FIXED_NAMES,
        confidence=_clamped(item.get("confidence", 1.0)),
    )


def _pixel_box(values: Any, frame: EncodedFrame) -> tuple[float, float, float, float] | None:
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        return None
    try:
        top, left, bottom, right = (float(value) / BOX_SCALE for value in values)
    except (TypeError, ValueError):
        return None
    top, bottom = sorted((_clamped(top), _clamped(bottom)))
    left, right = sorted((_clamped(left), _clamped(right)))
    if (right - left) < MIN_BOX_FRACTION or (bottom - top) < MIN_BOX_FRACTION:
        return None
    return (
        left * frame.width, top * frame.height,
        right * frame.width, bottom * frame.height,
    )


def _clamped(value: Any) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.0
