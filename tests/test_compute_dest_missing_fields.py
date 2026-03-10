"""Tests for B3: named missing-field indicators in compute_dest."""

from __future__ import annotations

from pathlib import Path

from tapes.templates import compute_dest
from tapes.tree_model import FileNode


class TestComputeDestMissingFields:
    def test_missing_season_shows_field_name(self) -> None:
        node = FileNode(path=Path("episode.mkv"))
        node.metadata = {
            "title": "Game of Thrones",
            "year": 2011,
            "episode": 1,
            "episode_title": "Pilot",
            "media_type": "episode",
        }
        template = "{title} ({year})/Season {season:02d}/{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"
        dest = compute_dest(node, template)
        assert dest is not None
        assert "{season?}" in dest
        assert "Game of Thrones" in dest

    def test_missing_year_shows_field_name(self) -> None:
        node = FileNode(path=Path("movie.mkv"))
        node.metadata = {"title": "Dune", "media_type": "movie"}
        template = "{title} ({year})/{title} ({year}).{ext}"
        dest = compute_dest(node, template)
        assert dest is not None
        assert "{year?}" in dest

    def test_all_fields_present_no_placeholders(self) -> None:
        node = FileNode(path=Path("movie.mkv"))
        node.metadata = {"title": "Dune", "year": 2021, "media_type": "movie"}
        template = "{title} ({year})/{title} ({year}).{ext}"
        dest = compute_dest(node, template)
        assert dest is not None
        assert "{" not in dest

    def test_all_fields_missing_returns_none(self) -> None:
        node = FileNode(path=Path("movie"))
        node.metadata = {}
        template = "{title} ({year})/{title} ({year})"
        dest = compute_dest(node, template)
        assert dest is None

    def test_multiple_missing_fields(self) -> None:
        node = FileNode(path=Path("episode.mkv"))
        node.metadata = {"title": "GOT", "media_type": "episode"}
        template = "{title}/Season {season:02d}/{title} - S{season:02d}E{episode:02d}.{ext}"
        dest = compute_dest(node, template)
        assert dest is not None
        assert "{season?}" in dest
        assert "{episode?}" in dest
