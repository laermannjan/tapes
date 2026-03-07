"""Tests for TreeView and DetailView rendering (CSS borders, no manual box-drawing)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from tapes.ui.detail_render import get_display_fields
from tapes.ui.detail_view import DetailView
from tapes.ui.tree_model import FileNode, FolderNode, Source, TreeModel
from tapes.ui.tree_view import TreeView

MOVIE_TEMPLATE = "{title} ({year})/{title} ({year}).{ext}"
TV_TEMPLATE = (
    "{title} ({year})/Season {season:02d}/"
    "{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"
)


def _make_tree_view() -> TreeView:
    """Create a TreeView with a simple model for testing."""
    node = FileNode(
        path=Path("/movies/Inception.mkv"),
        result={"title": "Inception", "year": 2010, "media_type": "movie"},
    )
    root = FolderNode(name="root", children=[node], collapsed=False)
    model = TreeModel(root=root)
    return TreeView(model=model, movie_template=MOVIE_TEMPLATE, tv_template=TV_TEMPLATE)


def _make_detail_view() -> DetailView:
    """Create a DetailView with a node for testing."""
    node = FileNode(
        path=Path("/media/Breaking.Bad.S01E01.mkv"),
        result={"title": "Breaking Bad", "year": 2008, "season": 1, "episode": 1},
        sources=[
            Source(
                name="TMDB #1",
                fields={"title": "Breaking Bad", "year": 2008},
                confidence=0.95,
            ),
        ],
    )
    view = DetailView(node, MOVIE_TEMPLATE, TV_TEMPLATE)
    view._fields = get_display_fields(view._active_template())
    return view


def _render_plain(widget, width: int = 80, height: int = 20) -> str:
    """Render a widget and return the plain text output."""
    fake_size = SimpleNamespace(width=width, height=height)
    with patch.object(type(widget), "size", new_callable=lambda: PropertyMock(return_value=fake_size)):
        rendered = widget.render()
    return rendered.plain


# --- TreeView rendering tests ---


class TestTreeViewRendering:
    def test_tree_render_contains_content(self) -> None:
        """Verify TreeView render output contains file content (no manual borders)."""
        view = _make_tree_view()
        plain = _render_plain(view)
        # Should contain the filename, not box-drawing chars at line start
        assert "Inception" in plain

    def test_tree_render_no_manual_borders(self) -> None:
        """Verify no manual box-drawing characters in rendered output."""
        view = _make_tree_view()
        plain = _render_plain(view)
        for char in "\u250c\u2510\u2514\u2518\u2502":
            assert char not in plain

    def test_tree_has_border_title(self) -> None:
        """TreeView should have BORDER_TITLE set to 'Files'."""
        view = _make_tree_view()
        assert view.BORDER_TITLE == "Files"

    def test_tree_set_status_updates_subtitle(self) -> None:
        """set_status should update border_subtitle."""
        view = _make_tree_view()
        view.set_status("2 staged")
        assert view.border_subtitle == "2 staged"


# --- DetailView rendering tests ---


class TestDetailViewRendering:
    def test_detail_render_no_manual_borders(self) -> None:
        """Verify no manual box-drawing border characters in rendered output."""
        view = _make_detail_view()
        plain = _render_plain(view)
        for char in "\u250c\u2510\u2514\u2518\u251c\u2524":
            assert char not in plain

    def test_detail_has_border_title(self) -> None:
        """DetailView should have BORDER_TITLE set to 'Detail'."""
        view = _make_detail_view()
        assert view.BORDER_TITLE == "Detail"

    def test_detail_no_help_line_in_expanded(self) -> None:
        """Expanded detail should not contain the help shortcut line."""
        view = _make_detail_view()
        view.add_class("expanded")
        plain = _render_plain(view, height=30)
        assert "enter: apply/edit" not in plain
        assert "shift-enter: apply all" not in plain


# --- Focus styling tests ---


class TestFocusStyling:
    def test_css_has_focus_rules_for_tree_view(self) -> None:
        """App CSS uses :focus pseudo-class for TreeView border."""
        from tapes.ui.tree_app import TreeApp
        css = TreeApp.CSS
        assert "TreeView:focus" in css

    def test_css_has_focus_rules_for_detail_view(self) -> None:
        """App CSS uses :focus pseudo-class for DetailView border."""
        from tapes.ui.tree_app import TreeApp
        css = TreeApp.CSS
        assert "DetailView:focus" in css
