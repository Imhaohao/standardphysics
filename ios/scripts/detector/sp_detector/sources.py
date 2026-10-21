"""Where training photos come from and the licence each one carries.

Every source must allow commercial use. Open Images lists all its photos as CC BY 2.0; COCO photos
carry the Flickr licence each owner chose, so only the commercial-friendly ones are used; an extra
COCO-format folder must name its licence in a README or LICENSE text file.
"""

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

# COCO's `licenses` table: 4 BY, 5 BY-SA, 6 BY-ND, 7 no known copyright restrictions, 8 US government work.
# 1-3 are non-commercial and are left out.
COCO_COMMERCIAL_LICENSE_IDS = frozenset({4, 5, 6, 7, 8})

COMMERCIAL_LICENSES = {
    "ccby4.0": "CC BY 4.0",
    "ccby3.0": "CC BY 3.0",
    "ccby2.0": "CC BY 2.0",
    "cc01.0": "CC0 1.0",
    "cc0": "CC0 1.0",
    "publicdomain": "Public Domain",
    "mit": "MIT",
    "apache2.0": "Apache-2.0",
}

LICENSE_LINE = re.compile(r"^\s*licen[cs]e\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
URL = re.compile(r"https?://\S+")


@dataclass
class DatasetSource:
    name: str
    url: str
    annotation_license: str
    image_license: str
    attribution: str
    image_count: int = 0
    labels: set[str] = field(default_factory=set)

    def as_json(self) -> dict:
        return asdict(self) | {"labels": sorted(self.labels)}


def open_images_source() -> DatasetSource:
    return DatasetSource(
        name="Open Images V7",
        url="https://storage.googleapis.com/openimages/web/index.html",
        annotation_license="CC BY 4.0 (Google LLC)",
        image_license="CC BY 2.0, as listed by Open Images for each photo",
        attribution=(
            "Annotations by Google LLC under CC BY 4.0. Photos are listed as CC BY 2.0 by their Flickr "
            "owners; Google does not verify each listing."
        ),
    )


def coco_source() -> DatasetSource:
    return DatasetSource(
        name="COCO 2017",
        url="https://cocodataset.org",
        annotation_license="CC BY 4.0 (COCO Consortium)",
        image_license="Flickr licences CC BY, CC BY-SA, CC BY-ND, no known restrictions and US government work",
        attribution=(
            "Annotations by the COCO Consortium under CC BY 4.0. Photos with a non-commercial Flickr licence "
            "were left out."
        ),
    )


class UnusableLicenseError(Exception):
    pass


def extra_folder_source(folder: Path) -> DatasetSource:
    """Reads `License: ...` and the first URL from the folder's README or LICENSE files."""
    text = "\n".join(path.read_text(errors="replace") for path in _license_files(folder))
    license_match = LICENSE_LINE.search(text)
    license_name = _commercial_license(license_match.group(1)) if license_match else None
    if license_name is None:
        raise UnusableLicenseError(
            f"{folder} needs a README or LICENSE text file with a line such as 'License: CC BY 4.0' naming a "
            f"licence that allows commercial use ({', '.join(sorted(set(COMMERCIAL_LICENSES.values())))})"
        )
    url_match = URL.search(text)
    url = url_match.group(0) if url_match else folder.name
    return DatasetSource(
        name=folder.name,
        url=url,
        annotation_license=license_name,
        image_license=license_name,
        attribution=f"Photos and annotations from {url}, used under {license_name}.",
    )


def _license_files(folder: Path) -> list[Path]:
    candidates = [*folder.glob("README*"), *folder.glob("LICENSE*"), *folder.glob("*/README*")]
    return sorted(path for path in candidates if path.is_file())


def _commercial_license(text: str) -> str | None:
    key = re.sub(r"[\s_-]", "", text).lower()
    return COMMERCIAL_LICENSES.get(key)
