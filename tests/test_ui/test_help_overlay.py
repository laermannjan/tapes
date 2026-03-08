"""Tests for the inline help view."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from tapes.ui.help_overlay import HelpView, _build_help_content
from tapes.ui.tree_app import TreeApp


def _render_plain(widget, width: int = 80, height: int = 40) -> str:
    fake_size = SimpleNamespace(width=width, height=height)
    with patch.object(
        type(widget), "size", new_callable=lambda: PropertyMock(return_value=fake_size)
    ):
        rendered = widget.render()
    return rendered.plain


class TestHelpContent:
    """Test that the help content contains expected sections."""

    def test_contains_how_it_works(self) -> None:
        lines = _build_help_content(80)
        plain = "\n".join(line.plain for line in lines)
        assert "How it works" in plain

    def test_contains_file_browser_section(self) -> None:
        lines = _build_help_content(80)
        plain = "\n".join(line.plain for line in lines)
        assert "File browser" in plain

    def test_contains_detail_section(self) -> None:
        lines = _build_help_content(80)
        plain = "\n".join(line.plain for line in lines)
        assert "Detail view" in plain

    def test_contains_tips_section(self) -> None:
        lines = _build_help_content(80)
        plain = "\n".join(line.plain for line in lines)
        assert "Tips" in plain

    def test_contains_close_hint(self) -> None:
        lines = _build_help_content(80)
        plain = "\n".join(line.plain for line in lines)
        assert "? or esc to close" in plain

    def test_contains_commit_key(self) -> None:
        lines = _build_help_content(80)
        plain = "\n".join(line.plain for line in lines)
        assert "commit staged" in plain


class TestHelpView:
    def test_is_widget(self) -> None:
        from textual.widget import Widget

        assert issubclass(HelpView, Widget)

    def test_renders_content(self) -> None:
        view = HelpView()
        plain = _render_plain(view)
        assert "Help" in plain
        assert "File browser" in plain

    def test_help_binding_registered_on_app(self) -> None:
        keys = [b.key for b in TreeApp.BINDINGS]
        assert "question_mark" in keys
