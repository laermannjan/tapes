"""Configuration models and loader for tapes."""

from __future__ import annotations

import os
import string
from pathlib import Path
from typing import Any, Literal

import yaml
from platformdirs import user_config_dir
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


class ScanConfig(BaseModel):
    import_path: str = ""
    ignore_patterns: list[str] = ["Thumbs.db", ".DS_Store", "desktop.ini"]
    video_extensions: list[str] = [".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".m2ts", ".wmv", ".flv"]


DEFAULT_AUTO_ACCEPT_THRESHOLD: float = 0.85


class MetadataConfig(BaseModel):
    tmdb_token: str = ""
    auto_accept_threshold: float = Field(default=DEFAULT_AUTO_ACCEPT_THRESHOLD, ge=0.0, le=1.0)
    margin_accept_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    min_accept_margin: float = Field(default=0.15, ge=0.0, le=1.0)
    max_results: int = Field(default=3, ge=1)
    duplicate_resolution: Literal["auto", "warn", "off"] = "auto"
    disambiguation: Literal["auto", "warn", "off"] = "auto"
    language: str = ""


# Known template fields. Templates may only reference these (plus "ext" which
# is always injected from the file suffix).
KNOWN_TEMPLATE_FIELDS: frozenset[str] = frozenset(
    {
        "title",
        "year",
        "season",
        "episode",
        "episode_title",
        "media_type",
        "tmdb_id",
        "ext",
        "codec",
        "media_source",
        "audio",
        "resolution",
        "release_group",
    }
)


def _validate_template(template: str) -> str:
    """Check that a template string only references known field names."""
    for _, field_name, _, _ in string.Formatter().parse(template):
        if field_name is not None and field_name not in KNOWN_TEMPLATE_FIELDS:
            msg = f"unknown template field {{{field_name}}}; valid fields: {sorted(KNOWN_TEMPLATE_FIELDS)}"
            raise ValueError(msg)
    return template


class LibraryConfig(BaseModel):
    movies: str = ""
    tv: str = ""
    movie_template: str = "{title} ({year})/{title} ({year}).{ext}"
    tv_template: str = (
        "{title} ({year})/Season {season:02d}/{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"
    )
    operation: Literal["copy", "move", "link", "hardlink"] = "copy"
    verify: bool = True

    @field_validator("movie_template", "tv_template")
    @classmethod
    def _check_template_fields(cls, v: str) -> str:
        return _validate_template(v)


class AdvancedConfig(BaseModel):
    max_workers: int = Field(default=4, ge=1)
    tmdb_timeout: float = Field(default=10.0, gt=0.0)
    tmdb_retries: int = Field(default=3, ge=1)


# Module-level store for YAML data injected by load_config before TapesConfig
# construction. settings_customise_sources reads this to build the source chain.
# Not thread-safe, but config loading is single-threaded.
_pending_yaml_data: dict[str, Any] = {}


class _YamlDictSource(PydanticBaseSettingsSource):
    """Settings source that reads from a pre-loaded YAML dict."""

    def __init__(self, settings_cls: type[BaseSettings], yaml_data: dict[str, Any]) -> None:
        super().__init__(settings_cls)
        self._data = yaml_data

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        val = self._data.get(field_name)
        return val, field_name, self.field_is_complex(field)

    def __call__(self) -> dict[str, Any]:
        return self._data


class TapesConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TAPES_",
        env_nested_delimiter="__",
    )

    scan: ScanConfig = ScanConfig()
    metadata: MetadataConfig = MetadataConfig()
    library: LibraryConfig = LibraryConfig()
    advanced: AdvancedConfig = AdvancedConfig()
    dry_run: bool = False

    @model_validator(mode="after")
    def _tmdb_token_compat(self) -> TapesConfig:
        """Fall back to legacy TMDB_TOKEN env var (no prefix) if token is empty."""
        if not self.metadata.tmdb_token:
            legacy = os.environ.get("TMDB_TOKEN", "")
            if legacy:
                self.metadata.tmdb_token = legacy
        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,  # noqa: ARG003
        file_secret_settings: PydanticBaseSettingsSource,  # noqa: ARG003
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Priority: init (CLI overrides) > env > yaml > defaults
        if _pending_yaml_data:
            yaml_source = _YamlDictSource(settings_cls, _pending_yaml_data)
            return (init_settings, env_settings, yaml_source)
        return (init_settings, env_settings)


# ---------------------------------------------------------------------------
# Config path resolution
# ---------------------------------------------------------------------------


def default_config_path() -> Path:
    """Return the XDG-compliant default config file path."""
    return Path(user_config_dir("tapes")) / "config.yaml"


def resolve_config_path(explicit: Path | None) -> Path | None:
    """Determine which config file to use.

    Priority: explicit argument > TAPES_CONFIG env var > XDG default (if exists).
    Returns None if no config file is found.
    """
    if explicit is not None:
        return explicit

    env_path = os.environ.get("TAPES_CONFIG")
    if env_path:
        return Path(env_path)

    xdg_default = default_config_path()
    if xdg_default.exists():
        return xdg_default

    return None


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------


def _load_yaml_data(path: Path) -> dict[str, Any]:
    """Load and validate YAML data from a file path.

    Returns an empty dict if the file doesn't exist, is empty, or isn't a dict.
    """
    if not path.exists():
        return {}

    text = path.read_text()
    if not text.strip():
        return {}

    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        return {}

    return data


def load_config(
    config_path: Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> TapesConfig:
    """Load configuration with precedence: CLI overrides > env vars > YAML file > defaults.

    Args:
        config_path: Explicit path to a YAML config file. If None, uses
            ``resolve_config_path`` to find one.
        cli_overrides: Dict of overrides from CLI flags (highest priority).

    Returns:
        A fully resolved TapesConfig instance.
    """
    global _pending_yaml_data  # noqa: PLW0603

    resolved_path = resolve_config_path(config_path)
    yaml_data: dict[str, Any] = {}
    if resolved_path is not None:
        yaml_data = _load_yaml_data(resolved_path)

    # Temporarily set module-level YAML data so settings_customise_sources can
    # pick it up during TapesConfig construction.
    _pending_yaml_data = yaml_data
    try:
        cfg = TapesConfig(**(cli_overrides or {}))
    finally:
        _pending_yaml_data = {}

    return cfg
