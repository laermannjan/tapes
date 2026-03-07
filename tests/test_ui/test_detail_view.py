"""Tests for detail_render and detail_view modules."""
from __future__ import annotations

from pathlib import Path

import pytest

from tapes.ui.detail_render import (
    display_val,
    get_display_fields,
    is_multi_value,
    render_detail_grid,
    render_detail_header,
)
from tapes.ui.detail_view import DetailView
from tapes.ui.tree_model import FileNode, Source

TEMPLATE = "{title} ({year})/S{season:02d}E{episode:02d}.{ext}"


def _make_node() -> FileNode:
    """Create a FileNode with sources for testing."""
    return FileNode(
        path=Path("/media/Breaking.Bad.S01E01.720p.BluRay.x264.mkv"),
        result={
            "title": "Breaking Bad",
            "year": 2008,
            "season": 1,
            "episode": 1,
        },
        sources=[
            Source(
                name="filename",
                fields={
                    "title": "Breaking Bad",
                    "season": 1,
                    "episode": 1,
                },
                confidence=0.0,
            ),
            Source(
                name="TMDB #1",
                fields={
                    "title": "Breaking Bad",
                    "year": 2008,
                    "season": 1,
                    "episode": 1,
                    "ep_title": "Pilot",
                },
                confidence=0.95,
            ),
        ],
    )


# --- get_display_fields ---


class TestGetDisplayFields:
    def test_extracts_fields_from_template(self) -> None:
        fields = get_display_fields(TEMPLATE)
        assert fields == ["title", "year", "season", "episode"]

    def test_excludes_ext(self) -> None:
        fields = get_display_fields("{title}.{ext}")
        assert "ext" not in fields
        assert fields == ["title"]

    def test_empty_template(self) -> None:
        assert get_display_fields("no_fields_here") == []

    def test_handles_format_specs(self) -> None:
        fields = get_display_fields("{season:02d}")
        assert fields == ["season"]


# --- display_val ---


class TestDisplayVal:
    def test_none_becomes_dot(self) -> None:
        assert display_val(None) == "\u00b7"

    def test_string_passthrough(self) -> None:
        assert display_val("hello") == "hello"

    def test_int_to_string(self) -> None:
        assert display_val(42) == "42"

    def test_empty_string(self) -> None:
        assert display_val("") == ""


# --- render_detail_header ---


class TestRenderDetailHeader:
    def test_shows_filename(self) -> None:
        node = _make_node()
        lines = render_detail_header(node, TEMPLATE)
        assert "Breaking.Bad.S01E01.720p.BluRay.x264.mkv" in lines[0]

    def test_shows_destination(self) -> None:
        node = _make_node()
        lines = render_detail_header(node, TEMPLATE)
        assert "\u2192" in lines[1]
        assert "Breaking Bad (2008)" in lines[1]

    def test_missing_fields_shows_partial(self) -> None:
        node = FileNode(path=Path("test.mkv"), result={})
        lines = render_detail_header(node, TEMPLATE)
        assert "?" in lines[1]


# --- render_detail_grid ---


class TestRenderDetailGrid:
    def test_result_column_values_shown(self) -> None:
        node = _make_node()
        lines = render_detail_grid(node, TEMPLATE)
        # Find the title row
        title_line = [l for l in lines if "title" in l.lower()[:15]]
        assert len(title_line) == 1
        assert "Breaking Bad" in title_line[0]

    def test_source_column_shown_with_confidence(self) -> None:
        node = _make_node()
        # Default source_index=0 shows filename source (confidence=0)
        lines = render_detail_grid(node, TEMPLATE, source_index=1)
        header = lines[0]
        assert "TMDB #1" in header
        assert "95%" in header

    def test_shows_source_indicator(self) -> None:
        node = _make_node()
        lines = render_detail_grid(node, TEMPLATE, source_index=0)
        header = lines[0]
        assert "[1/2]" in header

    def test_second_source_indicator(self) -> None:
        node = _make_node()
        lines = render_detail_grid(node, TEMPLATE, source_index=1)
        header = lines[0]
        assert "[2/2]" in header

    def test_separator_present(self) -> None:
        node = _make_node()
        lines = render_detail_grid(node, TEMPLATE)
        # The vertical separator should appear in each line
        for line in lines:
            assert "\u2503" in line

    def test_none_values_shown_as_dot(self) -> None:
        node = _make_node()
        # filename source (index 0) has no year
        lines = render_detail_grid(node, TEMPLATE, source_index=0)
        year_line = [l for l in lines if l.strip().startswith("year")]
        assert len(year_line) == 1
        assert "\u00b7" in year_line[0]

    def test_only_two_data_columns(self) -> None:
        node = _make_node()
        lines = render_detail_grid(node, TEMPLATE, source_index=0)
        # Each line should have exactly one separator
        for line in lines:
            assert line.count("\u2503") == 1


# --- DetailView cursor ---


class TestDetailViewCursor:
    def _make_view(self) -> DetailView:
        node = _make_node()
        view = DetailView(node, TEMPLATE, TEMPLATE)
        # Simulate on_mount
        view._fields = get_display_fields(TEMPLATE)
        return view

    def test_initial_position(self) -> None:
        view = self._make_view()
        assert view.cursor_row == 0
        assert view.source_index == 0

    def test_move_cursor_row_down(self) -> None:
        view = self._make_view()
        view.move_cursor(row_delta=1)
        assert view.cursor_row == 1

    def test_move_cursor_row_up_clamps_at_header(self) -> None:
        view = self._make_view()
        # Start at row 0, move up twice
        view.move_cursor(row_delta=-1)
        assert view.cursor_row == -1
        view.move_cursor(row_delta=-1)
        assert view.cursor_row == -1  # clamped

    def test_move_cursor_row_down_clamps_at_max(self) -> None:
        view = self._make_view()
        # Fields: title, year, season, episode => max row = 3
        for _ in range(10):
            view.move_cursor(row_delta=1)
        assert view.cursor_row == 3

    def test_cycle_source_right(self) -> None:
        view = self._make_view()
        view.cycle_source(1)
        assert view.source_index == 1

    def test_cycle_source_clamps_at_zero(self) -> None:
        view = self._make_view()
        view.cycle_source(-1)
        assert view.source_index == 0

    def test_cycle_source_clamps_at_max(self) -> None:
        view = self._make_view()
        # 2 sources => max index = 1
        for _ in range(10):
            view.cycle_source(1)
        assert view.source_index == 1

    def test_cycle_source_noop_no_sources(self) -> None:
        node = FileNode(path=Path("/test.mkv"), result={}, sources=[])
        view = DetailView(node, TEMPLATE, TEMPLATE)
        view._fields = get_display_fields(TEMPLATE)
        view.cycle_source(1)
        assert view.source_index == 0

    def test_move_cursor_noop_when_editing(self) -> None:
        view = self._make_view()
        view.editing = True
        view.move_cursor(row_delta=1)
        assert view.cursor_row == 0

    def test_cycle_source_noop_when_editing(self) -> None:
        view = self._make_view()
        view.editing = True
        view.cycle_source(1)
        assert view.source_index == 0


# --- DetailView apply_source_field ---


class TestDetailViewApply:
    def _make_view(self) -> DetailView:
        node = _make_node()
        view = DetailView(node, TEMPLATE, TEMPLATE)
        view._fields = get_display_fields(TEMPLATE)
        return view

    def test_copies_source_value_to_result(self) -> None:
        view = self._make_view()
        # source_index=0 (filename source), cursor on title row
        view.cursor_row = 0
        view.source_index = 0
        view.apply_source_field()
        assert view.node.result["title"] == "Breaking Bad"

    def test_copies_none_source_leaves_result_unchanged(self) -> None:
        view = self._make_view()
        # filename source has no year
        view.cursor_row = 1  # year
        view.source_index = 0  # filename source
        original = view.node.result["year"]
        view.apply_source_field()
        assert view.node.result["year"] == original

    def test_apply_source_all(self) -> None:
        view = self._make_view()
        # Clear result first
        view.node.result = {}
        # Move to header row, source_index=1 (TMDB #1)
        view.cursor_row = -1
        view.source_index = 1
        view.apply_source_field()
        assert view.node.result["title"] == "Breaking Bad"
        assert view.node.result["year"] == 2008
        assert view.node.result["season"] == 1
        assert view.node.result["episode"] == 1

    def test_apply_source_all_skips_none(self) -> None:
        view = self._make_view()
        view.node.result = {"year": 9999}
        # Apply filename source (has no year)
        view.cursor_row = -1
        view.source_index = 0
        view.apply_source_field()
        # year should remain since filename source has no year
        assert view.node.result["year"] == 9999

    def test_enter_on_result_starts_edit_no_sources(self) -> None:
        node = FileNode(path=Path("/test.mkv"), result={"title": "Test"}, sources=[])
        view = DetailView(node, TEMPLATE, TEMPLATE)
        view._fields = get_display_fields(TEMPLATE)
        view.cursor_row = 0
        view.apply_source_field()
        assert view.editing is True

    def test_enter_on_header_no_edit(self) -> None:
        view = self._make_view()
        view.cursor_row = -1
        view.source_index = 0
        # Header row with a source applies all from that source
        view.node.result = {}
        view.apply_source_field()
        # Should have applied fields, not started editing
        assert view.editing is False


# --- DetailView editing ---


class TestDetailViewEditing:
    def _make_view(self) -> DetailView:
        node = _make_node()
        view = DetailView(node, TEMPLATE, TEMPLATE)
        view._fields = get_display_fields(TEMPLATE)
        return view

    def test_start_edit_populates_value(self) -> None:
        view = self._make_view()
        view.cursor_row = 0  # title
        view._start_edit()
        assert view.editing is True
        assert view._edit_value == "Breaking Bad"

    def test_start_edit_none_value(self) -> None:
        view = self._make_view()
        view.node.result.pop("title", None)
        view.cursor_row = 0  # title
        view._start_edit()
        assert view._edit_value == ""

    def test_commit_edit_updates_result(self) -> None:
        view = self._make_view()
        view.cursor_row = 0  # title
        view._start_edit()
        view._edit_value = "Better Call Saul"
        view._commit_edit()
        assert view.node.result["title"] == "Better Call Saul"
        assert view.editing is False

    def test_commit_edit_int_coercion_year(self) -> None:
        view = self._make_view()
        view.cursor_row = 1  # year
        view._start_edit()
        view._edit_value = "2015"
        view._commit_edit()
        assert view.node.result["year"] == 2015
        assert isinstance(view.node.result["year"], int)

    def test_commit_edit_int_coercion_season(self) -> None:
        view = self._make_view()
        view.cursor_row = 2  # season
        view._start_edit()
        view._edit_value = "3"
        view._commit_edit()
        assert view.node.result["season"] == 3
        assert isinstance(view.node.result["season"], int)

    def test_commit_edit_int_coercion_episode(self) -> None:
        view = self._make_view()
        view.cursor_row = 3  # episode
        view._start_edit()
        view._edit_value = "10"
        view._commit_edit()
        assert view.node.result["episode"] == 10

    def test_commit_edit_invalid_int_stays_string(self) -> None:
        view = self._make_view()
        view.cursor_row = 1  # year
        view._start_edit()
        view._edit_value = "not_a_number"
        view._commit_edit()
        assert view.node.result["year"] == "not_a_number"

    def test_cancel_edit_discards_changes(self) -> None:
        view = self._make_view()
        view.cursor_row = 0
        view._start_edit()
        view._edit_value = "Something Else"
        view._cancel_edit()
        assert view.editing is False
        assert view.node.result["title"] == "Breaking Bad"


# --- DetailView.set_node ---


class TestDetailViewSetNode:
    def test_set_node_resets_cursor(self) -> None:
        node = _make_node()
        view = DetailView(node, TEMPLATE, TEMPLATE)
        view._fields = get_display_fields(TEMPLATE)
        view.cursor_row = 2
        view.source_index = 1
        view.editing = True

        new_node = FileNode(
            path=Path("/media/other.mkv"),
            result={"title": "Other"},
        )
        view.set_node(new_node)
        assert view.node is new_node
        assert view.cursor_row == 0
        assert view.source_index == 0
        assert view.editing is False

    def test_set_node_updates_fields(self) -> None:
        node = _make_node()
        view = DetailView(node, TEMPLATE, TEMPLATE)
        view._fields = []
        view.set_node(node)
        assert len(view._fields) == 4  # title, year, season, episode


# --- DetailView.apply_source_all_clear ---


class TestDetailViewApplyAllClear:
    def _make_view(self) -> DetailView:
        node = _make_node()
        view = DetailView(node, TEMPLATE, TEMPLATE)
        view._fields = get_display_fields(TEMPLATE)
        return view

    def test_applies_all_and_clears_empties(self) -> None:
        view = self._make_view()
        # filename source has title, season, episode but NOT year
        view.node.result = {
            "title": "Old",
            "year": 9999,
            "season": 99,
            "episode": 99,
        }
        view.cursor_row = -1
        view.source_index = 0  # filename source
        view.apply_source_all_clear()
        assert view.node.result["title"] == "Breaking Bad"
        assert view.node.result["season"] == 1
        assert view.node.result["episode"] == 1
        # year was cleared because filename source has no year
        assert "year" not in view.node.result

    def test_noop_on_field_row(self) -> None:
        view = self._make_view()
        view.cursor_row = 0  # not header
        view.source_index = 0
        original = dict(view.node.result)
        view.apply_source_all_clear()
        assert view.node.result == original


# --- Multi-file detail view (M15) ---


class TestMultiFileDetail:
    def _make_multi_view(self) -> tuple[DetailView, FileNode, FileNode]:
        node1 = FileNode(
            path=Path("/media/file1.mkv"),
            result={"title": "Breaking Bad", "year": 2008, "season": 1, "episode": 1},
            sources=[
                Source(
                    name="TMDB #1",
                    fields={"title": "Breaking Bad", "year": 2008},
                    confidence=0.75,
                ),
            ],
        )
        node2 = FileNode(
            path=Path("/media/file2.mkv"),
            result={"title": "Breaking Bad", "year": 2008, "season": 1, "episode": 2},
            sources=[
                Source(
                    name="TMDB #1",
                    fields={"title": "Breaking Bad", "year": 2008},
                    confidence=0.75,
                ),
            ],
        )
        view = DetailView(node1, TEMPLATE, TEMPLATE)
        view._fields = get_display_fields(TEMPLATE)
        view.set_nodes([node1, node2])
        return view, node1, node2

    def test_is_multi(self) -> None:
        view, _, _ = self._make_multi_view()
        assert view.is_multi is True

    def test_single_node_not_multi(self) -> None:
        view = DetailView(_make_node(), TEMPLATE, TEMPLATE)
        view._fields = get_display_fields(TEMPLATE)
        assert view.is_multi is False

    def test_shows_various_for_differing_values(self) -> None:
        view, _, _ = self._make_multi_view()
        shared = view._shared_result()
        # title and year are same, season is same, episode differs
        assert shared["title"] == "Breaking Bad"
        assert shared["year"] == 2008
        assert shared["season"] == 1
        assert shared["episode"] == "(2 values)"

    def test_shows_shared_values(self) -> None:
        view, _, _ = self._make_multi_view()
        shared = view._shared_result()
        assert shared["title"] == "Breaking Bad"
        assert shared["year"] == 2008

    def test_header_shows_count(self) -> None:
        view, _, _ = self._make_multi_view()
        header = view._render_multi_header()
        assert "2 files selected" in header[0].plain

    def test_header_is_bold_white(self) -> None:
        view, _, _ = self._make_multi_view()
        header = view._render_multi_header()
        assert header[0].style == "bold white"

    def test_header_shows_various_destinations(self) -> None:
        view, _, _ = self._make_multi_view()
        header = view._render_multi_header()
        assert "(various destinations)" in header[1].plain

    def test_editing_applies_to_all_nodes(self) -> None:
        view, node1, node2 = self._make_multi_view()
        view.cursor_row = 0  # title
        view._start_edit()
        view._edit_value = "Better Call Saul"
        view._commit_edit()
        assert node1.result["title"] == "Better Call Saul"
        assert node2.result["title"] == "Better Call Saul"

    def test_applying_source_applies_to_all_nodes(self) -> None:
        view, node1, node2 = self._make_multi_view()
        # Clear years to test applying source
        node1.result.pop("year", None)
        node2.result.pop("year", None)
        # Move to year field, source_index=0 (TMDB source)
        view.cursor_row = 1  # year
        view.source_index = 0  # TMDB source (only one source per node)
        view.apply_source_field()
        assert node1.result["year"] == 2008
        assert node2.result["year"] == 2008

    def test_apply_source_all_applies_to_all_nodes(self) -> None:
        view, node1, node2 = self._make_multi_view()
        # Clear results
        node1.result = {}
        node2.result = {}
        # Apply all from TMDB source (header row)
        view.cursor_row = -1
        view.source_index = 0
        view.apply_source_field()
        assert node1.result["title"] == "Breaking Bad"
        assert node2.result["title"] == "Breaking Bad"
        assert node1.result["year"] == 2008
        assert node2.result["year"] == 2008

    def test_set_nodes_resets_cursor(self) -> None:
        view, _, _ = self._make_multi_view()
        view.cursor_row = 2
        view.source_index = 1
        new_node = FileNode(path=Path("/x.mkv"), result={"title": "X"})
        view.set_nodes([new_node])
        assert view.cursor_row == 0
        assert view.source_index == 0
        assert not view.is_multi

    def test_edit_various_field_starts_empty(self) -> None:
        view, _, _ = self._make_multi_view()
        # episode is (2 values) -- multi-value marker
        view.cursor_row = 3  # episode
        view._start_edit()
        assert view._edit_value == ""

    def test_notify_before_mutate_sends_all_nodes(self) -> None:
        view, node1, node2 = self._make_multi_view()
        notified: list[list[FileNode]] = []
        view.on_before_mutate = lambda nodes: notified.append(nodes)
        view.cursor_row = 0
        view.source_index = 0
        view.apply_source_field()
        assert len(notified) == 1
        assert node1 in notified[0]
        assert node2 in notified[0]

    def test_apply_all_clear_applies_to_all_nodes(self) -> None:
        view, node1, node2 = self._make_multi_view()
        # Set up result with extra fields
        node1.result = {"title": "Old", "year": 9999, "season": 99, "episode": 99}
        node2.result = {"title": "Old", "year": 9999, "season": 99, "episode": 99}
        # TMDB source only has title and year
        view.cursor_row = -1
        view.source_index = 0
        view.apply_source_all_clear()
        assert node1.result["title"] == "Breaking Bad"
        assert node2.result["title"] == "Breaking Bad"
        assert node1.result["year"] == 2008
        assert node2.result["year"] == 2008
        # season and episode not in TMDB source, should be cleared
        assert "season" not in node1.result
        assert "season" not in node2.result

    def test_multi_value_count_reflects_distinct_values(self) -> None:
        node1 = FileNode(
            path=Path("/a.mkv"),
            result={"title": "A", "year": 2020},
        )
        node2 = FileNode(
            path=Path("/b.mkv"),
            result={"title": "B", "year": 2020},
        )
        node3 = FileNode(
            path=Path("/c.mkv"),
            result={"title": "C", "year": 2020},
        )
        view = DetailView(node1, TEMPLATE, TEMPLATE)
        view._fields = get_display_fields(TEMPLATE)
        view.set_nodes([node1, node2, node3])
        shared = view._shared_result()
        assert shared["title"] == "(3 values)"
        assert shared["year"] == 2020


# --- is_multi_value ---


class TestIsMultiValue:
    def test_multi_value_marker(self) -> None:
        assert is_multi_value("(2 values)") is True
        assert is_multi_value("(10 values)") is True

    def test_not_multi_value(self) -> None:
        assert is_multi_value("Breaking Bad") is False
        assert is_multi_value(None) is False
        assert is_multi_value(42) is False
        assert is_multi_value("") is False

    def test_various_is_not_multi_value(self) -> None:
        assert is_multi_value("(various)") is False


# --- Async integration: tree -> detail -> back ---


MOVIE_TEMPLATE = "{title} ({year})/{title} ({year}).{ext}"
TV_TEMPLATE = (
    "{title} ({year})/Season {season:02d}/"
    "{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"
)


class TestDetailViewTemplateSelection:
    """Tests for media_type-based template selection in DetailView."""

    def test_movie_node_uses_movie_template_fields(self) -> None:
        node = FileNode(
            path=Path("/movies/Inception.mkv"),
            result={"title": "Inception", "year": 2010, "media_type": "movie"},
        )
        view = DetailView(
            node, MOVIE_TEMPLATE, TV_TEMPLATE,
        )
        view._fields = get_display_fields(view._active_template())
        # Movie template has title, year
        assert "title" in view._fields
        assert "year" in view._fields
        assert "season" not in view._fields
        assert "episode" not in view._fields

    def test_episode_node_uses_tv_template_fields(self) -> None:
        node = FileNode(
            path=Path("/tv/show.s01e01.mkv"),
            result={
                "title": "Breaking Bad",
                "year": 2008,
                "season": 1,
                "episode": 1,
                "episode_title": "Pilot",
                "media_type": "episode",
            },
        )
        view = DetailView(
            node, MOVIE_TEMPLATE, TV_TEMPLATE,
        )
        view._fields = get_display_fields(view._active_template())
        assert "season" in view._fields
        assert "episode" in view._fields
        assert "episode_title" in view._fields

    def test_set_node_updates_fields_for_new_media_type(self) -> None:
        movie_node = FileNode(
            path=Path("/movies/Inception.mkv"),
            result={"title": "Inception", "year": 2010, "media_type": "movie"},
        )
        tv_node = FileNode(
            path=Path("/tv/show.s01e01.mkv"),
            result={
                "title": "Show",
                "year": 2020,
                "season": 1,
                "episode": 1,
                "episode_title": "Pilot",
                "media_type": "episode",
            },
        )
        view = DetailView(
            movie_node, MOVIE_TEMPLATE, TV_TEMPLATE,
        )
        view._fields = get_display_fields(view._active_template())
        assert "season" not in view._fields

        view.set_node(tv_node)
        assert "season" in view._fields
        assert "episode" in view._fields

    def test_template_selection_uses_media_type(self) -> None:
        node = FileNode(
            path=Path("/tv/show.mkv"),
            result={"title": "Show", "media_type": "episode"},
        )
        view = DetailView(node, MOVIE_TEMPLATE, TV_TEMPLATE)
        assert view._active_template() == TV_TEMPLATE


try:
    from textual.pilot import Pilot  # noqa: F401

    HAS_PILOT = True
except ImportError:
    HAS_PILOT = False


@pytest.mark.skipif(not HAS_PILOT, reason="textual pilot not available")
class TestTreeDetailIntegration:
    @pytest.mark.asyncio()
    async def test_enter_on_file_shows_detail_esc_returns(self) -> None:
        from tapes.ui.tree_app import TreeApp
        from tapes.ui.tree_model import FolderNode, TreeModel
        from tapes.ui.tree_view import TreeView

        node = _make_node()
        root = FolderNode(name="root", children=[node])
        model = TreeModel(root=root)
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            dv = app.query_one(DetailView)

            # Initially tree is not compressed, detail is not expanded
            assert "compressed" not in tv.classes
            assert "expanded" not in dv.classes

            # Enter on the file node opens detail
            await pilot.press("enter")
            assert app._in_detail is True
            assert "compressed" in tv.classes
            assert "expanded" in dv.classes
            assert dv.node is node

            # Navigate in detail view
            await pilot.press("j")
            assert dv.cursor_row == 1
            await pilot.press("l")
            assert dv.source_index == 1

            # Escape returns to tree
            await pilot.press("escape")
            assert app._in_detail is False
            assert "compressed" not in tv.classes
            assert "expanded" not in dv.classes


@pytest.mark.skipif(not HAS_PILOT, reason="textual pilot not available")
class TestMultiFileDetailIntegration:
    @pytest.mark.asyncio()
    async def test_enter_in_range_opens_multi_detail(self) -> None:
        from tapes.ui.tree_app import TreeApp
        from tapes.ui.tree_model import FolderNode, TreeModel
        from tapes.ui.tree_view import TreeView

        node1 = FileNode(
            path=Path("/media/file1.mkv"),
            result={"title": "Show", "year": 2020, "season": 1, "episode": 1},
            sources=[
                Source(name="TMDB", fields={"title": "Show"}, confidence=0.9),
            ],
        )
        node2 = FileNode(
            path=Path("/media/file2.mkv"),
            result={"title": "Show", "year": 2020, "season": 1, "episode": 2},
            sources=[
                Source(name="TMDB", fields={"title": "Show"}, confidence=0.9),
            ],
        )
        root = FolderNode(name="root", children=[node1, node2])
        model = TreeModel(root=root)
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            dv = app.query_one(DetailView)

            # Start range and select both files
            await pilot.press("v")
            await pilot.press("j")
            # Enter opens multi-file detail
            await pilot.press("enter")
            assert app._in_detail is True
            assert dv.is_multi is True
            assert len(dv._file_nodes) == 2

            # Escape returns to tree
            await pilot.press("escape")
            assert app._in_detail is False
