"""Tests for detail_render and detail_view modules."""

from __future__ import annotations

from pathlib import Path

import pytest

from tapes.tree_model import FileNode, Source
from tapes.ui.detail_render import (
    display_val,
    get_display_fields,
    is_multi_value,
)
from tapes.ui.detail_view import DetailView
from tapes.ui.tree_app import AppMode

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
        assert fields == ["tmdb_id", "title", "year", "season", "episode"]

    def test_tmdb_id_always_first(self) -> None:
        fields = get_display_fields("{title}/{year}")
        assert fields[0] == "tmdb_id"

    def test_tmdb_id_not_duplicated_if_in_template(self) -> None:
        fields = get_display_fields("{tmdb_id}/{title}")
        assert fields.count("tmdb_id") == 1

    def test_excludes_ext(self) -> None:
        fields = get_display_fields("{title}.{ext}")
        assert "ext" not in fields
        assert fields == ["tmdb_id", "title"]

    def test_empty_template(self) -> None:
        assert get_display_fields("no_fields_here") == ["tmdb_id"]

    def test_handles_format_specs(self) -> None:
        fields = get_display_fields("{season:02d}")
        assert fields == ["tmdb_id", "season"]


# --- display_val ---


class TestDisplayVal:
    def test_none_becomes_question_mark(self) -> None:
        assert display_val(None) == "?"

    def test_string_passthrough(self) -> None:
        assert display_val("hello") == "hello"

    def test_int_to_string(self) -> None:
        assert display_val(42) == "42"

    def test_empty_string(self) -> None:
        assert display_val("") == ""


# --- DetailView cursor ---


class TestDetailViewCursor:
    def _make_view(self) -> DetailView:
        node = _make_node()
        view = DetailView(node, TEMPLATE, TEMPLATE)
        # Simulate on_mount
        view.fields = get_display_fields(TEMPLATE)
        return view

    def test_initial_position(self) -> None:
        view = self._make_view()
        assert view.cursor_row == 0
        assert view.source_index == 0

    def test_move_cursor_row_down(self) -> None:
        view = self._make_view()
        view.move_cursor(row_delta=1)
        assert view.cursor_row == 1

    def test_move_cursor_row_up_clamps_at_zero(self) -> None:
        view = self._make_view()
        # Start at row 0, move up twice
        view.move_cursor(row_delta=-1)
        assert view.cursor_row == 0  # clamped at 0
        view.move_cursor(row_delta=-1)
        assert view.cursor_row == 0

    def test_move_cursor_row_down_clamps_at_max(self) -> None:
        view = self._make_view()
        # Fields: tmdb_id, title, year, season, episode => max row = 4
        for _ in range(10):
            view.move_cursor(row_delta=1)
        assert view.cursor_row == 4

    def test_cycle_source_right(self) -> None:
        view = self._make_view()
        view.cycle_source(1)
        assert view.source_index == 1

    def test_cycle_source_wraps_at_zero(self) -> None:
        view = self._make_view()
        view.cycle_source(-1)
        assert view.source_index == 1  # wraps to last

    def test_cycle_source_wraps_at_max(self) -> None:
        view = self._make_view()
        # 2 sources => wraps around
        view.cycle_source(1)
        assert view.source_index == 1
        view.cycle_source(1)
        assert view.source_index == 0  # wraps to first

    def test_cycle_source_noop_no_sources(self) -> None:
        node = FileNode(path=Path("/test.mkv"), result={}, sources=[])
        view = DetailView(node, TEMPLATE, TEMPLATE)
        view.fields = get_display_fields(TEMPLATE)
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


# --- DetailView editing ---


class TestDetailViewEditing:
    def _make_view(self) -> DetailView:
        node = _make_node()
        view = DetailView(node, TEMPLATE, TEMPLATE)
        view.fields = get_display_fields(TEMPLATE)
        return view

    def test_start_edit_populates_value(self) -> None:
        view = self._make_view()
        # tmdb_id is now at index 0; title is at index 1
        view.cursor_row = 1  # title
        view.start_edit()
        assert view.editing is True
        assert view.edit_value == "Breaking Bad"

    def test_start_edit_none_value(self) -> None:
        view = self._make_view()
        view.node.result.pop("title", None)
        view.cursor_row = 1  # title
        view.start_edit()
        assert view.edit_value == ""

    def test_commit_edit_updates_result(self) -> None:
        view = self._make_view()
        view.cursor_row = 1  # title (tmdb_id is at 0)
        view.start_edit()
        view.edit_value = "Better Call Saul"
        view.commit_edit()
        assert view.node.result["title"] == "Better Call Saul"
        assert view.editing is False

    def test_commit_edit_int_coercion_year(self) -> None:
        view = self._make_view()
        view.cursor_row = 2  # year (tmdb_id is at 0)
        view.start_edit()
        view.edit_value = "2015"
        view.commit_edit()
        assert view.node.result["year"] == 2015
        assert isinstance(view.node.result["year"], int)

    def test_commit_edit_int_coercion_season(self) -> None:
        view = self._make_view()
        view.cursor_row = 3  # season (tmdb_id is at 0)
        view.start_edit()
        view.edit_value = "3"
        view.commit_edit()
        assert view.node.result["season"] == 3
        assert isinstance(view.node.result["season"], int)

    def test_commit_edit_int_coercion_episode(self) -> None:
        view = self._make_view()
        view.cursor_row = 4  # episode (tmdb_id is at 0)
        view.start_edit()
        view.edit_value = "10"
        view.commit_edit()
        assert view.node.result["episode"] == 10

    def test_commit_edit_invalid_int_stays_string(self) -> None:
        view = self._make_view()
        view.cursor_row = 2  # year (tmdb_id is at 0)
        view.start_edit()
        view.edit_value = "not_a_number"
        view.commit_edit()
        assert view.node.result["year"] == "not_a_number"

    def test_cancel_edit_discards_changes(self) -> None:
        view = self._make_view()
        view.cursor_row = 1  # title (tmdb_id is at 0)
        view.start_edit()
        view.edit_value = "Something Else"
        view.cancel_edit()
        assert view.editing is False
        assert view.node.result["title"] == "Breaking Bad"


# --- DetailView.set_node ---


class TestDetailViewSetNode:
    def test_set_node_resets_cursor(self) -> None:
        node = _make_node()
        view = DetailView(node, TEMPLATE, TEMPLATE)
        view.fields = get_display_fields(TEMPLATE)
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
        view.fields = []
        view.set_node(node)
        assert len(view.fields) == 5  # tmdb_id, title, year, season, episode


# --- DetailView.apply_source_all_clear ---


class TestDetailViewApplyAllClear:
    def _make_view(self) -> DetailView:
        node = _make_node()
        view = DetailView(node, TEMPLATE, TEMPLATE)
        view.fields = get_display_fields(TEMPLATE)
        return view

    def test_applies_present_and_preserves_absent(self) -> None:
        view = self._make_view()
        # filename source has title, season, episode but NOT year
        view.node.result = {
            "title": "Old",
            "year": 9999,
            "season": 99,
            "episode": 99,
        }
        view.source_index = 0  # filename source
        view.apply_source_all_clear()
        assert view.node.result["title"] == "Breaking Bad"
        assert view.node.result["season"] == 1
        assert view.node.result["episode"] == 1
        # year is preserved because the source doesn't have it
        assert view.node.result["year"] == 9999

    def test_noop_without_sources(self) -> None:
        node = FileNode(path=Path("/test.mkv"), result={"title": "Test"}, sources=[])
        view = DetailView(node, TEMPLATE, TEMPLATE)
        view.fields = get_display_fields(TEMPLATE)
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
        view.fields = get_display_fields(TEMPLATE)
        view.set_nodes([node1, node2])
        return view, node1, node2

    def test_is_multi(self) -> None:
        view, _, _ = self._make_multi_view()
        assert view.is_multi is True

    def test_single_node_not_multi(self) -> None:
        view = DetailView(_make_node(), TEMPLATE, TEMPLATE)
        view.fields = get_display_fields(TEMPLATE)
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

    def test_path_line_shows_count(self) -> None:
        view, _, _ = self._make_multi_view()
        line = view._render_multi_path_line()
        assert "2 files selected" in line.plain

    def test_path_line_shows_various_destinations(self) -> None:
        view, _, _ = self._make_multi_view()
        line = view._render_multi_path_line()
        assert "(various destinations)" in line.plain

    def test_editing_applies_to_all_nodes(self) -> None:
        view, node1, node2 = self._make_multi_view()
        view.cursor_row = 1  # title (tmdb_id is at 0)
        view.start_edit()
        view.edit_value = "Better Call Saul"
        view.commit_edit()
        assert node1.result["title"] == "Better Call Saul"
        assert node2.result["title"] == "Better Call Saul"

    def test_apply_source_all_applies_to_all_nodes(self) -> None:
        view, node1, node2 = self._make_multi_view()
        # Clear results
        node1.result = {}
        node2.result = {}
        # Apply all from TMDB source via shift-enter
        view.source_index = 0
        view.apply_source_all_clear()
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
        view.cursor_row = 4  # episode (tmdb_id at 0)
        view.start_edit()
        assert view.edit_value == ""

    def test_apply_all_clear_applies_to_all_nodes(self) -> None:
        view, node1, node2 = self._make_multi_view()
        # Set up result with extra fields
        node1.result = {"title": "Old", "year": 9999, "season": 99, "episode": 99}
        node2.result = {"title": "Old", "year": 9999, "season": 99, "episode": 99}
        # TMDB source only has title and year
        view.source_index = 0
        view.apply_source_all_clear()
        assert node1.result["title"] == "Breaking Bad"
        assert node2.result["title"] == "Breaking Bad"
        assert node1.result["year"] == 2008
        assert node2.result["year"] == 2008
        # season and episode not in TMDB source, should be preserved
        assert node1.result["season"] == 99
        assert node2.result["season"] == 99

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
        view.fields = get_display_fields(TEMPLATE)
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


# --- Clear field ---


MOVIE_TPL = "{title} ({year})/{title} ({year}).{ext}"
TV_TPL = "{title} ({year})/Season {season:02d}/{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"


class TestClearField:
    def test_clear_field_removes_value(self) -> None:
        node = FileNode(
            path=Path("/media/Inception.2010.mkv"),
            result={"title": "Inception", "year": 2010, "media_type": "movie"},
        )
        dv = DetailView(node, MOVIE_TPL, TV_TPL)
        dv.fields = get_display_fields(dv._active_template())
        dv.cursor_row = dv.fields.index("title")
        dv.clear_field()
        assert "title" not in node.result

    def test_clear_field_noop_during_edit(self) -> None:
        node = FileNode(
            path=Path("/media/Inception.2010.mkv"),
            result={"title": "Inception", "year": 2010, "media_type": "movie"},
        )
        dv = DetailView(node, MOVIE_TPL, TV_TPL)
        dv.fields = get_display_fields(dv._active_template())
        dv.cursor_row = dv.fields.index("title")
        dv.editing = True
        dv.clear_field()
        assert node.result["title"] == "Inception"


# --- Reset field to guessit ---


class TestResetFieldToGuessit:
    def test_reset_restores_guessit_value(self) -> None:
        node = FileNode(
            path=Path("/media/Inception.2010.mkv"),
            result={"title": "Wrong Title", "year": 2010, "media_type": "movie"},
        )
        dv = DetailView(node, MOVIE_TPL, TV_TPL)
        dv.fields = get_display_fields(dv._active_template())
        dv.cursor_row = dv.fields.index("title")
        dv.reset_field_to_guessit()
        assert node.result["title"] == "Inception"

    def test_reset_clears_field_if_not_in_filename(self) -> None:
        node = FileNode(
            path=Path("/media/Inception.2010.mkv"),
            result={"title": "Inception", "year": 2010, "tmdb_id": 12345, "media_type": "movie"},
        )
        dv = DetailView(node, MOVIE_TPL, TV_TPL)
        dv.fields = get_display_fields(dv._active_template())
        dv.cursor_row = dv.fields.index("tmdb_id")
        dv.reset_field_to_guessit()
        assert "tmdb_id" not in node.result


# --- Async integration: tree -> detail -> back ---


MOVIE_TEMPLATE = "{title} ({year})/{title} ({year}).{ext}"
TV_TEMPLATE = "{title} ({year})/Season {season:02d}/{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"


class TestDetailViewTemplateSelection:
    """Tests for media_type-based template selection in DetailView."""

    def test_movie_node_uses_movie_template_fields(self) -> None:
        node = FileNode(
            path=Path("/movies/Inception.mkv"),
            result={"title": "Inception", "year": 2010, "media_type": "movie"},
        )
        view = DetailView(
            node,
            MOVIE_TEMPLATE,
            TV_TEMPLATE,
        )
        view.fields = get_display_fields(view._active_template())
        # Movie template has title, year
        assert "title" in view.fields
        assert "year" in view.fields
        assert "season" not in view.fields
        assert "episode" not in view.fields

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
            node,
            MOVIE_TEMPLATE,
            TV_TEMPLATE,
        )
        view.fields = get_display_fields(view._active_template())
        assert "season" in view.fields
        assert "episode" in view.fields
        assert "episode_title" in view.fields

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
            movie_node,
            MOVIE_TEMPLATE,
            TV_TEMPLATE,
        )
        view.fields = get_display_fields(view._active_template())
        assert "season" not in view.fields

        view.set_node(tv_node)
        assert "season" in view.fields
        assert "episode" in view.fields

    def test_template_selection_uses_media_type(self) -> None:
        node = FileNode(
            path=Path("/tv/show.mkv"),
            result={"title": "Show", "media_type": "episode"},
        )
        view = DetailView(node, MOVIE_TEMPLATE, TV_TEMPLATE)
        assert view._active_template() == TV_TEMPLATE


# --- Column focus ---


class TestColumnFocus:
    def _make_view(self) -> DetailView:
        node = _make_node()
        view = DetailView(node, TEMPLATE, TEMPLATE)
        view.fields = get_display_fields(TEMPLATE)
        return view

    def test_default_focus_is_match(self) -> None:
        view = self._make_view()
        assert view.focus_column == "match"

    def test_toggle_switches_to_result(self) -> None:
        view = self._make_view()
        view.toggle_column_focus()
        assert view.focus_column == "result"

    def test_toggle_back_to_match(self) -> None:
        view = self._make_view()
        view.toggle_column_focus()
        view.toggle_column_focus()
        assert view.focus_column == "match"

    def test_cycle_source_sets_focus_to_match(self) -> None:
        view = self._make_view()
        view.focus_column = "result"
        view.cycle_source(1)
        assert view.focus_column == "match"

    def test_set_node_resets_focus(self) -> None:
        view = self._make_view()
        view.focus_column = "result"
        new_node = FileNode(path=Path("/other.mkv"), result={"title": "X"})
        view.set_node(new_node)
        assert view.focus_column == "match"

    def test_set_nodes_resets_focus(self) -> None:
        view = self._make_view()
        view.focus_column = "result"
        new_node = FileNode(path=Path("/other.mkv"), result={"title": "X"})
        view.set_nodes([new_node])
        assert view.focus_column == "match"

    def test_accept_focused_match_applies_source(self) -> None:
        view = self._make_view()
        view.focus_column = "match"
        view.source_index = 1  # TMDB source with title, year, etc.
        view.node.result["title"] = "Old Title"
        view.accept_focused_column()
        assert view.node.result["title"] == "Breaking Bad"  # from TMDB source

    def test_accept_focused_result_no_change(self) -> None:
        view = self._make_view()
        view.focus_column = "result"
        view.node.result["title"] = "My Title"
        view.accept_focused_column()
        assert view.node.result["title"] == "My Title"  # unchanged


# --- Tab bar rendering ---


class TestTabBarMultipleSources:
    """Verify tab bar renders all TMDB source tabs."""

    def _make_view_with_sources(self, num_sources: int) -> DetailView:
        sources = [
            Source(
                name=f"TMDB #{i + 1}",
                fields={"title": f"Show {i + 1}", "year": 2020 + i, "media_type": "episode"},
                confidence=0.8 - i * 0.1,
            )
            for i in range(num_sources)
        ]
        node = FileNode(
            path=Path("/media/show.s01e01.mkv"),
            result={"title": "Show", "year": 2020, "media_type": "episode"},
            sources=sources,
        )
        view = DetailView(node, TEMPLATE, TEMPLATE)
        view.fields = get_display_fields(TEMPLATE)
        return view

    def test_three_sources_show_three_tabs(self) -> None:
        from tests.test_ui.conftest import render_plain

        view = self._make_view_with_sources(3)
        plain = render_plain(view, width=120, height=30)
        assert "TMDB #1" in plain
        assert "TMDB #2" in plain
        assert "TMDB #3" in plain

    def test_single_source_shows_one_tab(self) -> None:
        from tests.test_ui.conftest import render_plain

        view = self._make_view_with_sources(1)
        plain = render_plain(view, width=120, height=30)
        assert "TMDB #1" in plain
        assert "TMDB #2" not in plain

    def test_tab_cycle_changes_active_tab(self) -> None:
        view = self._make_view_with_sources(3)
        assert view.source_index == 0
        view.cycle_source(1)
        assert view.source_index == 1
        view.cycle_source(1)
        assert view.source_index == 2


try:
    from textual.pilot import Pilot  # noqa: F401

    HAS_PILOT = True
except ImportError:
    HAS_PILOT = False


@pytest.mark.skipif(not HAS_PILOT, reason="textual pilot not available")
class TestTreeDetailIntegration:
    @pytest.mark.asyncio()
    async def test_enter_on_folder_shows_detail_esc_returns(self) -> None:
        from tapes.tree_model import FolderNode, TreeModel
        from tapes.ui.tree_app import TreeApp
        from tapes.ui.tree_view import TreeView

        node = _make_node()
        folder = FolderNode(name="folder", children=[node])
        root = FolderNode(name="root", children=[folder])
        model = TreeModel(root=root)
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            app.query_one(TreeView)
            dv = app.query_one(DetailView)

            # Initially detail is not shown
            assert app.mode == AppMode.TREE

            # Enter on folder opens detail for all files in it
            await pilot.press("enter")
            assert app.mode == AppMode.DETAIL
            assert dv.node is node

            # Navigate in detail view
            await pilot.press("j")
            assert dv.cursor_row == 1

            # Escape returns to tree
            await pilot.press("escape")
            assert app.mode == AppMode.TREE


@pytest.mark.skipif(not HAS_PILOT, reason="textual pilot not available")
class TestMultiFileDetailIntegration:
    @pytest.mark.asyncio()
    async def test_enter_in_range_opens_multi_detail(self) -> None:
        from tapes.tree_model import FolderNode, TreeModel
        from tapes.ui.tree_app import TreeApp
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
            app.query_one(TreeView)
            dv = app.query_one(DetailView)

            # Start range and select both files
            await pilot.press("v")
            await pilot.press("j")
            # Enter opens multi-file detail
            await pilot.press("enter")
            assert app.mode == AppMode.DETAIL
            assert dv.is_multi is True
            assert len(dv.file_nodes) == 2

            # Escape returns to tree
            await pilot.press("escape")
            assert app.mode == AppMode.TREE
