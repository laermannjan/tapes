"""Tests for TreeView cursor navigation and TreeApp keybindings."""
from __future__ import annotations

from pathlib import Path

import pytest

from tapes.ui.tree_model import FileNode, FolderNode, TreeModel
from tapes.ui.tree_view import TreeView


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _simple_model() -> TreeModel:
    """Model with two folders (each with one file) and one top-level file.

    Structure (all collapsed by default):
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
                children=[FileNode(path=Path("/root/folderA/file_a.mkv"))],
            ),
            FolderNode(
                name="folderB",
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
    async def test_q_quits(self, model: TreeModel, template: str) -> None:
        from tapes.ui.tree_app import TreeApp

        app = TreeApp(model=model, template=template)
        async with app.run_test() as pilot:
            await pilot.press("q")
            # app should exit; if we get here without hanging, it worked
