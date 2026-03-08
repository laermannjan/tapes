"""Tests for the commit confirmation modal."""
from __future__ import annotations

from pathlib import Path

import pytest

from tapes.ui.commit_modal import OPERATIONS, build_commit_text
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

    def test_contains_count_singular(self) -> None:
        text = build_commit_text(1, "copy")
        plain = text.plain
        assert "Process 1 file?" in plain

    def test_contains_count_plural(self) -> None:
        text = build_commit_text(5, "move")
        plain = text.plain
        assert "Process 5 files?" in plain

    def test_shows_operation_in_brackets(self) -> None:
        text = build_commit_text(3, "copy")
        plain = text.plain
        assert "[copy]" in plain

    def test_shows_move_operation(self) -> None:
        text = build_commit_text(1, "move")
        plain = text.plain
        assert "[move]" in plain

    def test_shows_link_operation(self) -> None:
        text = build_commit_text(1, "link")
        plain = text.plain
        assert "[link]" in plain

    def test_shows_hardlink_operation(self) -> None:
        text = build_commit_text(1, "hardlink")
        plain = text.plain
        assert "[hardlink]" in plain

    def test_contains_confirm_cancel_hints(self) -> None:
        text = build_commit_text(1, "copy")
        plain = text.plain
        assert "confirm" in plain
        assert "cancel" in plain

    def test_contains_change_hint(self) -> None:
        text = build_commit_text(1, "copy")
        plain = text.plain
        assert "to change" in plain

    def test_zero_files(self) -> None:
        text = build_commit_text(0, "copy")
        plain = text.plain
        assert "Process 0 files?" in plain


# ---------------------------------------------------------------------------
# CommitScreen tests
# ---------------------------------------------------------------------------


class TestCommitScreen:
    """Test that CommitScreen is a proper ModalScreen."""

    def test_is_modal_screen(self) -> None:
        from textual.screen import ModalScreen

        from tapes.ui.commit_modal import CommitScreen

        assert issubclass(CommitScreen, ModalScreen)

    def test_has_confirm_cancel_and_nav_bindings(self) -> None:
        from tapes.ui.commit_modal import CommitScreen

        keys = [b.key for b in CommitScreen.BINDINGS]
        assert "y" in keys
        assert "n" in keys
        assert "escape" in keys
        assert "h,left" in keys
        assert "l,right" in keys

    def test_commit_binding_registered_on_app(self) -> None:
        """Verify the c binding is present in TreeApp.BINDINGS."""
        keys = [b.key for b in TreeApp.BINDINGS]
        assert "c" in keys

    def test_operations_list(self) -> None:
        assert OPERATIONS == ["copy", "move", "link", "hardlink"]

    def test_unknown_operation_defaults_to_copy(self) -> None:
        from tapes.ui.commit_modal import CommitScreen

        screen = CommitScreen(1, "unknown")
        assert screen._operation == "copy"
