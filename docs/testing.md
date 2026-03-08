# Testing Strategy

Guidelines for testing the tapes TUI and core logic.

---

## Principles

1. **Test the product, not a parallel implementation.** If a test calls a
   standalone function that approximates what a widget does, it tests the
   approximation. When the widget diverges, the test still passes and the
   bug ships. Every test should exercise the real code path.

2. **Test like the user.** The more a test resembles how the software is
   actually used, the more confidence it gives. For a TUI, that means
   simulating keypresses and asserting what appears on screen, not calling
   internal render helpers.

3. **Testing trophy over testing pyramid.** Few unit tests for pure logic,
   heavy on integration tests through real widgets, some E2E tests for
   critical flows (scan, curate, commit). Minimal snapshot tests.

---

## What to test at each level

### Unit tests (pure functions, no UI)

Scoring, template parsing, field extraction, config validation, file ops
logic. These have no Textual dependency and are fast.

```python
def test_confidence_exact_match():
    score = compute_confidence({"title": "Dune", "year": 2021}, {"title": "Dune", "year": 2021})
    assert score == pytest.approx(1.0)
```

### Integration tests (Textual widgets)

Use Textual's `app.run_test()` + `Pilot` to mount real widgets, simulate
input, and assert structural properties. This is the bulk of TUI testing.

```python
async def test_detail_view_shows_tabs_per_source(app):
    async with app.run_test() as pilot:
        await pilot.press("enter")  # open detail view
        tabs = app.query_one(DetailView).query(".tab")
        assert len(tabs) == 3  # 3 sources = 3 tabs
```

**Assert structural properties, not exact output:**
- "3 sources produce 3 tabs" -- yes
- "tab label is exactly `TMDB #12345`" -- only if the label format matters
- "field with no value shows `?`" -- yes, this is a design rule
- "the 4th line of output is `  title    The Matrix   The Matrix`" -- no,
  this breaks on any spacing change

### E2E tests (full app flows)

For critical paths: scan a temp directory, verify tree populates, stage
files, commit, verify files land in the right place. Expensive, keep few.

### Snapshot tests (visual regression)

Textual supports SVG snapshot testing. **Do not add these during active
design work** -- they break on every cosmetic change. Add them once the
UI design stabilizes, gated behind a separate test marker or CI step.
Use `--update-snapshots` workflow when intentionally changing visuals.

---

## Anti-patterns

- **Standalone render functions used only by tests.** If production code
  uses `Widget.render()` but tests call `render_thing()`, you are testing
  a fork. Delete the function, test the widget.

- **Snapshot tests during design iteration.** Every color tweak, spacing
  change, or layout adjustment breaks snapshots. You end up updating
  snapshots instead of catching regressions.

- **Testing implementation details.** Don't assert internal state
  (`widget._some_flag is True`). Assert what the user would observe
  (a label changed, a panel appeared, a file was written).

---

## Tooling

- **pytest** with `pytest-asyncio` for async widget tests
- **Textual's Pilot** (`async with app.run_test() as pilot`) for
  simulating user interaction and querying the widget tree
- **respx** for mocking httpx HTTP calls (TMDB API)
- **tmp_path** fixture for file system tests
