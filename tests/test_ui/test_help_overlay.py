"""Tests for the help overlay widget and keybinding."""
from __future__ import annotations

from pathlib import Path

import pytest

from tapes.ui.help_overlay import HelpScreen, _build_help_text
from tapes.ui.tree_app import TreeApp
from tapes.ui.tree_model import FileNode, FolderNode, TreeModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEMPLATE = "{title} ({year}).{ext}"


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
        movie_template=TEMPLATE,
        tv_template=TEMPLATE,
    )


# ---------------------------------------------------------------------------
# _build_help_text content tests
# ---------------------------------------------------------------------------


class TestHelpTextContent:
    """Test that the help text contains expected sections and keys."""

    def test_contains_files_section(self) -> None:
        text = _build_help_text()
        plain = text.plain
        assert "Files" in plain

    def test_contains_detail_section(self) -> None:
        text = _build_help_text()
        plain = text.plain
        assert "Detail" in plain

    def test_contains_concepts_section(self) -> None:
        text = _build_help_text()
        plain = text.plain
        assert "Concepts" in plain

    def test_contains_stage_key(self) -> None:
        text = _build_help_text()
        plain = text.plain
        assert "Toggle staged" in plain

    def test_contains_apply_key(self) -> None:
        text = _build_help_text()
        plain = text.plain
        assert "Apply field" in plain

    def test_contains_close_hint(self) -> None:
        text = _build_help_text()
        plain = text.plain
        assert "? or esc to close" in plain

    def test_contains_commit_key(self) -> None:
        text = _build_help_text()
        plain = text.plain
        assert "Commit staged" in plain

    def test_contains_sources_explanation(self) -> None:
        text = _build_help_text()
        plain = text.plain
        assert "Sources provide metadata" in plain


# ---------------------------------------------------------------------------
# TreeApp help overlay integration tests
# ---------------------------------------------------------------------------


class TestHelpScreen:
    """Test that HelpScreen is a proper ModalScreen."""

    def test_is_modal_screen(self) -> None:
        from textual.screen import ModalScreen

        assert issubclass(HelpScreen, ModalScreen)

    def test_has_dismiss_bindings(self) -> None:
        """HelpScreen should handle escape and ? to dismiss."""
        keys = [b.key for b in HelpScreen.BINDINGS]
        assert "escape" in keys
        assert "question_mark" in keys

    def test_help_binding_registered_on_app(self) -> None:
        """Verify the question_mark binding is present in TreeApp.BINDINGS."""
        keys = [b.key for b in TreeApp.BINDINGS]
        assert "question_mark" in keys
