"""The classes the fine-tuned detector learns, and how source labels are spelled into them.

Every label is lowercase with single spaces; `ios/Sources/Detection/ClassMapper.swift` maps these
spellings onto the rules catalog's object categories.
"""

import re

OPEN_IMAGES_CLASSES = (
    "Door handle",
    "Light switch",
    "Power plugs and sockets",
    "Soap dispenser",
    "Hand dryer",
    "Paper towel",
    "Toilet paper",
    "Mirror",
    "Countertop",
    "Sink",
    "Toilet",
)

COCO_CLASSES = (
    "chair",
    "couch",
    "dining table",
    "bench",
    "toilet",
    "sink",
    "tv",
    "refrigerator",
    "microwave",
    "oven",
    "bed",
    "potted plant",
    "suitcase",
    "backpack",
    "handbag",
    "umbrella",
    "bicycle",
    "fire hydrant",
    "vase",
)

# Spellings seen in small Roboflow Universe exports, after normalizing.
DEFAULT_RENAMES = {
    "grab bars": "grab bar",
    "grabbar": "grab bar",
    "grab rail": "grab bar",
    "accessible toilet sign": "sign",
    "disabled toilet sign": "sign",
    "toilet sign": "sign",
    "restroom sign": "sign",
    "accessibility sign": "sign",
    "signage": "sign",
}


def normalized(label: str) -> str:
    return re.sub(r"[\s_-]+", " ", label).strip().lower()


def parse_renames(spec: str) -> dict[str, str]:
    """`SP_LABEL_RENAMES` holds `from=to` pairs separated by semicolons, e.g. `rails=grab bar;wc sign=sign`."""
    renames = {}
    for pair in filter(None, (part.strip() for part in spec.split(";"))):
        source, separator, target = pair.partition("=")
        if not separator or not target.strip():
            raise ValueError(f"SP_LABEL_RENAMES entry {pair!r} needs the form from=to")
        renames[normalized(source)] = normalized(target)
    return renames


class LabelVocabulary:
    """Decides which source labels are kept and what they are called."""

    def __init__(self, extra_renames: dict[str, str]):
        self.renames = DEFAULT_RENAMES | extra_renames
        self.known = (
            {normalized(name) for name in OPEN_IMAGES_CLASSES + COCO_CLASSES} | set(self.renames.values())
        )

    def label_for(self, source_label: str) -> str | None:
        label = normalized(source_label)
        label = self.renames.get(label, label)
        return label if label in self.known else None
