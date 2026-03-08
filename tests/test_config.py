"""Tests for tapes.config module."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from tapes.config import (
    AdvancedConfig,
    LibraryConfig,
    MetadataConfig,
    ScanConfig,
    TapesConfig,
    default_config_path,
    load_config,
    resolve_config_path,
)


@pytest.fixture(autouse=True)
def _clean_tapes_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all TAPES_* env vars so BaseSettings does not pick up stray values.

    Also remove TMDB_TOKEN to avoid legacy fallback interference.
    """
    import os

    for key in list(os.environ):
        if key.startswith("TAPES_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("TMDB_TOKEN", raising=False)


# ---------------------------------------------------------------------------
# Sub-model tests (these are still plain BaseModel, no env reading)
# ---------------------------------------------------------------------------


class TestScanConfig:
    """Test ScanConfig defaults and customization."""

    def test_ignore_patterns_defaults(self) -> None:
        cfg = ScanConfig()
        assert cfg.ignore_patterns == ["Thumbs.db", ".DS_Store", "desktop.ini"]

    def test_ignore_patterns_custom(self) -> None:
        cfg = ScanConfig(ignore_patterns=["*.nfo", "*.txt"])
        assert cfg.ignore_patterns == ["*.nfo", "*.txt"]

    def test_ignore_patterns_empty(self) -> None:
        cfg = ScanConfig(ignore_patterns=[])
        assert cfg.ignore_patterns == []


class TestNewScanFields:
    def test_video_extensions_default(self) -> None:
        cfg = ScanConfig()
        assert ".mkv" in cfg.video_extensions
        assert ".mp4" in cfg.video_extensions
        assert len(cfg.video_extensions) == 9

    def test_video_extensions_custom(self) -> None:
        cfg = ScanConfig(video_extensions=[".mkv", ".webm"])
        assert cfg.video_extensions == [".mkv", ".webm"]


class TestMetadataConfig:
    """Test MetadataConfig defaults."""

    def test_tmdb_token_default_empty(self) -> None:
        config = MetadataConfig()
        assert config.tmdb_token == ""

    def test_auto_accept_threshold_default(self) -> None:
        config = MetadataConfig()
        assert config.auto_accept_threshold == 0.85

    def test_auto_accept_threshold_custom(self) -> None:
        config = MetadataConfig(auto_accept_threshold=0.5)
        assert config.auto_accept_threshold == 0.5

    def test_tmdb_token_explicit(self) -> None:
        config = MetadataConfig(tmdb_token="explicit")  # noqa: S106
        assert config.tmdb_token == "explicit"


class TestNewMetadataFields:
    def test_margin_defaults(self) -> None:
        cfg = MetadataConfig()
        assert cfg.margin_accept_threshold == 0.6
        assert cfg.min_accept_margin == 0.15
        assert cfg.max_results == 3

    def test_custom_values(self) -> None:
        cfg = MetadataConfig(margin_accept_threshold=0.8, min_accept_margin=0.2, max_results=5)
        assert cfg.margin_accept_threshold == 0.8
        assert cfg.min_accept_margin == 0.2
        assert cfg.max_results == 5


class TestOperationValidation:
    def test_valid_operations(self) -> None:
        for op in ("copy", "move", "link", "hardlink"):
            cfg = LibraryConfig(operation=op)
            assert cfg.operation == op

    def test_invalid_operation_raises(self) -> None:
        with pytest.raises(ValidationError):
            LibraryConfig(operation="ftp")  # type: ignore[arg-type]


class TestAdvancedConfig:
    def test_defaults(self) -> None:
        cfg = AdvancedConfig()
        assert cfg.max_workers == 4
        assert cfg.tmdb_timeout == 10.0
        assert cfg.tmdb_retries == 3

    def test_custom_values(self) -> None:
        cfg = AdvancedConfig(max_workers=8, tmdb_timeout=30.0, tmdb_retries=5)
        assert cfg.max_workers == 8
        assert cfg.tmdb_timeout == 30.0
        assert cfg.tmdb_retries == 5


# ---------------------------------------------------------------------------
# TapesConfig (BaseSettings) -- env var loading
# ---------------------------------------------------------------------------


class TestEnvVarLoading:
    def test_tmdb_token_via_prefixed_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAPES_METADATA__TMDB_TOKEN", "from-prefixed-env")
        cfg = TapesConfig()
        assert cfg.metadata.tmdb_token == "from-prefixed-env"

    def test_dry_run_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAPES_DRY_RUN", "true")
        cfg = TapesConfig()
        assert cfg.dry_run is True

    def test_operation_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAPES_LIBRARY__OPERATION", "move")
        cfg = TapesConfig()
        assert cfg.library.operation == "move"

    def test_max_workers_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAPES_ADVANCED__MAX_WORKERS", "8")
        cfg = TapesConfig()
        assert cfg.advanced.max_workers == 8


class TestTmdbTokenCompat:
    def test_legacy_tmdb_token_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TMDB_TOKEN", "legacy-token")
        cfg = TapesConfig()
        assert cfg.metadata.tmdb_token == "legacy-token"

    def test_prefixed_overrides_legacy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAPES_METADATA__TMDB_TOKEN", "new-style")
        monkeypatch.setenv("TMDB_TOKEN", "old-style")
        cfg = TapesConfig()
        assert cfg.metadata.tmdb_token == "new-style"

    def test_explicit_overrides_legacy_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Explicit init kwarg still wins over TMDB_TOKEN env."""
        monkeypatch.setenv("TMDB_TOKEN", "from-env")
        cfg = TapesConfig(metadata=MetadataConfig(tmdb_token="explicit"))  # noqa: S106
        assert cfg.metadata.tmdb_token == "explicit"


# ---------------------------------------------------------------------------
# YAML config loading via load_config
# ---------------------------------------------------------------------------


class TestYamlConfigSource:
    def test_load_from_yaml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "library": {"movies": "/media/movies", "operation": "move"},
                    "metadata": {"auto_accept_threshold": 0.7},
                }
            )
        )
        cfg = load_config(config_path=config_file)
        assert cfg.library.movies == "/media/movies"
        assert cfg.library.operation == "move"
        assert cfg.metadata.auto_accept_threshold == 0.7

    def test_env_overrides_yaml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"library": {"operation": "copy"}}))
        monkeypatch.setenv("TAPES_LIBRARY__OPERATION", "move")
        cfg = load_config(config_path=config_file)
        assert cfg.library.operation == "move"

    def test_cli_overrides_env_and_yaml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"library": {"operation": "copy"}}))
        monkeypatch.setenv("TAPES_LIBRARY__OPERATION", "move")
        cfg = load_config(config_path=config_file, cli_overrides={"library": {"operation": "hardlink"}})
        assert cfg.library.operation == "hardlink"

    def test_missing_yaml_uses_defaults(self, tmp_path: Path) -> None:
        cfg = load_config(config_path=tmp_path / "nonexistent.yaml")
        assert cfg == TapesConfig()

    def test_empty_yaml_uses_defaults(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text("")
        cfg = load_config(config_path=config_file)
        assert cfg.library.operation == "copy"

    def test_non_dict_yaml_returns_defaults(self, tmp_path: Path) -> None:
        p = tmp_path / "config.yaml"
        p.write_text("just a string")
        cfg = load_config(config_path=p)
        assert cfg == TapesConfig()

    def test_partial_config_from_yaml(self, tmp_path: Path) -> None:
        p = tmp_path / "config.yaml"
        p.write_text(yaml.dump({"library": {"movies": "/movies"}}))
        cfg = load_config(config_path=p)
        assert cfg.library.movies == "/movies"
        assert cfg.library.tv == ""
        assert cfg.dry_run is False

    def test_dry_run_from_yaml(self, tmp_path: Path) -> None:
        p = tmp_path / "config.yaml"
        p.write_text(yaml.dump({"dry_run": True}))
        cfg = load_config(config_path=p)
        assert cfg.dry_run is True

    def test_full_config_from_yaml(self, tmp_path: Path) -> None:
        data = {
            "metadata": {"tmdb_token": "abc123"},
            "library": {"movies": "/m", "tv": "/t"},
            "dry_run": True,
        }
        p = tmp_path / "config.yaml"
        p.write_text(yaml.dump(data))
        cfg = load_config(config_path=p)
        assert cfg.metadata.tmdb_token == "abc123"
        assert cfg.library.movies == "/m"
        assert cfg.library.tv == "/t"
        assert cfg.dry_run is True

    def test_ignore_patterns_from_yaml(self, tmp_path: Path) -> None:
        data = {"scan": {"ignore_patterns": ["*.log", "*.tmp"]}}
        p = tmp_path / "config.yaml"
        p.write_text(yaml.dump(data))
        cfg = load_config(config_path=p)
        assert cfg.scan.ignore_patterns == ["*.log", "*.tmp"]


# ---------------------------------------------------------------------------
# XDG / config path resolution
# ---------------------------------------------------------------------------


def test_default_config_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", "/fake/config")
    assert default_config_path() == Path("/fake/config/tapes/config.yaml")


def test_config_path_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAPES_CONFIG", "/custom/tapes.yaml")
    assert resolve_config_path(None) == Path("/custom/tapes.yaml")


def test_config_path_explicit_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAPES_CONFIG", "/custom/tapes.yaml")
    assert resolve_config_path(Path("/explicit.yaml")) == Path("/explicit.yaml")


def test_resolve_config_path_xdg_default_only_if_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When no explicit path and no TAPES_CONFIG, use XDG default only if file exists."""
    monkeypatch.delenv("TAPES_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    # File doesn't exist yet
    assert resolve_config_path(None) is None

    # Create the file
    config_dir = tmp_path / "tapes"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"
    config_file.write_text("dry_run: true")
    assert resolve_config_path(None) == config_file


# ---------------------------------------------------------------------------
# Existing tests adapted for new load_config signature
# ---------------------------------------------------------------------------


def test_library_config_custom() -> None:
    cfg = TapesConfig(library=LibraryConfig(operation="move", movie_template="{title}.{ext}"))
    assert cfg.library.operation == "move"
    assert cfg.library.movie_template == "{title}.{ext}"
