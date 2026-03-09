# Codebase Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Establish consistent vocabulary, clean architecture layering, remove dead code, and simplify plumbing across the entire codebase.

**Architecture:** Twelve tasks covering vocabulary documentation, file/module renames, architecture splits, data model renames, state machine renames, method renames, auto-accept simplification, parameter bundling, closure helper extraction, dead code removal, comment cleanup, and documentation updates. Each task is one atomic commit. All tasks are mechanical renames or targeted refactors -- no feature changes except the auto-accept simplification (Task 7).

**Tech Stack:** Python, pytest, ruff, ty

**IMPORTANT:** Before starting, read `docs/vocabulary.md` (created in Task 1). It defines every canonical term. When in doubt, consult it.

**IMPORTANT:** After every rename task, run `uv run pytest -x -q` and `uv tool run ruff check` to verify nothing broke. Do NOT proceed to the next task if tests fail.

**IMPORTANT:** For all file moves, use `git mv` so git tracks the rename. Do NOT delete + create.

---

## Vocabulary Reference

This is the canonical terminology decided in design discussion. Task 1 writes this to `docs/vocabulary.md`.

| Concept | Canonical term | Was | Notes |
|---|---|---|---|
| File's accumulated metadata | `node.metadata` | `node.result` | Dict of fields (title, year, etc.) |
| A potential match from TMDB/guessit | `Candidate` | `Source` | Has `.metadata`, `.score`, `.name` |
| Candidate's metadata dict | `candidate.metadata` | `source.fields` | Same key structure as node.metadata |
| One key-value pair in a metadata dict | "field" | "field" | Unchanged |
| Match quality measurement | `.score` | `.confidence` | Float 0-1 from similarity function |
| List of candidates on a file node | `node.candidates` | `node.sources` | |
| Choosing a candidate for the file | "accept" | "accept"/"apply" | `accept_current_candidate()` |
| Finalizing an inline field edit | "apply" | "commit" | `apply_edit()` |
| Executing file operations | "commit" | "commit" | Unchanged |
| App state machine states | `AppState` | `AppMode` | Enum values: TREE, METADATA, COMMIT, HELP, TREE_SEARCH |
| Metadata curation view/state | METADATA / MetadataView | DETAIL / DetailView | |
| Help view widget | HelpView | HelpOverlay | Already named HelpView, just the file |
| Metadata extraction module | `tapes/extract.py` | `tapes/metadata.py` | guessit wrapper, future nfo parsing |
| Template/path utilities | `tapes/templates.py` | scattered in `tapes/ui/tree_render.py` | |
| Color palette + semantic tokens | `tapes/ui/colors.py` | top of `tapes/ui/tree_render.py` | |
| Auto-accept gate params | `min_score`, `min_prominence` | `margin_accept_threshold`, `min_accept_margin` | Single gate, no tiers |
| Bundled pipeline params | `PipelineParams` | 10-13 kwargs | Dataclass |

---

### Task 1: Write vocabulary reference

**Files:**
- Create: `docs/vocabulary.md`

**Step 1: Write the vocabulary document**

Create `docs/vocabulary.md` with the table above plus brief explanations of the pipeline flow using the canonical terms. Keep it under 80 lines. This is a reference, not a tutorial.

**Step 2: Commit**

```bash
git add docs/vocabulary.md
git commit -m "docs: add vocabulary reference for canonical terminology"
```

---

### Task 2: Rename file modules

**Files:**
- Move: `tapes/metadata.py` -> `tapes/extract.py`
- Move: `tapes/ui/detail_view.py` -> `tapes/ui/metadata_view.py`
- Move: `tapes/ui/detail_render.py` -> `tapes/ui/metadata_render.py`
- Move: `tapes/ui/help_overlay.py` -> `tapes/ui/help_view.py`
- Move: `tests/test_metadata.py` -> `tests/test_extract.py`
- Move: `tests/test_ui/test_detail_view.py` -> `tests/test_ui/test_metadata_view.py`
- Move: `tests/test_ui/test_detail_render.py` -> `tests/test_ui/test_metadata_render.py`
- Move: `tests/test_ui/test_help_overlay.py` -> `tests/test_ui/test_help_view.py`
- Modify: every file that imports from the old module paths

**Step 1: Move files with git mv**

```bash
git mv tapes/metadata.py tapes/extract.py
git mv tapes/ui/detail_view.py tapes/ui/metadata_view.py
git mv tapes/ui/detail_render.py tapes/ui/metadata_render.py
git mv tapes/ui/help_overlay.py tapes/ui/help_view.py
git mv tests/test_metadata.py tests/test_extract.py
git mv tests/test_ui/test_detail_view.py tests/test_ui/test_metadata_view.py
git mv tests/test_ui/test_detail_render.py tests/test_ui/test_metadata_render.py
git mv tests/test_ui/test_help_overlay.py tests/test_ui/test_help_view.py
```

**Step 2: Update all import paths**

Find and replace across the codebase:

| Old import path | New import path |
|---|---|
| `tapes.metadata` | `tapes.extract` |
| `tapes.ui.detail_view` | `tapes.ui.metadata_view` |
| `tapes.ui.detail_render` | `tapes.ui.metadata_render` |
| `tapes.ui.help_overlay` | `tapes.ui.help_view` |

Files that import `tapes.metadata`:
- `tapes/pipeline.py:87` -- `from tapes.metadata import extract_metadata`
- `tests/test_extract.py` (was test_metadata.py) -- `from tapes.metadata import ...`

Files that import `tapes.ui.detail_view`:
- `tapes/ui/tree_app.py:27`
- `tests/test_ui/test_metadata_view.py` (was test_detail_view.py)
- `tests/test_ui/test_border_rendering.py:9`
- `tests/test_ui/test_pipeline.py:1080,1113,1148`
- `tests/test_ui/test_tree_app.py:1064,1180`

Files that import `tapes.ui.detail_render`:
- `tapes/ui/metadata_view.py` (was detail_view.py) -- internal import
- `tests/test_ui/test_metadata_render.py` (was test_detail_render.py)
- `tests/test_ui/test_metadata_view.py` (was test_detail_view.py)
- `tests/test_ui/test_border_rendering.py:8`

Files that import `tapes.ui.help_overlay`:
- `tapes/ui/tree_app.py:28`
- `tests/test_ui/test_help_view.py` (was test_help_overlay.py)

Also update the `FileMetadata` import name if it appears in the new `extract.py` module docstring.

**Step 3: Run tests**

Run: `uv run pytest -x -q`
Expected: All 698 tests pass.

**Step 4: Run linters**

Run: `uv tool run ruff check tapes/ tests/`
Run: `uv tool run ruff format tapes/ tests/`

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor: rename modules to match vocabulary

metadata.py -> extract.py (extraction, not generic metadata)
detail_view.py -> metadata_view.py (metadata curation view)
detail_render.py -> metadata_render.py (metadata rendering)
help_overlay.py -> help_view.py (consistent *View naming)"
```

---

### Task 3: Extract templates.py and colors.py from tree_render.py

**Files:**
- Create: `tapes/templates.py`
- Create: `tapes/ui/colors.py`
- Modify: `tapes/ui/tree_render.py` (remove extracted code, import from new modules)
- Modify: all files that import the moved symbols from tree_render.py

**Step 1: Create `tapes/templates.py`**

Move these functions and their dependencies from `tapes/ui/tree_render.py`:
- `template_field_names` (line 42)
- `select_template` (line 48)
- `can_fill_template` (line 60)
- `full_extension` (line 77, plus `_is_tag` helper at line 70)
- `_sanitize_field` (line 100)
- `compute_dest` (line 106)

These are pure functions with no Rich/Textual dependency. They import only from `tapes.fields` and `tapes.tree_model`.

**Step 2: Create `tapes/ui/colors.py`**

Move all color constants from `tapes/ui/tree_render.py` (lines 17-39). Organize as two layers:

```python
"""Color palette and semantic tokens."""

# --- Palette (what the colors ARE) ---
CREAM = "#F5F0E8"
SAGE = "#4EBA65"
CHARCOAL = "#373737"
LAVENDER = "#B1B9F9"
EMBER = "#E07A47"
SLATE = "#555555"
STONE = "#888888"
PEBBLE = "#aaaaaa"
MINT = "#86E89A"
CORAL = "#FF7A7A"
SKY = "#7AB8FF"
PLUM = "#3B3154"

# --- Semantic tokens (what the colors MEAN) ---
COLOR_MUTED = STONE
COLOR_MUTED_LIGHT = PEBBLE
COLOR_STAGED = SAGE
COLOR_CURSOR_BG = f"on {CHARCOAL}"
COLOR_RANGE_BG = f"on {CHARCOAL}"
COLOR_ACCENT = LAVENDER
COLOR_INACTIVE = SLATE
COLOR_DIFF = EMBER
COLOR_ADDITION = MINT
COLOR_WARNING = CORAL
COLOR_LINK = SKY
COLOR_COLUMN_FOCUS_BG = f"on {PLUM}"
```

Review the existing color usage to verify the palette names and semantic mappings are correct. The hex values must stay identical.

**Step 3: Update tree_render.py**

Remove the extracted functions and color constants. Add imports:
```python
from tapes.templates import can_fill_template, compute_dest, full_extension, select_template, template_field_names
from tapes.ui.colors import (
    COLOR_ACCENT, COLOR_CURSOR_BG, COLOR_DIFF, COLOR_MUTED, COLOR_MUTED_LIGHT,
    COLOR_RANGE_BG, COLOR_STAGED,
)
```

**Step 4: Update all importers**

Files that import template utilities from tree_render.py -- change to import from `tapes.templates`:
- `tapes/conflicts.py:18` -- `from tapes.ui.tree_render import full_extension` (THIS IS THE LAYERING FIX)
- `tapes/ui/tree_app.py` -- 6 inline imports of `can_fill_template` from `tapes.ui.tree_render`; change to `from tapes.templates import can_fill_template` (can be top-level now)
- `tapes/pipeline.py` -- if it imports any template functions
- `tests/test_can_stage.py` -- imports `can_fill_template` and friends
- `tests/test_ui/test_tree_render.py` -- template function tests

Files that import color constants from tree_render.py -- change to import from `tapes.ui.colors`:
- `tapes/ui/metadata_view.py` (was detail_view.py)
- `tapes/ui/metadata_render.py` (was detail_render.py)
- `tapes/ui/commit_view.py`
- `tapes/ui/bottom_bar.py`
- `tapes/ui/help_view.py` (was help_overlay.py)

Update color constant names to semantic tokens where used:
- `MUTED` -> `COLOR_MUTED`
- `MUTED_LIGHT` -> `COLOR_MUTED_LIGHT`
- `STAGED_COLOR` -> `COLOR_STAGED`
- `CURSOR_BG` -> `COLOR_CURSOR_BG`
- `RANGE_BG` -> `COLOR_RANGE_BG`
- `ACCENT` -> `COLOR_ACCENT`
- `INACTIVE` -> `COLOR_INACTIVE`
- `EMBER` -> use semantic name based on context (COLOR_DIFF, or for operation: use palette name via OPERATION_COLORS dict)
- `SOFT_GREEN` -> semantic name based on context
- `SOFT_RED` -> `COLOR_WARNING`
- `SOFT_BLUE` -> `COLOR_LINK`
- `COLUMN_FOCUS_BG` -> `COLOR_COLUMN_FOCUS_BG`

For `bottom_bar.py`'s OPERATION_COLORS dict, use palette names directly since these map operations to visual colors:
```python
from tapes.ui.colors import EMBER, MINT, SKY
OPERATION_COLORS = {"copy": MINT, "move": EMBER, "link": SKY, "hardlink": SKY}
```

**Step 5: Run tests**

Run: `uv run pytest -x -q`
Expected: All 698 tests pass.

**Step 6: Run linters**

Run: `uv tool run ruff check tapes/ tests/`

**Step 7: Commit**

```bash
git add -A
git commit -m "refactor: extract templates.py and colors.py from tree_render

- tapes/templates.py: pure template/path utilities (no UI dependency)
- tapes/ui/colors.py: palette + semantic color tokens
- fixes layering violation: conflicts.py no longer imports from UI
- color constants renamed to semantic tokens (COLOR_STAGED, etc.)"
```

---

### Task 4: Rename data model (Source -> Candidate, .confidence -> .score, .result -> .metadata, .sources -> .candidates, .fields -> .metadata)

**Files:**
- Modify: `tapes/tree_model.py` (class + field definitions)
- Modify: `tapes/pipeline.py` (extensive usage)
- Modify: `tapes/categorize.py`
- Modify: `tapes/conflicts.py`
- Modify: `tapes/ui/metadata_view.py` (was detail_view.py)
- Modify: `tapes/ui/tree_app.py`
- Modify: all test files that reference Source, .confidence, .result, .sources, .fields

This is a large mechanical rename. Use find-and-replace with care -- `.fields` and `.metadata` are common tokens, so replace only in the right context.

**Step 1: Rename in tree_model.py**

```python
@dataclass
class Candidate:
    """A metadata candidate (e.g. guessit parse, TMDB match)."""
    name: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0

@dataclass
class FileNode:
    """A file in the tree."""
    path: Path
    staged: bool = False
    ignored: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    candidates: list[Candidate] = field(default_factory=list)
```

Also update `compute_shared_fields` which iterates over `node.result`.

**Step 2: Rename in all production code**

Global replacements (be precise -- use word boundaries):
- Class: `Source` -> `Candidate` (in imports, type hints, instantiations)
- Field: `\.confidence` -> `.score` (on Candidate instances)
- Field: `node\.result` -> `node.metadata` (on FileNode instances)
- Field: `node\.sources` -> `node.candidates` (on FileNode instances)
- Field: `\.fields` -> `.metadata` (on Candidate instances only -- check context)
- Variable: `source_index` -> `candidate_index` (in metadata_view.py)
- Message: `FieldsChanged` -> `MetadataChanged`
- Handler: `on_detail_view_fields_changed` -> `on_metadata_view_metadata_changed`

The `_NodeSnapshot` tuple fields also need updating:
```python
class _NodeSnapshot(NamedTuple):
    node: FileNode
    metadata: dict
    candidates: list
    staged: bool
```

In pipeline.py, local variables named `source` or `src` should become `candidate` or `cand`. Variable `similarities` can stay (it's a list of scores, not candidates). Variable `tmdb_sources` -> `tmdb_candidates`.

**Step 3: Rename in all test files**

Same replacements across:
- `tests/test_ui/test_tree_model.py`
- `tests/test_ui/test_pipeline.py`
- `tests/test_ui/test_metadata_view.py` (was test_detail_view.py)
- `tests/test_ui/test_tree_app.py`
- `tests/test_ui/test_border_rendering.py`
- `tests/test_can_stage.py`
- `tests/test_ui/test_tree_render.py`

**Step 4: Run tests**

Run: `uv run pytest -x -q`
Expected: All 698 tests pass.

**Step 5: Run linters**

Run: `uv tool run ruff check tapes/ tests/`

**Step 6: Commit**

```bash
git add -A
git commit -m "refactor: rename data model to canonical vocabulary

Source -> Candidate, .confidence -> .score, .result -> .metadata,
.sources -> .candidates, source.fields -> candidate.metadata,
FieldsChanged -> MetadataChanged, source_index -> candidate_index"
```

---

### Task 5: Rename state machine (AppMode -> AppState, DETAIL -> METADATA, SEARCHING -> TREE_SEARCH)

**Files:**
- Modify: `tapes/ui/tree_app.py`
- Modify: all test files that reference AppMode or its values

**Step 1: Rename enum and values**

In `tapes/ui/tree_app.py`:
```python
class AppState(Enum):
    TREE = "tree"
    METADATA = "metadata"
    COMMIT = "commit"
    HELP = "help"
    TREE_SEARCH = "tree_search"
```

Replace throughout tree_app.py:
- `AppMode` -> `AppState`
- `AppMode.DETAIL` / `AppState.DETAIL` -> `AppState.METADATA`
- `AppMode.SEARCHING` / `AppState.SEARCHING` -> `AppState.TREE_SEARCH`
- `_mode` attribute stays (it's the state variable)
- `_MODAL_MODES` -> `_MODAL_STATES`

Also rename the `mode` property to `state` (used by tests):
```python
@property
def state(self) -> AppState:
    return self._mode
```

**Step 2: Rename detail-related methods**

- `_show_detail` -> `_show_metadata_view`
- `_show_detail_multi` -> `_show_metadata_view_multi`
- `_discard_detail` -> `_discard_metadata`
- `_accept_detail_and_return` -> `_accept_metadata_and_return`
- `_detail_snapshot` -> `_metadata_snapshot`

Update the "Info" header text to "Metadata" in the metadata view widget. Check `metadata_view.py` for where the header label is set.

**Step 3: Update all test files**

Replace `AppMode` -> `AppState`, `.DETAIL` -> `.METADATA`, `.SEARCHING` -> `.TREE_SEARCH`, `app.mode` -> `app.state` across:
- `tests/test_ui/test_tree_app.py` (~50 occurrences)
- `tests/test_ui/test_pipeline.py` (~10 occurrences)
- `tests/test_ui/test_metadata_view.py` (~6 occurrences)

**Step 4: Run tests**

Run: `uv run pytest -x -q`
Expected: All 698 tests pass.

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor: rename state machine to AppState with canonical values

AppMode -> AppState, DETAIL -> METADATA, SEARCHING -> TREE_SEARCH.
Detail methods renamed: _show_metadata_view, _discard_metadata, etc."
```

---

### Task 6: Rename methods (accept_current_candidate, apply_edit)

**Files:**
- Modify: `tapes/ui/metadata_view.py`
- Modify: `tapes/ui/tree_app.py`
- Modify: test files

**Step 1: Rename in metadata_view.py**

- `apply_source_all_clear` -> `accept_current_candidate`
- `commit_edit` -> `apply_edit`
- `accept_focused_column` -> keep (already uses "accept" correctly)
- Update `accept_focused_column` to call `self.accept_current_candidate()`
- `cycle_source` -> `cycle_candidate`

**Step 2: Rename in tree_app.py**

- `dv.commit_edit()` -> `dv.apply_edit()` (line 440)
- References in comments

**Step 3: Rename in test files**

- `tests/test_ui/test_metadata_view.py` -- all `apply_source_all_clear` calls -> `accept_current_candidate`, all `commit_edit` calls -> `apply_edit`
- `tests/test_ui/test_pipeline.py` -- `dv.apply_source_all_clear()` calls

Also rename test class `TestApplySourceAllClear` -> `TestAcceptCurrentCandidate`.

**Step 4: Run tests**

Run: `uv run pytest -x -q`

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor: rename methods to canonical vocabulary

apply_source_all_clear -> accept_current_candidate
commit_edit -> apply_edit
cycle_source -> cycle_candidate"
```

---

### Task 7: Simplify auto-accept to single gate

**Files:**
- Modify: `tapes/similarity.py`
- Modify: `tapes/config.py`
- Modify: `tapes/cli.py`
- Modify: `tapes/pipeline.py`
- Modify: `tapes/ui/tree_app.py`
- Modify: `tests/test_similarity.py`
- Modify: `tests/test_config.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_ui/test_pipeline.py`
- Modify: `config.example.yaml`

This task changes behavior: the two-tier auto-accept gate collapses into a single gate.

**Step 1: Write failing test**

In `tests/test_similarity.py`, add a test that verifies two high-scoring candidates (0.99 and 0.98) do NOT auto-accept (low prominence):

```python
def test_high_scores_low_prominence_no_accept():
    """Two near-identical scores should NOT auto-accept -- user must decide."""
    assert should_auto_accept([0.99, 0.98]) is False
```

Run: `uv run pytest tests/test_similarity.py::test_high_scores_low_prominence_no_accept -v`
Expected: FAIL (current tier 1 would accept 0.99 unconditionally).

**Step 2: Simplify `should_auto_accept`**

```python
def should_auto_accept(
    scores: list[float],
    min_score: float = DEFAULT_MIN_SCORE,
    min_prominence: float = DEFAULT_MIN_PROMINENCE,
) -> bool:
    """Decide whether to auto-accept the best candidate.

    Auto-accepts when the best score is above min_score AND the candidate
    is prominent (margin to second-best >= min_prominence). A single
    candidate has infinite prominence.
    """
    if not scores:
        return False
    best = scores[0]
    if best < min_score:
        return False
    if len(scores) == 1:
        return True  # single candidate, infinite prominence
    prominence = best - scores[1]
    return prominence >= min_prominence
```

**Step 3: Rename constants**

In `similarity.py`:
- Delete `MARGIN_ACCEPT_THRESHOLD`
- Rename `MIN_ACCEPT_MARGIN` -> `DEFAULT_MIN_PROMINENCE` (value stays 0.15)

In `config.py`:
- Rename `DEFAULT_AUTO_ACCEPT_THRESHOLD` -> `DEFAULT_MIN_SCORE` (change value from 0.85 to 0.6 -- the old tier 2 threshold, since tier 1 is gone)
- Rename `auto_accept_threshold` -> `min_score`
- Rename `margin_accept_threshold` -> DELETE (no longer needed)
- Rename `min_accept_margin` -> `min_prominence`

**IMPORTANT:** The default `min_score` should be 0.6 (was `margin_accept_threshold`). The old `auto_accept_threshold` of 0.85 is gone -- it was the tier 1 "accept without checking prominence" threshold, which we're eliminating. With `min_score=0.6` and `min_prominence=0.15`, a single candidate at 0.85 still auto-accepts (score >= 0.6, single candidate = infinite prominence). Two candidates at 0.85 and 0.60 also auto-accept (prominence = 0.25 >= 0.15). But two candidates at 0.99 and 0.98 do NOT (prominence = 0.01 < 0.15).

**Step 4: Update CLI**

In `cli.py`:
- Rename `--auto-accept-threshold` -> `--min-score`
- Delete `--margin-accept-threshold`
- Rename `--min-accept-margin` -> `--min-prominence`
- Update CLI_OVERRIDES mapping

**Step 5: Update pipeline.py**

- Rename `confidence_threshold` parameter -> `min_score` in all pipeline functions
- Delete `margin_threshold` parameter (was tier 2 minimum score, now merged into `min_score`)
- Rename `min_margin` parameter -> `min_prominence`
- Update `_accept_kwargs` construction to pass `min_prominence=min_prominence`
- Update all calls to `should_auto_accept`

**Step 6: Update tree_app.py**

- Update `_run_tmdb_worker` and `_run_refresh_worker` to use new config field names
- `self.config.metadata.auto_accept_threshold` -> `self.config.metadata.min_score`
- Delete `margin_threshold` local variable
- `self.config.metadata.min_accept_margin` -> `self.config.metadata.min_prominence`

**Step 7: Update config.example.yaml**

Rename the fields in the example config file.

**Step 8: Fix all tests**

Update test assertions and parameter names across:
- `tests/test_similarity.py` -- update all `should_auto_accept` calls
- `tests/test_config.py` -- rename config field assertions
- `tests/test_cli.py` -- rename CLI option tests
- `tests/test_ui/test_pipeline.py` -- rename parameter names in calls

**Step 9: Run tests**

Run: `uv run pytest -x -q`
Expected: All tests pass (some test expectations may need updating due to the behavior change).

**Step 10: Commit**

```bash
git add -A
git commit -m "refactor: simplify auto-accept to single gate

Collapse two-tier auto-accept into: score >= min_score AND
prominence >= min_prominence. A single candidate has infinite
prominence. Two candidates at 0.99/0.98 now require user decision."
```

---

### Task 8: Create PipelineParams dataclass and deduplicate workers

**Files:**
- Modify: `tapes/pipeline.py`
- Modify: `tapes/ui/tree_app.py`
- Modify: test files that call pipeline functions with keyword args

**Step 1: Create PipelineParams in pipeline.py**

```python
@dataclass
class PipelineParams:
    """Bundled parameters for pipeline functions."""
    token: str = ""
    min_score: float = DEFAULT_MIN_SCORE
    min_prominence: float = DEFAULT_MIN_PROMINENCE
    max_results: int = DEFAULT_MAX_RESULTS
    max_workers: int = DEFAULT_MAX_WORKERS
    tmdb_timeout: float = 10.0
    tmdb_retries: int = 3
    language: str = ""
```

**Step 2: Add `PipelineParams.from_config` classmethod**

```python
@classmethod
def from_config(cls, config: TapesConfig) -> PipelineParams:
    return cls(
        token=config.metadata.tmdb_token,
        min_score=config.metadata.min_score,
        min_prominence=config.metadata.min_prominence,
        max_results=config.metadata.max_results,
        max_workers=config.advanced.max_workers,
        tmdb_timeout=config.advanced.tmdb_timeout,
        tmdb_retries=config.advanced.tmdb_retries,
        language=config.metadata.language,
    )
```

**Step 3: Update pipeline functions to accept PipelineParams**

Keep the existing keyword-arg signatures for backwards compatibility but add an optional `params: PipelineParams | None = None` parameter. When `params` is provided, its values are used as defaults (individual kwargs still override). This avoids a big-bang rewrite of all callers.

Alternatively (cleaner): convert `run_tmdb_pass`, `run_auto_pipeline`, `refresh_tmdb_source`, `refresh_tmdb_batch` to accept `PipelineParams` directly. Update all callers. This is more work but cleaner.

Choose the cleaner approach: all pipeline functions take `PipelineParams` as first positional arg after required args (model/node).

**Step 4: Deduplicate workers in tree_app.py**

Replace `_run_tmdb_worker` and `_run_refresh_worker` with a single `_make_pipeline_worker`:

```python
def _make_pipeline_worker(
    self,
    pipeline_fn: Callable,
    nodes_or_model: TreeModel | list[FileNode],
    params: PipelineParams,
) -> Callable:
    from tapes.templates import can_fill_template
    mt, tt = self.movie_template, self.tv_template

    def _can_stage(node: FileNode, merged: dict) -> bool:
        return can_fill_template(node, merged, mt, tt)

    def worker() -> None:
        # ... call pipeline_fn with params and progress callbacks
        self.call_from_thread(self._on_tmdb_done)

    return worker
```

Construct `PipelineParams.from_config(self.config)` once in each call site.

**Step 5: Run tests**

Run: `uv run pytest -x -q`

**Step 6: Commit**

```bash
git add -A
git commit -m "refactor: bundle pipeline params into PipelineParams dataclass

Eliminates 10-13 kwargs threaded through every pipeline function.
Deduplicates _run_tmdb_worker and _run_refresh_worker in TreeApp."
```

---

### Task 9: Extract closure helper for dispatch pattern

**Files:**
- Modify: `tapes/pipeline.py`

**Step 1: Extract helper**

The default-argument closure pattern appears ~5 times in pipeline.py. Extract a helper:

```python
def _make_metadata_updater(
    node: FileNode,
    fields: dict[str, Any],
    stage: bool,
) -> Callable[[], None]:
    """Create a closure that updates node metadata on the main thread.

    Uses explicit parameters instead of closing over loop variables to avoid
    late-binding bugs -- each closure captures the values at creation time,
    not at call time.
    """
    def _apply() -> None:
        for field_name, val in fields.items():
            if val is not None:
                node.metadata[field_name] = val
        if stage:
            node.staged = True
    return _apply
```

Similarly for the source-extending closures, create:

```python
def _make_candidates_updater(
    node: FileNode,
    candidates: list[Candidate],
) -> Callable[[], None]:
    """Create a closure that extends node candidates."""
    def _extend() -> None:
        node.candidates.extend(candidates)
    return _extend
```

**Step 2: Replace all closure sites**

Replace the 5 inline closure definitions with calls to the helpers. Delete the `# noqa` comments that were suppressing complexity warnings.

**Step 3: Run tests**

Run: `uv run pytest -x -q`

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor: extract closure helpers for dispatch pattern

_make_metadata_updater and _make_candidates_updater replace inline
closures with default-argument binding. Makes the late-binding
protection explicit and self-documenting."
```

---

### Task 10: Remove dead code

**Files:**
- Modify: `tapes/ui/metadata_render.py` -- delete `confidence_style`
- Modify: `tapes/ui/tree_view.py` -- delete `toggle_staged_at_cursor`, `toggle_ignored_range`
- Modify: `tests/test_ui/test_metadata_render.py` -- delete `confidence_style` tests
- Modify: `tests/test_ui/test_tree_app.py` -- delete tests that call dead methods

**Step 1: Delete `confidence_style`**

Remove the function definition from `metadata_render.py` and all 8 test cases from `test_metadata_render.py`. Remove the import.

**Step 2: Delete `toggle_staged_at_cursor` and `toggle_ignored_range`**

Remove from `tree_view.py`. The `toggle_ignored_at_cursor` method calls `toggle_ignored_range` -- if `toggle_ignored_at_cursor` is also only called from tests, delete it too. Check first.

Remove tests in `test_tree_app.py` that call these methods directly. The behavior they test should already be covered by pilot-based integration tests (space key for staging, x key for ignoring).

**Step 3: Wire `folder_name` in pipeline**

In `pipeline.py`, in `_populate_node_guessit`, pass the parent directory name:

```python
def _populate_node_guessit(node: FileNode, extract_fn: Callable) -> None:
    fm = extract_fn(node.path.name, folder_name=node.path.parent.name)
    ...
```

This is wiring existing unused functionality, not adding new code.

**Step 4: Run tests**

Run: `uv run pytest -x -q`
Expected: Some tests deleted, remaining tests pass. Total count will decrease.

**Step 5: Commit**

```bash
git add -A
git commit -m "chore: remove dead code, wire folder_name extraction

Delete: confidence_style, toggle_staged_at_cursor, toggle_ignored_range.
Wire: pass folder_name to extract_metadata for better guessit results."
```

---

### Task 11: Clean up comments

**Files:**
- Modify: various files across codebase

**Step 1: Remove "restating the obvious" comments**

Delete comments that restate what the code does. Examples from the audit:
- `pipeline.py:489` -- `# Create sources for each search result`
- `tmdb.py:153` -- `# Skip 'person' and other types`
- `tree_model.py:200` -- `# Sort folders alphabetically, then files alphabetically`
- `tree_view.py:289` -- `# Pad or truncate to fit inner width`
- All redundant comments in `categorize.py`

**Step 2: Keep and improve WHY comments**

Keep comments that explain non-obvious reasons:
- Thread safety notes in pipeline.py
- Timing bug explanation in tree_app.py
- Platform limitation in file_ops.py
- Config global explanation in config.py

**Step 3: Add missing WHY comment for config global**

In `config.py`, at the `settings_customise_sources` method, add a brief comment explaining WHY a module-level global is needed (pydantic-settings calls this classmethod without custom args).

**Step 4: Run tests**

Run: `uv run pytest -x -q`

**Step 5: Commit**

```bash
git add -A
git commit -m "chore: clean up comments -- keep WHY, remove obvious"
```

---

### Task 12: Update documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/pipeline-model.md`
- Modify: `docs/vocabulary.md` (if any terms changed during implementation)
- Modify: `config.example.yaml`

**Step 1: Update CLAUDE.md architecture section**

Update the architecture listing to reflect new file names:
- `tapes/extract.py` (was metadata.py)
- `tapes/templates.py` (new)
- `tapes/ui/metadata_view.py` (was detail_view.py)
- `tapes/ui/metadata_render.py` (was detail_render.py)
- `tapes/ui/help_view.py` (was help_overlay.py)
- `tapes/ui/colors.py` (new)

Update terminology used in CLAUDE.md to match vocabulary.md.

Add a reference: `See docs/vocabulary.md for canonical terminology.`

**Step 2: Update pipeline-model.md**

Update to use canonical terms:
- "Source objects" -> "Candidate objects"
- "confidence scores" -> "scores"
- "sources" -> "candidates"
- "node.sources" -> "node.candidates"
- Update the auto-accept section to describe the single gate

**Step 3: Update config.example.yaml**

Rename fields to match new config names (`min_score`, `min_prominence`).

**Step 4: Run tests**

Run: `uv run pytest -x -q`

**Step 5: Commit**

```bash
git add -A
git commit -m "docs: update all documentation to canonical vocabulary"
```

---

### Task 13: Full verification

**Step 1: Run the full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass (count will be slightly lower due to dead code removal in Task 10).

**Step 2: Run linters**

Run: `uv tool run ruff check tapes/ tests/`
Run: `uv tool run ruff format --check tapes/ tests/`
Run: `uv tool run ty check`

**Step 3: Verify no stale imports**

Run: `uv tool run ruff check --select F401 tapes/ tests/`
Expected: No unused imports.

**Step 4: Verify vocabulary consistency**

Grep for old terms that should not appear:
```bash
# These should return zero matches in .py files:
rg "\.confidence\b" tapes/ tests/ --type py
rg "\bSource\b" tapes/tree_model.py  # should only be in old comments if any
rg "\.result\b" tapes/tree_model.py
rg "AppMode" tapes/ tests/ --type py
rg "detail_view" tapes/ tests/ --type py
rg "help_overlay" tapes/ tests/ --type py
rg "confidence_threshold" tapes/ tests/ --type py
rg "margin_accept_threshold" tapes/ tests/ --type py
```
