"""Tests for TreeView cursor navigation and TreeApp keybindings."""

from __future__ import annotations

from pathlib import Path

import pytest

from tapes.tree_model import (
    Candidate,
    FileNode,
    FolderNode,
    TreeModel,
)
from tapes.ui.tree_app import AppState
from tapes.ui.tree_view import TreeView

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _simple_model() -> TreeModel:
    """Model with two folders (each with one file) and one top-level file.

    Structure (collapsed for test predictability):
        folderA/
            file_a.mkv
        folderB/
            file_b.mkv
        top.mkv

    Flattened (collapsed): folderA, folderB, top.mkv  (3 items)
    """
    root = FolderNode(
        name="root",
        children=[
            FolderNode(
                name="folderA",
                collapsed=True,
                children=[FileNode(path=Path("/root/folderA/file_a.mkv"))],
            ),
            FolderNode(
                name="folderB",
                collapsed=True,
                children=[FileNode(path=Path("/root/folderB/file_b.mkv"))],
            ),
            FileNode(path=Path("/root/top.mkv")),
        ],
    )
    return TreeModel(root=root)


TEMPLATE = "{title} ({year}).{ext}"


def _make_view(model: TreeModel | None = None) -> TreeView:
    """Create a TreeView without mounting it (for unit testing methods)."""
    if model is None:
        model = _simple_model()
    return TreeView(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)


# ---------------------------------------------------------------------------
# TreeView unit tests
# ---------------------------------------------------------------------------


class TestTreeViewCursor:
    def test_initial_cursor_is_zero(self) -> None:
        view = _make_view()
        assert view.cursor_index == 0

    def test_item_count(self) -> None:
        view = _make_view()
        # All folders collapsed: folderA, folderB, top.mkv
        assert view.item_count == 3

    def test_move_cursor_down(self) -> None:
        view = _make_view()
        view.move_cursor(1)
        assert view.cursor_index == 1

    def test_move_cursor_up(self) -> None:
        view = _make_view()
        view.move_cursor(1)
        view.move_cursor(-1)
        assert view.cursor_index == 0

    def test_cursor_clamps_at_zero(self) -> None:
        view = _make_view()
        view.move_cursor(-5)
        assert view.cursor_index == 0

    def test_cursor_clamps_at_max(self) -> None:
        view = _make_view()
        view.move_cursor(100)
        assert view.cursor_index == 2  # 3 items, max index = 2

    def test_cursor_node_returns_correct_node(self) -> None:
        view = _make_view()
        node = view.cursor_node()
        assert isinstance(node, FolderNode)
        assert node.name == "folderA"

        view.move_cursor(2)
        node = view.cursor_node()
        assert isinstance(node, FileNode)
        assert node.path.name == "top.mkv"

    def test_cursor_node_empty_model(self) -> None:
        model = TreeModel(root=FolderNode(name="empty"))
        view = _make_view(model)
        assert view.cursor_node() is None

    def test_move_cursor_empty_model(self) -> None:
        model = TreeModel(root=FolderNode(name="empty"))
        view = _make_view(model)
        view.move_cursor(1)
        assert view.cursor_index == 0

    def test_toggle_folder_expands(self) -> None:
        view = _make_view()
        # Cursor on folderA (collapsed)
        assert view.item_count == 3
        view.toggle_folder_at_cursor()
        # Now folderA is expanded: folderA, file_a.mkv, folderB, top.mkv
        assert view.item_count == 4
        node = view.cursor_node()
        assert isinstance(node, FolderNode)
        assert node.name == "folderA"
        assert not node.collapsed

    def test_toggle_folder_collapses(self) -> None:
        view = _make_view()
        view.toggle_folder_at_cursor()  # expand
        assert view.item_count == 4
        view.toggle_folder_at_cursor()  # collapse
        assert view.item_count == 3

    def test_toggle_on_file_does_nothing(self) -> None:
        view = _make_view()
        view.move_cursor(2)  # top.mkv
        view.toggle_folder_at_cursor()
        assert view.item_count == 3

    def test_cursor_clamps_after_collapse(self) -> None:
        """If cursor is past the end after collapse, it should clamp."""
        view = _make_view()
        # Expand folderA -> 4 items
        view.toggle_folder_at_cursor()
        assert view.item_count == 4
        # Move cursor to last item (index 3)
        view.move_cursor(3)
        assert view.cursor_index == 3
        # Move back to folderA (index 0) and collapse
        view.cursor_index = 0
        view.toggle_folder_at_cursor()
        # Should be back to 3 items, cursor stays at 0
        assert view.item_count == 3
        assert view.cursor_index == 0

    def test_refresh_tree_recomputes(self) -> None:
        view = _make_view()
        assert view.item_count == 3
        # Manually expand a folder in the model
        folder_a = view.model.root.children[0]
        assert isinstance(folder_a, FolderNode)
        folder_a.collapsed = False
        view.refresh_tree()
        assert view.item_count == 4


class TestTreeViewRender:
    def test_render_returns_renderable(self) -> None:
        view = _make_view()
        result = view.render()
        # Should be a Rich Text object
        from rich.text import Text

        assert isinstance(result, Text)

    def test_render_empty_model(self) -> None:
        model = TreeModel(root=FolderNode(name="empty"))
        view = _make_view(model)
        result = view.render()
        from rich.text import Text

        assert isinstance(result, Text)
        assert "empty" in str(result)

    def test_render_highlights_cursor_row(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import PropertyMock, patch

        view = _make_view()
        fake_size = SimpleNamespace(width=80, height=20)
        with patch.object(type(view), "size", new_callable=lambda: PropertyMock(return_value=fake_size)):
            result = view.render()
        # The render method applies "on #36345a" style to the cursor row.
        # Output includes content rows only (no manual borders).
        plain = result.plain  # ty: ignore[unresolved-attribute]  # Rich render return type
        lines = plain.split("\n")
        assert len(lines) == 3  # 3 content items (no borders)


# ---------------------------------------------------------------------------
# TreeApp async tests (using textual test harness)
# ---------------------------------------------------------------------------

try:
    from textual.pilot import Pilot  # noqa: F401

    HAS_PILOT = True
except ImportError:
    HAS_PILOT = False


# ---------------------------------------------------------------------------
# Range selection unit tests
# ---------------------------------------------------------------------------


def _expanded_model() -> TreeModel:
    """Model with files visible (folders expanded) for range selection tests.

    Structure:
        folderA/          (expanded)
            file_a.mkv
        folderB/          (expanded)
            file_b.mkv
        top.mkv

    Flattened: folderA, file_a.mkv, folderB, file_b.mkv, top.mkv (5 items)
    """
    root = FolderNode(
        name="root",
        children=[
            FolderNode(
                name="folderA",
                children=[FileNode(path=Path("/root/folderA/file_a.mkv"))],
                collapsed=False,
            ),
            FolderNode(
                name="folderB",
                children=[FileNode(path=Path("/root/folderB/file_b.mkv"))],
                collapsed=False,
            ),
            FileNode(path=Path("/root/top.mkv")),
        ],
    )
    return TreeModel(root=root)


class TestRangeSelection:
    def test_start_range_sets_anchor(self) -> None:
        view = _make_view()
        view.move_cursor(1)
        view.start_range_select()
        assert view._range_anchor == 1
        assert view.in_range_mode

    def test_selected_range_returns_bounds(self) -> None:
        view = _make_view(_expanded_model())
        view.start_range_select()  # anchor at 0
        view.move_cursor(2)  # cursor at 2
        rng = view.selected_range
        assert rng == (0, 2)

    def test_selected_range_cursor_before_anchor(self) -> None:
        view = _make_view(_expanded_model())
        view.move_cursor(3)
        view.start_range_select()  # anchor at 3
        view.move_cursor(-2)  # cursor at 1
        rng = view.selected_range
        assert rng == (1, 3)

    def test_selected_nodes_returns_correct_nodes(self) -> None:
        model = _expanded_model()
        view = _make_view(model)
        view.start_range_select()  # anchor at 0
        view.move_cursor(2)  # cursor at 2
        nodes = view.selected_nodes()
        assert len(nodes) == 3
        assert isinstance(nodes[0], FolderNode)
        assert nodes[0].name == "folderA"
        assert isinstance(nodes[1], FileNode)
        assert nodes[1].path.name == "file_a.mkv"
        assert isinstance(nodes[2], FolderNode)
        assert nodes[2].name == "folderB"

    def test_clear_range_select(self) -> None:
        view = _make_view()
        view.start_range_select()
        assert view.in_range_mode
        view.clear_range_select()
        assert not view.in_range_mode
        assert view._range_anchor is None

    def test_v_again_exits_range_mode(self) -> None:
        view = _make_view()
        view.start_range_select()
        assert view.in_range_mode
        view.start_range_select()
        assert not view.in_range_mode

    def test_render_highlights_range(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import PropertyMock, patch

        model = _expanded_model()
        view = _make_view(model)
        view.start_range_select()  # anchor at 0
        view.move_cursor(2)  # cursor at 2
        fake_size = SimpleNamespace(width=80, height=20)
        with patch.object(type(view), "size", new_callable=lambda: PropertyMock(return_value=fake_size)):
            result = view.render()
        # The cursor row (idx 2) has "on #36345a", range rows (idx 0, 1) have "on #2a2844"
        # We verify that the Text object has spans applied
        assert len(result._spans) > 0  # ty: ignore[unresolved-attribute]  # Rich render return type

    def test_selected_range_none_when_not_in_range_mode(self) -> None:
        view = _make_view()
        assert view.selected_range is None
        assert view.selected_nodes() == []


@pytest.mark.skipif(not HAS_PILOT, reason="textual pilot not available")
class TestTreeAppKeys:
    @pytest.fixture
    def model(self) -> TreeModel:
        return _simple_model()

    @pytest.fixture
    def template(self) -> str:
        return "{title} ({year}).{ext}"

    @pytest.mark.asyncio()
    async def test_j_moves_cursor_down(self, model: TreeModel, template: str) -> None:
        from tapes.ui.tree_app import TreeApp

        app = TreeApp(model=model, movie_template=template, tv_template=template)
        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            assert tv.cursor_index == 0
            await pilot.press("j")
            assert tv.cursor_index == 1

    @pytest.mark.asyncio()
    async def test_k_moves_cursor_up(self, model: TreeModel, template: str) -> None:
        from tapes.ui.tree_app import TreeApp

        app = TreeApp(model=model, movie_template=template, tv_template=template)
        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            await pilot.press("j")
            await pilot.press("k")
            assert tv.cursor_index == 0

    @pytest.mark.asyncio()
    async def test_down_arrow_moves_cursor(self, model: TreeModel, template: str) -> None:
        from tapes.ui.tree_app import TreeApp

        app = TreeApp(model=model, movie_template=template, tv_template=template)
        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            await pilot.press("down")
            assert tv.cursor_index == 1

    @pytest.mark.asyncio()
    async def test_up_arrow_moves_cursor(self, model: TreeModel, template: str) -> None:
        from tapes.ui.tree_app import TreeApp

        app = TreeApp(model=model, movie_template=template, tv_template=template)
        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            await pilot.press("down")
            await pilot.press("up")
            assert tv.cursor_index == 0

    @pytest.mark.asyncio()
    async def test_enter_on_folder_opens_detail(self, model: TreeModel, template: str) -> None:
        from tapes.ui.tree_app import TreeApp

        # Enter on a folder opens detail view for all files in it
        app = TreeApp(model=model, movie_template=template, tv_template=template)
        async with app.run_test() as pilot:
            await pilot.press("enter")
            assert app.state == AppState.METADATA

    @pytest.mark.asyncio()
    async def test_h_collapses_folder(self, model: TreeModel, template: str) -> None:
        from tapes.ui.tree_app import TreeApp

        # First expand via l, then collapse via h
        app = TreeApp(model=model, movie_template=template, tv_template=template)
        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            assert tv.item_count == 3
            await pilot.press("l")  # expand folderA
            assert tv.item_count == 4
            await pilot.press("h")  # collapse folderA
            assert tv.item_count == 3

    @pytest.mark.asyncio()
    async def test_l_expands_folder(self, model: TreeModel, template: str) -> None:
        from tapes.ui.tree_app import TreeApp

        app = TreeApp(model=model, movie_template=template, tv_template=template)
        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            assert tv.item_count == 3
            await pilot.press("l")  # expand folderA
            assert tv.item_count == 4

    @pytest.mark.asyncio()
    async def test_v_enters_range_mode(self, model: TreeModel, template: str) -> None:
        from tapes.ui.tree_app import TreeApp

        app = TreeApp(model=model, movie_template=template, tv_template=template)
        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            await pilot.press("v")
            assert tv.in_range_mode
            assert tv._range_anchor == 0

    @pytest.mark.asyncio()
    async def test_escape_exits_range_mode(self, model: TreeModel, template: str) -> None:
        from tapes.ui.tree_app import TreeApp

        app = TreeApp(model=model, movie_template=template, tv_template=template)
        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            await pilot.press("v")
            assert tv.in_range_mode
            await pilot.press("escape")
            assert not tv.in_range_mode

    @pytest.mark.asyncio()
    async def test_space_toggles_staged_file(self, template: str) -> None:
        from tapes.ui.tree_app import TreeApp

        # File needs complete metadata to pass the staging gate
        node = FileNode(path=Path("/root/top.mkv"))
        node.metadata = {"media_type": "movie", "title": "Top", "year": 2020}
        root = FolderNode(name="root", children=[node])
        model = TreeModel(root=root)
        app = TreeApp(model=model, movie_template=template, tv_template=template)
        async with app.run_test() as pilot:
            assert not node.staged
            await pilot.press("space")
            assert node.staged

    @pytest.mark.asyncio()
    async def test_space_updates_status(self, template: str) -> None:
        from tapes.ui.bottom_bar import BottomBar
        from tapes.ui.tree_app import TreeApp

        # File needs complete metadata to pass the staging gate
        node = FileNode(path=Path("/root/top.mkv"))
        node.metadata = {"media_type": "movie", "title": "Top", "year": 2020}
        root = FolderNode(name="root", children=[node])
        model = TreeModel(root=root)
        app = TreeApp(model=model, movie_template=template, tv_template=template)
        async with app.run_test() as pilot:
            await pilot.press("space")
            bar = app.query_one(BottomBar)
            assert "1 staged" in bar.stats_text

    @pytest.mark.asyncio()
    async def test_space_in_range_stages_range(self, template: str) -> None:
        from tapes.ui.tree_app import TreeApp

        # Files need complete metadata to pass the staging gate
        file_a = FileNode(path=Path("/root/folderA/file_a.mkv"))
        file_a.metadata = {"media_type": "movie", "title": "File A", "year": 2020}
        file_b = FileNode(path=Path("/root/folderB/file_b.mkv"))
        file_b.metadata = {"media_type": "movie", "title": "File B", "year": 2021}
        root = FolderNode(
            name="root",
            children=[
                FolderNode(name="folderA", children=[file_a], collapsed=False),
                FolderNode(name="folderB", children=[file_b], collapsed=False),
                FileNode(path=Path("/root/top.mkv")),
            ],
        )
        expanded = TreeModel(root=root)
        app = TreeApp(model=expanded, movie_template=template, tv_template=template)
        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            # Move to file_a (idx 1)
            await pilot.press("j")
            await pilot.press("v")  # start range
            # Move down 2 to file_b (idx 3)
            await pilot.press("j")
            await pilot.press("j")
            await pilot.press("space")  # stage range
            assert not tv.in_range_mode
            assert file_a.staged
            assert file_b.staged

    @pytest.mark.asyncio()
    async def test_ctrl_c_twice_quits(self, model: TreeModel, template: str) -> None:
        from tapes.ui.tree_app import TreeApp

        app = TreeApp(model=model, movie_template=template, tv_template=template)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+c")
            await pilot.press("ctrl+c")
            # app should exit; if we get here without hanging, it worked


# ---------------------------------------------------------------------------
# Ignore toggle unit tests
# ---------------------------------------------------------------------------


class TestIgnoreToggle:
    def test_toggle_ignored_on_file(self) -> None:
        view = _make_view(_expanded_model())
        view.move_cursor(1)  # file_a.mkv
        node = view.cursor_node()
        assert isinstance(node, FileNode)
        assert not node.ignored
        view.toggle_ignored_at_cursor()
        assert node.ignored
        view.toggle_ignored_at_cursor()
        assert not node.ignored

    def test_toggle_ignored_on_folder(self) -> None:
        model = _expanded_model()
        view = _make_view(model)
        # Cursor on folderA
        node = view.cursor_node()
        assert isinstance(node, FolderNode)
        view.toggle_ignored_at_cursor()
        file_a = model.all_files()[0]
        assert file_a.ignored
        # Toggle again to un-ignore
        view.toggle_ignored_at_cursor()
        assert not file_a.ignored

    def test_toggle_ignored_range(self) -> None:
        model = _expanded_model()
        view = _make_view(model)
        view.move_cursor(1)  # file_a.mkv
        view.start_range_select()
        view.move_cursor(2)  # cursor at 3, range covers 1-3
        view.toggle_ignored_at_cursor()
        assert not view.in_range_mode
        files = model.all_files()
        assert files[0].ignored  # file_a
        assert files[1].ignored  # file_b

    def test_ignored_count(self) -> None:
        model = _expanded_model()
        view = _make_view(model)
        assert view.ignored_count == 0
        model.all_files()[0].ignored = True
        assert view.ignored_count == 1
        model.all_files()[1].ignored = True
        assert view.ignored_count == 2


# ---------------------------------------------------------------------------
# Commit action tests (async)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_PILOT, reason="textual pilot not available")
class TestCommitAction:
    @pytest.mark.asyncio()
    async def test_commit_blocked_when_no_staged(self) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _simple_model()
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            await pilot.press("tab")
            assert app.state == AppState.TREE

    @pytest.mark.asyncio()
    async def test_tab_shows_commit_view(self) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        model.all_files()[0].staged = True
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            await pilot.press("tab")
            assert app.state == AppState.COMMIT

    @pytest.mark.asyncio()
    async def test_commit_esc_cancels(self) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        model.all_files()[0].staged = True
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            await pilot.press("tab")
            assert app.state == AppState.COMMIT
            await pilot.press("escape")
            assert app.state == AppState.TREE

    @pytest.mark.asyncio()
    async def test_x_toggles_ignored(self) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            # Move to file_a.mkv (index 1)
            await pilot.press("j")
            node = tv.cursor_node()
            assert isinstance(node, FileNode)
            assert not node.ignored
            await pilot.press("x")
            assert node.ignored

    @pytest.mark.asyncio()
    async def test_footer_shows_ignored_count(self) -> None:
        from tapes.ui.bottom_bar import BottomBar
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            # Move to file and ignore it
            await pilot.press("j")
            await pilot.press("x")
            bar = app.query_one(BottomBar)
            assert "1 ignored" in bar.stats_text


# ---------------------------------------------------------------------------
# Flat/Tree toggle tests
# ---------------------------------------------------------------------------


class TestFlatTreeToggle:
    def test_toggle_flat_mode(self) -> None:
        model = _expanded_model()
        view = _make_view(model)
        assert not view.flat_mode
        view.toggle_flat_mode()
        assert view.flat_mode
        view.toggle_flat_mode()
        assert not view.flat_mode

    def test_flat_mode_shows_only_files(self) -> None:
        model = _expanded_model()
        view = _make_view(model)
        # Tree mode: folderA, file_a, folderB, file_b, top = 5 items
        assert view.item_count == 5
        view.toggle_flat_mode()
        # Flat mode: file_a, file_b, top = 3 items (no folders)
        assert view.item_count == 3
        for node, _depth in view._items:
            assert isinstance(node, FileNode)

    def test_cursor_stays_on_same_file_after_toggle(self) -> None:
        model = _expanded_model()
        view = _make_view(model)
        # Move to file_b.mkv (index 3 in tree mode)
        view.move_cursor(3)
        node_before = view.cursor_node()
        assert isinstance(node_before, FileNode)
        assert node_before.path.name == "file_b.mkv"
        # Toggle to flat
        view.toggle_flat_mode()
        node_after = view.cursor_node()
        assert node_after is node_before

    def test_cursor_clamps_when_toggling_from_folder(self) -> None:
        model = _simple_model()  # all collapsed
        view = _make_view(model)
        # Cursor on folderA (index 0), which won't exist in flat mode
        assert isinstance(view.cursor_node(), FolderNode)
        view.toggle_flat_mode()
        # Cursor should be clamped to valid range
        assert view.cursor_index >= 0
        assert view.cursor_index < view.item_count
        assert isinstance(view.cursor_node(), FileNode)


@pytest.mark.skipif(not HAS_PILOT, reason="textual pilot not available")
class TestFlatTreeToggleAsync:
    @pytest.mark.asyncio()
    async def test_backtick_toggles_flat_mode(self) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            assert not tv.flat_mode
            await pilot.press("grave_accent")
            assert tv.flat_mode
            await pilot.press("grave_accent")
            assert not tv.flat_mode


# ---------------------------------------------------------------------------
# Filter / search unit tests (M14)
# ---------------------------------------------------------------------------


class TestTreeViewFilter:
    def test_set_filter_narrows_items(self) -> None:
        model = _expanded_model()
        view = _make_view(model)
        assert view.item_count == 5  # folderA, file_a, folderB, file_b, top
        view.set_filter("file_a")
        # Should show folderA and file_a.mkv
        assert view.item_count == 2
        nodes = [n for n, _d in view._items]
        assert isinstance(nodes[0], FolderNode)
        assert nodes[0].name == "folderA"
        assert isinstance(nodes[1], FileNode)
        assert nodes[1].path.name == "file_a.mkv"

    def test_set_filter_case_insensitive(self) -> None:
        model = _expanded_model()
        view = _make_view(model)
        view.set_filter("FILE_A")
        assert view.item_count == 2
        file_nodes = [n for n, _d in view._items if isinstance(n, FileNode)]
        assert len(file_nodes) == 1
        assert file_nodes[0].path.name == "file_a.mkv"

    def test_clear_filter_restores_all(self) -> None:
        model = _expanded_model()
        view = _make_view(model)
        original_count = view.item_count
        view.set_filter("file_a")
        assert view.item_count < original_count
        view.clear_filter()
        assert view.item_count == original_count

    def test_filter_no_match_shows_empty(self) -> None:
        model = _expanded_model()
        view = _make_view(model)
        view.set_filter("nonexistent_file")
        assert view.item_count == 0

    def test_filter_matches_multiple_files(self) -> None:
        model = _expanded_model()
        view = _make_view(model)
        view.set_filter("file_")
        file_nodes = [n for n, _d in view._items if isinstance(n, FileNode)]
        assert len(file_nodes) == 2

    def test_filter_in_flat_mode(self) -> None:
        model = _expanded_model()
        view = _make_view(model)
        view.toggle_flat_mode()
        view.set_filter("top")
        assert view.item_count == 1
        node = view._items[0][0]
        assert isinstance(node, FileNode)
        assert node.path.name == "top.mkv"

    def test_filter_text_property(self) -> None:
        view = _make_view()
        assert view.filter_text == ""
        view.set_filter("test")
        assert view.filter_text == "test"
        view.clear_filter()
        assert view.filter_text == ""

    def test_filter_clamps_cursor(self) -> None:
        model = _expanded_model()
        view = _make_view(model)
        view.move_cursor(4)  # cursor at last item
        view.set_filter("top")
        # Should clamp cursor to valid range
        assert view.cursor_index == 0

    def test_filter_finds_files_in_collapsed_folders(self) -> None:
        model = _simple_model()  # all folders collapsed
        view = _make_view(model)
        # In collapsed state, only folders and top.mkv are visible
        assert view.item_count == 3
        # Filter should find file_a even though folderA is collapsed
        view.set_filter("file_a")
        file_nodes = [n for n, _d in view._items if isinstance(n, FileNode)]
        assert len(file_nodes) == 1
        assert file_nodes[0].path.name == "file_a.mkv"

    def test_filter_with_partial_match(self) -> None:
        model = _expanded_model()
        view = _make_view(model)
        view.set_filter(".mkv")
        file_nodes = [n for n, _d in view._items if isinstance(n, FileNode)]
        assert len(file_nodes) == 3  # all files match


@pytest.mark.skipif(not HAS_PILOT, reason="textual pilot not available")
class TestSearchModeAsync:
    @pytest.mark.asyncio()
    async def test_slash_enters_search_mode(self) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            await pilot.press("slash")
            assert app.state == AppState.TREE_SEARCH

    @pytest.mark.asyncio()
    async def test_typing_filters_items(self) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            await pilot.press("slash")
            await pilot.press("t", "o", "p")
            assert app._search_query == "top"
            assert tv.item_count == 1

    @pytest.mark.asyncio()
    async def test_escape_clears_filter(self) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            original_count = tv.item_count
            await pilot.press("slash")
            await pilot.press("t", "o", "p")
            assert tv.item_count == 1
            await pilot.press("escape")
            assert app.state == AppState.TREE
            assert tv.item_count == original_count

    @pytest.mark.asyncio()
    async def test_enter_keeps_filter(self) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            await pilot.press("slash")
            await pilot.press("t", "o", "p")
            await pilot.press("enter")
            assert app.state == AppState.TREE
            # Filter remains active
            assert tv.item_count == 1

    @pytest.mark.asyncio()
    async def test_backspace_removes_last_char(self) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            app.query_one(TreeView)
            await pilot.press("slash")
            await pilot.press("t", "o", "p")
            assert app._search_query == "top"
            await pilot.press("backspace")
            assert app._search_query == "to"

    @pytest.mark.asyncio()
    async def test_search_noop_in_detail(self) -> None:
        from tapes.ui.tree_app import TreeApp

        node = FileNode(
            path=Path("/media/test.mkv"),
            metadata={"title": "Test"},
        )
        folder = FolderNode(name="folder", children=[node])
        root = FolderNode(name="root", children=[folder])
        model = TreeModel(root=root)
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            # Enter detail view via folder (enter on folder opens detail)
            await pilot.press("enter")
            assert app.state == AppState.METADATA
            await pilot.press("slash")
            assert app.state == AppState.METADATA


# ---------------------------------------------------------------------------
# BottomBar tests
# ---------------------------------------------------------------------------


class TestBottomBar:
    """Tests for the BottomBar integration in TreeApp."""

    @pytest.mark.asyncio()
    async def test_bottom_bar_visible_on_launch(self) -> None:
        from tapes.ui.bottom_bar import BottomBar
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test():
            bar = app.query_one(BottomBar)
            assert bar is not None

    @pytest.mark.asyncio()
    async def test_bottom_bar_hidden_in_detail(self) -> None:
        from tapes.ui.bottom_bar import BottomBar
        from tapes.ui.tree_app import TreeApp

        node = FileNode(path=Path("/media/test.mkv"), metadata={"title": "Test"})
        folder = FolderNode(name="folder", children=[node])
        root = FolderNode(name="root", children=[folder])
        model = TreeModel(root=root)
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            bar = app.query_one(BottomBar)
            # Enter detail via folder
            await pilot.press("enter")
            assert str(bar.styles.display) == "none"

            await pilot.press("escape")
            assert str(bar.styles.display) != "none"

    @pytest.mark.asyncio()
    async def test_cycle_operation_changes_bar(self) -> None:
        from tapes.ui.bottom_bar import BottomBar
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test():
            bar = app.query_one(BottomBar)
            initial_op = bar.operation
            bar.cycle_operation()
            assert bar.operation != initial_op


# ---------------------------------------------------------------------------
# Integration tests: visual states
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_PILOT, reason="textual pilot not available")
class TestVisualIntegration:
    """End-to-end integration tests exercising key visual states via Pilot."""

    @pytest.mark.asyncio()
    async def test_launch_tree_view_visible_with_border(self) -> None:
        """Launch the app and verify TreeView, MetadataView, and BottomBar are composed."""
        from tapes.ui.bottom_bar import BottomBar
        from tapes.ui.metadata_view import MetadataView
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test():
            tv = app.query_one(TreeView)
            dv = app.query_one(MetadataView)
            bar = app.query_one(BottomBar)
            # All three panels exist
            assert tv is not None
            assert dv is not None
            assert bar is not None

    @pytest.mark.asyncio()
    async def test_question_mark_toggles_help(self) -> None:
        """Pressing ? shows inline help view, pressing ? again hides it."""
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            assert app.state == AppState.TREE

            # Show help
            await pilot.press("question_mark")
            assert app.state == AppState.HELP

            # Hide help
            await pilot.press("question_mark")
            assert app.state == AppState.TREE

    @pytest.mark.asyncio()
    async def test_help_from_detail_returns_to_detail(self) -> None:
        """Pressing ? in detail opens help, closing returns to detail."""
        from tapes.ui.tree_app import TreeApp

        node = FileNode(path=Path("/media/test.mkv"), metadata={"title": "Test"})
        folder = FolderNode(name="folder", children=[node])
        root = FolderNode(name="root", children=[folder])
        model = TreeModel(root=root)
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            # Enter detail via folder
            await pilot.press("enter")
            assert app.state == AppState.METADATA
            await pilot.press("question_mark")
            assert app.state == AppState.HELP
            await pilot.press("question_mark")
            assert app.state == AppState.METADATA


# ---------------------------------------------------------------------------
# Detail confirm/discard tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_PILOT, reason="textual pilot not available")
class TestDetailConfirmDiscard:
    """Tests for the confirm/discard model in detail view."""

    @pytest.mark.asyncio()
    async def test_esc_discards_changes(self) -> None:
        from tapes.ui.tree_app import TreeApp

        node = FileNode(
            path=Path("/media/test.mkv"),
            metadata={"title": "Original"},
            candidates=[Candidate(name="TMDB #1", metadata={"title": "Changed"}, score=0.9)],
        )
        folder = FolderNode(name="folder", children=[node])
        root = FolderNode(name="root", children=[folder])
        model = TreeModel(root=root)
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            # Enter detail via folder
            await pilot.press("enter")
            assert app.state == AppState.METADATA
            # Manually edit result to simulate a change
            node.metadata["title"] = "Changed"
            await pilot.press("escape")
            assert app.state == AppState.TREE
            assert node.metadata["title"] == "Original"

    @pytest.mark.asyncio()
    async def test_enter_accepts_changes(self) -> None:
        from tapes.ui.tree_app import TreeApp

        node = FileNode(
            path=Path("/media/test.mkv"),
            metadata={"title": "Original"},
            candidates=[Candidate(name="TMDB #1", metadata={"title": "Changed"}, score=0.9)],
        )
        folder = FolderNode(name="folder", children=[node])
        root = FolderNode(name="root", children=[folder])
        model = TreeModel(root=root)
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            # Enter detail via folder
            await pilot.press("enter")
            assert app.state == AppState.METADATA
            # Manually edit result
            node.metadata["title"] = "Changed"
            # Enter accepts changes and returns to tree
            await pilot.press("enter")
            assert app.state == AppState.TREE
            assert node.metadata["title"] == "Changed"

    @pytest.mark.asyncio()
    async def test_esc_during_edit_cancels_edit_not_detail(self) -> None:
        """Esc while editing cancels edit, doesn't discard detail changes."""
        from tapes.ui.metadata_view import MetadataView
        from tapes.ui.tree_app import TreeApp

        node = FileNode(
            path=Path("/media/test.mkv"),
            metadata={"title": "Original"},
        )
        folder = FolderNode(name="folder", children=[node])
        root = FolderNode(name="root", children=[folder])
        model = TreeModel(root=root)
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            # Enter detail via folder
            await pilot.press("enter")
            dv = app.query_one(MetadataView)
            assert app.state == AppState.METADATA
            await pilot.press("e")  # start edit via e key
            assert dv.editing
            await pilot.press("escape")  # cancel edit
            assert not dv.editing
            assert app.state == AppState.METADATA  # still in detail


# ---------------------------------------------------------------------------
# AppState transition tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_PILOT, reason="textual pilot not available")
class TestAppStateTransitions:
    @pytest.mark.asyncio()
    async def test_initial_mode_is_tree(self) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)
        async with app.run_test():
            assert app.state == AppState.TREE

    @pytest.mark.asyncio()
    async def test_enter_detail_and_back(self) -> None:
        from tapes.ui.tree_app import TreeApp

        node = FileNode(path=Path("/media/test.mkv"), metadata={"title": "Test"})
        folder = FolderNode(name="folder", children=[node])
        root = FolderNode(name="root", children=[folder])
        model = TreeModel(root=root)
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)
        async with app.run_test() as pilot:
            assert app.state == AppState.TREE
            # Enter detail via folder
            await pilot.press("enter")
            assert app.state == AppState.METADATA
            await pilot.press("escape")
            assert app.state == AppState.TREE

    @pytest.mark.asyncio()
    async def test_commit_and_cancel(self) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        model.all_files()[0].staged = True
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)
        async with app.run_test() as pilot:
            assert app.state == AppState.TREE
            await pilot.press("tab")
            assert app.state == AppState.COMMIT
            await pilot.press("escape")
            assert app.state == AppState.TREE

    @pytest.mark.asyncio()
    async def test_help_and_back(self) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)
        async with app.run_test() as pilot:
            assert app.state == AppState.TREE
            await pilot.press("question_mark")
            assert app.state == AppState.HELP
            await pilot.press("question_mark")
            assert app.state == AppState.TREE

    @pytest.mark.asyncio()
    async def test_search_and_cancel(self) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)
        async with app.run_test() as pilot:
            assert app.state == AppState.TREE
            await pilot.press("slash")
            assert app.state == AppState.TREE_SEARCH
            await pilot.press("escape")
            assert app.state == AppState.TREE


# ---------------------------------------------------------------------------
# Tree key redesign tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_PILOT, reason="textual pilot not available")
class TestTreeKeyRedesign:
    @pytest.mark.asyncio()
    async def test_enter_opens_detail_for_file(self) -> None:
        """enter on a file opens the detail/info view."""
        from tapes.ui.tree_app import TreeApp

        node = FileNode(path=Path("/media/test.mkv"))
        node.metadata = {"media_type": "movie", "title": "Test", "year": 2020}
        root = FolderNode(name="root", children=[node])
        model = TreeModel(root=root)
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)
        async with app.run_test() as pilot:
            await pilot.press("enter")
            assert app._mode == AppState.METADATA

    @pytest.mark.asyncio()
    async def test_tab_opens_commit(self) -> None:
        """tab from tree opens commit preview when files are staged."""
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        model.all_files()[0].staged = True
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)
        async with app.run_test() as pilot:
            await pilot.press("tab")
            assert app.state == AppState.COMMIT

    @pytest.mark.asyncio()
    async def test_h_collapses_expanded_folder(self) -> None:
        """h collapses an expanded folder."""
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)
        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            # Cursor on folderA (expanded), 5 items total
            assert tv.item_count == 5
            await pilot.press("h")
            # folderA collapsed: folderA, folderB, file_b.mkv, top.mkv = 4 items
            assert tv.item_count == 4

    @pytest.mark.asyncio()
    async def test_l_expands_collapsed_folder(self) -> None:
        """l expands a collapsed folder."""
        from tapes.ui.tree_app import TreeApp

        model = _simple_model()  # all collapsed
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)
        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            assert tv.item_count == 3
            await pilot.press("l")  # expand folderA
            assert tv.item_count == 4

    @pytest.mark.asyncio()
    async def test_enter_on_folder_opens_detail_for_files(self) -> None:
        """enter on a folder opens detail view for all files in that folder."""
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)
        async with app.run_test() as pilot:
            # Cursor on folderA
            await pilot.press("enter")
            assert app.state == AppState.METADATA

    @pytest.mark.asyncio()
    async def test_h_moves_to_parent_on_file(self) -> None:
        """h on a file moves cursor to its parent folder."""
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)
        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            # Move to file_a.mkv (index 1)
            await pilot.press("j")
            assert isinstance(tv.cursor_node(), FileNode)
            await pilot.press("h")
            # Should move to parent folderA (index 0)
            assert tv.cursor_index == 0
            assert isinstance(tv.cursor_node(), FolderNode)
