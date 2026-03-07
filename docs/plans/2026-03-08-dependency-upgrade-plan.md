# Dependency Upgrade Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade textual 3 → 8, rich 13 → 14, pytest-asyncio 0.x → 1.x, refactor modals to ModalScreen, and replace manual focus styling with CSS pseudo-classes.

**Architecture:** Bump dependencies first, then refactor outward from widgets (focus styling) through screens (modals). Each task is self-contained with its own tests and commit.

**Tech Stack:** Python 3.11+, Textual 8, Rich 14, pytest + pytest-asyncio 1.x, uv

---

### Task 1: Bump Dependencies

**Files:**
- Modify: `pyproject.toml`
- Verify: `uv.lock` (auto-generated)

**Step 1: Update version constraints in pyproject.toml**

Change three dependency ranges:

```python
# In [project] dependencies:
"textual>=8,<9",     # was >=3,<4
"rich>=14,<15",      # was >=13,<14

# In [dependency-groups] dev:
"pytest-asyncio>=1,<2",  # was >=0.25,<1
```

**Step 2: Run uv sync**

Run: `uv sync`
Expected: resolves and installs textual 8.x, rich 14.x, pytest-asyncio 1.x

**Step 3: Verify installed versions**

Run: `uv run python -c "import textual; print(textual.__version__)"`
Expected: 8.x.x

Run: `uv run python -c "import rich; print(rich.__version__)"`
Expected: 14.x.x

Run: `uv run python -c "import pytest_asyncio; print(pytest_asyncio.__version__)"`
Expected: 1.x.x

**Step 4: Run all tests**

Run: `uv run pytest -x -q`
Expected: 467 tests pass (or close — some may fail due to API changes; note failures for the next step)

**Step 5: Fix any immediate breakage**

Likely issues:
- `textual-ansi` theme might be renamed or removed. Check the `on_mount` in `tree_app.py:189-192`. The try/except already guards this, so tests should not fail, but verify the theme name is still valid. If not, try `"ansi"` or remove the theme line entirely (the default theme is fine).
- Rich 14 markup escaping changed, but the project uses `Text()` objects, never string markup. No code changes expected.

**Step 6: Commit**

```
git add pyproject.toml uv.lock
git commit -m "build: bump textual 8, rich 14, pytest-asyncio 1.x"
```

---

### Task 2: Focus Styling via CSS Pseudo-Classes

Replace the manual `active` reactive + `watch_active()` pattern on TreeView and DetailView with Textual's built-in `:focus` / `:blur` CSS pseudo-classes.

**Files:**
- Modify: `tapes/ui/tree_view.py` (delete `active` reactive, delete `watch_active`)
- Modify: `tapes/ui/detail_view.py` (delete `active` reactive, delete `watch_active`)
- Modify: `tapes/ui/tree_app.py` (delete `tv.active = ...` / `detail.active = ...` calls, update CSS)
- Modify: `tests/test_ui/test_border_rendering.py` (delete tests for watch_active)
- Modify: `tests/test_ui/test_tree_app.py` (remove `tv.active` assertion)

**Step 1: Write a failing test for :focus styling**

In `tests/test_ui/test_border_rendering.py`, replace the two `test_*_active_toggles_css_classes` tests with a test that verifies the CSS rules exist:

```python
class TestFocusStyling:
    def test_css_has_focus_rules_for_tree_view(self) -> None:
        """App CSS uses :focus pseudo-class for TreeView border."""
        from tapes.ui.tree_app import TreeApp
        css = TreeApp.CSS
        assert "TreeView:focus" in css

    def test_css_has_focus_rules_for_detail_view(self) -> None:
        """App CSS uses :focus pseudo-class for DetailView border."""
        from tapes.ui.tree_app import TreeApp
        css = TreeApp.CSS
        assert "DetailView:focus" in css
```

Run: `uv run pytest tests/test_ui/test_border_rendering.py::TestFocusStyling -v`
Expected: FAIL (CSS does not yet contain `:focus` rules)

**Step 2: Update TreeApp CSS**

In `tapes/ui/tree_app.py`, replace the CSS rules for TreeView/DetailView active/inactive styling:

Remove:
```css
TreeView.-inactive {
    border: round #555555;
}
```
```css
DetailView.-active {
    border: round #7AB8FF;
}
```

The existing default rules already set the inactive border color. Add `:focus` overrides:

```css
TreeView {
    height: 1fr;
    border: round #555555;
    padding: 0 1;
}
TreeView:focus {
    border: round #7AB8FF;
}
DetailView {
    height: 5;
    border: round #555555;
    padding: 0 1;
}
DetailView:focus {
    border: round #7AB8FF;
}
```

Note: TreeView's default border changes from `#7AB8FF` to `#555555` (was only cyan because it was active by default). Focus gives it cyan. This matches the old behavior since TreeView receives focus on app mount.

**Step 3: Run the new tests**

Run: `uv run pytest tests/test_ui/test_border_rendering.py::TestFocusStyling -v`
Expected: PASS

**Step 4: Remove `active` reactive and `watch_active` from TreeView**

In `tapes/ui/tree_view.py`:
- Delete line 24: `active: reactive[bool] = reactive(True)`
- Delete lines 294-302: the entire `watch_active` method

**Step 5: Remove `active` reactive and `watch_active` from DetailView**

In `tapes/ui/detail_view.py`:
- Delete line 42: `active: reactive[bool] = reactive(False)`
- Delete lines 122-130: the entire `watch_active` method

**Step 6: Remove `tv.active` and `detail.active` assignments from TreeApp**

In `tapes/ui/tree_app.py`, delete these lines:
- Line 242: `tv.active = False` (in `_show_detail`)
- Line 246: `detail.active = True` (in `_show_detail`)
- Line 258: `tv.active = False` (in `_show_detail_multi`)
- Line 262: `detail.active = True` (in `_show_detail_multi`)
- Line 281: `detail.active = False` (in `_show_tree`)
- Line 283: `tv.active = True` (in `_show_tree`)

**Step 7: Delete old tests and fix assertions**

In `tests/test_ui/test_border_rendering.py`:
- Delete `test_tree_active_toggles_css_classes` (entire method)
- Delete `test_detail_active_toggles_css_classes` (entire method)

In `tests/test_ui/test_tree_app.py`, in `TestVisualIntegration::test_launch_tree_view_visible_with_border`:
- Delete line 1451: `assert tv.active is True`

**Step 8: Run all tests**

Run: `uv run pytest -x -q`
Expected: all pass

**Step 9: Commit**

```
git add tapes/ui/tree_view.py tapes/ui/detail_view.py tapes/ui/tree_app.py tests/test_ui/test_border_rendering.py tests/test_ui/test_tree_app.py
git commit -m "refactor: replace manual focus styling with :focus CSS pseudo-class"
```

---

### Task 3: Refactor HelpOverlay to ModalScreen

Convert `HelpOverlay` from a `Middle` subclass (always mounted, toggled via CSS classes) to a `ModalScreen` subclass (pushed/popped on demand).

**Files:**
- Rewrite: `tapes/ui/help_overlay.py` (HelpOverlay → HelpScreen)
- Modify: `tapes/ui/tree_app.py` (push/pop instead of class toggle, remove from compose/CSS)
- Modify: `tests/test_ui/test_help_overlay.py` (update integration tests)
- Modify: `tests/test_ui/test_tree_app.py` (update help toggle test)

**Step 1: Write failing tests for HelpScreen**

In `tests/test_ui/test_help_overlay.py`, replace `TestHelpOverlayToggle` with:

```python
from textual.screen import ModalScreen


class TestHelpScreen:
    """Test that HelpScreen is a proper ModalScreen."""

    def test_is_modal_screen(self) -> None:
        assert issubclass(HelpScreen, ModalScreen)

    def test_has_dismiss_bindings(self) -> None:
        """HelpScreen should handle escape and ? to dismiss."""
        keys = [b.key for b in HelpScreen.BINDINGS]
        assert "escape" in keys
        assert "question_mark" in keys
```

Update the import at the top of the file from `HelpOverlay` to `HelpScreen`:

```python
from tapes.ui.help_overlay import HelpScreen, _build_help_text
```

Run: `uv run pytest tests/test_ui/test_help_overlay.py::TestHelpScreen -v`
Expected: FAIL (HelpScreen does not exist)

**Step 2: Rewrite help_overlay.py**

Replace the `HelpOverlay` class with `HelpScreen`:

```python
"""Help screen showing keybinding reference."""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Static

from tapes.ui.tree_render import MUTED


# _build_help_text() stays exactly as-is (lines 17-86 unchanged)


class HelpScreen(ModalScreen):
    """Modal screen showing keybinding reference."""

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    HelpScreen #help-panel {
        width: 64;
        height: auto;
        max-height: 90%;
        border: round #7AB8FF;
        padding: 1 2;
        background: #1a1a2e;
    }
    """

    BINDINGS = [
        Binding("question_mark", "dismiss", "Close", show=False),
        Binding("escape", "dismiss", "Close", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Static(_build_help_text(), id="help-panel")

    def on_key(self, event: Key) -> None:
        """Block all unhandled keys from reaching the app."""
        event.stop()
```

Note: no more `Center`/`Middle` containers, no `can_focus`, no `TYPE_CHECKING` guard. The `align: center middle` on the screen itself centers the child.

**Step 3: Run the new tests**

Run: `uv run pytest tests/test_ui/test_help_overlay.py -v`
Expected: PASS (both TestHelpTextContent and TestHelpScreen classes)

**Step 4: Update TreeApp to push/pop HelpScreen**

In `tapes/ui/tree_app.py`:

Update import:
```python
from tapes.ui.help_overlay import HelpScreen  # was HelpOverlay
```

In `__init__`, delete:
```python
self._help_visible = False
```

In `compose()`, delete:
```python
yield HelpOverlay(id="help")
```

Remove these CSS rules from the `CSS` string:
```css
HelpOverlay {
    display: none;
    layer: overlay;
    dock: top;
    width: 100%;
    height: 100%;
}
HelpOverlay.visible {
    display: block;
}
```

If the `Screen { layers: default overlay; }` rule is only used by the modals, remove it too. It is only used by HelpOverlay and CommitModal, but CommitModal still uses it at this point. Remove the `Screen { layers: ... }` rule in Task 4 when both modals are converted.

Replace `action_toggle_help`:
```python
def action_toggle_help(self) -> None:
    """Show the help screen."""
    self.push_screen(HelpScreen())
```

In `on_key`, delete the `_help_visible` section (lines 548-553):
```python
# DELETE this block:
if self._help_visible:
    if event.key not in ("question_mark", "escape"):
        event.prevent_default()
        event.stop()
    return
```

In `action_cancel`, delete the `_help_visible` check (lines 395-397):
```python
# DELETE this block:
if self._help_visible:
    self.action_toggle_help()
    return
```

Also remove the `.modal-open` CSS rule if you can. But CommitModal still uses it at this point. Remove it in Task 4. For now, just leave it.

**Step 5: Update help overlay tests**

In `tests/test_ui/test_help_overlay.py`, delete the old `TestHelpOverlayToggle` class entirely (the `test_help_initially_hidden`, `test_help_binding_registered`, `test_help_overlay_in_compose` tests). The binding test is still valuable, move it into `TestHelpScreen`:

```python
class TestHelpScreen:
    def test_is_modal_screen(self) -> None:
        assert issubclass(HelpScreen, ModalScreen)

    def test_has_dismiss_bindings(self) -> None:
        keys = [b.key for b in HelpScreen.BINDINGS]
        assert "escape" in keys
        assert "question_mark" in keys

    def test_help_binding_registered_on_app(self) -> None:
        """Verify the question_mark binding is present in TreeApp.BINDINGS."""
        keys = [b.key for b in TreeApp.BINDINGS]
        assert "question_mark" in keys
```

**Step 6: Update tree_app.py help toggle test**

In `tests/test_ui/test_tree_app.py`, rewrite `TestVisualIntegration::test_question_mark_toggles_help`:

```python
@pytest.mark.asyncio()
async def test_question_mark_toggles_help(self) -> None:
    """Pressing ? pushes HelpScreen, pressing ? again dismisses it."""
    from tapes.ui.help_overlay import HelpScreen
    from tapes.ui.tree_app import TreeApp

    model = _expanded_model()
    app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

    async with app.run_test() as pilot:
        # No modal initially
        assert len(app.screen_stack) == 1

        # Show help
        await pilot.press("question_mark")
        assert len(app.screen_stack) == 2
        assert isinstance(app.screen, HelpScreen)

        # Dismiss help (? is bound to dismiss on HelpScreen)
        await pilot.press("question_mark")
        assert len(app.screen_stack) == 1
```

**Step 7: Run all tests**

Run: `uv run pytest -x -q`
Expected: all pass

**Step 8: Commit**

```
git add tapes/ui/help_overlay.py tapes/ui/tree_app.py tests/test_ui/test_help_overlay.py tests/test_ui/test_tree_app.py
git commit -m "refactor: convert HelpOverlay to ModalScreen"
```

---

### Task 4: Refactor CommitModal to ModalScreen

Convert `CommitModal` from a `Middle` subclass to a `ModalScreen[bool]` that dismisses with `True` (confirm) or `False` (cancel).

**Files:**
- Rewrite: `tapes/ui/commit_modal.py` (CommitModal → CommitScreen)
- Modify: `tapes/ui/tree_app.py` (push_screen with callback, remove from compose/CSS, clean up on_key)
- Modify: `tests/test_ui/test_commit_modal.py` (update integration tests)
- Modify: `tests/test_ui/test_tree_app.py` (update commit tests)

**Step 1: Write failing tests for CommitScreen**

In `tests/test_ui/test_commit_modal.py`, replace `TestCommitModalIntegration` with:

```python
from textual.screen import ModalScreen


class TestCommitScreen:
    """Test that CommitScreen is a proper ModalScreen."""

    def test_is_modal_screen(self) -> None:
        assert issubclass(CommitScreen, ModalScreen)

    def test_has_confirm_and_cancel_bindings(self) -> None:
        keys = [b.key for b in CommitScreen.BINDINGS]
        assert "y" in keys
        assert "n" in keys
        assert "escape" in keys

    def test_commit_binding_registered_on_app(self) -> None:
        """Verify the c binding is present in TreeApp.BINDINGS."""
        keys = [b.key for b in TreeApp.BINDINGS]
        assert "c" in keys
```

Update import:
```python
from tapes.ui.commit_modal import CommitScreen, build_commit_text
```

Run: `uv run pytest tests/test_ui/test_commit_modal.py::TestCommitScreen -v`
Expected: FAIL

**Step 2: Rewrite commit_modal.py**

Replace the `CommitModal` class with `CommitScreen`:

```python
"""Commit confirmation screen listing staged files with destinations."""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Static

from tapes.ui.tree_render import MUTED, render_dest


# build_commit_text() stays exactly as-is (lines 17-63 unchanged)


class CommitScreen(ModalScreen[bool]):
    """Modal screen showing commit confirmation. Dismisses with True/False."""

    DEFAULT_CSS = """
    CommitScreen {
        align: center middle;
    }
    CommitScreen #commit-panel {
        width: 80%;
        max-width: 100;
        min-width: 50;
        height: auto;
        max-height: 80%;
        border: round #7AB8FF;
        padding: 1 2;
        background: #1a1a2e;
    }
    """

    BINDINGS = [
        Binding("y", "confirm", "Confirm", show=False),
        Binding("n", "cancel", "Cancel", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(
        self,
        staged_files: list[tuple[str, str | None]],
        operation: str,
    ) -> None:
        super().__init__()
        self._staged_files = staged_files
        self._operation = operation

    def compose(self) -> ComposeResult:
        yield Static(
            build_commit_text(self._staged_files, self._operation),
            id="commit-panel",
        )

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)

    def on_key(self, event: Key) -> None:
        """Block all unhandled keys from reaching the app."""
        event.stop()
```

Note: no more `Center`/`Middle` containers, no `can_focus`, no `update_content` method, no `**kwargs`.

**Step 3: Run the new tests**

Run: `uv run pytest tests/test_ui/test_commit_modal.py -v`
Expected: PASS

**Step 4: Update TreeApp for CommitScreen**

In `tapes/ui/tree_app.py`:

Update import:
```python
from tapes.ui.commit_modal import CommitScreen  # was CommitModal
```

In `__init__`, delete:
```python
self._commit_visible = False
```

In `compose()`, delete:
```python
yield CommitModal(id="commit-modal")
```

Remove ALL remaining modal CSS rules from the `CSS` string:
```css
Screen {
    layers: default overlay;
}
```
```css
CommitModal {
    display: none;
    layer: overlay;
    dock: top;
    width: 100%;
    height: 100%;
}
CommitModal.visible {
    display: block;
}
```
```css
.modal-open TreeView,
.modal-open DetailView {
    opacity: 0.3;
}
```

Replace `action_commit`:
```python
def action_commit(self) -> None:
    if self._in_detail:
        return
    tv = self.query_one(TreeView)
    if tv.staged_count == 0:
        tv.set_status("No staged files to commit")
        return
    from tapes.ui.tree_render import compute_dest, select_template

    staged = [f for f in self.model.all_files() if f.staged]
    staged_files: list[tuple[str, str | None]] = []
    for node in staged:
        tmpl = select_template(node, self.movie_template, self.tv_template)
        dest = compute_dest(node, tmpl)
        staged_files.append((node.path.name, dest))

    self.push_screen(
        CommitScreen(staged_files, self.config.library.operation),
        callback=self._on_commit_result,
    )

def _on_commit_result(self, confirmed: bool) -> None:
    """Handle commit screen dismissal."""
    if confirmed:
        self._do_commit()
    else:
        self._update_footer()
```

Delete these methods entirely:
- `_show_commit_modal`
- `_hide_commit_modal`

In `on_key`, delete the `_commit_visible` section (lines 555-563):
```python
# DELETE this block:
if self._commit_visible:
    event.prevent_default()
    event.stop()
    if event.character == "y":
        self._do_commit()
    elif event.character == "n" or event.key == "escape":
        self._hide_commit_modal()
        self._update_footer()
    return
```

In `action_cancel`, delete the `_commit_visible` check (lines 401-404):
```python
# DELETE this block:
if self._commit_visible:
    self._hide_commit_modal()
    self._update_footer()
    return
```

**Step 5: Delete old commit modal integration tests**

In `tests/test_ui/test_commit_modal.py`, delete the entire `TestCommitModalIntegration` class. Its tests (`test_commit_modal_initially_hidden`, `test_commit_modal_in_compose`, `test_commit_binding_registered`, `test_css_contains_modal_rules`) test the old pattern. The binding check is already covered in `TestCommitScreen`.

Also delete `TestCommitModalWidget::test_instantiation` since CommitModal no longer exists. Keep `test_default_empty` since it tests `build_commit_text` which is unchanged.

**Step 6: Rewrite commit tests in test_tree_app.py**

In `tests/test_ui/test_tree_app.py`, rewrite `TestCommitAction`:

```python
class TestCommitAction:
    @pytest.mark.asyncio()
    async def test_commit_blocked_when_no_staged(self) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _simple_model()
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            await pilot.press("c")
            tv = app.query_one(TreeView)
            assert "No staged" in tv._status_text
            # No screen pushed
            assert len(app.screen_stack) == 1

    @pytest.mark.asyncio()
    async def test_commit_shows_confirmation(self) -> None:
        from tapes.ui.commit_modal import CommitScreen
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        model.all_files()[0].staged = True
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            await pilot.press("c")
            assert len(app.screen_stack) == 2
            assert isinstance(app.screen, CommitScreen)

    @pytest.mark.asyncio()
    async def test_commit_y_confirms_and_exits(self) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        model.all_files()[0].staged = True
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            await pilot.press("c")
            assert len(app.screen_stack) == 2
            await pilot.press("y")
            # App should exit after commit
            assert app.return_code is not None or app._exit

    @pytest.mark.asyncio()
    async def test_commit_escape_cancels(self) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        model.all_files()[0].staged = True
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)

        async with app.run_test() as pilot:
            await pilot.press("c")
            assert len(app.screen_stack) == 2
            await pilot.press("escape")
            # Back to main screen
            assert len(app.screen_stack) == 1
```

**Step 7: Run all tests**

Run: `uv run pytest -x -q`
Expected: all pass

**Step 8: Commit**

```
git add tapes/ui/commit_modal.py tapes/ui/tree_app.py tests/test_ui/test_commit_modal.py tests/test_ui/test_tree_app.py
git commit -m "refactor: convert CommitModal to ModalScreen"
```

---

### Task 5: Remove Redundant .refresh() Calls

Textual's `reactive` auto-repaints by default. Watchers that only call `self.refresh()` are redundant.

**Files:**
- Modify: `tapes/ui/tree_view.py`
- Modify: `tapes/ui/detail_view.py`

**Step 1: Run all tests (baseline)**

Run: `uv run pytest -x -q`
Expected: all pass

**Step 2: Clean up TreeView watcher**

In `tapes/ui/tree_view.py`, `watch_cursor_index` (lines 304-307):

Change from:
```python
def watch_cursor_index(self) -> None:
    """React to cursor changes by scrolling and refreshing."""
    self._scroll_to_cursor()
    self.refresh()
```

To:
```python
def watch_cursor_index(self) -> None:
    """Keep cursor visible in viewport when index changes."""
    self._scroll_to_cursor()
```

**Step 3: Clean up DetailView watchers**

In `tapes/ui/detail_view.py`:

Delete `watch_cursor_row` entirely (lines 456-458):
```python
# DELETE - reactive auto-repaints
def watch_cursor_row(self) -> None:
    """React to cursor row changes."""
    self.refresh()
```

Delete `watch_source_index` entirely (lines 460-462):
```python
# DELETE - reactive auto-repaints
def watch_source_index(self) -> None:
    """React to source index changes."""
    self.refresh()
```

**Step 4: Run all tests**

Run: `uv run pytest -x -q`
Expected: all pass (Textual's auto-repaint handles the refresh)

**Step 5: Commit**

```
git add tapes/ui/tree_view.py tapes/ui/detail_view.py
git commit -m "refactor: remove redundant refresh() calls from reactive watchers"
```

---

### Task 6: Final Verification

**Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: all tests pass

**Step 2: Verify TUI launches**

Run: `uv run tapes --help`
Expected: CLI help output renders correctly

**Step 3: Check for stale imports**

Search for any remaining references to removed symbols:

- `HelpOverlay` should not appear anywhere except `help_overlay.py` (as a comment if at all)
- `CommitModal` should not appear anywhere except `commit_modal.py`
- `_help_visible` should not appear anywhere
- `_commit_visible` should not appear anywhere
- `modal-open` should not appear anywhere
- `watch_active` should not appear in tree_view.py or detail_view.py

Run: `grep -rn "HelpOverlay\|CommitModal\|_help_visible\|_commit_visible\|modal-open" tapes/ tests/`
Expected: no matches (or only in comments/commit history)

**Step 4: Update CLAUDE.md current status**

Update the "Current status" section in `CLAUDE.md` to reflect:
- textual 8, rich 14
- Modals use ModalScreen
- Remove mention of "upgrade textual from v3 to v8" from Next up

**Step 5: Commit**

```
git add CLAUDE.md
git commit -m "docs: update status after dependency upgrade"
```
