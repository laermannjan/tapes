"""Tests for box-drawing border rendering in TreeView and DetailView."""
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


# --- TreeView border tests ---


class TestTreeViewBorders:
    def test_tree_border_top_contains_title(self) -> None:
        """Verify 'Files' appears in the first line of TreeView rendered output."""
        view = _make_tree_view()
        plain = _render_plain(view)
        first_line = plain.split("\n")[0]
        assert "Files" in first_line

    def test_tree_border_active_vs_inactive(self) -> None:
        """Toggle active and verify the border style changes (cyan vs dim)."""
        view = _make_tree_view()
        fake_size = SimpleNamespace(width=80, height=20)
        with patch.object(type(view), "size", new_callable=lambda: PropertyMock(return_value=fake_size)):
            # Active state (default)
            view.active = True
            rendered_active = view.render()
            top_line_active = rendered_active.split("\n")[0]

            # Inactive state
            view.active = False
            rendered_inactive = view.render()
            top_line_inactive = rendered_inactive.split("\n")[0]

        # Both should have the same plain text
        assert top_line_active.plain == top_line_inactive.plain
        # But different styles: active uses cyan, inactive uses dim
        # Check spans on the top line
        active_styles = {span.style for span in top_line_active._spans}
        inactive_styles = {span.style for span in top_line_inactive._spans}
        assert "cyan" in active_styles or any("cyan" in str(s) for s in active_styles)
        assert "dim" in inactive_styles or any("dim" in str(s) for s in inactive_styles)

    def test_tree_bottom_border_shows_status(self) -> None:
        """Call set_status('2 staged') and verify it appears in the bottom line."""
        view = _make_tree_view()
        view.set_status("2 staged")
        plain = _render_plain(view)
        last_line = plain.split("\n")[-1]
        assert "2 staged" in last_line


# --- DetailView border tests ---


class TestDetailViewBorders:
    def test_detail_border_top_contains_title(self) -> None:
        """Verify 'Detail' appears in the first line of DetailView rendered output."""
        view = _make_detail_view()
        plain = _render_plain(view)
        first_line = plain.split("\n")[0]
        assert "Detail" in first_line

    def test_detail_border_active_vs_inactive(self) -> None:
        """Toggle active and verify the border style changes (cyan vs dim)."""
        view = _make_detail_view()
        fake_size = SimpleNamespace(width=80, height=30)
        with patch.object(type(view), "size", new_callable=lambda: PropertyMock(return_value=fake_size)):
            # Active state
            view.active = True
            rendered_active = view.render()
            top_line_active = rendered_active.split("\n")[0]

            # Inactive state
            view.active = False
            rendered_inactive = view.render()
            top_line_inactive = rendered_inactive.split("\n")[0]

        # Same plain text content
        assert top_line_active.plain == top_line_inactive.plain
        # Different styles
        active_styles = {span.style for span in top_line_active._spans}
        inactive_styles = {span.style for span in top_line_inactive._spans}
        assert "cyan" in active_styles or any("cyan" in str(s) for s in active_styles)
        assert "dim" in inactive_styles or any("dim" in str(s) for s in inactive_styles)
