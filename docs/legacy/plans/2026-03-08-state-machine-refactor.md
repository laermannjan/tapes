# TreeApp State Machine Refactor

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace 4 independent boolean flags with a single `AppMode` enum to eliminate impossible states.

**Architecture:** Add an `AppMode` enum with 5 values (TREE, DETAIL, COMMIT, HELP, SEARCHING). Replace `_in_detail`, `_in_commit`, `_in_help`, `_searching` with one `_mode` field. Update all guard clauses and show/hide methods. Update tests to check `app.mode` instead of boolean flags.

**Tech Stack:** Python enum, Textual, pytest

---

### Task 1: Add AppMode enum and replace boolean flags

**Files:**
- Modify: `tapes/ui/tree_app.py`

**Step 1: Add the enum and a `mode` property**

After the `DETAIL_CHROME_LINES` constant and before `_NodeSnapshot`, add:

```python
from enum import Enum

class AppMode(Enum):
    TREE = "tree"
    DETAIL = "detail"
    COMMIT = "commit"
    HELP = "help"
    SEARCHING = "searching"
```

Add the `Enum` import to the existing `from enum import Enum` at the top (or
add a new import line). Export `AppMode` from the module.

**Step 2: Replace the 4 boolean flags in `__init__`**

Replace:
```python
self._in_detail = False
self._searching = False
self._in_commit = False
self._in_help = False
```

With:
```python
self._mode = AppMode.TREE
```

Add a read-only property for external access:
```python
@property
def mode(self) -> AppMode:
    return self._mode
```

**Step 3: Update all show/hide methods**

Each `_show_*` / `_hide_*` method sets a boolean. Replace with enum assignment:

| Method | Old | New |
|--------|-----|-----|
| `_show_detail` | `self._in_detail = True` | `self._mode = AppMode.DETAIL` |
| `_show_detail_multi` | `self._in_detail = True` | `self._mode = AppMode.DETAIL` |
| `_show_tree` | `self._in_detail = False` | `self._mode = AppMode.TREE` |
| `_show_commit` | `self._in_commit = True` | `self._mode = AppMode.COMMIT` |
| `_hide_commit` | `self._in_commit = False` | `self._mode = AppMode.TREE` |
| `_show_help` | `self._in_help = True` | `self._mode = AppMode.HELP` |
| `_hide_help` | `self._in_help = False` | `self._mode = AppMode.TREE` |
| `action_start_search` | `self._searching = True` | `self._mode = AppMode.SEARCHING` |
| `_finish_search` | `self._searching = False` | `self._mode = AppMode.TREE` |

**Step 4: Run tests to verify**

Run: `uv run pytest tests/test_ui/test_tree_app.py -x -q`
Expected: Many failures (tests still check old boolean flags). That's expected -- Task 2 fixes them.

**Step 5: Commit**

```
refactor: add AppMode enum, replace boolean state flags (I34, step 1)
```

---

### Task 2: Update all guard clauses in action methods

**Files:**
- Modify: `tapes/ui/tree_app.py`

Replace every guard clause pattern. Here is the complete mapping:

**Pattern A: `if self._in_commit or self._in_help: return`**
Replace with: `if self._mode in (AppMode.COMMIT, AppMode.HELP): return`

Appears in: `action_cursor_down`, `action_cursor_up`, `action_cursor_left`,
`action_cursor_right`, `action_toggle_staged`, `action_cycle_op`,
`action_apply_all_clear`, `action_range_select`, `action_toggle_ignored`,
`action_refresh_query`, `action_clear_field`, `action_reset_guessit`,
`action_start_search`, `action_collapse_all`, `action_expand_all`,
`action_toggle_flat`.

Use a module-level frozenset for readability:
```python
_MODAL_MODES = frozenset({AppMode.COMMIT, AppMode.HELP})
```
Then guards become: `if self._mode in _MODAL_MODES: return`

**Pattern B: `if self._in_detail:`**
Replace with: `if self._mode == AppMode.DETAIL:`

**Pattern C: `if not self._in_detail:`**
Replace with: `if self._mode != AppMode.DETAIL:`

**Pattern D: `if self._searching:`**
Replace with: `if self._mode == AppMode.SEARCHING:`

**Pattern E: `if not self._searching:`**
Replace with: `if self._mode != AppMode.SEARCHING:`

**Specific action methods and their complete guard logic:**

`action_cursor_down` / `action_cursor_up`:
```python
if self._mode in _MODAL_MODES:
    return
if self._mode == AppMode.DETAIL:
    ...  # detail cursor
else:
    ...  # tree cursor
```

`action_cursor_left` / `action_cursor_right`:
```python
if self._mode in _MODAL_MODES:
    return
if self._mode == AppMode.DETAIL:
    ...  # cycle source
```

`action_toggle_staged`, `action_cycle_op`, `action_range_select`,
`action_toggle_ignored`, `action_start_search`, `action_collapse_all`,
`action_expand_all`, `action_toggle_flat`:
```python
if self._mode != AppMode.TREE:
    return
```
(These are tree-only actions. The old code checked `_in_commit or _in_help`
then `_in_detail` separately, but the effect is the same: only runs in TREE.)

`action_toggle_or_enter`:
```python
if self._mode == AppMode.COMMIT:
    ...  # confirm commit
elif self._mode == AppMode.DETAIL:
    ...  # start edit
elif self._mode == AppMode.TREE:
    ...  # toggle folder or open detail
```
(No action in HELP or SEARCHING.)

`action_apply_all_clear`:
```python
if self._mode != AppMode.DETAIL:
    return
...
```

`action_cancel`:
```python
if self._mode == AppMode.SEARCHING:
    self._finish_search(keep_filter=False)
elif self._mode == AppMode.HELP:
    self._hide_help()
elif self._mode == AppMode.COMMIT:
    self._hide_commit()
elif self._mode == AppMode.DETAIL:
    ...  # cancel edit or discard
elif self._mode == AppMode.TREE:
    ...  # clear range
```

`action_commit`:
```python
if self._mode == AppMode.DETAIL:
    self._confirm_detail()
    return
if self._mode == AppMode.COMMIT:
    ...  # confirm + do commit
    return
if self._mode != AppMode.TREE:
    return
...  # show commit
```

`action_refresh_query`:
```python
if self._mode in _MODAL_MODES:
    return
if self._mode == AppMode.DETAIL:
    ...
else:
    ...
```

`action_clear_field`, `action_reset_guessit`:
```python
if self._mode != AppMode.DETAIL:
    return
```

`action_toggle_help`:
```python
if self._mode == AppMode.HELP:
    self._hide_help()
else:
    self._show_help()
```
(Unchanged -- help can be toggled from any mode.)

**Update `on_key`:**

ctrl+c hint display:
```python
if self._mode == AppMode.DETAIL:
    ...
elif self._mode == AppMode.COMMIT:
    ...
else:
    ...
```

shift+tab:
```python
if event.key == "shift+tab" and self._mode not in (AppMode.DETAIL, AppMode.SEARCHING):
    if self._mode == AppMode.COMMIT:
        ...
    else:
        ...
```

Search mode:
```python
if self._mode != AppMode.SEARCHING:
    return
```

**Update `_on_tmdb_progress` and `_on_tmdb_done`:**
```python
if self._mode == AppMode.DETAIL:
    ...
else:
    ...
```

**Update `_update_footer`:**
```python
if self._mode == AppMode.SEARCHING:
    bar.hint_text = "enter to confirm ..."
else:
    bar.hint_text = "space to stage ..."
```

**Step 2: Run tests**

Run: `uv run pytest tests/test_ui/test_tree_app.py -x -q`
Expected: Failures from tests still checking old boolean attributes.

**Step 3: Commit**

```
refactor: replace all boolean guards with AppMode checks (I34, step 2)
```

---

### Task 3: Update tests

**Files:**
- Modify: `tests/test_ui/test_tree_app.py`

**Step 1: Import AppMode**

Add to imports:
```python
from tapes.ui.tree_app import AppMode
```

**Step 2: Replace all boolean flag assertions**

| Old | New |
|-----|-----|
| `app._in_detail` / `app._in_detail is True` | `app.mode == AppMode.DETAIL` |
| `not app._in_detail` / `app._in_detail is False` | `app.mode != AppMode.DETAIL` |
| `app._in_commit` | `app.mode == AppMode.COMMIT` |
| `not app._in_commit` | `app.mode != AppMode.COMMIT` |
| `app._in_help` | `app.mode == AppMode.HELP` |
| `not app._in_help` | `app.mode != AppMode.HELP` |
| `app._searching is True` | `app.mode == AppMode.SEARCHING` |
| `app._searching is False` | `app.mode != AppMode.SEARCHING` |

Specific test methods to update:

- `test_commit_blocked_when_no_staged`: `assert not app._in_commit` -> `assert app.mode == AppMode.TREE`
- `test_c_shows_commit_view`: `assert app._in_commit` -> `assert app.mode == AppMode.COMMIT`
- `test_commit_esc_cancels`: both assertions
- `test_question_mark_toggles_help`: `app._in_help` assertions
- `test_esc_discards_changes`: `app._in_detail` assertions
- `test_c_confirms_changes`: `app._in_detail` assertions
- `test_esc_during_edit_cancels_edit_not_detail`: `app._in_detail` assertions
- `test_slash_enters_search_mode`: `app._searching` assertion
- `test_escape_clears_filter`: `app._searching` assertion
- `test_enter_keeps_filter`: `app._searching` assertion
- `test_search_noop_in_detail`: `app._in_detail` and `app._searching` assertions
- `test_bottom_bar_hidden_in_detail`: `app._in_detail` is not directly checked but enter/escape transitions are tested

Note: `app._search_query` stays as-is (it's search state, not mode state).

**Step 3: Add a test for mode transitions**

Add a new test class:

```python
class TestAppModeTransitions:
    @pytest.mark.asyncio()
    async def test_initial_mode_is_tree(self) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)
        async with app.run_test():
            assert app.mode == AppMode.TREE

    @pytest.mark.asyncio()
    async def test_enter_detail_and_back(self) -> None:
        from tapes.ui.tree_app import TreeApp

        node = FileNode(path=Path("/media/test.mkv"), result={"title": "Test"})
        root = FolderNode(name="root", children=[node])
        model = TreeModel(root=root)
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)
        async with app.run_test() as pilot:
            assert app.mode == AppMode.TREE
            await pilot.press("enter")
            assert app.mode == AppMode.DETAIL
            await pilot.press("escape")
            assert app.mode == AppMode.TREE

    @pytest.mark.asyncio()
    async def test_commit_and_cancel(self) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        model.all_files()[0].staged = True
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)
        async with app.run_test() as pilot:
            assert app.mode == AppMode.TREE
            await pilot.press("c")
            assert app.mode == AppMode.COMMIT
            await pilot.press("escape")
            assert app.mode == AppMode.TREE

    @pytest.mark.asyncio()
    async def test_help_and_back(self) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)
        async with app.run_test() as pilot:
            assert app.mode == AppMode.TREE
            await pilot.press("question_mark")
            assert app.mode == AppMode.HELP
            await pilot.press("question_mark")
            assert app.mode == AppMode.TREE

    @pytest.mark.asyncio()
    async def test_search_and_cancel(self) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _expanded_model()
        app = TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)
        async with app.run_test() as pilot:
            assert app.mode == AppMode.TREE
            await pilot.press("slash")
            assert app.mode == AppMode.SEARCHING
            await pilot.press("escape")
            assert app.mode == AppMode.TREE
```

**Step 4: Run all tests**

Run: `uv run pytest tests/test_ui/test_tree_app.py -v`
Expected: All pass.

Run: `uv run pytest -x -q`
Expected: All 467 tests pass.

**Step 5: Commit**

```
refactor: update tests for AppMode enum (I34, step 3)
```

---

### Task 4: Update issues.md and CLAUDE.md

**Files:**
- Modify: `docs/issues.md` (mark I34 as done)

**Step 1: Update I34 status**

Change I34 to `done` with summary: "Replaced 4 boolean flags with `AppMode`
enum. Impossible states eliminated by construction."

**Step 2: Commit**

```
docs: mark I34 as done
```
