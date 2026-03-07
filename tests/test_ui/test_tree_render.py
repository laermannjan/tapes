"""Tests for tree_render pure rendering functions."""
from __future__ import annotations

from pathlib import Path

from tapes.ui.tree_model import FileNode, FolderNode, TreeModel
from tapes.ui.tree_render import (
    compute_dest,
    flatten_with_depth,
    render_file_row,
    render_folder_row,
    render_row,
)

MOVIE_TEMPLATE = "{title} ({year})/{title} ({year}).{ext}"
TV_TEMPLATE = (
    "{title} ({year})/Season {season:02d}/"
    "{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"
)


# --- compute_dest ---


class TestComputeDest:
    def test_movie_all_fields_present(self) -> None:
        node = FileNode(
            path=Path("/movies/Inception.mkv"),
            result={"title": "Inception", "year": 2010},
        )
        result = compute_dest(node, MOVIE_TEMPLATE)
        assert result == "Inception (2010)/Inception (2010).mkv"

    def test_returns_none_when_fields_missing(self) -> None:
        node = FileNode(
            path=Path("/movies/Inception.mkv"),
            result={"title": "Inception"},
        )
        result = compute_dest(node, MOVIE_TEMPLATE)
        assert result is None

    def test_tv_template_with_season_episode(self) -> None:
        node = FileNode(
            path=Path("/tv/breaking.bad.s01e02.mkv"),
            result={
                "title": "Breaking Bad",
                "year": 2008,
                "season": 1,
                "episode": 2,
                "episode_title": "Cat's in the Bag...",
            },
        )
        result = compute_dest(node, TV_TEMPLATE)
        assert result == (
            "Breaking Bad (2008)/Season 01/"
            "Breaking Bad - S01E02 - Cat's in the Bag....mkv"
        )


# --- render_file_row ---


class TestRenderFileRow:
    def test_staged_file_with_destination(self) -> None:
        node = FileNode(
            path=Path("/movies/Inception.mkv"),
            staged=True,
            result={"title": "Inception", "year": 2010},
        )
        row = render_file_row(node, MOVIE_TEMPLATE)
        assert row == "\u2713 Inception.mkv  \u2192  Inception (2010)/Inception (2010).mkv"

    def test_unstaged_file(self) -> None:
        node = FileNode(
            path=Path("/movies/Inception.mkv"),
            staged=False,
            result={"title": "Inception", "year": 2010},
        )
        row = render_file_row(node, MOVIE_TEMPLATE)
        assert row.startswith("\u25cb ")

    def test_ignored_file_space_marker(self) -> None:
        node = FileNode(
            path=Path("/movies/Inception.mkv"),
            ignored=True,
            result={"title": "Inception", "year": 2010},
        )
        row = render_file_row(node, MOVIE_TEMPLATE)
        assert row.startswith("  ")  # space marker + space before filename

    def test_missing_dest_shows_question_marks(self) -> None:
        node = FileNode(
            path=Path("/movies/Inception.mkv"),
            result={},
        )
        row = render_file_row(node, MOVIE_TEMPLATE)
        assert "???" in row

    def test_with_indentation_depth_2(self) -> None:
        node = FileNode(
            path=Path("/movies/Inception.mkv"),
            result={"title": "Inception", "year": 2010},
        )
        row = render_file_row(node, MOVIE_TEMPLATE, depth=2)
        assert row.startswith("    ")  # 2 * "  " = 4 spaces

    def test_flat_mode_no_indentation_relative_path(self) -> None:
        root = Path("/media")
        node = FileNode(
            path=Path("/media/movies/Inception.mkv"),
            result={"title": "Inception", "year": 2010},
        )
        row = render_file_row(
            node, MOVIE_TEMPLATE, depth=3, flat_mode=True, root_path=root
        )
        # Flat mode: no indentation regardless of depth
        assert not row.startswith(" " * 6)
        # Uses relative path
        assert "movies/Inception.mkv" in row


# --- render_folder_row ---


class TestRenderFolderRow:
    def test_collapsed_arrow(self) -> None:
        node = FolderNode(name="movies", collapsed=True)
        row = render_folder_row(node)
        assert row == "\u25b6 movies/"

    def test_expanded_arrow(self) -> None:
        node = FolderNode(name="movies", collapsed=False)
        row = render_folder_row(node)
        assert row == "\u25bc movies/"

    def test_with_indentation(self) -> None:
        node = FolderNode(name="Season 01", collapsed=True)
        row = render_folder_row(node, depth=1)
        assert row == "  \u25b6 Season 01/"


# --- render_row ---


class TestRenderRow:
    def test_dispatches_to_file(self) -> None:
        node = FileNode(
            path=Path("/movies/Inception.mkv"),
            result={"title": "Inception", "year": 2010},
        )
        row = render_row(node, MOVIE_TEMPLATE)
        # Should contain the arrow separator from file rendering
        assert "\u2192" in row

    def test_dispatches_to_folder(self) -> None:
        node = FolderNode(name="tv", collapsed=True)
        row = render_row(node, MOVIE_TEMPLATE)
        assert row == "\u25b6 tv/"


# --- flatten_with_depth ---


class TestFlattenWithDepth:
    def test_correct_depths_for_nested_tree(self) -> None:
        """Build a tree and verify depth values."""
        inner_file = FileNode(path=Path("/root/sub/file.mkv"))
        inner_folder = FolderNode(
            name="sub", children=[inner_file], collapsed=False
        )
        top_file = FileNode(path=Path("/root/top.mkv"))
        root = FolderNode(
            name="root", children=[inner_folder, top_file], collapsed=False
        )
        model = TreeModel(root=root)

        items = flatten_with_depth(model)

        assert len(items) == 3
        # inner_folder at depth 0
        assert items[0] == (inner_folder, 0)
        # inner_file at depth 1 (child of expanded inner_folder)
        assert items[1] == (inner_file, 1)
        # top_file at depth 0
        assert items[2] == (top_file, 0)

    def test_collapsed_folder_hides_children(self) -> None:
        inner_file = FileNode(path=Path("/root/sub/file.mkv"))
        inner_folder = FolderNode(
            name="sub", children=[inner_file], collapsed=True
        )
        root = FolderNode(
            name="root", children=[inner_folder], collapsed=False
        )
        model = TreeModel(root=root)

        items = flatten_with_depth(model)

        # Only the folder itself, not its child
        assert len(items) == 1
        assert items[0] == (inner_folder, 0)
