"""Tests for the tapes CLI."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from tapes.cli import app
from tapes.models import FileEntry, FileMetadata, GroupType, ImportGroup

runner = CliRunner()


def test_empty_directory_shows_no_files(tmp_path: Path) -> None:
    result = runner.invoke(app, ["import", str(tmp_path)])
    assert result.exit_code == 0
    assert "No video files found." in result.output


def test_finds_files_and_shows_label(tmp_path: Path) -> None:
    group = ImportGroup(
        metadata=FileMetadata(title="Dune", year=2021, media_type="movie"),
        group_type=GroupType.STANDALONE,
    )
    video = tmp_path / "Dune.2021.mkv"
    video.touch()
    group.add_file(FileEntry(path=video, metadata=FileMetadata(title="Dune", year=2021, media_type="movie")))

    with patch("tapes.cli.run_pipeline", return_value=[group]):
        result = runner.invoke(app, ["import", str(tmp_path), "--no-tui"])

    assert result.exit_code == 0
    assert "Dune" in result.output
    assert "2021" in result.output


def test_multiple_groups(tmp_path: Path) -> None:
    g1 = ImportGroup(
        metadata=FileMetadata(title="Dune", year=2021, media_type="movie"),
        group_type=GroupType.STANDALONE,
    )
    v1 = tmp_path / "Dune.2021.mkv"
    v1.touch()
    g1.add_file(FileEntry(path=v1, metadata=g1.metadata))

    g2 = ImportGroup(
        metadata=FileMetadata(title="Breaking Bad", media_type="episode", season=1, episode=1),
        group_type=GroupType.STANDALONE,
    )
    v2 = tmp_path / "Breaking.Bad.S01E01.mkv"
    v2.touch()
    g2.add_file(FileEntry(path=v2, metadata=g2.metadata))

    with patch("tapes.cli.run_pipeline", return_value=[g1, g2]):
        result = runner.invoke(app, ["import", str(tmp_path), "--no-tui"])

    assert result.exit_code == 0
    assert "Dune" in result.output
    assert "Breaking Bad" in result.output


def test_dry_run_flag(tmp_path: Path) -> None:
    group = ImportGroup(
        metadata=FileMetadata(title="Test"),
        group_type=GroupType.STANDALONE,
    )
    v = tmp_path / "Test.mkv"
    v.touch()
    group.add_file(FileEntry(path=v))

    captured_configs: list = []

    def fake_pipeline(root: Path, config=None, **kwargs):
        captured_configs.append(config)
        return [group]

    with patch("tapes.cli.run_pipeline", side_effect=fake_pipeline):
        result = runner.invoke(app, ["import", str(tmp_path), "--dry-run", "--no-tui"])

    assert result.exit_code == 0
    assert len(captured_configs) == 1
    assert captured_configs[0].dry_run is True


def test_no_tui_flag(tmp_path: Path) -> None:
    group = ImportGroup(
        metadata=FileMetadata(title="Movie", media_type="movie"),
        group_type=GroupType.STANDALONE,
    )
    v = tmp_path / "Movie.mkv"
    v.touch()
    group.add_file(FileEntry(path=v, metadata=group.metadata))

    with patch("tapes.cli.run_pipeline", return_value=[group]):
        result = runner.invoke(app, ["import", str(tmp_path), "--no-tui"])

    assert result.exit_code == 0
    assert "Movie" in result.output


def test_config_file_option(tmp_path: Path) -> None:
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

    def fake_pipeline(root: Path, config=None, **kwargs):
        captured_configs.append(config)
        return [group]

    with patch("tapes.cli.run_pipeline", side_effect=fake_pipeline):
        result = runner.invoke(
            app, ["import", str(tmp_path), "--config", str(config_path), "--no-tui"]
        )

    assert result.exit_code == 0
    assert len(captured_configs) == 1
    assert captured_configs[0].dry_run is True


def test_companion_in_output(tmp_path: Path) -> None:
    group = ImportGroup(
        metadata=FileMetadata(title="Dune", year=2021, media_type="movie"),
        group_type=GroupType.STANDALONE,
    )
    video = tmp_path / "Dune.2021.mkv"
    video.touch()
    sub = tmp_path / "Dune.2021.srt"
    sub.touch()
    group.add_file(FileEntry(path=video, metadata=group.metadata))
    group.add_file(FileEntry(path=sub))

    with patch("tapes.cli.run_pipeline", return_value=[group]):
        result = runner.invoke(app, ["import", str(tmp_path), "--no-tui"])

    assert result.exit_code == 0
    assert "Dune.2021.mkv" in result.output
    assert "Dune.2021.srt" in result.output


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "tapes" in result.output.lower()


def test_import_help() -> None:
    result = runner.invoke(app, ["import", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" in result.output
    assert "--no-tui" in result.output
    assert "--config" in result.output


def test_scan_help() -> None:
    result = runner.invoke(app, ["scan", "--help"])
    assert result.exit_code == 0
    assert "--find-companions" in result.output
    assert "--group" in result.output


def test_scan_empty(tmp_path: Path) -> None:
    result = runner.invoke(app, ["scan", str(tmp_path)])
    assert result.exit_code == 0
    assert "No video files found." in result.output
