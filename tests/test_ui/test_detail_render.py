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
        assert diff_style("Breaking Bad", "Breaking Bad") == "#888888"

    def test_matches_result_int_coerced(self) -> None:
        # str comparison: int result vs int source
        assert diff_style(2008, 2008) == "#888888"

    def test_differs_from_result(self) -> None:
        assert diff_style("Breaking Bad", "Better Call Saul") == "#E07A47"

    def test_differs_int_vs_different_int(self) -> None:
        assert diff_style(2008, 2010) == "#E07A47"

    def test_fills_empty_none_result(self) -> None:
        assert diff_style(None, "Breaking Bad") == "#86E89A"

    def test_fills_empty_string_result(self) -> None:
        assert diff_style("", "Breaking Bad") == "#86E89A"

    def test_missing_source(self) -> None:
        assert diff_style("Breaking Bad", None) == "#888888"

    def test_both_none(self) -> None:
        assert diff_style(None, None) == "#888888"

    def test_source_zero_fills_none_result(self) -> None:
        # 0 is a valid value, not None
        assert diff_style(None, 0) == "#86E89A"


# --- confidence_style ---


class TestConfidenceStyle:
    def test_high_confidence_muted(self) -> None:
        assert confidence_style(0.95) == "#888888"

    def test_boundary_80_muted(self) -> None:
        assert confidence_style(0.8) == "#888888"

    def test_medium_confidence_yellow(self) -> None:
        assert confidence_style(0.65) == "#E07A47"

    def test_boundary_50_yellow(self) -> None:
        assert confidence_style(0.5) == "#E07A47"

    def test_low_confidence_red(self) -> None:
        assert confidence_style(0.3) == "#FF7A7A"

    def test_zero_confidence_red(self) -> None:
        assert confidence_style(0.0) == "#FF7A7A"

    def test_boundary_just_below_80_yellow(self) -> None:
        assert confidence_style(0.79) == "#E07A47"

    def test_boundary_just_below_50_red(self) -> None:
        assert confidence_style(0.49) == "#FF7A7A"


# --- render_compact_preview ---

MOVIE_TEMPLATE = "{title} ({year})/{title}.{ext}"
TV_TEMPLATE = "{title}/S{season:02d}E{episode:02d} - {episode_title}.{ext}"


class TestRenderCompactPreview:
    def test_shows_filename_and_destination(self) -> None:
        node = FileNode(
            path=Path("/movies/Inception.2010.1080p.BluRay.x264.mkv"),
            result={"title": "Inception", "year": 2010, "media_type": "movie"},
            sources=[Source(name="tmdb", confidence=0.92)],
        )
        text = render_compact_preview(node, MOVIE_TEMPLATE)
        plain = text.plain
        assert "Inception.2010.1080p.BluRay.x264.mkv" in plain
        assert "\u2192" in plain  # arrow

    def test_tmdb_id_shown_when_set(self) -> None:
        node = FileNode(
            path=Path("/movies/file.mkv"),
            result={"title": "Test", "tmdb_id": 603},
            sources=[Source(name="tmdb", confidence=0.92)],
        )
        text = render_compact_preview(node, MOVIE_TEMPLATE)
        plain = text.plain
        assert "tmdb: 603" in plain
        assert "92%" in plain

    def test_tmdb_question_mark_when_missing(self) -> None:
        node = FileNode(
            path=Path("/movies/file.mkv"),
            result={"title": "Test"},
        )
        text = render_compact_preview(node, MOVIE_TEMPLATE)
        plain = text.plain
        assert "tmdb: ?" in plain

    def test_no_confidence_without_tmdb_id(self) -> None:
        node = FileNode(
            path=Path("/movies/file.mkv"),
            result={"title": "Test"},
            sources=[Source(name="tmdb", confidence=0.85)],
        )
        text = render_compact_preview(node, MOVIE_TEMPLATE)
        plain = text.plain
        # No tmdb_id in result, so no confidence shown
        assert "85%" not in plain

    def test_confidence_shown_with_tmdb_id(self) -> None:
        node = FileNode(
            path=Path("/movies/file.mkv"),
            result={"title": "Test", "tmdb_id": 123},
            sources=[
                Source(name="guessit", confidence=0.5),
                Source(name="tmdb", confidence=0.95),
            ],
        )
        text = render_compact_preview(node, MOVIE_TEMPLATE)
        plain = text.plain
        assert "tmdb: 123" in plain
        assert "95%" in plain

    def test_zero_confidence_sources_no_percent(self) -> None:
        node = FileNode(
            path=Path("/movies/file.mkv"),
            result={"title": "Test", "tmdb_id": 42},
            sources=[Source(name="guessit", confidence=0.0)],
        )
        text = render_compact_preview(node, MOVIE_TEMPLATE)
        plain = text.plain
        assert "tmdb: 42" in plain
        assert "%" not in plain


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
