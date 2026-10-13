"""Names for changed objects from a vision-language model, and descriptors for telling them apart."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image

QWEN_ID = "mlx-community/Qwen3-VL-8B-Instruct-4bit"
DINO_ID = "facebook/dinov2-large"
PROMPT = (
    "This is a photo of a room. We traced one object with an orange outline; the outline is ours and "
    "is not part of the object. Reply with only a JSON object with three keys: "
    '"name": the everyday name of the outlined object in one to three lowercase words; '
    '"detail": a short lowercase noun phrase naming it with its colour or material, at most six words, '
    "without mentioning the outline; "
    '"where": where it sits relative to the furniture around it, written the way a person would say it, '
    'with "the" before each piece of furniture, such as "on the coffee table" or '
    '"between the sofa and the bookshelf", at most eight words. Mention only furniture you can clearly '
    'see in this photo; if none is close, say where it is on the floor or against which wall.'
)
FALLBACK = {"name": "object", "detail": "object", "where": ""}


class Namer(Protocol):
    def name(self, image: Image.Image) -> dict: ...


class PlainNamer:
    """No model: every region is an object, and the geometry still says where and how big."""

    def name(self, image: Image.Image) -> dict:
        return dict(FALLBACK)


class QwenNamer:
    """Qwen3-VL running locally through mlx-vlm on Apple silicon."""

    def __init__(self, model_id: str = QWEN_ID) -> None:
        from mlx_vlm import load

        self.model, self.processor = load(model_id)

    def name(self, image: Image.Image) -> dict:
        from mlx_vlm import generate
        from mlx_vlm.prompt_utils import apply_chat_template

        prompt = apply_chat_template(self.processor, self.model.config, PROMPT, num_images=1)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "crop.jpg"
            image.convert("RGB").save(path, quality=92)
            result = generate(self.model, self.processor, prompt, image=[str(path)], max_tokens=96,
                              temperature=0.0, verbose=False)
        return parse_names(getattr(result, "text", str(result)))


def parse_names(text: str) -> dict:
    """The model's JSON, trimmed to the three expected keys; anything unreadable becomes the fallback."""
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    try:
        raw = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        raw = {}
    names = {key: str(raw.get(key, "")).strip().lower().rstrip(".") for key in FALLBACK}
    if not names["name"]:
        return dict(FALLBACK)
    names["detail"] = names["detail"] or names["name"]
    return names


def make_namer(kind: str) -> Namer:
    if kind == "none":
        return PlainNamer()
    try:
        return QwenNamer()
    except ImportError:
        if kind == "qwen":
            raise
        return PlainNamer()


SEGMENTER_ID = "facebook/mask2former-swin-large-coco-panoptic"


class Segmenter:
    """Mask2Former panoptic labels per pixel, so touching furniture can be told apart by what it is."""

    def __init__(self, model_id: str = SEGMENTER_ID) -> None:
        import torch
        from transformers import AutoImageProcessor, Mask2FormerForUniversalSegmentation

        self.torch = torch
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.processor = AutoImageProcessor.from_pretrained(model_id)
        self.model = Mask2FormerForUniversalSegmentation.from_pretrained(model_id).to(self.device).eval()
        self.names = {int(key): value for key, value in self.model.config.id2label.items()}

    def classes(self, image: np.ndarray) -> np.ndarray:
        """Class id per pixel, -1 where no segment is confident."""
        height, width = image.shape[:2]
        inputs = self.processor(images=Image.fromarray(image), return_tensors="pt")
        with self.torch.no_grad():
            output = self.model(**{key: value.to(self.device) for key, value in inputs.items()})
        result = self.processor.post_process_panoptic_segmentation(output, target_sizes=[(height, width)])[0]
        segments = result["segmentation"].cpu().numpy()
        classes = np.full((height, width), -1, dtype=np.int16)
        for info in result["segments_info"]:
            classes[segments == info["id"]] = info["label_id"]
        return classes


class Embedder:
    """DINOv2 class tokens: close for two views of one object, far for different objects."""

    def __init__(self, model_id: str = DINO_ID) -> None:
        import torch
        from transformers import AutoImageProcessor, AutoModel

        self.torch = torch
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.processor = AutoImageProcessor.from_pretrained(model_id)
        self.model = AutoModel.from_pretrained(model_id).to(self.device).eval()

    def embed(self, images: list[Image.Image]) -> np.ndarray:
        inputs = self.processor(images=[image.convert("RGB") for image in images], return_tensors="pt")
        with self.torch.no_grad():
            output = self.model(pixel_values=inputs["pixel_values"].to(self.device))
        tokens = output.last_hidden_state
        features = self.torch.cat([tokens[:, 0], tokens[:, 1:].mean(dim=1)], dim=1)
        mean = features.mean(dim=0)
        return (mean / mean.norm()).float().cpu().numpy()
