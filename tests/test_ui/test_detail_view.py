"""Tests for detail_render and detail_view modules."""
from __future__ import annotations

from pathlib import Path

import pytest

from tapes.ui.detail_render import (
    display_val,
    get_display_fields,
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

    def test_missing_fields_shows_questionmarks(self) -> None:
        node = FileNode(path=Path("test.mkv"), result={})
        lines = render_detail_header(node, TEMPLATE)
        assert "???" in lines[1]


# --- render_detail_grid ---


class TestRenderDetailGrid:
    def test_result_column_values_shown(self) -> None:
        node = _make_node()
        lines = render_detail_grid(node, TEMPLATE)
        # Find the title row
        title_line = [l for l in lines if "title" in l.lower()[:15]]
        assert len(title_line) == 1
        assert "Breaking Bad" in title_line[0]

    def test_source_columns_shown_with_confidence(self) -> None:
        node = _make_node()
        lines = render_detail_grid(node, TEMPLATE)
        header = lines[0]
        assert "TMDB #1" in header
        assert "95%" in header

    def test_separator_present(self) -> None:
        node = _make_node()
        lines = render_detail_grid(node, TEMPLATE)
        # The vertical separator should appear in each line
        for line in lines:
            assert "\u2503" in line

    def test_none_values_shown_as_dot(self) -> None:
        node = _make_node()
        lines = render_detail_grid(node, TEMPLATE)
        # filename source has no year, so the year row should have a dot
        year_line = [l for l in lines if l.strip().startswith("year")]
        assert len(year_line) == 1
        assert "\u00b7" in year_line[0]


# --- DetailView cursor ---


class TestDetailViewCursor:
    def _make_view(self) -> DetailView:
        node = _make_node()
        view = DetailView(node, TEMPLATE)
        # Simulate on_mount
        view._fields = get_display_fields(TEMPLATE)
        return view

    def test_initial_position(self) -> None:
        view = self._make_view()
        assert view.cursor_row == 0
        assert view.cursor_col == 0

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

    def test_move_cursor_col_right(self) -> None:
        view = self._make_view()
        view.move_cursor(col_delta=1)
        assert view.cursor_col == 1

    def test_move_cursor_col_clamps_at_zero(self) -> None:
        view = self._make_view()
        view.move_cursor(col_delta=-1)
        assert view.cursor_col == 0

    def test_move_cursor_col_clamps_at_max(self) -> None:
        view = self._make_view()
        # 2 sources => max col = 2
        for _ in range(10):
            view.move_cursor(col_delta=1)
        assert view.cursor_col == 2

    def test_move_cursor_noop_when_editing(self) -> None:
        view = self._make_view()
        view.editing = True
        view.move_cursor(row_delta=1, col_delta=1)
        assert view.cursor_row == 0
        assert view.cursor_col == 0


# --- DetailView apply_source_field ---


class TestDetailViewApply:
    def _make_view(self) -> DetailView:
        node = _make_node()
        view = DetailView(node, TEMPLATE)
        view._fields = get_display_fields(TEMPLATE)
        return view

    def test_copies_source_value_to_result(self) -> None:
        view = self._make_view()
        # Move to row 0 (title), col 1 (filename source)
        view.cursor_row = 0
        view.cursor_col = 1
        view.apply_source_field()
        assert view.node.result["title"] == "Breaking Bad"

    def test_copies_none_source_leaves_result_unchanged(self) -> None:
        view = self._make_view()
        # filename source has no year
        view.cursor_row = 1  # year
        view.cursor_col = 1  # filename source
        original = view.node.result["year"]
        view.apply_source_field()
        assert view.node.result["year"] == original

    def test_apply_source_all(self) -> None:
        view = self._make_view()
        # Clear result first
        view.node.result = {}
        # Move to header row, col 2 (TMDB #1)
        view.cursor_row = -1
        view.cursor_col = 2
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
        view.cursor_col = 1
        view.apply_source_field()
        # year should remain since filename source has no year
        assert view.node.result["year"] == 9999

    def test_enter_on_result_starts_edit(self) -> None:
        view = self._make_view()
        view.cursor_row = 0
        view.cursor_col = 0
        view.apply_source_field()
        assert view.editing is True

    def test_enter_on_result_header_no_edit(self) -> None:
        view = self._make_view()
        view.cursor_row = -1
        view.cursor_col = 0
        view.apply_source_field()
        # _start_edit returns early for row < 0
        assert view.editing is False


# --- DetailView editing ---


class TestDetailViewEditing:
    def _make_view(self) -> DetailView:
        node = _make_node()
        view = DetailView(node, TEMPLATE)
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
        view = DetailView(node, TEMPLATE)
        view._fields = get_display_fields(TEMPLATE)
        view.cursor_row = 2
        view.cursor_col = 1
        view.editing = True

        new_node = FileNode(
            path=Path("/media/other.mkv"),
            result={"title": "Other"},
        )
        view.set_node(new_node)
        assert view.node is new_node
        assert view.cursor_row == 0
        assert view.cursor_col == 0
        assert view.editing is False

    def test_set_node_updates_fields(self) -> None:
        node = _make_node()
        view = DetailView(node, TEMPLATE)
        view._fields = []
        view.set_node(node)
        assert len(view._fields) == 4  # title, year, season, episode


# --- DetailView.apply_source_all_clear ---


class TestDetailViewApplyAllClear:
    def _make_view(self) -> DetailView:
        node = _make_node()
        view = DetailView(node, TEMPLATE)
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
        view.cursor_col = 1  # filename source
        view.apply_source_all_clear()
        assert view.node.result["title"] == "Breaking Bad"
        assert view.node.result["season"] == 1
        assert view.node.result["episode"] == 1
        # year was cleared because filename source has no year
        assert "year" not in view.node.result

    def test_noop_on_result_column(self) -> None:
        view = self._make_view()
        view.cursor_row = -1
        view.cursor_col = 0  # result column
        original = dict(view.node.result)
        view.apply_source_all_clear()
        assert view.node.result == original

    def test_noop_on_field_row(self) -> None:
        view = self._make_view()
        view.cursor_row = 0  # not header
        view.cursor_col = 1
        original = dict(view.node.result)
        view.apply_source_all_clear()
        assert view.node.result == original


# --- Async integration: tree -> detail -> back ---


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
        app = TreeApp(model=model, template=TEMPLATE)

        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            dv = app.query_one(DetailView)

            # Initially tree is visible, detail is hidden
            assert tv.display is True
            assert dv.display is False

            # Enter on the file node opens detail
            await pilot.press("enter")
            assert app._in_detail is True
            assert tv.display is False
            assert dv.display is True
            assert dv.node is node

            # Navigate in detail view
            await pilot.press("j")
            assert dv.cursor_row == 1
            await pilot.press("l")
            assert dv.cursor_col == 1

            # Escape returns to tree
            await pilot.press("escape")
            assert app._in_detail is False
            assert tv.display is True
            assert dv.display is False
