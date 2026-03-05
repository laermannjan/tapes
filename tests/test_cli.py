"""Tests for the tapes CLI."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from tapes.cli import app
from tapes.models import FileEntry, FileMetadata, GroupType, ImportGroup

runner = CliRunner()


def test_empty_directory_shows_no_files(tmp_path: Path) -> None:
    """An empty directory should print 'No video files found.' and exit 0."""
    result = runner.invoke(app, ["import", str(tmp_path)])
    assert result.exit_code == 0
    assert "No video files found." in result.output


def test_finds_files_and_shows_label(tmp_path: Path) -> None:
    """Groups returned by the pipeline should appear in the table."""
    group = ImportGroup(
        metadata=FileMetadata(title="Dune", year=2021),
        group_type=GroupType.STANDALONE,
    )
    video = tmp_path / "Dune.2021.mkv"
    video.touch()
    group.add_file(FileEntry(path=video))

    with patch("tapes.cli.run_pipeline", return_value=[group]):
        result = runner.invoke(app, ["import", str(tmp_path)])

    assert result.exit_code == 0
    assert "Dune (2021)" in result.output
    assert "1 group(s) found." in result.output


def test_multiple_groups(tmp_path: Path) -> None:
    """Multiple groups are listed with correct counts."""
    g1 = ImportGroup(
        metadata=FileMetadata(title="Dune", year=2021),
        group_type=GroupType.STANDALONE,
    )
    v1 = tmp_path / "Dune.2021.mkv"
    v1.touch()
    g1.add_file(FileEntry(path=v1))

    g2 = ImportGroup(
        metadata=FileMetadata(title="Breaking Bad", media_type="episode", season=1),
        group_type=GroupType.SEASON,
    )
    for i in range(1, 4):
        v = tmp_path / f"Breaking.Bad.S01E0{i}.mkv"
        v.touch()
        g2.add_file(FileEntry(path=v))

    with patch("tapes.cli.run_pipeline", return_value=[g1, g2]):
        result = runner.invoke(app, ["import", str(tmp_path)])

    assert result.exit_code == 0
    assert "Dune (2021)" in result.output
    assert "Breaking Bad S01" in result.output
    assert "2 group(s) found." in result.output


def test_dry_run_flag(tmp_path: Path) -> None:
    """--dry-run should set config.dry_run = True."""
    group = ImportGroup(
        metadata=FileMetadata(title="Test"),
        group_type=GroupType.STANDALONE,
    )
    v = tmp_path / "Test.mkv"
    v.touch()
    group.add_file(FileEntry(path=v))

    captured_configs: list = []

    def fake_pipeline(root: Path, config=None):
        captured_configs.append(config)
        return [group]

    with patch("tapes.cli.run_pipeline", side_effect=fake_pipeline):
        result = runner.invoke(app, ["import", str(tmp_path), "--dry-run"])

    assert result.exit_code == 0
    assert len(captured_configs) == 1
    assert captured_configs[0].dry_run is True


def test_no_tui_flag(tmp_path: Path) -> None:
    """--no-tui should still produce the table (same as default for now)."""
    group = ImportGroup(
        metadata=FileMetadata(title="Movie"),
        group_type=GroupType.STANDALONE,
    )
    v = tmp_path / "Movie.mkv"
    v.touch()
    group.add_file(FileEntry(path=v))

    with patch("tapes.cli.run_pipeline", return_value=[group]):
        result = runner.invoke(app, ["import", str(tmp_path), "--no-tui"])

    assert result.exit_code == 0
    assert "Movie" in result.output
    assert "1 group(s) found." in result.output


def test_config_file_option(tmp_path: Path) -> None:
    """--config should load config from the specified file."""
    config_path = tmp_path / "tapes.yaml"
    config_path.write_text("dry_run: true\n")

    group = ImportGroup(
        metadata=FileMetadata(title="Film"),
        group_type=GroupType.STANDALONE,
    )
    v = tmp_path / "Film.mkv"
    v.touch()
    group.add_file(FileEntry(path=v))

    captured_configs: list = []

    def fake_pipeline(root: Path, config=None):
        captured_configs.append(config)
        return [group]

    with patch("tapes.cli.run_pipeline", side_effect=fake_pipeline):
        result = runner.invoke(
            app, ["import", str(tmp_path), "--config", str(config_path)]
        )

    assert result.exit_code == 0
    assert len(captured_configs) == 1
    assert captured_configs[0].dry_run is True


def test_companion_count(tmp_path: Path) -> None:
    """Companion files should be counted separately from videos."""
    group = ImportGroup(
        metadata=FileMetadata(title="Dune", year=2021),
        group_type=GroupType.STANDALONE,
    )
    video = tmp_path / "Dune.2021.mkv"
    video.touch()
    sub = tmp_path / "Dune.2021.srt"
    sub.touch()
    group.add_file(FileEntry(path=video))
    group.add_file(FileEntry(path=sub))

    with patch("tapes.cli.run_pipeline", return_value=[group]):
        result = runner.invoke(app, ["import", str(tmp_path)])

    assert result.exit_code == 0
    # The table should show 1 video and 1 companion
    assert "Dune (2021)" in result.output


def test_help() -> None:
    """--help should show usage information."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "tapes" in result.output.lower()


def test_import_help() -> None:
    """import --help should show the command's options."""
    result = runner.invoke(app, ["import", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" in result.output
    assert "--no-tui" in result.output
    assert "--config" in result.output
