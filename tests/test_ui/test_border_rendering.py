"""Tests for widget rendering (separators, no manual box-drawing)."""
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
    node = FileNode(
        path=Path("/movies/Inception.mkv"),
        result={"title": "Inception", "year": 2010, "media_type": "movie"},
    )
    root = FolderNode(name="root", children=[node], collapsed=False)
    model = TreeModel(root=root)
    return TreeView(model=model, movie_template=MOVIE_TEMPLATE, tv_template=TV_TEMPLATE)


def _make_detail_view() -> DetailView:
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
    view.fields = get_display_fields(view._active_template())
    return view


def _render_plain(widget, width: int = 80, height: int = 20) -> str:
    fake_size = SimpleNamespace(width=width, height=height)
    with patch.object(
        type(widget), "size", new_callable=lambda: PropertyMock(return_value=fake_size)
    ):
        rendered = widget.render()
    return rendered.plain


class TestTreeViewRendering:
    def test_tree_render_contains_content(self) -> None:
        view = _make_tree_view()
        plain = _render_plain(view)
        assert "Inception" in plain

    def test_tree_render_no_manual_borders(self) -> None:
        view = _make_tree_view()
        plain = _render_plain(view)
        for char in "\u250c\u2510\u2514\u2518\u2502":
            assert char not in plain


class TestDetailViewRendering:
    def test_detail_render_has_separator(self) -> None:
        view = _make_detail_view()
        plain = _render_plain(view, height=30)
        assert "\u2500\u2500\u2500 Info" in plain

    def test_detail_render_has_footer_hints(self) -> None:
        view = _make_detail_view()
        plain = _render_plain(view, height=30)
        assert "enter edit" in plain
        assert "esc discard" in plain

    def test_detail_render_no_manual_borders(self) -> None:
        view = _make_detail_view()
        plain = _render_plain(view, height=30)
        for char in "\u250c\u2510\u2514\u2518\u251c\u2524":
            assert char not in plain
