"""Tests for tapes.config module."""

from __future__ import annotations

from pathlib import Path

import yaml

from tapes.config import (
    LibraryConfig,
    MetadataConfig,
    ScanConfig,
    TapesConfig,
    load_config,
)


class TestDefaults:
    """Test that all config models have sane defaults."""

    def test_scan_defaults(self) -> None:
        cfg = ScanConfig()
        assert cfg.companion_separators == [".", "_", "-"]
        assert cfg.companion_depth == 3

    def test_metadata_defaults(self) -> None:
        cfg = MetadataConfig()
        assert cfg.tmdb_token == ""

    def test_library_defaults(self) -> None:
        cfg = LibraryConfig()
        assert cfg.movies == ""
        assert cfg.tv == ""
        assert cfg.movie_template == "{title} ({year})/{title} ({year}).{ext}"
        assert cfg.tv_template == (
            "{title} ({year})/Season {season:02d}/"
            "{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"
        )
        assert cfg.operation == "copy"

    def test_tapes_config_defaults(self) -> None:
        cfg = TapesConfig()
        assert isinstance(cfg.scan, ScanConfig)
        assert isinstance(cfg.metadata, MetadataConfig)
        assert isinstance(cfg.library, LibraryConfig)

    def test_dry_run_default_false(self) -> None:
        cfg = TapesConfig()
        assert cfg.dry_run is False


class TestLoadConfig:
    """Test load_config with various file states."""

    def test_no_config_file(self, tmp_path: Path) -> None:
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert cfg == TapesConfig()

    def test_empty_config_file(self, tmp_path: Path) -> None:
        p = tmp_path / "config.yaml"
        p.write_text("")
        cfg = load_config(p)
        assert cfg == TapesConfig()

    def test_partial_config(self, tmp_path: Path) -> None:
        p = tmp_path / "config.yaml"
        p.write_text(yaml.dump({"library": {"movies": "/movies"}}))
        cfg = load_config(p)
        assert cfg.library.movies == "/movies"
        assert cfg.library.tv == ""
        assert cfg.dry_run is False

    def test_dry_run_from_config(self, tmp_path: Path) -> None:
        p = tmp_path / "config.yaml"
        p.write_text(yaml.dump({"dry_run": True}))
        cfg = load_config(p)
        assert cfg.dry_run is True

    def test_full_config(self, tmp_path: Path) -> None:
        data = {
            "scan": {"companion_separators": ["."], "companion_depth": 1},
            "metadata": {"tmdb_token": "abc123"},
            "library": {"movies": "/m", "tv": "/t"},
            "dry_run": True,
        }
        p = tmp_path / "config.yaml"
        p.write_text(yaml.dump(data))
        cfg = load_config(p)
        assert cfg.scan.companion_separators == ["."]
        assert cfg.scan.companion_depth == 1
        assert cfg.metadata.tmdb_token == "abc123"
        assert cfg.library.movies == "/m"
        assert cfg.library.tv == "/t"
        assert cfg.dry_run is True

    def test_non_dict_yaml_returns_defaults(self, tmp_path: Path) -> None:
        p = tmp_path / "config.yaml"
        p.write_text("just a string")
        cfg = load_config(p)
        assert cfg == TapesConfig()


def test_library_config_defaults():
    cfg = TapesConfig()
    assert cfg.library.movie_template == "{title} ({year})/{title} ({year}).{ext}"
    assert cfg.library.tv_template == (
        "{title} ({year})/Season {season:02d}/"
        "{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"
    )
    assert cfg.library.operation == "copy"


def test_library_config_custom():
    cfg = TapesConfig(library=LibraryConfig(operation="move", movie_template="{title}.{ext}"))
    assert cfg.library.operation == "move"
    assert cfg.library.movie_template == "{title}.{ext}"
