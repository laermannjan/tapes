"""Tests for the commit confirmation modal."""
from __future__ import annotations

from pathlib import Path

import pytest

from tapes.ui.commit_modal import build_commit_text
from tapes.ui.tree_app import TreeApp
from tapes.ui.tree_model import FileNode, FolderNode, TreeModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MOVIE_TEMPLATE = "{title} ({year})/{title} ({year}).{ext}"
TV_TEMPLATE = "{title} ({year})/S{season:02d}/S{season:02d}E{episode:02d}.{ext}"


def _simple_model() -> TreeModel:
    root = FolderNode(
        name="root",
        children=[
            FileNode(path=Path("/root/movie.mkv")),
        ],
    )
    return TreeModel(root=root)


def _make_app() -> TreeApp:
    model = _simple_model()
    return TreeApp(
        model=model,
        movie_template=MOVIE_TEMPLATE,
        tv_template=TV_TEMPLATE,
    )


# ---------------------------------------------------------------------------
# build_commit_text content tests
# ---------------------------------------------------------------------------


class TestBuildCommitText:
    """Test that the modal text contains expected content."""

    def test_contains_operation_and_count(self) -> None:
        text = build_commit_text(
            [("movie.mkv", "Movie (2024)/Movie (2024).mkv")],
            "copy",
        )
        plain = text.plain
        assert "Copy 1 file to library?" in plain

    def test_plural_files(self) -> None:
        text = build_commit_text(
            [
                ("movie1.mkv", "Movie1 (2024)/Movie1 (2024).mkv"),
                ("movie2.mkv", "Movie2 (2024)/Movie2 (2024).mkv"),
            ],
            "move",
        )
        plain = text.plain
        assert "Move 2 files to library?" in plain

    def test_link_operation(self) -> None:
        text = build_commit_text(
            [("movie.mkv", "Movie (2024)/Movie (2024).mkv")],
            "link",
        )
        plain = text.plain
        assert "Link 1 file to library?" in plain

    def test_contains_filename(self) -> None:
        text = build_commit_text(
            [("Breaking.Bad.S01E01.mkv", "Breaking Bad (2008)/S01/S01E01.mkv")],
            "copy",
        )
        plain = text.plain
        assert "Breaking.Bad.S01E01.mkv" in plain

    def test_contains_destination_arrow(self) -> None:
        text = build_commit_text(
            [("movie.mkv", "Movie (2024)/Movie (2024).mkv")],
            "copy",
        )
        plain = text.plain
        assert "\u2192" in plain  # arrow
        assert "Movie (2024)" in plain

    def test_contains_checkmark(self) -> None:
        text = build_commit_text(
            [("movie.mkv", "Movie (2024)/Movie (2024).mkv")],
            "copy",
        )
        plain = text.plain
        assert "\u2713" in plain  # checkmark in commit list

    def test_contains_confirm_cancel_hints(self) -> None:
        text = build_commit_text(
            [("movie.mkv", "Movie (2024)/Movie (2024).mkv")],
            "copy",
        )
        plain = text.plain
        assert "y" in plain
        assert "confirm" in plain
        assert "n" in plain
        assert "cancel" in plain

    def test_contains_operation_label(self) -> None:
        text = build_commit_text(
            [("movie.mkv", "Movie (2024)/Movie (2024).mkv")],
            "copy",
        )
        plain = text.plain
        assert "Copy" in plain

    def test_none_destination_shows_placeholder(self) -> None:
        text = build_commit_text(
            [("movie.mkv", None)],
            "copy",
        )
        plain = text.plain
        assert "???" in plain

    def test_multiple_files_listed(self) -> None:
        files = [
            ("file1.mkv", "Dest1/file1.mkv"),
            ("file2.mkv", "Dest2/file2.mkv"),
            ("file3.mkv", "Dest3/file3.mkv"),
        ]
        text = build_commit_text(files, "copy")
        plain = text.plain
        assert "file1.mkv" in plain
        assert "file2.mkv" in plain
        assert "file3.mkv" in plain
        assert "Copy 3 files to library?" in plain


# ---------------------------------------------------------------------------
# CommitModal widget tests
# ---------------------------------------------------------------------------


class TestCommitModalWidget:
    """Test build_commit_text."""

    def test_default_empty(self) -> None:
        text = build_commit_text([], "copy")
        plain = text.plain
        assert "Copy 0 files to library?" in plain


# ---------------------------------------------------------------------------
# CommitScreen tests
# ---------------------------------------------------------------------------


class TestCommitScreen:
    """Test that CommitScreen is a proper ModalScreen."""

    def test_is_modal_screen(self) -> None:
        from textual.screen import ModalScreen

        from tapes.ui.commit_modal import CommitScreen

        assert issubclass(CommitScreen, ModalScreen)

    def test_has_confirm_and_cancel_bindings(self) -> None:
        from tapes.ui.commit_modal import CommitScreen

        keys = [b.key for b in CommitScreen.BINDINGS]
        assert "y" in keys
        assert "n" in keys
        assert "escape" in keys

    def test_commit_binding_registered_on_app(self) -> None:
        """Verify the c binding is present in TreeApp.BINDINGS."""
        keys = [b.key for b in TreeApp.BINDINGS]
        assert "c" in keys
