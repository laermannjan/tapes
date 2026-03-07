"""Tests for TreeView cursor navigation and TreeApp keybindings."""
from __future__ import annotations

from pathlib import Path

import pytest

from tapes.ui.tree_model import (
    FileNode,
    FolderNode,
    Source,
    TreeModel,
    UndoManager,
    accept_best_source,
)
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


def _make_view(model: TreeModel | None = None) -> TreeView:
    """Create a TreeView without mounting it (for unit testing methods)."""
    if model is None:
        model = _simple_model()
    return TreeView(model=model, template="{title} ({year}).{ext}")


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

    def test_render_tree_backward_compat(self) -> None:
        """render_tree() returns a plain string (M2 compat)."""
        view = _make_view()
        text = view.render_tree()
        assert isinstance(text, str)
        lines = text.strip().split("\n")
        assert len(lines) == 3


class TestTreeViewStaging:
    def test_toggle_staged_on_file(self) -> None:
        view = _make_view()
        view.move_cursor(2)  # top.mkv (FileNode)
        node = view.cursor_node()
        assert isinstance(node, FileNode)
        assert not node.staged
        view.toggle_staged_at_cursor()
        assert node.staged
        view.toggle_staged_at_cursor()
        assert not node.staged

    def test_toggle_staged_on_folder(self) -> None:
        model = _simple_model()
        view = _make_view(model)
        # Cursor on folderA (FolderNode)
        node = view.cursor_node()
        assert isinstance(node, FolderNode)
        # Stage all children
        view.toggle_staged_at_cursor()
        file_a = model.root.children[0]
        assert isinstance(file_a, FolderNode)
        assert file_a.children[0].staged  # type: ignore[union-attr]
        # Unstage all children
        view.toggle_staged_at_cursor()
        assert not file_a.children[0].staged  # type: ignore[union-attr]

    def test_staged_count(self) -> None:
        model = _simple_model()
        view = _make_view(model)
        assert view.staged_count == 0
        assert view.total_count == 3  # file_a.mkv, file_b.mkv, top.mkv
        # Stage top.mkv
        view.move_cursor(2)
        view.toggle_staged_at_cursor()
        assert view.staged_count == 1
        assert view.total_count == 3

    def test_staged_marker_in_render(self) -> None:
        view = _make_view()
        view.move_cursor(2)  # top.mkv
        view.toggle_staged_at_cursor()
        output = view.render_tree()
        # Staged file should show checkmark
        assert "\u2713" in output  # ✓

    def test_unstaged_marker_in_render(self) -> None:
        view = _make_view()
        output = view.render_tree()
        # Unstaged, non-ignored files show ○
        assert "\u25cb" in output  # ○


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
        view = _make_view()
        result = view.render()
        # The render method applies "reverse" style to the cursor row.
        # We check that the Text object contains styled spans.
        plain = result.plain
        lines = plain.split("\n")
        assert len(lines) == 3


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

    def test_toggle_staged_range_all_unstaged_become_staged(self) -> None:
        model = _expanded_model()
        view = _make_view(model)
        # Select range covering file_a.mkv (idx 1) and file_b.mkv (idx 3)
        view.move_cursor(1)
        view.start_range_select()
        view.move_cursor(2)  # cursor at 3
        view.toggle_staged_range()
        nodes = view.selected_nodes()
        file_nodes = [n for n in nodes if isinstance(n, FileNode)]
        assert all(f.staged for f in file_nodes)

    def test_toggle_staged_range_all_staged_become_unstaged(self) -> None:
        model = _expanded_model()
        view = _make_view(model)
        # Stage files first
        for f in model.all_files():
            f.staged = True
        view.move_cursor(1)
        view.start_range_select()
        view.move_cursor(2)  # cursor at 3
        view.toggle_staged_range()
        nodes = view.selected_nodes()
        file_nodes = [n for n in nodes if isinstance(n, FileNode)]
        assert all(not f.staged for f in file_nodes)

    def test_toggle_staged_range_mixed_becomes_all_staged(self) -> None:
        model = _expanded_model()
        view = _make_view(model)
        # Stage only file_a
        files = model.all_files()
        files[0].staged = True  # file_a staged
        files[1].staged = False  # file_b unstaged
        view.move_cursor(1)
        view.start_range_select()
        view.move_cursor(2)  # cursor at 3, range covers file_a and file_b
        view.toggle_staged_range()
        nodes = view.selected_nodes()
        file_nodes = [n for n in nodes if isinstance(n, FileNode)]
        assert all(f.staged for f in file_nodes)

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
        model = _expanded_model()
        view = _make_view(model)
        view.start_range_select()  # anchor at 0
        view.move_cursor(2)  # cursor at 2
        result = view.render()
        # The cursor row (idx 2) has "reverse", range rows (idx 0, 1) have styling
        # We verify that the Text object has spans applied
        assert len(result._spans) > 0  # noqa: SLF001

    def test_space_in_range_mode_stages_and_exits(self) -> None:
        model = _expanded_model()
        view = _make_view(model)
        view.move_cursor(1)  # file_a.mkv
        view.start_range_select()
        view.move_cursor(2)  # cursor at 3, range 1-3
        view.toggle_staged_at_cursor()
        # Should have staged and exited range mode
        assert not view.in_range_mode
        file_a = model.all_files()[0]
        file_b = model.all_files()[1]
        assert file_a.staged
        assert file_b.staged

    def test_selected_range_none_when_not_in_range_mode(self) -> None:
        view = _make_view()
        assert view.selected_range is None
        assert view.selected_nodes() == []


@pytest.mark.skipif(not HAS_PILOT, reason="textual pilot not available")
class TestTreeAppKeys:
    @pytest.fixture()
    def model(self) -> TreeModel:
        return _simple_model()

    @pytest.fixture()
    def template(self) -> str:
        return "{title} ({year}).{ext}"

    @pytest.mark.asyncio()
    async def test_j_moves_cursor_down(self, model: TreeModel, template: str) -> None:
        from tapes.ui.tree_app import TreeApp

        app = TreeApp(model=model, template=template)
        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            assert tv.cursor_index == 0
            await pilot.press("j")
            assert tv.cursor_index == 1

    @pytest.mark.asyncio()
    async def test_k_moves_cursor_up(self, model: TreeModel, template: str) -> None:
        from tapes.ui.tree_app import TreeApp

        app = TreeApp(model=model, template=template)
        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            await pilot.press("j")
            await pilot.press("k")
            assert tv.cursor_index == 0

    @pytest.mark.asyncio()
    async def test_down_arrow_moves_cursor(
        self, model: TreeModel, template: str
    ) -> None:
        from tapes.ui.tree_app import TreeApp

        app = TreeApp(model=model, template=template)
        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            await pilot.press("down")
            assert tv.cursor_index == 1

    @pytest.mark.asyncio()
    async def test_up_arrow_moves_cursor(
        self, model: TreeModel, template: str
    ) -> None:
        from tapes.ui.tree_app import TreeApp

        app = TreeApp(model=model, template=template)
        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            await pilot.press("down")
            await pilot.press("up")
            assert tv.cursor_index == 0

    @pytest.mark.asyncio()
    async def test_enter_toggles_folder(
        self, model: TreeModel, template: str
    ) -> None:
        from tapes.ui.tree_app import TreeApp

        app = TreeApp(model=model, template=template)
        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            assert tv.item_count == 3
            await pilot.press("enter")
            # folderA expanded
            assert tv.item_count == 4

    @pytest.mark.asyncio()
    async def test_v_enters_range_mode(self, model: TreeModel, template: str) -> None:
        from tapes.ui.tree_app import TreeApp

        app = TreeApp(model=model, template=template)
        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            await pilot.press("v")
            assert tv.in_range_mode
            assert tv._range_anchor == 0  # noqa: SLF001

    @pytest.mark.asyncio()
    async def test_escape_exits_range_mode(
        self, model: TreeModel, template: str
    ) -> None:
        from tapes.ui.tree_app import TreeApp

        app = TreeApp(model=model, template=template)
        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            await pilot.press("v")
            assert tv.in_range_mode
            await pilot.press("escape")
            assert not tv.in_range_mode

    @pytest.mark.asyncio()
    async def test_space_toggles_staged_file(
        self, model: TreeModel, template: str
    ) -> None:
        from tapes.ui.tree_app import TreeApp

        app = TreeApp(model=model, template=template)
        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            # Move to top.mkv (index 2)
            await pilot.press("j")
            await pilot.press("j")
            node = tv.cursor_node()
            assert isinstance(node, FileNode)
            assert not node.staged
            await pilot.press("space")
            assert node.staged

    @pytest.mark.asyncio()
    async def test_space_updates_status(
        self, model: TreeModel, template: str
    ) -> None:
        from tapes.ui.tree_app import TreeApp
        from textual.widgets import Static

        app = TreeApp(model=model, template=template)
        async with app.run_test() as pilot:
            # Move to top.mkv and stage it
            await pilot.press("j")
            await pilot.press("j")
            await pilot.press("space")
            status = app.query_one("#status", Static)
            assert "1 staged" in status.renderable  # type: ignore[operator]

    @pytest.mark.asyncio()
    async def test_space_in_range_stages_range(
        self, model: TreeModel, template: str
    ) -> None:
        from tapes.ui.tree_app import TreeApp

        # Use expanded model so files are visible
        expanded = _expanded_model()
        app = TreeApp(model=expanded, template=template)
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
            files = expanded.all_files()
            assert files[0].staged  # file_a
            assert files[1].staged  # file_b

    @pytest.mark.asyncio()
    async def test_q_quits(self, model: TreeModel, template: str) -> None:
        from tapes.ui.tree_app import TreeApp

        app = TreeApp(model=model, template=template)
        async with app.run_test() as pilot:
            await pilot.press("q")
            # app should exit; if we get here without hanging, it worked


# ---------------------------------------------------------------------------
# UndoManager unit tests
# ---------------------------------------------------------------------------


class TestUndoManager:
    def test_snapshot_and_undo_restores_result(self) -> None:
        node = FileNode(path=Path("/test.mkv"), result={"title": "Original"})
        undo = UndoManager()
        undo.snapshot([node])
        node.result["title"] = "Changed"
        assert undo.undo() is True
        assert node.result["title"] == "Original"

    def test_undo_noop_when_no_snapshot(self) -> None:
        undo = UndoManager()
        assert undo.undo() is False

    def test_undo_clears_snapshot(self) -> None:
        node = FileNode(path=Path("/test.mkv"), result={"title": "Original"})
        undo = UndoManager()
        undo.snapshot([node])
        assert undo.has_snapshot is True
        undo.undo()
        assert undo.has_snapshot is False
        # Second undo is a noop
        assert undo.undo() is False

    def test_snapshot_is_deep_copy(self) -> None:
        node = FileNode(path=Path("/test.mkv"), result={"title": "Original"})
        undo = UndoManager()
        undo.snapshot([node])
        # Mutate deeply
        node.result["title"] = "Changed"
        node.result["year"] = 2020
        undo.undo()
        assert node.result == {"title": "Original"}

    def test_multiple_nodes(self) -> None:
        n1 = FileNode(path=Path("/a.mkv"), result={"title": "A"})
        n2 = FileNode(path=Path("/b.mkv"), result={"title": "B"})
        undo = UndoManager()
        undo.snapshot([n1, n2])
        n1.result["title"] = "A2"
        n2.result["title"] = "B2"
        undo.undo()
        assert n1.result["title"] == "A"
        assert n2.result["title"] == "B"

    def test_undo_restores_sources_and_staged(self) -> None:
        undo = UndoManager()
        node = FileNode(
            path=Path("/a.mkv"),
            result={"title": "Old"},
            sources=[Source(name="src", fields={"title": "Old"}, confidence=0.5)],
            staged=False,
        )
        undo.snapshot([node])
        # Mutate everything
        node.result = {"title": "New"}
        node.sources = [Source(name="new", fields={"title": "New"}, confidence=0.9)]
        node.staged = True
        # Undo
        assert undo.undo() is True
        assert node.result == {"title": "Old"}
        assert len(node.sources) == 1
        assert node.sources[0].name == "src"
        assert node.sources[0].confidence == 0.5
        assert node.staged is False

    def test_single_level_only(self) -> None:
        node = FileNode(path=Path("/test.mkv"), result={"title": "V1"})
        undo = UndoManager()
        undo.snapshot([node])
        node.result["title"] = "V2"
        undo.snapshot([node])
        node.result["title"] = "V3"
        # Only the latest snapshot (V2) is restored
        undo.undo()
        assert node.result["title"] == "V2"


# ---------------------------------------------------------------------------
# Undo integration tests (async)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_PILOT, reason="textual pilot not available")
class TestUndoIntegration:
    @pytest.mark.asyncio()
    async def test_undo_after_edit_in_detail(self) -> None:
        from tapes.ui.detail_view import DetailView
        from tapes.ui.tree_app import TreeApp

        node = FileNode(
            path=Path("/media/test.mkv"),
            result={"title": "Original", "year": 2020},
            sources=[
                Source(name="src1", fields={"title": "Alt", "year": 2021}),
            ],
        )
        root = FolderNode(name="root", children=[node])
        model = TreeModel(root=root)
        app = TreeApp(model=model, template="{title} ({year}).{ext}")

        async with app.run_test() as pilot:
            # Enter detail view
            await pilot.press("enter")
            dv = app.query_one(DetailView)
            assert dv.node is node

            # Apply source field (title from src1)
            dv.cursor_row = 0
            dv.cursor_col = 1
            await pilot.press("enter")
            assert node.result["title"] == "Alt"

            # Undo
            await pilot.press("u")
            assert node.result["title"] == "Original"

    @pytest.mark.asyncio()
    async def test_undo_noop_when_no_changes(self) -> None:
        from tapes.ui.tree_app import TreeApp

        node = FileNode(
            path=Path("/media/test.mkv"),
            result={"title": "Original"},
        )
        root = FolderNode(name="root", children=[node])
        model = TreeModel(root=root)
        app = TreeApp(model=model, template="{title} ({year}).{ext}")

        async with app.run_test() as pilot:
            # Press u without any changes - should not crash
            await pilot.press("u")
            assert node.result["title"] == "Original"


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

    def test_ignored_file_renders_with_space_marker(self) -> None:
        model = _expanded_model()
        view = _make_view(model)
        files = model.all_files()
        files[0].ignored = True
        output = view.render_tree()
        lines = output.split("\n")
        # file_a is at index 1 in flattened view
        file_a_line = lines[1]
        # Ignored file uses space as marker (indent + space + space + filename)
        # Should NOT have checkmark or circle
        assert "\u2713" not in file_a_line
        assert "\u25cb" not in file_a_line
        # The marker is a space, so after indent we get "  " + space_marker + " " + filename
        # Verify the line contains the filename but no other markers
        assert "file_a.mkv" in file_a_line

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
        from textual.widgets import Static

        from tapes.ui.tree_app import TreeApp

        model = _simple_model()
        app = TreeApp(model=model, template="{title} ({year}).{ext}")

        async with app.run_test() as pilot:
            await pilot.press("c")
            status = app.query_one("#status", Static)
            assert "No staged" in status.renderable  # type: ignore[operator]

    @pytest.mark.asyncio()
    async def test_commit_shows_confirmation(self) -> None:
        from textual.widgets import Static

        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        # Stage a file
        model.all_files()[0].staged = True
        app = TreeApp(model=model, template="{title} ({year}).{ext}")

        async with app.run_test() as pilot:
            await pilot.press("c")
            assert app._confirming_commit is True
            status = app.query_one("#status", Static)
            rendered = str(status.renderable)
            assert "1 file staged" in rendered
            assert "enter to confirm" in rendered

    @pytest.mark.asyncio()
    async def test_commit_enter_confirms_and_exits(self) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        model.all_files()[0].staged = True
        app = TreeApp(model=model, template="{title} ({year}).{ext}")

        async with app.run_test() as pilot:
            await pilot.press("c")
            assert app._confirming_commit is True
            await pilot.press("enter")
            # App should exit with staged files as result
            assert app.return_code is not None or app._exit

    @pytest.mark.asyncio()
    async def test_commit_escape_cancels(self) -> None:
        from textual.widgets import Static

        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        model.all_files()[0].staged = True
        app = TreeApp(model=model, template="{title} ({year}).{ext}")

        async with app.run_test() as pilot:
            await pilot.press("c")
            assert app._confirming_commit is True
            await pilot.press("escape")
            assert app._confirming_commit is False
            status = app.query_one("#status", Static)
            assert "staged" in status.renderable  # type: ignore[operator]

    @pytest.mark.asyncio()
    async def test_x_toggles_ignored(self) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, template="{title} ({year}).{ext}")

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
        from textual.widgets import Static

        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, template="{title} ({year}).{ext}")

        async with app.run_test() as pilot:
            # Move to file and ignore it
            await pilot.press("j")
            await pilot.press("x")
            status = app.query_one("#status", Static)
            assert "1 ignored" in status.renderable  # type: ignore[operator]


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

    def test_flat_mode_renders_relative_paths(self) -> None:
        model = _expanded_model()
        view = TreeView(
            model=model,
            template="{title} ({year}).{ext}",
            root_path=Path("/root"),
        )
        view.toggle_flat_mode()
        output = view.render_tree()
        # In flat mode with root_path, files show relative paths
        assert "folderA/file_a.mkv" in output
        assert "folderB/file_b.mkv" in output

    def test_tree_mode_renders_with_indentation(self) -> None:
        model = _expanded_model()
        view = _make_view(model)
        output = view.render_tree()
        lines = output.split("\n")
        # file_a.mkv should be indented (child of folderA)
        file_a_line = lines[1]
        assert file_a_line.startswith("  ")  # indented

    def test_flat_mode_no_indentation(self) -> None:
        model = _expanded_model()
        view = _make_view(model)
        view.toggle_flat_mode()
        output = view.render_tree()
        lines = output.split("\n")
        # No indentation in flat mode
        for line in lines:
            assert not line.startswith("  ")

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
        app = TreeApp(model=model, template="{title} ({year}).{ext}")

        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            assert not tv.flat_mode
            await pilot.press("grave_accent")
            assert tv.flat_mode
            await pilot.press("grave_accent")
            assert not tv.flat_mode


# ---------------------------------------------------------------------------
# Accept best source (M9) unit tests
# ---------------------------------------------------------------------------


class TestAcceptBestSource:
    def test_applies_highest_confidence_source(self) -> None:
        node = FileNode(
            path=Path("/test.mkv"),
            result={"title": "Old"},
            sources=[
                Source(name="src1", fields={"title": "Low", "year": 2000}, confidence=0.5),
                Source(name="src2", fields={"title": "High", "year": 2020}, confidence=0.9),
            ],
        )
        assert accept_best_source(node) is True
        assert node.result["title"] == "High"
        assert node.result["year"] == 2020

    def test_noop_when_no_sources(self) -> None:
        node = FileNode(path=Path("/test.mkv"), result={"title": "Original"})
        assert accept_best_source(node) is False
        assert node.result["title"] == "Original"

    def test_noop_when_all_zero_confidence(self) -> None:
        node = FileNode(
            path=Path("/test.mkv"),
            result={"title": "Original"},
            sources=[
                Source(name="src1", fields={"title": "Other"}, confidence=0.0),
            ],
        )
        assert accept_best_source(node) is False
        assert node.result["title"] == "Original"

    def test_skips_none_values(self) -> None:
        node = FileNode(
            path=Path("/test.mkv"),
            result={"title": "Keep", "year": 2000},
            sources=[
                Source(
                    name="src1",
                    fields={"title": "New", "year": None},
                    confidence=0.8,
                ),
            ],
        )
        accept_best_source(node)
        assert node.result["title"] == "New"
        assert node.result["year"] == 2000  # Not overwritten by None


@pytest.mark.skipif(not HAS_PILOT, reason="textual pilot not available")
class TestAcceptBestAsync:
    @pytest.mark.asyncio()
    async def test_a_key_applies_best_source_on_cursor(self) -> None:
        from tapes.ui.tree_app import TreeApp

        node = FileNode(
            path=Path("/media/test.mkv"),
            result={"title": "Old"},
            sources=[
                Source(name="TMDB", fields={"title": "New", "year": 2021}, confidence=0.9),
            ],
        )
        root = FolderNode(name="root", children=[node])
        model = TreeModel(root=root)
        app = TreeApp(model=model, template="{title} ({year}).{ext}")

        async with app.run_test() as pilot:
            await pilot.press("a")
            assert node.result["title"] == "New"
            assert node.result["year"] == 2021

    @pytest.mark.asyncio()
    async def test_a_key_applies_per_file_in_range(self) -> None:
        from tapes.ui.tree_app import TreeApp

        node1 = FileNode(
            path=Path("/media/a.mkv"),
            result={"title": "A"},
            sources=[
                Source(name="TMDB", fields={"title": "A2"}, confidence=0.8),
            ],
        )
        node2 = FileNode(
            path=Path("/media/b.mkv"),
            result={"title": "B"},
            sources=[
                Source(name="TMDB", fields={"title": "B2"}, confidence=0.7),
            ],
        )
        root = FolderNode(name="root", children=[node1, node2])
        model = TreeModel(root=root)
        app = TreeApp(model=model, template="{title} ({year}).{ext}")

        async with app.run_test() as pilot:
            # Select range over both files
            await pilot.press("v")
            await pilot.press("j")
            await pilot.press("a")
            assert node1.result["title"] == "A2"
            assert node2.result["title"] == "B2"

    @pytest.mark.asyncio()
    async def test_a_key_noop_in_detail(self) -> None:
        from tapes.ui.tree_app import TreeApp

        node = FileNode(
            path=Path("/media/test.mkv"),
            result={"title": "Old"},
            sources=[
                Source(name="TMDB", fields={"title": "New"}, confidence=0.9),
            ],
        )
        root = FolderNode(name="root", children=[node])
        model = TreeModel(root=root)
        app = TreeApp(model=model, template="{title} ({year}).{ext}")

        async with app.run_test() as pilot:
            # Enter detail view
            await pilot.press("enter")
            assert app._in_detail is True
            await pilot.press("a")
            # Should be no-op in detail view
            assert node.result["title"] == "Old"


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
        app = TreeApp(model=model, template="{title} ({year}).{ext}")

        async with app.run_test() as pilot:
            await pilot.press("slash")
            assert app._searching is True

    @pytest.mark.asyncio()
    async def test_typing_filters_items(self) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, template="{title} ({year}).{ext}")

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
        app = TreeApp(model=model, template="{title} ({year}).{ext}")

        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            original_count = tv.item_count
            await pilot.press("slash")
            await pilot.press("t", "o", "p")
            assert tv.item_count == 1
            await pilot.press("escape")
            assert app._searching is False
            assert tv.item_count == original_count

    @pytest.mark.asyncio()
    async def test_enter_keeps_filter(self) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, template="{title} ({year}).{ext}")

        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
            await pilot.press("slash")
            await pilot.press("t", "o", "p")
            await pilot.press("enter")
            assert app._searching is False
            # Filter remains active
            assert tv.item_count == 1

    @pytest.mark.asyncio()
    async def test_backspace_removes_last_char(self) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, template="{title} ({year}).{ext}")

        async with app.run_test() as pilot:
            tv = app.query_one(TreeView)
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
            result={"title": "Test"},
        )
        root = FolderNode(name="root", children=[node])
        model = TreeModel(root=root)
        app = TreeApp(model=model, template="{title} ({year}).{ext}")

        async with app.run_test() as pilot:
            # Enter detail view
            await pilot.press("enter")
            assert app._in_detail is True
            await pilot.press("slash")
            assert app._searching is False
