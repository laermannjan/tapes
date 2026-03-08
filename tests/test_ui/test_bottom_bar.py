"""Tests for the BottomBar widget."""

from __future__ import annotations

from tapes.ui.bottom_bar import OPERATIONS, BottomBar
from tests.test_ui.conftest import render_plain


class TestBottomBarRender:
    def test_renders_five_lines(self) -> None:
        bar = BottomBar()
        plain = render_plain(bar, height=5)
        lines = plain.split("\n")
        assert len(lines) == 5

    def test_blank_line_above_separator(self) -> None:
        bar = BottomBar()
        plain = render_plain(bar, height=5)
        lines = plain.split("\n")
        assert lines[0].strip() == ""

    def test_separator_lines_contain_dashes(self) -> None:
        bar = BottomBar()
        plain = render_plain(bar, height=5)
        lines = plain.split("\n")
        assert "─" in lines[1]
        assert "─" in lines[3]

    def test_search_prompt_visible(self) -> None:
        bar = BottomBar()
        plain = render_plain(bar, height=5)
        lines = plain.split("\n")
        assert "/" in lines[2]

    def test_operation_shown_in_bottom_line(self) -> None:
        bar = BottomBar()
        bar.operation = "move"
        plain = render_plain(bar, height=5)
        lines = plain.split("\n")
        assert "move" in lines[4]

    def test_stats_in_top_separator(self) -> None:
        bar = BottomBar()
        bar.stats_text = "2 staged · 5 total"
        plain = render_plain(bar, height=5)
        lines = plain.split("\n")
        assert "2 staged · 5 total" in lines[1]

    def test_search_query_shown(self) -> None:
        bar = BottomBar()
        bar.search_query = "matrix"
        plain = render_plain(bar, height=5)
        lines = plain.split("\n")
        assert "/matrix" in lines[2]

    def test_search_active_shows_cursor(self) -> None:
        bar = BottomBar()
        bar.search_active = True
        bar.search_query = "test"
        plain = render_plain(bar, height=5)
        lines = plain.split("\n")
        assert "█" in lines[2]

    def test_search_inactive_no_cursor(self) -> None:
        bar = BottomBar()
        bar.search_active = False
        bar.search_query = "test"
        plain = render_plain(bar, height=5)
        lines = plain.split("\n")
        assert "█" not in lines[2]

    def test_hint_text_shown(self) -> None:
        bar = BottomBar()
        bar.hint_text = "Space to stage"
        plain = render_plain(bar, height=5)
        lines = plain.split("\n")
        assert "Space to stage" in lines[4]


class TestBottomBarCycleOperation:
    def test_cycle_forward(self) -> None:
        bar = BottomBar()
        bar.operation = "copy"
        bar.cycle_operation(1)
        assert bar.operation == "move"

    def test_cycle_backward(self) -> None:
        bar = BottomBar()
        bar.operation = "copy"
        bar.cycle_operation(-1)
        assert bar.operation == "hardlink"

    def test_cycle_wraps(self) -> None:
        bar = BottomBar()
        bar.operation = "hardlink"
        bar.cycle_operation(1)
        assert bar.operation == "copy"

    def test_operations_list(self) -> None:
        assert OPERATIONS == ["copy", "move", "link", "hardlink"]
