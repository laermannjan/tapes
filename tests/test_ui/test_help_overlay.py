"""Tests for the help overlay widget and keybinding."""
from __future__ import annotations

from pathlib import Path

import pytest

from tapes.ui.help_overlay import HelpOverlay, _build_help_text
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


class TestHelpOverlayToggle:
    """Test that the help overlay state is managed correctly."""

    def test_help_initially_hidden(self) -> None:
        app = _make_app()
        assert app._help_visible is False

    def test_help_binding_registered(self) -> None:
        """Verify the question_mark binding is present in BINDINGS."""
        keys = [b.key for b in TreeApp.BINDINGS]
        assert "question_mark" in keys

    def test_help_overlay_in_compose(self) -> None:
        """Verify HelpOverlay is yielded by compose."""
        app = _make_app()
        widgets = list(app.compose())
        overlay_widgets = [w for w in widgets if isinstance(w, HelpOverlay)]
        assert len(overlay_widgets) == 1
        assert overlay_widgets[0].id == "help"
