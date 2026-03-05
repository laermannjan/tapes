"""Configuration models and loader for tapes."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel


class ScanConfig(BaseModel):
    companion_separators: list[str] = [".", "_", "-"]
    companion_depth: int = 3


class MetadataConfig(BaseModel):
    tmdb_token: str = ""


class LibraryConfig(BaseModel):
    movies: str = ""
    tv: str = ""


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
