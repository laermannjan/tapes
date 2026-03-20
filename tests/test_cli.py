"""Smoke tests for the tapes CLI entry points."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tapes.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _clean_tapes_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all TAPES_* env vars so BaseSettings does not pick up stray values."""
    for key in list(os.environ):
        if key.startswith("TAPES_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("TMDB_TOKEN", raising=False)


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "tapes" in result.output.lower()
    assert "--serve" in result.output


# ---------------------------------------------------------------------------
# _build_overrides
# ---------------------------------------------------------------------------


class TestBuildOverrides:
    def test_empty_when_all_none(self) -> None:
        from tapes.cli import _build_overrides

        result = _build_overrides(library_movies=None, operation=None)
        assert result == {}

    def test_maps_operation_to_library(self) -> None:
        from tapes.cli import _build_overrides

        result = _build_overrides(operation="move")
        assert result == {"library": {"operation": "move"}}

    def test_maps_multiple_sections(self) -> None:
        from tapes.cli import _build_overrides

        result = _build_overrides(operation="move", tmdb_token="abc", max_workers=8)  # noqa: S106
        assert result["library"]["operation"] == "move"
        assert result["metadata"]["tmdb_token"] == "abc"
        assert result["advanced"]["max_workers"] == 8

    def test_dry_run_override(self) -> None:
        from tapes.cli import _build_overrides

        result = _build_overrides(dry_run=True)
        assert result["dry_run"] is True

    def test_dry_run_false_not_included(self) -> None:
        from tapes.cli import _build_overrides

        result = _build_overrides(dry_run=False)
        assert "dry_run" not in result

    def test_csv_lists(self) -> None:
        from tapes.cli import _build_overrides

        result = _build_overrides(ignore_patterns=["*.nfo", "*.txt"])
        assert result["scan"]["ignore_patterns"] == ["*.nfo", "*.txt"]

    def test_library_movies_maps_correctly(self) -> None:
        from tapes.cli import _build_overrides

        result = _build_overrides(library_movies="/media/movies")
        assert result == {"library": {"movies": "/media/movies"}}

    def test_library_tv_maps_correctly(self) -> None:
        from tapes.cli import _build_overrides

        result = _build_overrides(library_tv="/media/tv")
        assert result == {"library": {"tv": "/media/tv"}}

    def test_movie_template_maps_correctly(self) -> None:
        from tapes.cli import _build_overrides

        result = _build_overrides(movie_template="{title}.{ext}")
        assert result == {"library": {"movie_template": "{title}.{ext}"}}

    def test_metadata_fields(self) -> None:
        from tapes.cli import _build_overrides

        result = _build_overrides(
            min_score=0.9,
            min_prominence=0.2,
            max_results=5,
        )
        assert result["metadata"]["min_score"] == 0.9
        assert result["metadata"]["min_prominence"] == 0.2
        assert result["metadata"]["max_results"] == 5

    def test_advanced_fields(self) -> None:
        from tapes.cli import _build_overrides

        result = _build_overrides(tmdb_timeout=30.0, tmdb_retries=5)
        assert result["advanced"]["tmdb_timeout"] == 30.0
        assert result["advanced"]["tmdb_retries"] == 5


# ---------------------------------------------------------------------------
# Flags (single command, no subcommands)
# ---------------------------------------------------------------------------


class TestFlags:
    def test_operation_flag_in_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert "--operation" in result.output

    def test_tmdb_token_flag_in_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert "--tmdb-token" in result.output

    def test_max_workers_flag_in_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert "--max-workers" in result.output

    def test_library_flags_in_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert "--library-movies" in result.output
        assert "--library-tv" in result.output
        assert "--movie-template" in result.output
        assert "--tv-template" in result.output

    def test_metadata_flags_in_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert "--min-score" in result.output
        assert "--min-prominence" in result.output
        assert "--max-results" in result.output

    def test_scan_flags_in_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert "--ignore-patterns" in result.output
        assert "--video-extensions" in result.output

    def test_advanced_flags_in_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert "--tmdb-timeout" in result.output
        assert "--tmdb-retries" in result.output

    def test_help_panels_present(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert "Library" in result.output
        assert "Metadata" in result.output
        assert "Advanced" in result.output
        assert "Scan" in result.output
        assert "Serve" in result.output


# ---------------------------------------------------------------------------
# Config loading via load_config (always, not just when --config given)
# ---------------------------------------------------------------------------


class TestAlwaysUsesLoadConfig:
    """Both code paths should always call load_config, not bypass it."""

    def test_uses_load_config_without_config_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """main uses load_config even without --config flag."""
        # Set up a TAPES_CONFIG env var pointing to a yaml file
        config_file = tmp_path / "config.yaml"
        config_file.write_text("dry_run: true\n")
        monkeypatch.setenv("TAPES_CONFIG", str(config_file))

        # Create a directory with a file so scan finds something
        scan_dir = tmp_path / "media"
        scan_dir.mkdir()
        (scan_dir / "test.mkv").write_text("fake")

        # Mock TreeApp so we don't actually start the TUI
        from unittest.mock import patch

        with patch("tapes.ui.tree_app.TreeApp") as mock_app_cls:
            mock_app_cls.return_value.run.return_value = None
            runner.invoke(app, [str(scan_dir)])
            # The config passed to TreeApp should have dry_run=True from yaml
            _kwargs = mock_app_cls.call_args[1]
            assert _kwargs["config"].dry_run is True

    def test_dry_run_flag_sets_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--dry-run flag is passed as override to load_config."""
        scan_dir = tmp_path / "media"
        scan_dir.mkdir()
        (scan_dir / "test.mkv").write_text("fake")

        # Ensure no config file is found
        monkeypatch.delenv("TAPES_CONFIG", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

        from unittest.mock import patch

        with patch("tapes.ui.tree_app.TreeApp") as mock_app_cls:
            mock_app_cls.return_value.run.return_value = None
            runner.invoke(app, ["--dry-run", str(scan_dir)])
            _kwargs = mock_app_cls.call_args[1]
            assert _kwargs["config"].dry_run is True

    def test_operation_flag_overrides_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--operation flag overrides config file value."""
        import yaml

        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"library": {"operation": "copy"}}))
        monkeypatch.setenv("TAPES_CONFIG", str(config_file))

        scan_dir = tmp_path / "media"
        scan_dir.mkdir()
        (scan_dir / "test.mkv").write_text("fake")

        from unittest.mock import patch

        with patch("tapes.ui.tree_app.TreeApp") as mock_app_cls:
            mock_app_cls.return_value.run.return_value = None
            runner.invoke(app, ["--operation", "move", str(scan_dir)])
            _kwargs = mock_app_cls.call_args[1]
            assert _kwargs["config"].library.operation == "move"

    def test_library_movies_flag_reaches_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--library-movies flag sets cfg.library.movies."""
        monkeypatch.delenv("TAPES_CONFIG", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

        scan_dir = tmp_path / "media"
        scan_dir.mkdir()
        (scan_dir / "test.mkv").write_text("fake")

        from unittest.mock import patch

        with patch("tapes.ui.tree_app.TreeApp") as mock_app_cls:
            mock_app_cls.return_value.run.return_value = None
            runner.invoke(app, ["--library-movies", "/my/movies", str(scan_dir)])
            _kwargs = mock_app_cls.call_args[1]
            assert _kwargs["config"].library.movies == "/my/movies"

    def test_library_tv_flag_reaches_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--library-tv flag sets cfg.library.tv."""
        monkeypatch.delenv("TAPES_CONFIG", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

        scan_dir = tmp_path / "media"
        scan_dir.mkdir()
        (scan_dir / "test.mkv").write_text("fake")

        from unittest.mock import patch

        with patch("tapes.ui.tree_app.TreeApp") as mock_app_cls:
            mock_app_cls.return_value.run.return_value = None
            runner.invoke(app, ["--library-tv", "/my/tv", str(scan_dir)])
            _kwargs = mock_app_cls.call_args[1]
            assert _kwargs["config"].library.tv == "/my/tv"


# ---------------------------------------------------------------------------
# Path fallback (CLI argument > config import_path > error)
# ---------------------------------------------------------------------------


class TestPathFallback:
    def test_uses_config_import_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """main uses scan.import_path from config when no path argument given."""
        monkeypatch.delenv("TAPES_CONFIG", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

        scan_dir = tmp_path / "media"
        scan_dir.mkdir()
        (scan_dir / "test.mkv").write_text("fake")

        monkeypatch.setenv("TAPES_SCAN__IMPORT_PATH", str(scan_dir))

        from unittest.mock import patch

        with patch("tapes.ui.tree_app.TreeApp") as mock_app_cls:
            mock_app_cls.return_value.run.return_value = None
            result = runner.invoke(app, [])
            assert result.exit_code == 0
            mock_app_cls.assert_called_once()

    def test_errors_when_no_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """main exits with error when no path argument and no import_path configured."""
        monkeypatch.delenv("TAPES_CONFIG", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

        result = runner.invoke(app, [])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Serve flag
# ---------------------------------------------------------------------------


class TestServeFlag:
    def test_serve_calls_start_server(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TAPES_CONFIG", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        monkeypatch.setattr("sys.argv", ["tapes", "--serve", "/media"])

        from unittest.mock import patch

        with patch("tapes.cli._start_server") as mock_start:
            runner.invoke(app, ["--serve", "/media"])
            mock_start.assert_called_once()
            _cmd, host, port = mock_start.call_args[0]
            assert host == "0.0.0.0"  # noqa: S104
            assert port == 8080

    def test_serve_custom_host_port(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TAPES_CONFIG", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        monkeypatch.setattr(
            "sys.argv", ["tapes", "--serve", "--serve-host", "127.0.0.1", "--serve-port", "3000", "/media"]
        )

        from unittest.mock import patch

        with patch("tapes.cli._start_server") as mock_start:
            runner.invoke(app, ["--serve", "--serve-host", "127.0.0.1", "--serve-port", "3000", "/media"])
            mock_start.assert_called_once()
            _cmd, host, port = mock_start.call_args[0]
            assert host == "127.0.0.1"
            assert port == 3000

    def test_serve_command_excludes_serve_flags(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TAPES_CONFIG", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        monkeypatch.setattr("sys.argv", ["tapes", "--serve", "--serve-port", "3000", "--dry-run", "/media"])

        from unittest.mock import patch

        with patch("tapes.cli._start_server") as mock_start:
            runner.invoke(app, ["--serve", "--serve-port", "3000", "--dry-run", "/media"])
            mock_start.assert_called_once()
            cmd = mock_start.call_args[0][0]
            assert "--serve" not in cmd
            assert "--serve-port" not in cmd
            assert "--dry-run" in cmd
            assert "/media" in cmd

    def test_serve_unsets_env_var(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TAPES_CONFIG", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        monkeypatch.setenv("TAPES_MODE__SERVE", "true")
        monkeypatch.setattr("sys.argv", ["tapes", "--serve", "/media"])

        import os
        from unittest.mock import patch

        with patch("tapes.cli._start_server"):
            runner.invoke(app, ["--serve", "/media"])
            assert "TAPES_MODE__SERVE" not in os.environ

    def test_serve_via_env_var_only(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """TAPES_MODE__SERVE=true triggers serve mode without --serve flag."""
        monkeypatch.delenv("TAPES_CONFIG", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        monkeypatch.setenv("TAPES_MODE__SERVE", "true")
        monkeypatch.setenv("TAPES_MODE__SERVE_PORT", "9000")
        monkeypatch.setattr("sys.argv", ["tapes", "/media"])

        from unittest.mock import patch

        with patch("tapes.cli._start_server") as mock_start:
            runner.invoke(app, ["/media"])
            mock_start.assert_called_once()
            _cmd, host, port = mock_start.call_args[0]
            assert host == "0.0.0.0"  # noqa: S104
            assert port == 9000


# ---------------------------------------------------------------------------
# _build_serve_command
# ---------------------------------------------------------------------------


class TestBuildServeCommand:
    def test_strips_serve_flag(self) -> None:
        from tapes.cli import _build_serve_command

        result = _build_serve_command(["/path/to/tapes", "--serve", "/media"])
        assert result == "/path/to/tapes /media"

    def test_strips_serve_host_and_port(self) -> None:
        from tapes.cli import _build_serve_command

        result = _build_serve_command(
            ["/path/to/tapes", "--serve", "--serve-host", "127.0.0.1", "--serve-port", "3000", "/media"]
        )
        assert result == "/path/to/tapes /media"

    def test_strips_serve_flags_equals_syntax(self) -> None:
        from tapes.cli import _build_serve_command

        result = _build_serve_command(
            ["/path/to/tapes", "--serve", "--serve-host=127.0.0.1", "--serve-port=3000", "/media"]
        )
        assert result == "/path/to/tapes /media"

    def test_preserves_other_flags(self) -> None:
        from tapes.cli import _build_serve_command

        result = _build_serve_command(
            ["/path/to/tapes", "--serve", "--dry-run", "--config", "/etc/tapes.yaml", "/media"]
        )
        assert result == "/path/to/tapes --dry-run --config /etc/tapes.yaml /media"

    def test_quotes_args_with_spaces(self) -> None:
        from tapes.cli import _build_serve_command

        result = _build_serve_command(["/path/to/tapes", "--serve", "/media/my incoming"])
        assert result == "/path/to/tapes '/media/my incoming'"

    def test_preserves_verbose_short_flag(self) -> None:
        from tapes.cli import _build_serve_command

        result = _build_serve_command(["/path/to/tapes", "-v", "--serve", "/media"])
        assert result == "/path/to/tapes -v /media"
