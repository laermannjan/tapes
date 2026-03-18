# Code Review Issues Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all non-deferred open issues from the code review (I17-I42), improving reliability, performance, and code quality.

**Architecture:** Four phases. Phase 0 moves business logic out of `tapes/ui/` (I33) since it touches imports everywhere. Phases 1-2 are parallel worktrees per issue group. Phase 3 adds test coverage for all changes.

**Tech Stack:** Python 3.11+, uv, httpx, tenacity (new dep), Textual 8

**Decisions made:**
- TMDB retry: `tenacity` with exponential backoff, respect `Retry-After` on 429
- No proactive rate limiting (TMDB's limit is undisclosed, ~40 req/s currently)
- Thread safety: dispatch pattern (`post_update: Callable`) to decouple pipeline from UI
- `file_ops.process_file`: add `progress_callback` param (prep for future progress bar)
- `best_match_found` in pipeline.py already removed (verified)

---

## Phase 0: I33 -- Move business logic out of `tapes/ui/`

**Why first:** Touches imports in 20+ files. Must land before parallel work starts.

### Task 0.1: Move `tapes/ui/tree_model.py` to `tapes/tree_model.py`

**Files:**
- Move: `tapes/ui/tree_model.py` -> `tapes/tree_model.py`
- Update imports in all consumers

The entire file is pure logic (zero Textual imports).

**Step 1:** Move the file

```bash
git mv tapes/ui/tree_model.py tapes/tree_model.py
```

**Step 2:** Update all import sites. Replace `tapes.ui.tree_model` with `tapes.tree_model` in:

- `tapes/ui/tree_render.py:12`
- `tapes/ui/tree_app.py:21-25`
- `tapes/ui/tree_view.py:12`
- `tapes/ui/detail_view.py:21`
- `tapes/ui/detail_render.py:7`
- `tapes/ui/pipeline.py:23`
- `tapes/ui/commit_view.py:13`
- `tapes/cli.py:42`
- `tests/test_ui/test_tree_model.py`
- `tests/test_ui/test_pipeline.py`
- `tests/test_ui/test_tree_render.py`
- `tests/test_ui/test_commit_view.py`
- `tests/test_ui/test_detail_view.py`
- `tests/test_ui/test_tree_app.py`
- `tests/test_ui/test_border_rendering.py`

**Step 3:** Run tests

```bash
uv run pytest -x -q
```

**Step 4:** Commit

```bash
git commit -m "refactor: move tree_model.py out of ui/ package"
```

### Task 0.2: Extract pure rendering logic from `tapes/ui/tree_render.py`

These functions are pure data logic with no Textual dependency (only Rich Text):

- `template_field_names()` (line 26-28)
- `select_template()` (line 31-40)
- `full_extension()` (line 51-84) + `_is_tag()` (line 46-48)
- `compute_dest()` (line 87-116)

However, they're deeply interleaved with Rich rendering code in the same file, and moving them would split one cohesive module into two. The rendering functions (`render_dest`, `render_file_row`, etc.) call `compute_dest`, `full_extension`, and `select_template` directly.

**Decision:** Keep these in `tree_render.py` for now. The file already has no Textual imports -- it only uses Rich. Moving 5 functions out would create a circular import or require the render functions to import from a sibling module for no real benefit. The issue description says "move to tapes/ proper" but the actual coupling makes this a net negative. Revisit if/when a non-Rich consumer needs these functions.

### Task 0.3: Extract `categorize_staged` from `tapes/ui/commit_view.py`

**Files:**
- Modify: `tapes/ui/commit_view.py` -- remove `categorize_staged`, update import
- Create: `tapes/categorize.py` -- new home for `categorize_staged`
- Update: `tapes/ui/tree_app.py:18` -- update import

**Step 1:** Create `tapes/categorize.py`:

```python
"""Categorization logic for staged files."""

from __future__ import annotations

from typing import Any

from tapes.fields import MEDIA_TYPE, MEDIA_TYPE_EPISODE, MEDIA_TYPE_MOVIE, TITLE, SEASON
from tapes.tree_model import FileNode

SUBTITLE_EXTS = frozenset({".srt", ".sub", ".ass", ".ssa", ".idx"})
SIDECAR_EXTS = frozenset({".nfo", ".xml", ".jpg", ".png"})


def categorize_staged(files: list[FileNode]) -> dict[str, int]:
    """Categorize staged files and return counts."""
    movies = 0
    episodes = 0
    subtitles = 0
    sidecars = 0
    other = 0
    shows: set[str] = set()
    seasons: set[tuple[str, Any]] = set()

    for f in files:
        ext = f.path.suffix.lower()
        media_type = f.result.get(MEDIA_TYPE)

        if media_type == MEDIA_TYPE_MOVIE:
            movies += 1
        elif media_type == MEDIA_TYPE_EPISODE:
            episodes += 1
            title = f.result.get(TITLE, "")
            season = f.result.get(SEASON)
            if title:
                shows.add(title)
            if title and season is not None:
                seasons.add((title, season))
        elif ext in SUBTITLE_EXTS:
            subtitles += 1
        elif ext in SIDECAR_EXTS:
            sidecars += 1
        else:
            other += 1

    return {
        "movies": movies,
        "episodes": episodes,
        "shows": len(shows),
        "seasons": len(seasons),
        "subtitles": subtitles,
        "sidecars": sidecars,
        "other": other,
        "total": len(files),
    }
```

**Step 2:** Update `commit_view.py` -- remove `categorize_staged`, `SUBTITLE_EXTS`, `SIDECAR_EXTS`. Import from new location:

```python
from tapes.categorize import categorize_staged
```

Remove the `MEDIA_TYPE_MOVIE` import if no longer needed (check `categorize_staged` was the only consumer).

**Step 3:** Update `tapes/ui/tree_app.py:18`:

```python
from tapes.categorize import categorize_staged
from tapes.ui.commit_view import CommitView
```

**Step 4:** Update test imports if any test imports `categorize_staged` from `commit_view`.

**Step 5:** Run tests, commit:

```bash
uv run pytest -x -q
git commit -m "refactor: extract categorize_staged from ui/commit_view"
```

### Task 0.4: Extract pipeline business logic

`tapes/ui/pipeline.py` has zero Textual imports. The entire file is business logic.

**Files:**
- Move: `tapes/ui/pipeline.py` -> `tapes/pipeline.py`
- Update imports in all consumers

**Step 1:** Move the file

```bash
git mv tapes/ui/pipeline.py tapes/pipeline.py
```

**Step 2:** Update import `tapes.ui.tree_model` -> `tapes.tree_model` inside the moved file.

**Step 3:** Update all import sites. Replace `tapes.ui.pipeline` with `tapes.pipeline` in:

- `tapes/cli.py:71`
- `tapes/ui/detail_view.py:418` (local import inside method)
- `tapes/ui/tree_app.py:131,150,439`
- `tests/test_ui/test_pipeline.py`

**Step 4:** Run tests, commit:

```bash
uv run pytest -x -q
git commit -m "refactor: move pipeline.py out of ui/ package"
```

---

## Phase 1: Independent fixes (parallel worktrees)

All tasks branch from main after Phase 0 is merged. Each runs in its own worktree.

---

### Task 1.1: I17 -- Implement hardlink operation

**Files:**
- Modify: `tapes/file_ops.py`
- Test: `tests/test_file_ops.py`

**Step 1:** Write the failing test in `tests/test_file_ops.py`:

```python
def test_hardlink_creates_hard_link(tmp_path):
    src = tmp_path / "source.txt"
    src.write_text("hello")
    dest = tmp_path / "out" / "dest.txt"
    result = process_file(src, dest, "hardlink")
    assert dest.exists()
    assert dest.read_text() == "hello"
    assert dest.stat().st_ino == src.stat().st_ino  # same inode = hard link
    assert "Hardlinked" in result


def test_hardlink_dry_run(tmp_path):
    src = tmp_path / "source.txt"
    src.write_text("hello")
    dest = tmp_path / "out" / "dest.txt"
    result = process_file(src, dest, "hardlink", dry_run=True)
    assert not dest.exists()
    assert "[dry-run]" in result
```

**Step 2:** Run test to verify it fails:

```bash
uv run pytest tests/test_file_ops.py -k hardlink -v
```

Expected: FAIL with `ValueError: Unknown operation: 'hardlink'`

**Step 3:** Add hardlink support in `tapes/file_ops.py`. After the `if operation == "link":` block (line 55-57), add:

```python
    if operation == "hardlink":
        dest.parent.mkdir(parents=True, exist_ok=True)  # already done above, but safe
        import os
        os.link(src, dest)
        return f"Hardlinked {dest} -> {src}"
```

Wait -- `dest.parent.mkdir` is already called on line 41. So just add before the final `raise ValueError`:

```python
    if operation == "hardlink":
        import os
        os.link(src, dest)
        return f"Hardlinked {dest} -> {src}"
```

Also update the docstring for `operation` param to include `"hardlink"`.

**Step 4:** Run tests:

```bash
uv run pytest tests/test_file_ops.py -v
```

**Step 5:** Commit:

```bash
git commit -m "feat: implement hardlink file operation (I17)"
```

---

### Task 1.2: I20 -- File ops single-pass copy+hash with progress callback

**Files:**
- Modify: `tapes/file_ops.py`
- Test: `tests/test_file_ops.py`

**Step 1:** Write failing tests:

```python
def test_move_single_pass(tmp_path):
    """Move should only read source once (single-pass copy+hash)."""
    src = tmp_path / "big.bin"
    src.write_bytes(b"x" * 10000)
    dest = tmp_path / "out" / "big.bin"
    result = process_file(src, dest, "move")
    assert not src.exists()
    assert dest.read_bytes() == b"x" * 10000
    assert "Moved" in result


def test_progress_callback(tmp_path):
    """Progress callback should be called during copy."""
    src = tmp_path / "data.bin"
    src.write_bytes(b"x" * 10000)
    dest = tmp_path / "out" / "data.bin"
    calls = []
    process_file(src, dest, "copy", progress_callback=lambda copied, total: calls.append((copied, total)))
    assert len(calls) > 0
    assert calls[-1][0] == calls[-1][1]  # last call: copied == total
```

**Step 2:** Rewrite `_sha256` to use `hashlib.file_digest()` (Python 3.11+):

```python
def _sha256(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()
```

**Step 3:** Rewrite move operation as single-pass copy+hash. Replace the current `_sha256` + `shutil.copy2` pattern with a streaming copy that hashes while copying:

```python
_COPY_BUFSIZE = 1024 * 1024  # 1 MB


def _copy_and_hash(
    src: Path,
    dest: Path,
    progress_callback: Callable[[int, int], None] | None = None,
) -> str:
    """Copy src to dest while computing SHA-256 of the data written.

    Returns the hex digest. Preserves file metadata (like shutil.copy2).
    """
    total = src.stat().st_size
    h = hashlib.sha256()
    copied = 0
    with src.open("rb") as fsrc, dest.open("wb") as fdst:
        while True:
            buf = fsrc.read(_COPY_BUFSIZE)
            if not buf:
                break
            fdst.write(buf)
            h.update(buf)
            copied += len(buf)
            if progress_callback is not None:
                progress_callback(copied, total)
    shutil.copystat(src, dest)
    return h.hexdigest()
```

**Step 4:** Update `process_file` signature to accept `progress_callback`:

```python
def process_file(
    src: Path,
    dest: Path,
    operation: str,
    dry_run: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
) -> str:
```

Update the copy operation to use `_copy_and_hash`:

```python
    if operation == "copy":
        _copy_and_hash(src, dest, progress_callback)
        return f"Copied {src} -> {dest}"
    if operation == "move":
        src_hash = _copy_and_hash(src, dest, progress_callback)
        if _sha256(dest) == src_hash:
            src.unlink()
        else:
            dest.unlink()
            raise OSError(f"SHA-256 mismatch after copy: {src} -> {dest} (dest removed)")
        return f"Moved {src} -> {dest}"
```

**Step 5:** Add `from collections.abc import Callable` import.

**Step 6:** Run tests, commit:

```bash
uv run pytest tests/test_file_ops.py -v
git commit -m "perf: single-pass copy+hash and progress callback (I20)"
```

---

### Task 1.3: I25 -- Scanner rglob to os.walk

**Files:**
- Modify: `tapes/scanner.py`
- Test: `tests/test_scanner.py`

**Step 1:** Rewrite the scan function to use `os.walk`:

```python
import os

def scan(root: Path, ignore_patterns: list[str] | None = None) -> list[Path]:
    if ignore_patterns is None:
        ignore_patterns = []

    if root.is_file():
        if _matches_ignore(root, ignore_patterns):
            return []
        if _is_video(root) and _is_sample(root):
            return []
        return [root]

    results: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune hidden directories in-place (prevents descending)
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        dirnames.sort()

        for name in sorted(filenames):
            if name.startswith("."):
                continue
            path = Path(dirpath) / name
            if _matches_ignore(path, ignore_patterns):
                continue
            if _is_video(path) and _is_sample(path):
                continue
            results.append(path)

    results.sort()
    return results
```

**Step 2:** Remove `_is_hidden_path()` -- no longer needed since `os.walk` prunes hidden dirs in-place.

**Step 3:** Run tests:

```bash
uv run pytest tests/test_scanner.py -v
```

**Step 4:** Commit:

```bash
git commit -m "perf: use os.walk instead of rglob for scanning (I25)"
```

---

### Task 1.4: I28 -- Use string.Formatter().parse() for template fields

**Files:**
- Modify: `tapes/ui/tree_render.py`
- Test: `tests/test_ui/test_tree_render.py`

**Step 1:** Write a test for escaped braces:

```python
def test_template_field_names_escaped_braces():
    """Escaped braces should not be extracted as field names."""
    assert template_field_names("{{literal}} {title}/{year}") == ["title", "year"]
```

**Step 2:** Run test to see it fail (current regex picks up "literal").

**Step 3:** Replace `template_field_names` implementation:

```python
import string

def template_field_names(template: str) -> list[str]:
    """Extract unique field names referenced in a template string."""
    return list(dict.fromkeys(
        fname for _, fname, _, _ in string.Formatter().parse(template) if fname is not None
    ))
```

Remove the `import re` if no other function in the file uses it. (Check: `compute_dest` uses `re.sub` on line 115, so keep it.)

**Step 4:** Run tests:

```bash
uv run pytest tests/test_ui/test_tree_render.py -v
```

**Step 5:** Commit:

```bash
git commit -m "fix: use string.Formatter().parse() for template fields (I28)"
```

---

### Task 1.5: I37a -- Name magic numbers

**Files:**
- Modify: `tapes/ui/tree_app.py`, `tapes/pipeline.py`, `tapes/tmdb.py`, `tapes/ui/tree_view.py`

No new tests needed -- these are pure renames.

**Step 1:** `tapes/tmdb.py` -- add constant and use it:

```python
REQUEST_TIMEOUT_S = 10.0
```

In `create_client`: replace `timeout=10.0` with `timeout=REQUEST_TIMEOUT_S`.

**Step 2:** `tapes/pipeline.py` -- add constant:

```python
MAX_TMDB_RESULTS = 3
```

Replace `search_results[:3]` (line 280) with `search_results[:MAX_TMDB_RESULTS]`.
Replace `all_episode_sources[:3]` (line 396) with `all_episode_sources[:MAX_TMDB_RESULTS]`.

Also: `DEFAULT_MAX_WORKERS = 4`, replace `max_workers: int = 4` with `max_workers: int = DEFAULT_MAX_WORKERS`.

**Step 3:** `tapes/ui/tree_view.py` -- add constant:

```python
DEFAULT_ARROW_COL = 40
```

Replace `self._arrow_col: int = 40` with `self._arrow_col: int = DEFAULT_ARROW_COL`.

**Step 4:** `tapes/ui/tree_app.py` -- add constant:

```python
DETAIL_CHROME_LINES = 9
```

Replace both `+ 9` occurrences (lines 175, 187) with `+ DETAIL_CHROME_LINES`.

**Step 5:** Run tests, commit:

```bash
uv run pytest -x -q
git commit -m "refactor: replace magic numbers with named constants (I37a)"
```

---

### Task 1.6: I40 -- Dead code removal

**Files:**
- Modify: `tapes/tmdb.py`, `tapes/tree_model.py`, `tapes/ui/detail_render.py`, `tapes/ui/tree_view.py`
- Modify: `tests/test_tmdb.py`, `tests/test_ui/test_tree_model.py`, `tests/test_ui/test_detail_view.py`, `tests/test_ui/test_tree_app.py`

Dead code confirmed (only called from tests):
1. `get_movie()` in `tapes/tmdb.py` (lines 108-138) + `TestGetMovie` in `tests/test_tmdb.py`
2. `TreeModel.flatten()` + `_flatten_children()` in `tapes/tree_model.py` (lines 45-63) + 6 tests in `test_tree_model.py`
3. `accept_best_source()` in `tapes/tree_model.py` (lines 210-223) + 4 tests in `test_tree_app.py`
4. `render_detail_header()` in `tapes/ui/detail_render.py` (lines 34-40) + `TestRenderDetailHeader` tests
5. `render_detail_grid()` in `tapes/ui/detail_render.py` (lines 43-83) + `TestRenderDetailGrid` tests + `col()` helper (only used by `render_detail_grid`)
6. `render_tree()` in `tapes/ui/tree_view.py` (lines 243-260) + tests in `test_tree_app.py`

**Step 1:** Remove each dead function and its tests. Be careful:
- `col()` in `detail_render.py` is ONLY used by `render_detail_grid` -- remove both
- `LABEL_WIDTH` and `COL_WIDTH` in `detail_render.py` are ONLY used by `render_detail_grid` and `col` -- remove both
- Keep `get_display_fields`, `display_val`, `is_multi_value`, `diff_style`, `confidence_style` (still used)

**Step 2:** Run tests to verify nothing broke:

```bash
uv run pytest -x -q
```

**Step 3:** Commit:

```bash
git commit -m "chore: remove dead code -- get_movie, flatten, accept_best_source, render_detail_header/grid, render_tree (I40)"
```

---

### Task 1.7: I41 -- Error handling fixes

**Files:**
- Modify: `tapes/tmdb.py`, `tapes/file_ops.py`, `tapes/ui/tree_app.py`

**Step 1:** `tapes/tmdb.py` -- fix redundant exception catch at lines 67, 126, 159. Replace:

```python
except (httpx.HTTPError, httpx.HTTPStatusError) as exc:
```

with:

```python
except httpx.HTTPError as exc:
```

Do this at all 3 locations (search_multi, get_movie if not removed by I40, get_show, get_season_episodes).

Note: if I40 already removed `get_movie`, only fix the remaining 3 locations.

**Step 2:** `tapes/file_ops.py` -- add logging for errors. Add `import logging` and:

```python
logger = logging.getLogger(__name__)
```

Change line 84-85 from:

```python
        except Exception as exc:  # noqa: BLE001
            results.append(f"Error processing {src}: {exc}")
```

to:

```python
        except Exception:  # noqa: BLE001
            logger.exception("Error processing %s", src)
            results.append(f"Error processing {src}")
```

**Step 3:** `tapes/ui/tree_app.py` -- narrow exception suppression at line 125. Change:

```python
        with contextlib.suppress(Exception):
            self.theme = "textual-ansi"
```

to:

```python
        try:
            self.theme = "textual-ansi"
        except Exception:  # noqa: BLE001
            logger.warning("Could not set textual-ansi theme, using default")
```

Add `import logging` and `logger = logging.getLogger(__name__)` at module level.

**Step 4:** `tapes/ui/tree_app.py` -- add `NamedTuple` for `_detail_snapshot`. Add at module level:

```python
from typing import NamedTuple

class _NodeSnapshot(NamedTuple):
    node: FileNode
    result: dict
    sources: list
    staged: bool
```

Change type annotation at line 94:

```python
self._detail_snapshot: list[_NodeSnapshot] | None = None
```

Update the snapshot creation (line 170-171) to use `_NodeSnapshot(...)`.
Update the restore (line 240-243) -- unpacking works identically with NamedTuple.

**Step 5:** Run tests, commit:

```bash
uv run pytest -x -q
git commit -m "fix: improve error handling -- redundant catch, logging, narrowed suppress (I41)"
```

---

### Task 1.8: I23+I24 -- Render caching

**Files:**
- Modify: `tapes/ui/tree_render.py`, `tapes/tree_model.py`, `tapes/ui/tree_view.py`, `tapes/ui/detail_view.py`

**Step 1:** I23 -- Cache `all_files()` on TreeModel. The tree structure never changes after build. Add in `tapes/tree_model.py`:

```python
class TreeModel:
    root: FolderNode

    def __post_init__(self) -> None:
        self._cached_files: list[FileNode] | None = None

    def all_files(self) -> list[FileNode]:
        if self._cached_files is None:
            self._cached_files = collect_files(self.root)
        return self._cached_files
```

**Step 2:** I24a -- Cache `template_field_names`. Add `@functools.lru_cache` in `tapes/ui/tree_render.py`:

```python
import functools

@functools.lru_cache(maxsize=8)
def template_field_names(template: str) -> list[str]:
    ...
```

**Step 3:** I24b -- Cache `_compute_arrow_col` in `tapes/ui/tree_view.py`. The arrow column only changes when the tree structure changes (items are refreshed). Compute once in `_refresh_items` and store:

Find where `_compute_arrow_col` is called and ensure it's only called once per refresh, storing the result in `self._arrow_col`.

**Step 4:** Run tests, commit:

```bash
uv run pytest -x -q
git commit -m "perf: cache all_files, template_field_names, arrow column (I23+I24)"
```

---

## Phase 2: Dependent fixes (parallel worktrees, after Phase 1 merged)

---

### Task 2.1: I26+I18+I21+I22 -- TMDB reliability

**Files:**
- Modify: `tapes/tmdb.py`, `tapes/pipeline.py`
- Create: (none -- tenacity is just a dependency)
- Test: `tests/test_tmdb.py`, `tests/test_pipeline.py`

#### Step 1: Add tenacity dependency

```bash
uv add "tenacity>=9,<10"
```

#### Step 2: I26 -- Extract request helper in `tapes/tmdb.py`

The `if client is not None: ... else: with create_client() as c: ...` pattern is duplicated 4 times (now 3 after I40 removes `get_movie`). Extract:

```python
def _request(
    method: str,
    path: str,
    token: str,
    client: httpx.Client | None = None,
    **kwargs,
) -> httpx.Response:
    """Make a TMDB API request, reusing client if provided."""
    if client is not None:
        resp = client.request(method, path, **kwargs)
        resp.raise_for_status()
        return resp
    with create_client(token) as c:
        resp = c.request(method, path, **kwargs)
        resp.raise_for_status()
        return resp
```

Refactor `search_multi`, `get_show`, `get_season_episodes` to use `_request`.

#### Step 3: I21 -- Add tenacity retry with Retry-After

Wrap `_request` with tenacity:

```python
import tenacity

def _retry_after_wait(retry_state: tenacity.RetryCallState) -> float:
    """Extract wait time from Retry-After header on 429 responses."""
    exc = retry_state.outcome.exception()
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
        retry_after = exc.response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
    return tenacity.wait_exponential(multiplier=1, min=1, max=30)(retry_state)


@tenacity.retry(
    retry=tenacity.retry_if_exception_type(httpx.HTTPStatusError)
    & tenacity.retry_if_result(lambda r: False)  # never retry on result
    | tenacity.retry_if_exception(lambda e: isinstance(e, httpx.HTTPStatusError) and e.response.status_code in (429, 500, 502, 503, 504)),
    wait=_retry_after_wait,
    stop=tenacity.stop_after_attempt(3),
    reraise=True,
)
def _request(...):
    ...
```

Simplify: use a custom retry predicate:

```python
def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {429, 500, 502, 503, 504}

@tenacity.retry(
    retry=tenacity.retry_if_exception(_is_retryable),
    wait=_retry_after_wait,
    stop=tenacity.stop_after_attempt(3),
    reraise=True,
)
def _request(...):
    ...
```

#### Step 4: I18 -- Fix _TmdbCache stuck keys

In `tapes/pipeline.py`, `_TmdbCache.get_or_fetch`: when the fetcher fails, the key stays in `_pending` forever. Fix:

```python
        # We are the fetcher
        try:
            result = fetch_fn()
            with self._lock:
                self._data[key] = result
            return result
        except Exception:
            with self._lock:
                del self._pending[key]  # allow retry on next request
            raise
        finally:
            event.set()
```

The key change: on failure, remove from `_pending` (allow retry) instead of leaving it stuck. The `finally: event.set()` still fires to unblock waiters, who will then get `KeyError` and can also retry.

#### Step 5: I22 -- Remove dead `best_match_found` variable

Already confirmed removed. Verify and skip if true. If somehow still present, delete the assignment.

#### Step 6: Write tests for cache retry:

```python
def test_cache_retries_after_failure():
    cache = _TmdbCache()
    call_count = 0

    def failing_then_succeeding():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("transient")
        return "result"

    with pytest.raises(RuntimeError):
        cache.get_or_fetch(("key",), failing_then_succeeding)

    # Second attempt should retry (key removed from pending)
    result = cache.get_or_fetch(("key",), failing_then_succeeding)
    assert result == "result"
    assert call_count == 2
```

#### Step 7: Run tests, commit:

```bash
uv run pytest -x -q
git commit -m "fix: TMDB reliability -- request helper, tenacity retry, cache retry (I26+I18+I21+I22)"
```

---

### Task 2.2: I19 -- Thread safety via dispatch pattern

**Files:**
- Modify: `tapes/pipeline.py`, `tapes/ui/tree_app.py`

**Step 1:** Add `post_update` parameter to pipeline functions. In `tapes/pipeline.py`:

```python
def run_tmdb_pass(
    model: TreeModel,
    token: str = "",
    confidence_threshold: float | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
    post_update: Callable[[Callable[[], None]], None] | None = None,
) -> None:
```

If `post_update` is None, default to direct execution:

```python
    if post_update is None:
        post_update = lambda fn: fn()
```

**Step 2:** Wrap all node mutations in `_query_tmdb_for_node` and `_query_episodes` with `post_update`:

Instead of:
```python
node.result[field] = val
```

Do:
```python
def _apply(node=node, field=field, val=val):
    node.result[field] = val
post_update(_apply)
```

Thread the `post_update` parameter through `_query_tmdb_for_node` -> `_query_episodes`.

Key mutation sites:
- `_query_tmdb_for_node` line 304-307: apply best fields + set staged
- `_query_tmdb_for_node` line 315: `node.sources.extend(tmdb_sources)`
- `_query_episodes` line 402-406: apply best episode fields
- `_query_episodes` line 412: `node.sources.extend(top_sources)`

Similarly update `refresh_tmdb_source`.

**Step 3:** In `tapes/ui/tree_app.py`, pass `post_update=self.call_from_thread` when calling pipeline from workers:

```python
run_tmdb_pass(
    self.model,
    token=...,
    on_progress=...,
    post_update=self.call_from_thread,
)
```

**Step 4:** Run tests, commit:

```bash
uv run pytest -x -q
git commit -m "fix: thread-safe node mutations via dispatch pattern (I19)"
```

---

### Task 2.3: I38+I39 -- Code dedup and constant consolidation

**Files:**
- Modify: `tapes/ui/tree_render.py`, `tapes/ui/detail_render.py`, `tapes/ui/bottom_bar.py`, `tapes/ui/commit_view.py`, `tapes/ui/detail_view.py`, `tapes/ui/help_overlay.py`

#### Step 1: I39 -- Consolidate color constants

Add to `tapes/ui/tree_render.py` (where `MUTED`, `STAGED_COLOR` etc. already live):

```python
ACCENT = "#B1B9F9"
INACTIVE = "#555555"
EMBER = "#E07A47"
SOFT_GREEN = "#86E89A"
SOFT_RED = "#FF7A7A"
SOFT_BLUE = "#7AB8FF"
```

Update consumers:
- `bottom_bar.py`: remove local `ACCENT`, `INACTIVE`. Import from `tree_render`.
- `commit_view.py`: remove local `ACCENT`. Import from `tree_render`.
- `detail_view.py`: remove local `ACCENT`. Import from `tree_render`.
- `help_overlay.py`: remove local `ACCENT`. Import from `tree_render`.
- `detail_render.py`: replace inline hex codes with constants. Import `EMBER`, `SOFT_GREEN`, `SOFT_RED` from `tree_render`.
- `bottom_bar.py` `OP_COLORS`: use `SOFT_GREEN`, `EMBER`, `SOFT_BLUE` constants.

#### Step 2: I39 -- Use field constants in commit_view.py

In `tapes/ui/commit_view.py` (now in `tapes/categorize.py` after I33), replace:
```python
title = f.result.get("title", "")
season = f.result.get("season")
```
with:
```python
title = f.result.get(TITLE, "")
season = f.result.get(SEASON)
```

(Already done in Task 0.3 above since we moved the function.)

#### Step 3: I38 -- Extract `cycle_operation` shared function

`cycle_operation` is identical in `BottomBar` and `CommitView`. Extract to `bottom_bar.py` as a module-level function:

```python
def cycle_operation_index(current: str, delta: int = 1) -> str:
    """Return the next operation after cycling by delta."""
    idx = OPERATIONS.index(current)
    return OPERATIONS[(idx + delta) % len(OPERATIONS)]
```

Update both `BottomBar.cycle_operation` and `CommitView.cycle_operation` to call it:

```python
def cycle_operation(self, delta: int = 1) -> None:
    self.operation = cycle_operation_index(self.operation, delta)
```

#### Step 4: Run tests, commit:

```bash
uv run pytest -x -q
git commit -m "refactor: consolidate color constants and deduplicate cycle_operation (I38+I39)"
```

---

## Phase 3: Test coverage (after Phases 1+2 merged)

### Task 3.1: I42 -- Add missing tests

**Files:**
- Modify/create tests as needed

**Tests to add:**

1. **Hardlink operation** -- already added in Task 1.1

2. **Cache retry behavior** -- already added in Task 2.1

3. **Extract `_render_plain` helper** -- find the 3 duplicate test sites that parse Rich Text to plain text, extract a shared helper:

```python
def _render_plain(text: Text) -> str:
    """Strip Rich markup, return plain text."""
    return text.plain
```

(This may already be trivial with `text.plain` -- check if the duplication is more complex.)

4. **CLI entry points** -- basic smoke tests:

```python
def test_import_cmd_help(capsys):
    from typer.testing import CliRunner
    from tapes.cli import app
    runner = CliRunner()
    result = runner.invoke(app, ["import", "--help"])
    assert result.exit_code == 0
```

5. **`MetadataConfig.model_post_init` env var fallback** -- test that TMDB_TOKEN env var is picked up.

**Run all tests and commit:**

```bash
uv run pytest -x -q
git commit -m "test: add missing test coverage for hardlink, cache retry, CLI (I42)"
```

---

## Execution Summary

| Phase | Tasks | Strategy | Depends on |
|-------|-------|----------|------------|
| 0 | I33 (4 subtasks) | Sequential on main | nothing |
| 1 | I17, I20, I25, I28, I37a, I40, I41, I23+I24 | 8 parallel worktrees | Phase 0 |
| 2 | I26+I18+I21+I22, I19, I38+I39 | 3 parallel worktrees | Phase 1 |
| 3 | I42 | 1 worktree | Phase 2 |

After each phase, merge all worktree branches into main and verify tests pass before starting the next phase.
