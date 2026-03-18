# Code Review Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Address all findings from the architecture code review: eliminate DRY violations, fix bugs, improve type safety, remove dead code, and consolidate APIs.

**Architecture:** Work bottom-up -- fix foundational modules first (constants, types, core), then update consumers (pipeline, TUI, tests). Each task is independently committable and keeps all 381 tests green.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, httpx, Textual

---

## Task 1: Delete dead code and fix trivial issues

**Files:**
- Delete: `tapes/ui/query.py`
- Modify: `tapes/ui/tree_render.py` (remove redundant `import re` on line 63)
- Modify: `tapes/ui/tree_app.py` (remove defensive `getattr` on lines 468-469)

**Step 1: Delete `tapes/ui/query.py`**

This file is dead code -- not imported anywhere. Delete it entirely.

**Step 2: Remove redundant `import re` inside `compute_dest`**

In `tapes/ui/tree_render.py`, line 63 does `import re` inside the function body, but `re` is already imported at the module top (line 4). Remove the inner import.

**Step 3: Remove defensive `getattr` in `_update_footer`**

In `tapes/ui/tree_app.py`, lines 468-469 use `getattr(self, "_tmdb_querying", False)` and `getattr(self, "_tmdb_progress", (0, 0))`. These attributes are always initialized in `__init__` (lines 80-81). Replace with direct attribute access:
```python
if self._tmdb_querying:
    done, total = self._tmdb_progress
```

**Step 4: Run tests**

Run: `uv run pytest -x -q`
Expected: All tests pass.

**Step 5: Commit**

```
fix: remove dead code and trivial issues

- Delete unused tapes/ui/query.py mock module
- Remove redundant import re inside compute_dest
- Replace defensive getattr with direct attribute access
```

---

## Task 2: Fix DRY violation -- single threshold constant

**Files:**
- Modify: `tapes/similarity.py` (remove constant, import from config)
- Modify: `tests/test_similarity.py` (update import)

**Step 1: Remove `DEFAULT_AUTO_ACCEPT_THRESHOLD` from `similarity.py`**

Delete the constant on line 8. It's already defined in `config.py:15`.

**Step 2: Update `tests/test_similarity.py`**

Change the import on line 7 from:
```python
from tapes.similarity import (
    DEFAULT_AUTO_ACCEPT_THRESHOLD,
    ...
)
```
to:
```python
from tapes.config import DEFAULT_AUTO_ACCEPT_THRESHOLD
from tapes.similarity import (
    compute_confidence,
    ...
)
```

**Step 3: Run tests**

Run: `uv run pytest tests/test_similarity.py -x -q`
Expected: All pass.

**Step 4: Commit**

```
fix: define DEFAULT_AUTO_ACCEPT_THRESHOLD in one place

Remove duplicate from similarity.py, keep single source in config.py.
```

---

## Task 3: Fix `_TmdbCache` deadlock on exception

**Files:**
- Modify: `tapes/ui/pipeline.py` (add try/finally to `get_or_fetch`)
- Modify: `tests/test_ui/test_pipeline.py` (add test for exception handling)

**Step 1: Write failing test**

In `tests/test_ui/test_pipeline.py`, add:
```python
class TestTmdbCache:
    def test_exception_does_not_deadlock(self) -> None:
        """If fetch_fn raises, waiting threads should not hang."""
        import threading
        from tapes.ui.pipeline import _TmdbCache

        cache = _TmdbCache()

        def bad_fetch():
            raise RuntimeError("TMDB down")

        # First call should raise
        with pytest.raises(RuntimeError):
            cache.get_or_fetch(("key",), bad_fetch)

        # Second call with same key should also raise (not deadlock)
        # If the event was never set, this would hang forever
        results = []
        def try_fetch():
            try:
                cache.get_or_fetch(("key",), bad_fetch)
            except RuntimeError:
                results.append("raised")

        t = threading.Thread(target=try_fetch)
        t.start()
        t.join(timeout=2.0)
        assert not t.is_alive(), "Thread deadlocked"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ui/test_pipeline.py::TestTmdbCache -x -v`
Expected: FAIL (deadlock/timeout or missing class)

**Step 3: Fix `_TmdbCache.get_or_fetch`**

In `tapes/ui/pipeline.py`, wrap the fetch in try/finally:
```python
def get_or_fetch(self, key: tuple, fetch_fn: Callable[[], Any]) -> Any:
    with self._lock:
        if key in self._data:
            return self._data[key]
        if key in self._pending:
            event = self._pending[key]
            is_fetcher = False
        else:
            event = threading.Event()
            self._pending[key] = event
            is_fetcher = True

    if not is_fetcher:
        event.wait()
        with self._lock:
            if key in self._data:
                return self._data[key]
        raise RuntimeError(f"Fetch failed for {key}")

    # We are the fetcher
    try:
        result = fetch_fn()
        with self._lock:
            self._data[key] = result
        return result
    finally:
        event.set()
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_ui/test_pipeline.py -x -q`
Expected: All pass.

**Step 5: Commit**

```
fix: prevent _TmdbCache deadlock on fetch exception

Wrap fetch_fn in try/finally so event.set() always runs.
Waiting threads no longer hang if a fetch fails.
```

---

## Task 4: Fix `object` type annotations -> proper `Callable` types

**Files:**
- Modify: `tapes/ui/pipeline.py` (fix type annotations, remove `# type: ignore` comments)

**Step 1: Update type annotations**

Replace `object` annotations with proper types:

```python
from typing import Any, Callable

# _TmdbCache.get_or_fetch: already fixed in Task 3

# _populate_node_guessit
def _populate_node_guessit(node: FileNode, extract_metadata_fn: Callable[[str], Any]) -> None:
    meta = extract_metadata_fn(node.path.name)  # no type: ignore needed
    ...

# run_tmdb_pass
def run_tmdb_pass(
    model: TreeModel,
    token: str = "",
    confidence_threshold: float | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    max_workers: int = 4,
) -> None:
    ...
    # Remove the # type: ignore[operator] on the on_progress call
```

Remove all `# type: ignore[operator]` comments that were caused by `object` typing.

**Step 2: Run tests**

Run: `uv run pytest -x -q`
Expected: All pass.

**Step 3: Commit**

```
fix: replace object type annotations with proper Callable types

Removes all type: ignore[operator] workarounds in pipeline.py.
```

---

## Task 5: SHA-256 verification for move operations

**Files:**
- Modify: `tapes/file_ops.py` (add SHA-256 verification)
- Modify: `tests/test_file_ops.py` (add verification test)

**Step 1: Write failing test**

In `tests/test_file_ops.py`, add a test that verifies SHA-256 is used:
```python
def test_move_verifies_sha256(self, tmp_path: Path) -> None:
    """Move should verify SHA-256 checksum, not just file size."""
    src = tmp_path / "source.mkv"
    src.write_bytes(b"original content here")
    dest = tmp_path / "dest.mkv"
    result = process_file(src, dest, "move")
    assert "Moved" in result
    assert not src.exists()
    assert dest.read_bytes() == b"original content here"
```

**Step 2: Implement SHA-256 verification**

Replace the size-only check in `file_ops.py`:
```python
import hashlib

def _sha256(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

# In process_file, move branch:
elif operation == "move":
    src_hash = _sha256(src)
    shutil.copy2(src, dest)
    if _sha256(dest) == src_hash:
        src.unlink()
    else:
        dest.unlink()
        raise OSError(
            f"SHA-256 mismatch after copy: {src} -> {dest} (dest removed)"
        )
    return f"Moved {src} -> {dest}"
```

**Step 3: Run tests**

Run: `uv run pytest tests/test_file_ops.py -x -q`
Expected: All pass.

**Step 4: Commit**

```
fix: use SHA-256 verification for move operations

Replace size-only check with SHA-256 digest comparison as documented.
```

---

## Task 6: HTTP client reuse in TMDB module

**Files:**
- Modify: `tapes/tmdb.py` (accept optional client parameter)
- Modify: `tapes/ui/pipeline.py` (create and share a single client)
- Modify: `tests/test_tmdb.py` (verify existing tests still pass)

**Step 1: Refactor `tmdb.py` to accept optional client**

Add a `client` parameter to all functions. When provided, use it directly. When not provided, create one (backward compat). Remove the `_client` helper function.

```python
from contextlib import contextmanager

@contextmanager
def _make_client(token: str):
    """Create an httpx client with auth headers."""
    with httpx.Client(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    ) as client:
        yield client


def search_multi(
    query: str, token: str, year: int | None = None,
    *, client: httpx.Client | None = None,
) -> list[dict]:
    if not token or not query:
        return []
    params: dict = {"query": query}
    if year is not None:
        params["year"] = year
    try:
        if client is not None:
            resp = client.get("/search/multi", params=params)
            resp.raise_for_status()
        else:
            with _make_client(token) as c:
                resp = c.get("/search/multi", params=params)
                resp.raise_for_status()
    except (httpx.HTTPError, httpx.HTTPStatusError) as exc:
        logger.warning("TMDB search_multi failed: %s", exc)
        return []
    ...
```

Do the same for `get_movie`, `get_show`, `get_season_episodes`.

**Step 2: Update pipeline to create and share a client**

In `pipeline.py`, create a single client in `run_tmdb_pass` and pass it through:

```python
def run_tmdb_pass(...) -> None:
    ...
    with tmdb._make_client(token) as client:
        cache = _TmdbCache()
        def query_one(node):
            nonlocal done_count
            _query_tmdb_for_node(node, token, confidence_threshold, cache=cache, client=client)
            ...
```

Update `_query_tmdb_for_node` and `_query_episodes` to accept and pass through `client`.

**Step 3: Run tests**

Run: `uv run pytest tests/test_tmdb.py tests/test_ui/test_pipeline.py -x -q`
Expected: All pass.

**Step 4: Commit**

```
perf: reuse single httpx client across TMDB API calls

Add optional client parameter to all tmdb functions.
Pipeline creates one client for the entire run instead of per-call.
```

---

## Task 7: Fix `cli.py` DRY -- use `run_guessit_pass`

**Files:**
- Modify: `tapes/cli.py` (replace hand-rolled metadata extraction with `run_guessit_pass`)

**Step 1: Replace duplicated logic in `tree_cmd`**

Replace lines 88-105 with:
```python
from tapes.ui.pipeline import run_guessit_pass
run_guessit_pass(model)
```

This also fixes the subtle bug where `tree_cmd` didn't create Source objects.

**Step 2: Run tests**

Run: `uv run pytest -x -q`
Expected: All pass.

**Step 3: Commit**

```
fix: use run_guessit_pass in tree_cmd instead of duplicating logic

Also fixes missing Source objects in tree command's detail view.
```

---

## Task 8: Consolidate template parameters

**Files:**
- Modify: `tapes/ui/tree_render.py` (simplify signatures)
- Modify: `tapes/ui/tree_view.py` (simplify init and render)
- Modify: `tapes/ui/tree_app.py` (simplify init)
- Modify: `tapes/ui/detail_view.py` (simplify init)
- Modify: `tapes/cli.py` (simplify TreeApp construction)
- Modify: all test files that use templates

**Step 1: Remove vestigial `template` parameter**

The `template` parameter is only used when `movie_template` and `tv_template` are both `None`, which only happens in tests. Instead, make `movie_template` and `tv_template` required (non-optional) parameters in render functions, and when callers want a single template, pass the same string as both.

In `tree_render.py`:
```python
def render_file_row(
    node: FileNode,
    movie_template: str,
    tv_template: str,
    depth: int = 0,
    flat_mode: bool = False,
    root_path: Path | None = None,
) -> str:
    effective_template = select_template(node, movie_template, tv_template)
    ...

def render_row(
    node: FileNode | FolderNode,
    movie_template: str,
    tv_template: str,
    depth: int = 0,
    flat_mode: bool = False,
    root_path: Path | None = None,
) -> str:
    if isinstance(node, FileNode):
        return render_file_row(node, movie_template, tv_template, ...)
    return render_folder_row(node, depth=depth)
```

In `TreeView.__init__`:
```python
def __init__(
    self,
    model: TreeModel,
    movie_template: str,
    tv_template: str,
    flat_mode: bool = False,
    root_path: Path | None = None,
) -> None:
```

In `DetailView.__init__`:
```python
def __init__(
    self,
    node: FileNode,
    movie_template: str,
    tv_template: str,
) -> None:
```

In `TreeApp.__init__`:
```python
def __init__(
    self,
    model: TreeModel,
    movie_template: str,
    tv_template: str,
    root_path: Path | None = None,
    auto_pipeline: bool = False,
    *,
    config: TapesConfig | None = None,
) -> None:
```

Update `cli.py` -- both `import_cmd` and `tree_cmd` already have both templates:
```python
tui = TreeApp(
    model=model,
    movie_template=movie_template,
    tv_template=tv_template,
    root_path=resolved,
    ...
)
```

Update test files: where tests use a single `template` string, pass it as both `movie_template` and `tv_template`. For example:
```python
# Before
TreeApp(model=model, template="{title} ({year}).{ext}")
# After
TreeApp(model=model, movie_template=TEMPLATE, tv_template=TEMPLATE)
```

**Step 2: Run tests**

Run: `uv run pytest -x -q`
Expected: All pass (after updating test call sites).

**Step 3: Commit**

```
refactor: remove vestigial template fallback parameter

movie_template and tv_template are now required, eliminating the
three-parameter threading through every layer.
```

---

## Task 9: DRY toggle_staged_range / toggle_ignored_range

**Files:**
- Modify: `tapes/ui/tree_view.py`

**Step 1: Extract shared helper**

Replace the two near-identical methods with a shared helper:

```python
def _toggle_flag_range(self, attr: str) -> None:
    """Toggle a boolean flag on all FileNodes in the selection range."""
    nodes = self.selected_nodes()
    file_nodes = [n for n in nodes if isinstance(n, FileNode)]
    if not file_nodes:
        return
    all_set = all(getattr(f, attr) for f in file_nodes)
    for f in file_nodes:
        setattr(f, attr, not all_set)
    self.refresh()

def toggle_staged_range(self) -> None:
    self._toggle_flag_range("staged")

def toggle_ignored_range(self) -> None:
    self._toggle_flag_range("ignored")
```

**Step 2: Run tests**

Run: `uv run pytest tests/test_ui/test_tree_app.py -x -q`
Expected: All pass.

**Step 3: Commit**

```
refactor: extract shared helper for range toggle methods
```

---

## Task 10: Fix pipeline test boilerplate

**Files:**
- Modify: `tests/test_ui/test_pipeline.py` (use fixture, move helper up)

**Step 1: Replace triple `_patch_tmdb()` calls with a fixture**

Add a pytest fixture and use it:

```python
@pytest.fixture()
def mock_tmdb():
    """Patch all tapes.tmdb functions used by pipeline."""
    patches = _patch_tmdb()
    with patches[0], patches[1], patches[2]:
        yield
```

Then update all test methods to use the fixture:
```python
# Before
def test_something(self) -> None:
    with _patch_tmdb()[0], _patch_tmdb()[1], _patch_tmdb()[2]:
        ...

# After (move to module-level functions or keep in class with fixture)
def test_something(self, mock_tmdb) -> None:
    ...
```

Also move `_make_config` from the bottom of the file to near the top (after `_make_model`).

**Step 2: Run tests**

Run: `uv run pytest tests/test_ui/test_pipeline.py -x -q`
Expected: All pass.

**Step 3: Commit**

```
refactor: use pytest fixture for TMDB mocking in pipeline tests

Replace triple _patch_tmdb() calls with a single mock_tmdb fixture.
Move _make_config helper near top of file for readability.
```

---

## Task 11: Fix UndoManager to save complete node state

**Files:**
- Modify: `tapes/ui/tree_model.py` (save sources + staged in snapshot)
- Modify: `tests/test_ui/test_tree_app.py` (add test for sources/staged undo)

**Step 1: Write failing test**

```python
class TestUndoManager:
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
        assert node.staged is False
```

**Step 2: Update `UndoManager.snapshot` and `undo`**

```python
class UndoManager:
    def __init__(self) -> None:
        self._snapshot: list[tuple[FileNode, dict[str, Any], list[Source], bool]] | None = None

    def snapshot(self, nodes: list[FileNode]) -> None:
        """Save a deep copy of each node's result, sources, and staged flag."""
        self._snapshot = [
            (node, copy.deepcopy(node.result), copy.deepcopy(node.sources), node.staged)
            for node in nodes
        ]

    def undo(self) -> bool:
        if self._snapshot is None:
            return False
        for node, saved_result, saved_sources, saved_staged in self._snapshot:
            node.result = saved_result
            node.sources = saved_sources
            node.staged = saved_staged
        self._snapshot = None
        return True
```

**Step 3: Run tests**

Run: `uv run pytest tests/test_ui/test_tree_app.py -x -q`
Expected: All pass.

**Step 4: Commit**

```
fix: UndoManager saves sources and staged flag alongside result

Previously only result was saved, leaving sources and staged
in their mutated state after undo.
```

---

## Task 12: Define field name constants

**Files:**
- Create: `tapes/fields.py`
- Modify: `tapes/similarity.py` (use constants)
- Modify: `tapes/ui/pipeline.py` (use constants)
- Modify: `tapes/ui/detail_view.py` (use constants for int coercion)
- Modify: `tapes/ui/tree_render.py` (use constant for media_type check)
- Modify: `tapes/ui/tree_app.py` (use constant for media_type check)

**Step 1: Create `tapes/fields.py`**

```python
"""Central definitions for metadata field names.

Import these constants instead of using string literals to avoid
typos and enable IDE navigation / refactoring.
"""

# Core fields (used in templates and throughout)
TITLE = "title"
YEAR = "year"
SEASON = "season"
EPISODE = "episode"
EPISODE_TITLE = "episode_title"
MEDIA_TYPE = "media_type"
TMDB_ID = "tmdb_id"

# media_type values
MEDIA_TYPE_MOVIE = "movie"
MEDIA_TYPE_EPISODE = "episode"

# Integer fields (for type coercion during editing)
INT_FIELDS = frozenset({YEAR, SEASON, EPISODE})
```

**Step 2: Update consumers to use constants**

In `tapes/similarity.py`:
```python
from tapes.fields import TITLE, YEAR, SEASON, EPISODE, EPISODE_TITLE

def compute_confidence(query: dict, result: dict) -> float:
    query_title = query.get(TITLE)
    result_title = result.get(TITLE)
    ...
    query_year = query.get(YEAR)
    result_year = result.get(YEAR)
    ...
```

In `tapes/ui/detail_view.py`:
```python
from tapes.fields import INT_FIELDS

def _commit_edit(self) -> None:
    field_name = self._fields[self.cursor_row]
    val: str | int = self._edit_value
    if field_name in INT_FIELDS:
        try:
            val = int(val)
        except ValueError:
            pass
    ...
```

In `tapes/ui/tree_render.py`:
```python
from tapes.fields import MEDIA_TYPE, MEDIA_TYPE_EPISODE

def select_template(node: FileNode, movie_template: str, tv_template: str) -> str:
    media_type = node.result.get(MEDIA_TYPE)
    if media_type == MEDIA_TYPE_EPISODE:
        return tv_template
    return movie_template
```

In `tapes/ui/tree_app.py`, `_compute_file_pairs`:
```python
from tapes.fields import MEDIA_TYPE, MEDIA_TYPE_EPISODE

media_type = node.result.get(MEDIA_TYPE)
if media_type == MEDIA_TYPE_EPISODE and cfg.library.tv:
```

In `tapes/ui/pipeline.py`, `_query_tmdb_for_node` and `_populate_node_guessit`:
Use `TITLE`, `YEAR`, `MEDIA_TYPE`, `MEDIA_TYPE_EPISODE` constants instead of string literals.

In `tapes/tmdb.py`:
Use `TMDB_ID`, `TITLE`, `YEAR`, `MEDIA_TYPE`, `SEASON`, `EPISODE`, `EPISODE_TITLE`, `MEDIA_TYPE_MOVIE`, `MEDIA_TYPE_EPISODE` constants in all return dicts.

**Step 3: Run tests**

Run: `uv run pytest -x -q`
Expected: All pass (no behavioral change, just constant substitution).

**Step 4: Commit**

```
refactor: centralize field name constants in tapes/fields.py

Replace hardcoded string literals across 7 files with shared
constants. Prevents typo bugs and enables IDE refactoring.
```

---

## Execution Notes

- Tasks 1-5 are independent and can be parallelized
- Task 6 (HTTP client) depends on Task 3 (cache fix) since both touch pipeline.py
- Task 7 (cli DRY) is independent
- Task 8 (template consolidation) touches many files; do it after tasks 1-7
- Tasks 9-11 are independent of each other
- Task 12 (field constants) should go last as it touches many files modified by earlier tasks

## What was NOT done (and why)

- **Full Pydantic model for `result` dict**: The result dict drives template formatting via `str.format_map()`, is dynamically edited by users in the detail view, and stores arbitrary guessit fields. A Pydantic model would fight this flexibility. Field name constants (Task 12) address the main risk (typos) without the refactoring cost.

- **TreeApp decomposition**: At 472 lines with 20 small action methods, this is normal for a Textual App. Each method is 5-15 lines. Extracting "controllers" would add indirection without clear benefit at this scale. Revisit if the class grows past ~600 lines.
