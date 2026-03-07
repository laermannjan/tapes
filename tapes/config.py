"""Configuration models and loader for tapes."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel


class ScanConfig(BaseModel):
    pass


class MetadataConfig(BaseModel):
    tmdb_token: str = ""


class LibraryConfig(BaseModel):
    movies: str = ""
    tv: str = ""
    movie_template: str = "{title} ({year})/{title} ({year}).{ext}"
    tv_template: str = (
        "{title} ({year})/Season {season:02d}/"
        "{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"
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
