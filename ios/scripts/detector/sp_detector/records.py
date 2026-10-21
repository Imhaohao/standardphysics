"""One labelled photo, independent of the dataset it came from."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Box:
    """A labelled box with its top-left corner and size as fractions of the photo."""

    label: str
    left: float
    top: float
    width: float
    height: float

    @property
    def is_visible(self) -> bool:
        return self.width > 0 and self.height > 0


@dataclass(frozen=True)
class ImageRecord:
    key: str
    source: str
    path: Path
    boxes: tuple[Box, ...]
