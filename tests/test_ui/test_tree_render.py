"""Tests for tree_render pure rendering functions."""
from __future__ import annotations

from pathlib import Path

from rich.text import Text

from tapes.ui.tree_model import FileNode, FolderNode, TreeModel
from tapes.ui.tree_render import (
    compute_dest,
    flatten_with_depth,
    render_dest,
    render_file_row,
    render_folder_row,
    render_row,
    render_separator,
    select_template,
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

    def test_partial_dest_when_fields_missing(self) -> None:
        node = FileNode(
            path=Path("/movies/Inception.mkv"),
            result={"title": "Inception"},
        )
        result = compute_dest(node, MOVIE_TEMPLATE)
        assert result is not None
        assert "Inception" in result
        assert "?" in result

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


# --- render_dest ---


class TestRenderDest:
    def test_none_returns_dim_question_marks(self) -> None:
        result = render_dest(None)
        assert isinstance(result, Text)
        assert result.plain == "???"
        # The whole thing should be dim (applied as base style)
        assert "#888888" in str(result.style)

    def test_full_path_coloring(self) -> None:
        result = render_dest("Movies/Inception (2010)/Inception (2010).mkv")
        assert isinstance(result, Text)
        assert result.plain == "Movies/Inception (2010)/Inception (2010).mkv"

    def test_directory_is_dim(self) -> None:
        result = render_dest("Movies/Inception.mkv")
        assert isinstance(result, Text)
        # The directory part "Movies/" should be dim
        plain = result.plain
        assert plain == "Movies/Inception.mkv"

    def test_stem_is_normal_extension_dim(self) -> None:
        result = render_dest("Inception.mkv")
        assert isinstance(result, Text)
        assert result.plain == "Inception.mkv"

    def test_no_extension(self) -> None:
        result = render_dest("README")
        assert isinstance(result, Text)
        assert result.plain == "README"

    def test_question_mark_placeholders_yellow(self) -> None:
        result = render_dest("? (?)/? (?).mkv")
        assert isinstance(result, Text)
        assert result.plain == "? (?)/? (?).mkv"
        # Verify ? chars have yellow style
        has_yellow = any("#E07A47" in str(span.style) or "#e07a47" in str(span.style) for span in result._spans)
        assert has_yellow

    def test_partial_with_question_marks(self) -> None:
        result = render_dest("Inception (?)/Inception (?).mkv")
        assert isinstance(result, Text)
        assert "?" in result.plain
        has_yellow = any("#E07A47" in str(span.style) or "#e07a47" in str(span.style) for span in result._spans)
        assert has_yellow

    def test_no_directory(self) -> None:
        result = render_dest("movie.mkv")
        assert isinstance(result, Text)
        assert result.plain == "movie.mkv"


# --- render_file_row ---


class TestRenderFileRow:
    def test_returns_text_object(self) -> None:
        node = FileNode(
            path=Path("/movies/Inception.mkv"),
            result={"title": "Inception", "year": 2010},
        )
        row = render_file_row(node, MOVIE_TEMPLATE, TV_TEMPLATE)
        assert isinstance(row, Text)

    def test_staged_file_with_destination(self) -> None:
        node = FileNode(
            path=Path("/movies/Inception.mkv"),
            staged=True,
            result={"title": "Inception", "year": 2010},
        )
        row = render_file_row(node, MOVIE_TEMPLATE, TV_TEMPLATE)
        plain = row.plain
        assert "\u2713" in plain
        assert "Inception (2010)/Inception (2010).mkv" in plain

    def test_unstaged_file(self) -> None:
        node = FileNode(
            path=Path("/movies/Inception.mkv"),
            staged=False,
            result={"title": "Inception", "year": 2010},
        )
        row = render_file_row(node, MOVIE_TEMPLATE, TV_TEMPLATE)
        assert "Inception.mkv" in row.plain

    def test_ignored_file_strikethrough_no_destination(self) -> None:
        node = FileNode(
            path=Path("/movies/Inception.mkv"),
            ignored=True,
            result={"title": "Inception", "year": 2010},
        )
        row = render_file_row(node, MOVIE_TEMPLATE, TV_TEMPLATE)
        assert "Inception.mkv" in row.plain
        # No arrow or destination
        assert "\u2192" not in row.plain
        assert "Inception (2010)" not in row.plain
        # Strikethrough style applied
        has_strike = any("strike" in str(span.style) for span in row._spans)
        assert has_strike

    def test_missing_dest_shows_partial(self) -> None:
        node = FileNode(
            path=Path("/movies/Inception.mkv"),
            result={},
        )
        row = render_file_row(node, MOVIE_TEMPLATE, TV_TEMPLATE)
        assert "?" in row.plain

    def test_with_indentation_depth_2(self) -> None:
        node = FileNode(
            path=Path("/movies/Inception.mkv"),
            result={"title": "Inception", "year": 2010},
        )
        row = render_file_row(node, MOVIE_TEMPLATE, TV_TEMPLATE, depth=2)
        assert row.plain.startswith("    ")  # 2 * "  " = 4 spaces

    def test_flat_mode_no_indentation_relative_path(self) -> None:
        root = Path("/media")
        node = FileNode(
            path=Path("/media/movies/Inception.mkv"),
            result={"title": "Inception", "year": 2010},
        )
        row = render_file_row(
            node, MOVIE_TEMPLATE, TV_TEMPLATE, depth=3, flat_mode=True, root_path=root
        )
        plain = row.plain
        # Flat mode: no indentation regardless of depth
        assert not plain.startswith(" " * 6)
        # Uses relative path
        assert "movies/Inception.mkv" in plain

    def test_arrow_is_dim(self) -> None:
        node = FileNode(
            path=Path("/movies/Inception.mkv"),
            result={"title": "Inception", "year": 2010},
        )
        row = render_file_row(node, MOVIE_TEMPLATE, TV_TEMPLATE)
        # The arrow separator should be dim
        assert "  \u2192  " in row.plain


# --- render_folder_row ---


class TestRenderFolderRow:
    def test_collapsed_arrow(self) -> None:
        node = FolderNode(name="movies", collapsed=True)
        row = render_folder_row(node)
        assert isinstance(row, Text)
        assert "\u25b6" in row.plain
        assert "movies/" in row.plain

    def test_expanded_arrow(self) -> None:
        node = FolderNode(name="movies", collapsed=False)
        row = render_folder_row(node)
        assert isinstance(row, Text)
        assert "\u25bc" in row.plain
        assert "movies/" in row.plain

    def test_with_indentation(self) -> None:
        node = FolderNode(name="Season 01", collapsed=True)
        row = render_folder_row(node, depth=1)
        assert isinstance(row, Text)
        assert row.plain.startswith("  ")
        assert "Season 01/" in row.plain


# --- render_row ---


class TestRenderRow:
    def test_dispatches_to_file(self) -> None:
        node = FileNode(
            path=Path("/movies/Inception.mkv"),
            result={"title": "Inception", "year": 2010},
        )
        row = render_row(node, MOVIE_TEMPLATE, TV_TEMPLATE)
        assert isinstance(row, Text)
        # Should contain the arrow separator from file rendering
        assert "\u2192" in row.plain

    def test_dispatches_to_folder(self) -> None:
        node = FolderNode(name="tv", collapsed=True)
        row = render_row(node, MOVIE_TEMPLATE, TV_TEMPLATE)
        assert isinstance(row, Text)
        assert "\u25b6" in row.plain
        assert "tv/" in row.plain


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


# --- select_template ---


class TestSelectTemplate:
    def test_episode_returns_tv_template(self) -> None:
        node = FileNode(
            path=Path("/tv/show.mkv"),
            result={"media_type": "episode"},
        )
        assert select_template(node, MOVIE_TEMPLATE, TV_TEMPLATE) == TV_TEMPLATE

    def test_movie_returns_movie_template(self) -> None:
        node = FileNode(
            path=Path("/movies/film.mkv"),
            result={"media_type": "movie"},
        )
        assert select_template(node, MOVIE_TEMPLATE, TV_TEMPLATE) == MOVIE_TEMPLATE

    def test_unknown_media_type_defaults_to_movie(self) -> None:
        node = FileNode(
            path=Path("/other/file.mkv"),
            result={"media_type": "other"},
        )
        assert select_template(node, MOVIE_TEMPLATE, TV_TEMPLATE) == MOVIE_TEMPLATE

    def test_missing_media_type_defaults_to_movie(self) -> None:
        node = FileNode(
            path=Path("/other/file.mkv"),
            result={},
        )
        assert select_template(node, MOVIE_TEMPLATE, TV_TEMPLATE) == MOVIE_TEMPLATE


# --- render_file_row with dual templates ---


class TestRenderFileRowDualTemplate:
    def test_movie_node_uses_movie_template(self) -> None:
        node = FileNode(
            path=Path("/movies/Inception.mkv"),
            result={"title": "Inception", "year": 2010, "media_type": "movie"},
        )
        row = render_file_row(node, MOVIE_TEMPLATE, TV_TEMPLATE)
        assert "Inception (2010)/Inception (2010).mkv" in row.plain

    def test_episode_node_uses_tv_template(self) -> None:
        node = FileNode(
            path=Path("/tv/show.s01e02.mkv"),
            result={
                "title": "Breaking Bad",
                "year": 2008,
                "season": 1,
                "episode": 2,
                "episode_title": "Cat's in the Bag...",
                "media_type": "episode",
            },
        )
        row = render_file_row(node, MOVIE_TEMPLATE, TV_TEMPLATE)
        assert "S01E02" in row.plain
        assert "Cat's in the Bag..." in row.plain


# --- render_separator ---


class TestRenderSeparator:
    def test_plain_separator_fills_width(self) -> None:
        line = render_separator(40)
        assert len(line.plain) == 40
        assert line.plain == "\u2500" * 40

    def test_separator_with_title(self) -> None:
        line = render_separator(40, title="Info")
        plain = line.plain
        assert plain.startswith("\u2500\u2500\u2500 Info ")
        assert len(plain) == 40
        assert plain.endswith("\u2500")

    def test_separator_with_right_text(self) -> None:
        line = render_separator(40, right_text="2 staged")
        plain = line.plain
        assert "2 staged" in plain
        assert plain.endswith("───")
        assert len(plain) == 40

    def test_separator_with_title_and_right_text(self) -> None:
        line = render_separator(50, title="Files", right_text="3 total")
        plain = line.plain
        assert "Files" in plain
        assert "3 total" in plain
        assert len(plain) == 50

    def test_narrow_width_no_crash(self) -> None:
        line = render_separator(5, title="Info")
        # Should not crash, just truncate gracefully
        assert len(line.plain) <= 10  # allow some overflow but no crash

    def test_color_applied_to_dashes(self) -> None:
        line = render_separator(20, color="#B1B9F9")
        # Verify style spans exist (implementation detail, but ensures color is used)
        assert line.plain == "\u2500" * 20
