"""Tests for widget rendering (separators, no manual box-drawing)."""

from __future__ import annotations

from pathlib import Path

from tapes.tree_model import Candidate, FileNode, FolderNode, TreeModel
from tapes.ui.metadata_render import get_display_fields
from tapes.ui.metadata_view import MetadataView
from tapes.ui.tree_view import TreeView
from tests.test_ui.conftest import render_plain

MOVIE_TEMPLATE = "{title} ({year})/{title} ({year}).{ext}"
TV_TEMPLATE = "{title} ({year})/Season {season:02d}/{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"


def _make_tree_view() -> TreeView:
    node = FileNode(
        path=Path("/movies/Inception.mkv"),
        metadata={"title": "Inception", "year": 2010, "media_type": "movie"},
    )
    root = FolderNode(name="root", children=[node], collapsed=False)
    model = TreeModel(root=root)
    return TreeView(model=model, movie_template=MOVIE_TEMPLATE, tv_template=TV_TEMPLATE)


def _make_metadata_view() -> MetadataView:
    node = FileNode(
        path=Path("/media/Breaking.Bad.S01E01.mkv"),
        metadata={"title": "Breaking Bad", "year": 2008, "season": 1, "episode": 1},
        candidates=[
            Candidate(
                name="TMDB #1",
                metadata={"title": "Breaking Bad", "year": 2008},
                score=0.95,
            ),
        ],
    )
    view = MetadataView(node, MOVIE_TEMPLATE, TV_TEMPLATE)
    view.fields = get_display_fields(view._active_template())
    return view


class TestTreeViewRendering:
    def test_tree_render_contains_content(self) -> None:
        view = _make_tree_view()
        plain = render_plain(view)
        assert "Inception" in plain

    def test_tree_render_no_manual_borders(self) -> None:
        view = _make_tree_view()
        plain = render_plain(view)
        for char in "\u250c\u2510\u2514\u2518\u2502":
            assert char not in plain


class TestMetadataViewRendering:
    def test_metadata_render_has_separator(self) -> None:
        view = _make_metadata_view()
        plain = render_plain(view, height=30)
        assert "\u2500\u2500\u2500 Metadata" in plain

    def test_metadata_render_has_footer_hints(self) -> None:
        view = _make_metadata_view()
        plain = render_plain(view, height=30)
        assert "enter to accept" in plain
        assert "esc to discard" in plain

    def test_metadata_render_no_manual_borders(self) -> None:
        view = _make_metadata_view()
        plain = render_plain(view, height=30)
        for char in "\u250c\u2510\u2514\u2518\u251c\u2524":
            assert char not in plain
