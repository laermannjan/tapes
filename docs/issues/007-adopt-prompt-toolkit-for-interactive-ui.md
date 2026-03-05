# Adopt prompt_toolkit for interactive UI

**Date:** 2026-03-05
**Type:** Refactor
**Component:** `tapes/importer/interactive.py`, `tapes/importer/service.py`
**Replaces:** #005 (arrow key navigation), #006 (fuzzy search)

---

## Problem

The interactive import UI is hand-rolled using raw `termios`/`tty` for keypress
reading and manual ANSI escape sequences for screen clearing. This approach has
produced a steady stream of bugs:

- Screen not clearing between re-renders (fixed with `_clear_lines`, still
  fragile)
- Line counting breaks when Rich wraps long text in narrow terminals
- `_clear_lines` writes ANSI garbage when output is piped/redirected
- Ctrl+C swallowed in raw mode (fixed, but only because we remembered to check
  for `\x03`)
- `_read_key` reads one byte, so multi-byte sequences (arrow keys) silently
  produce multiple ignored keypresses
- `edit_companions` limited to 10 items (single digit keys)
- No arrow key navigation, no fuzzy filtering
- Mixing `input()` (cooked mode) and `_read_key()` (raw mode) is a fragile
  coupling

These are not incidental bugs. They are structural consequences of building a
stateful re-rendering terminal UI on top of stateless `print()` calls and manual
cursor manipulation.

## Solution

Adopt `prompt_toolkit` (via the `questionary` wrapper where appropriate) for all
interactive input. Keep Rich for non-interactive output (tables, progress,
status messages).

### Why prompt_toolkit

- Handles single keypresses, multi-byte escape sequences, Ctrl+C, non-TTY
  detection, and Windows support out of the box
- Powers IPython and the AWS CLI -- battle-tested
- `questionary` builds on it and provides ready-made checkbox, select, and text
  prompts with arrow navigation, space toggle, and fuzzy filtering
- Clean separation: prompt_toolkit handles input, Rich handles output

### Why not alternatives

- **Rich.Live:** Fixes clearing but not input. Would still need raw keypress
  handling alongside it.
- **blessed:** Lower-level terminal control. Fixes `_read_key` but does not
  provide UI widgets. More code to write, not less.
- **textual:** Full TUI framework by the Rich author. Overkill for "show
  prompt, read key, maybe re-render." Would require restructuring the entire
  import flow.
- **Language switch (TS/Rust/Go):** The interactive prompt is ~200 lines in a
  Python project with Python-only dependencies. Not a rational trade-off.

## Scope

All changes are confined to `tapes/importer/interactive.py` and its call sites
in `tapes/importer/service.py`. No other modules are affected.

### What gets replaced

| Current | Replacement |
|---------|-------------|
| `_read_key()` (raw termios) | `prompt_toolkit` keybinding or `questionary.select` |
| `_clear_lines()` (manual ANSI) | Removed entirely -- prompt_toolkit handles re-rendering |
| `display_prompt()` + `read_action()` | Single function using `questionary.select` or custom `prompt_toolkit` prompt |
| `edit_companions()` (digit toggle) | `questionary.checkbox` with arrow keys + space |
| `search_prompt()` / `manual_prompt()` (raw `input()`) | `questionary.text` with defaults and validation |

### What stays

- `InteractivePrompt` dataclass and `default_action` logic -- this is pure
  business logic with no terminal dependency
- `PromptAction` enum
- `_format_match()` helper
- `_render_companions()` -- may still be useful for non-interactive display
  (dry-run, logging)
- Rich Console for all non-interactive output

## New dependencies

```toml
[project]
dependencies = [
    # ... existing ...
    "questionary >= 2.0",   # pulls in prompt_toolkit >= 3.0
]
```

One new direct dependency (`questionary`), one transitive (`prompt_toolkit`).
Both are well-maintained and widely used.

## Implementation sketch

### Main prompt (candidate selection + action keys)

```python
import questionary

def prompt_for_action(prompt: InteractivePrompt, filename: str,
                      index: int, total: int, source: str | None,
                      companions: list | None) -> PromptAction | tuple | str:
    """Show candidates and return the user's chosen action."""

    # Build display header (Rich, printed once)
    console.print(f"[bold][{index}/{total}][/bold] {filename}")
    for i, cand in enumerate(prompt.candidates, 1):
        console.print(f"{i}. {_format_match(cand)}")
    if companions:
        _render_companions(console, companions)

    # Build choices for questionary
    choices = _build_action_choices(prompt, has_companions=bool(companions))
    result = questionary.select(
        "",
        choices=choices,
        default=_default_choice(prompt),
        use_shortcuts=True,
    ).ask()

    return _parse_action(result)
```

### Companion editing

```python
def edit_companions(companions: list[CompanionFile]) -> list[CompanionFile]:
    choices = [
        questionary.Choice(
            title=f"{comp.category.value:>12}  {comp.relative_to_video}",
            value=i,
            checked=comp.move_by_default,
            disabled="locked" if comp.category == Category.VIDEO else None,
        )
        for i, comp in enumerate(companions)
    ]
    selected = questionary.checkbox(
        "Select companions to import:",
        choices=choices,
    ).ask()

    return [companions[i] for i in selected]
```

This gives us arrow keys, space toggle, and no item limit for free. Fuzzy
filtering can be added later via questionary's `search_filter` parameter.

### Search and manual prompts

```python
def search_prompt(default_media_type, default_title, default_year):
    mt = questionary.select(
        "Media type:",
        choices=["movie", "tv"],
        default=default_media_type,
    ).ask()
    title = questionary.text("Title:", default=default_title).ask()
    year = questionary.text("Year (optional):",
                            default=str(default_year) if default_year else "",
                            validate=lambda v: v == "" or v.isdigit()).ask()
    return mt, title, int(year) if year else None
```

## Migration plan

1. Add `questionary` dependency
2. Replace `edit_companions` with `questionary.checkbox` (smallest, most
   self-contained change)
3. Replace `search_prompt` and `manual_prompt` with `questionary.text` /
   `questionary.select`
4. Replace `display_prompt` + `read_action` with a combined function using
   questionary
5. Remove `_read_key`, `_clear_lines`, and all raw termios/ANSI code
6. Update tests -- mock questionary's `.ask()` instead of `_read_key`

Steps 2-3 can be done independently. Step 4 is the largest change. Step 5 is
cleanup.

## Acceptance criteria

- [ ] `questionary` added as dependency
- [ ] `edit_companions` uses checkbox with arrow keys + space
- [ ] `search_prompt` / `manual_prompt` use questionary text/select
- [ ] Main prompt uses questionary for action selection
- [ ] `_read_key`, `_clear_lines`, raw termios/ANSI code removed
- [ ] Ctrl+C works naturally (no manual `\x03` handling needed)
- [ ] Non-TTY graceful degradation (questionary handles this)
- [ ] All existing interactive tests updated and passing
- [ ] No item limit on companion editing
- [ ] Arrow key navigation works throughout
