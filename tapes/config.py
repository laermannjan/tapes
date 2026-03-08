"""Configuration models and loader for tapes."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel


class ScanConfig(BaseModel):
    ignore_patterns: list[str] = ["Thumbs.db", ".DS_Store", "desktop.ini"]


DEFAULT_AUTO_ACCEPT_THRESHOLD: float = 0.85


class MetadataConfig(BaseModel):
    tmdb_token: str = ""
    auto_accept_threshold: float = DEFAULT_AUTO_ACCEPT_THRESHOLD

    def model_post_init(self, context: object, /) -> None:  # noqa: ARG002
        import os

        if not self.tmdb_token:
            self.tmdb_token = os.environ.get("TMDB_TOKEN", "")


class LibraryConfig(BaseModel):
    movies: str = ""
    tv: str = ""
    movie_template: str = "{title} ({year})/{title} ({year}).{ext}"
    tv_template: str = (
        "{title} ({year})/Season {season:02d}/{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"
    )
    operation: str = "copy"


class TapesConfig(BaseModel):
    scan: ScanConfig = ScanConfig()
    metadata: MetadataConfig = MetadataConfig()
    library: LibraryConfig = LibraryConfig()
    dry_run: bool = False


def load_config(path: Path) -> TapesConfig:
    """Load configuration from a YAML file.

    Returns defaults if the file doesn't exist, is empty, or isn't a dict.
    """
    if not path.exists():
        return TapesConfig()

    text = path.read_text()
    if not text.strip():
        return TapesConfig()

    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        return TapesConfig()

    return TapesConfig(**data)
