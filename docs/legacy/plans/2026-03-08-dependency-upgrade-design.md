# Dependency Upgrade: Textual 8, Rich 14, pytest-asyncio 1.x

Date: 2026-03-08

## Problem

Tapes pins `textual>=3,<4` (installed: 3.7.1), five major versions behind
the current release (8.0.2). Textual 8 requires `rich>=14.2.0`, but tapes
pins `rich>=13,<14`. The project also pins `pytest-asyncio>=0.25,<1`,
one major version behind 1.3.0.

The modals (HelpOverlay, CommitModal) reimplement functionality that
Textual provides natively via `ModalScreen`. The current layer-based
approach does not work reliably. Focus styling uses manual CSS class
toggling that `:focus`/`:blur` pseudo-classes replace entirely.

## Scope

1. Bump textual, rich, and pytest-asyncio to their latest major versions.
2. Refactor modals from custom `Middle` subclasses to `ModalScreen`.
3. Replace manual focus styling with CSS pseudo-classes.
4. Remove redundant `.refresh()` calls from reactive watchers.

Out of scope: inline editing refactor, ScrollableContainer migration,
Input widget integration, StatusFooter replacement.

## Dependency Changes

| Package | Current | Target | Reason |
|---------|---------|--------|--------|
| textual | 3.7.1 (`>=3,<4`) | 8.0.2 (`>=8,<9`) | Five major versions behind |
| rich | 13.9.4 (`>=13,<14`) | 14.x (`>=14,<15`) | Required by textual 8 |
| pytest-asyncio | 0.26.0 (`>=0.25,<1`) | 1.x (`>=1,<2`) | `event_loop` fixture removed; `asyncio_mode=auto` still works |
| textual-dev | 1.8.0 (`>=1,<2`) | 1.8.0 | Already latest; requires textual `>=0.86.2`, no upper bound |

All other dependencies (typer, httpx, pydantic, guessit, pyyaml, pytest,
respx, pytest-cov) are already at their latest stable versions.

## Breaking Changes Assessment

### Textual 3.7 to 8.0 (LOW impact)

- **v6.0: `Static.renderable` renamed to `Static.content`** -- grep
  confirms zero `.renderable` usage in the project.
- **v2.0: strings from `render()` interpreted as `Content.from_markup`** --
  the project returns Rich `Text` objects, never raw strings.
- **v3.0: `App.query` always queries the default screen** -- single-screen
  app, no impact.
- **v4.0 Widget.anchor, v5.0 Visual.render_strips, v7.0
  Node.update_node_styles, v8.0 Select.BLANK to NULL** -- none of these
  APIs are used.

### Rich 13 to 14 (LOW impact)

- Markup escaping changed from double brackets to backslash prefix. The
  project uses `Text()` objects with `.append()`/`.stylize()`, never string
  markup.
- `typing_extensions` removed from runtime deps (no impact).

### pytest-asyncio 0.26 to 1.x (LOW impact)

- `event_loop` fixture removed -- grep confirms zero usage in tests.
- `asyncio_mode = "auto"` remains supported.

## Modal Refactor

### Before (current, broken)

Modals are `Middle` subclasses, always mounted in `compose()`, hidden via
CSS `display: none`:

- CSS layers: `Screen { layers: default overlay; }`, each modal uses
  `layer: overlay`.
- Manual class toggling: `.add_class("visible")` /
  `.remove_class("visible")`, `.add_class("modal-open")` /
  `.remove_class("modal-open")`.
- Manual opacity dimming: `.modal-open TreeView { opacity: 0.3; }`.
- Manual focus save/restore on show/hide.
- `on_key` in TreeApp intercepts all keys when a modal is open.
- Boolean flags `_help_visible` and `_commit_visible` track state.

### After (ModalScreen)

Modals become `ModalScreen` subclasses, pushed and popped on demand:

- Textual handles overlay dimming, focus trapping, and key isolation.
- `dismiss()` returns a typed value (commit modal returns `True`/`False`).
- No `_help_visible`/`_commit_visible` flags.
- No CSS layer setup, no manual class toggling.
- `on_key` modal interception code deleted from TreeApp.
- Rendering functions (`_build_help_text`, `build_commit_text`) unchanged.

## Focus Styling Refactor

### Before

Both TreeView and DetailView have `active: reactive[bool]` with
`watch_active()` toggling `-active`/`-inactive` CSS classes. TreeApp
manually sets `.active = True/False` when switching panels.

### After

CSS pseudo-classes replace all manual class toggling:

```css
TreeView { border: round #555555; }
TreeView:focus { border: round #7AB8FF; }
DetailView { border: round #555555; }
DetailView:focus { border: round #7AB8FF; }
```

Delete `active: reactive[bool]` and `watch_active()` from both widgets.
Delete all `tv.active = ...` / `detail.active = ...` calls from TreeApp.

The `_in_detail` flag remains -- it tracks app mode (tree vs detail),
which persists across modal pushes and is not equivalent to focus.

## Redundant Refresh Cleanup

Textual's `reactive` auto-repaints by default (`repaint=True`). Defining
a `watch_*` method does not suppress this. These explicit `.refresh()`
calls in watchers are redundant:

- `tree_view.py` `watch_cursor_index`: calls `_scroll_to_cursor()` then
  `refresh()` -- remove the `refresh()`.
- `detail_view.py` `watch_cursor_row`: only calls `refresh()` -- remove
  the entire method (or keep if side effects are added later).
- `detail_view.py` `watch_source_index`: same as above.

Explicit `.refresh()` calls after non-reactive state mutations (toggling
staged/ignored, rebuilding items, setting filters) remain necessary.
