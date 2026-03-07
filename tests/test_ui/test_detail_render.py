"""Tests for diff_style, confidence_style, and compact preview in detail_render."""
from __future__ import annotations

from pathlib import Path

import pytest

from tapes.ui.detail_render import (
    confidence_style,
    diff_style,
    render_compact_preview,
    render_folder_preview,
)
from tapes.ui.tree_model import FileNode, FolderNode, Source


# --- diff_style ---


class TestDiffStyle:
    def test_matches_result(self) -> None:
        assert diff_style("Breaking Bad", "Breaking Bad") == "dim"

    def test_matches_result_int_coerced(self) -> None:
        # str comparison: int result vs int source
        assert diff_style(2008, 2008) == "dim"

    def test_differs_from_result(self) -> None:
        assert diff_style("Breaking Bad", "Better Call Saul") == "#E8734A"

    def test_differs_int_vs_different_int(self) -> None:
        assert diff_style(2008, 2010) == "#E8734A"

    def test_fills_empty_none_result(self) -> None:
        assert diff_style(None, "Breaking Bad") == "#7daea3"

    def test_fills_empty_string_result(self) -> None:
        assert diff_style("", "Breaking Bad") == "#7daea3"

    def test_missing_source(self) -> None:
        assert diff_style("Breaking Bad", None) == "dim"

    def test_both_none(self) -> None:
        assert diff_style(None, None) == "dim"

    def test_source_zero_fills_none_result(self) -> None:
        # 0 is a valid value, not None
        assert diff_style(None, 0) == "#7daea3"


# --- confidence_style ---


class TestConfidenceStyle:
    def test_high_confidence_green(self) -> None:
        assert confidence_style(0.95) == "#7daea3"

    def test_boundary_80_green(self) -> None:
        assert confidence_style(0.8) == "#7daea3"

    def test_medium_confidence_yellow(self) -> None:
        assert confidence_style(0.65) == "#E8734A"

    def test_boundary_50_yellow(self) -> None:
        assert confidence_style(0.5) == "#E8734A"

    def test_low_confidence_red(self) -> None:
        assert confidence_style(0.3) == "#ea6962"

    def test_zero_confidence_red(self) -> None:
        assert confidence_style(0.0) == "#ea6962"

    def test_boundary_just_below_80_yellow(self) -> None:
        assert confidence_style(0.79) == "#E8734A"

    def test_boundary_just_below_50_red(self) -> None:
        assert confidence_style(0.49) == "#ea6962"


# --- render_compact_preview ---

MOVIE_TEMPLATE = "{title} ({year})/{title}.{ext}"
TV_TEMPLATE = "{title}/S{season:02d}E{episode:02d} - {episode_title}.{ext}"


class TestRenderCompactPreview:
    def test_full_movie_fields(self) -> None:
        node = FileNode(
            path=Path("/movies/Inception.2010.1080p.BluRay.x264.mkv"),
            result={"title": "Inception", "year": 2010, "media_type": "movie"},
            sources=[Source(name="tmdb", confidence=0.92)],
        )
        text = render_compact_preview(node, MOVIE_TEMPLATE)
        plain = text.plain
        assert "Inception.2010.1080p.BluRay.x264.mkv" in plain
        assert "\u2192" in plain  # arrow
        assert "title: Inception" in plain
        assert "year: 2010" in plain
        assert "type: movie" in plain
        assert "TMDB 92%" in plain

    def test_missing_fields_show_dot(self) -> None:
        node = FileNode(
            path=Path("/movies/unknown.mkv"),
            result={"title": "Unknown"},
        )
        text = render_compact_preview(node, MOVIE_TEMPLATE)
        plain = text.plain
        assert "title: Unknown" in plain
        # year, season, episode should be dots
        assert "year: \u00b7" in plain
        assert "S: \u00b7" in plain
        assert "E: \u00b7" in plain

    def test_no_sources_no_tmdb(self) -> None:
        node = FileNode(
            path=Path("/movies/file.mkv"),
            result={"title": "Test"},
        )
        text = render_compact_preview(node, MOVIE_TEMPLATE)
        plain = text.plain
        assert "TMDB" not in plain

    def test_tv_episode_fields(self) -> None:
        node = FileNode(
            path=Path("/tv/breaking.bad.s01e01.mkv"),
            result={
                "title": "Breaking Bad",
                "year": 2008,
                "media_type": "episode",
                "season": 1,
                "episode": 1,
            },
            sources=[Source(name="tmdb", confidence=0.85)],
        )
        text = render_compact_preview(node, TV_TEMPLATE)
        plain = text.plain
        assert "S: 1" in plain
        assert "E: 1" in plain
        assert "TMDB 85%" in plain

    def test_best_confidence_used(self) -> None:
        node = FileNode(
            path=Path("/movies/file.mkv"),
            result={"title": "Test"},
            sources=[
                Source(name="guessit", confidence=0.5),
                Source(name="tmdb", confidence=0.95),
            ],
        )
        text = render_compact_preview(node, MOVIE_TEMPLATE)
        plain = text.plain
        assert "TMDB 95%" in plain

    def test_zero_confidence_sources_hidden(self) -> None:
        node = FileNode(
            path=Path("/movies/file.mkv"),
            result={"title": "Test"},
            sources=[Source(name="guessit", confidence=0.0)],
        )
        text = render_compact_preview(node, MOVIE_TEMPLATE)
        plain = text.plain
        assert "TMDB" not in plain


# --- render_folder_preview ---


class TestRenderFolderPreview:
    def test_empty_folder(self) -> None:
        folder = FolderNode(name="extras")
        text = render_folder_preview(folder)
        plain = text.plain
        assert "extras/" in plain
        assert "empty" in plain

    def test_folder_with_files(self) -> None:
        folder = FolderNode(
            name="extras",
            children=[
                FileNode(path=Path("/a.mkv")),
                FileNode(path=Path("/b.mkv")),
            ],
        )
        text = render_folder_preview(folder)
        plain = text.plain
        assert "extras/" in plain
        assert "2 files" in plain
        assert "2 unstaged" in plain

    def test_folder_mixed_staged_ignored(self) -> None:
        folder = FolderNode(
            name="subs",
            children=[
                FileNode(path=Path("/a.srt"), staged=True),
                FileNode(path=Path("/b.srt")),
                FileNode(path=Path("/c.srt"), ignored=True),
            ],
        )
        text = render_folder_preview(folder)
        plain = text.plain
        assert "3 files" in plain
        assert "1 unstaged" in plain
        assert "1 ignored" in plain

    def test_folder_all_staged(self) -> None:
        folder = FolderNode(
            name="movies",
            children=[
                FileNode(path=Path("/a.mkv"), staged=True),
                FileNode(path=Path("/b.mkv"), staged=True),
            ],
        )
        text = render_folder_preview(folder)
        plain = text.plain
        assert "2 files" in plain
        assert "unstaged" not in plain
        assert "ignored" not in plain

    def test_folder_single_file(self) -> None:
        folder = FolderNode(
            name="one",
            children=[FileNode(path=Path("/a.mkv"))],
        )
        text = render_folder_preview(folder)
        plain = text.plain
        assert "1 file" in plain
        # Should not say "1 files"
        assert "1 files" not in plain

    def test_nested_folder_counts_all_files(self) -> None:
        inner = FolderNode(
            name="inner",
            children=[FileNode(path=Path("/inner/a.mkv"))],
        )
        folder = FolderNode(
            name="outer",
            children=[
                FileNode(path=Path("/outer/b.mkv"), staged=True),
                inner,
            ],
        )
        text = render_folder_preview(folder)
        plain = text.plain
        assert "2 files" in plain
        assert "1 unstaged" in plain
