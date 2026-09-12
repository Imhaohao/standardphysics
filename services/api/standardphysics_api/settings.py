"""Server configuration, read once at startup.

Keys live in the repo-root `.env` and are loaded into this process only. They
never appear in a response, a log line or the web build.
"""

from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = pathlib.Path(__file__).resolve().parents[1] / "var"


def load_dotenv(path: pathlib.Path) -> None:
    """KEY=value lines, without overriding anything already in the environment."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _flag(name: str) -> bool:
    return os.environ.get(name, "").lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    data_dir: pathlib.Path = DEFAULT_DATA_DIR
    max_artifact_bytes: int = 1024 * 1024 * 1024
    preview_unverified_rules: bool = False
    """Development only. Runs every rule as if a person had verified it, so the
    viewer has findings to draw before the rule pack is reviewed."""
    seed_sample_shop: bool = True

    @property
    def database_path(self) -> pathlib.Path:
        return self.data_dir / "standardphysics.sqlite3"

    @classmethod
    def from_environment(cls) -> Settings:
        load_dotenv(REPO_ROOT / ".env")
        return cls(
            data_dir=pathlib.Path(os.environ.get("SP_DATA_DIR", DEFAULT_DATA_DIR)),
            preview_unverified_rules=_flag("SP_PREVIEW_UNVERIFIED_RULES"),
        )
