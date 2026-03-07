# Issue 002: Fix match_source field in DB records

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this fix.

**Bug:** `_write_db_record` stores the wrong value in the `match_source` DB
field. It reads `file_info.get("source", "tmdb")`, but `file_info` comes from
guessit which populates `source` with the media source ("Blu-ray", "WEB-DL",
"HDTV"). The actual identification source (how the file was matched --
"filename", "nfo", "tmdb", etc.) lives in `result.source` but is never passed
to `_write_db_record`.

**Fix:** Stash `result.source` into `file_info` under a namespaced key early in
`_process_file`, then read it in `_write_db_record`.

**Scope:** This ticket ONLY touches `tapes/importer/service.py` lines 112-113
and 322-325, plus test additions. Do NOT touch `_move_companions`,
`_prompt_user`, `_execute_file_op`, `filename.py`, or any other code.

**Parallel note:** Issue 001 renames guessit's `source` -> `media_source` in
`filename.py`. This fix is complementary: even after 001, we still need to
store the correct identification source. These two fixes work together but
neither depends on the other.

---

## Context

### Where identification source comes from

The `IdentificationPipeline.identify()` method returns an
`IdentificationResult` with a `source` field:

```python
@dataclass
class IdentificationResult:
    item: ItemRecord | None = None
    candidates: list[SearchResult] = field(default_factory=list)
    file_info: dict = field(default_factory=dict)
    source: str | None = None           # <-- "db_cache", "nfo", "filename", or None
    requires_interaction: bool = False
    multi_episode: bool = False
```

Values of `result.source`:
- `"db_cache"` -- matched from SQLite cache (these are skipped, never reach `_write_db_record`)
- `"nfo"` -- matched via NFO sidecar file containing TMDB ID
- `"filename"` -- auto-matched via guessit + TMDB search (high confidence)
- `None` -- requires interaction (low confidence TMDB results, or no results)

### Current buggy code (`tapes/importer/service.py:299-332`)

```python
def _write_db_record(self, src, dst, candidate, file_info):
    ...
    match_source=file_info.get("source", "tmdb"),   # line 325 -- BUG: gets "Blu-ray" etc.
```

### Where the fix goes

In `_process_file` at line 112-113:

```python
result = self._pipeline.identify(video)    # line 112
# FIX: line 113 -- stash identification source
```

This is well above the companion/file-op code (lines 161-174), so there is no
edit conflict with Issue 003.

---

## Files to modify

- **Modify:** `tapes/importer/service.py:112-113` (add one line after `identify`)
- **Modify:** `tapes/importer/service.py:325` (change `match_source=` line in `_write_db_record`)
- **Test:** `tests/test_importer/test_service.py` (add test at end of file)

---

## Step 1: Write failing test

Add to the END of `tests/test_importer/test_service.py`:

```python
def test_db_record_stores_identification_source(tmp_path, repo, meta_source, cfg):
    """match_source in DB should be the identification method, not guessit's media source."""
    video = _make_video(tmp_path)
    candidate = _make_candidate()
    # file_info with guessit's "source" field (media source, e.g. "Blu-ray")
    mock_result = IdentificationResult(
        candidates=[candidate],
        file_info={"source": "Blu-ray", "title": "The Matrix"},
        source="filename",  # <-- this is the identification source
    )

    service = ImportService(repo=repo, metadata_source=meta_source, config=cfg)
    with patch.object(service._pipeline, "identify", return_value=mock_result):
        summary = service.import_path(tmp_path)

    assert summary["imported"] == 1
    # Verify the DB record has identification source, not media source
    row = repo._conn.execute("SELECT match_source FROM items").fetchone()
    assert row[0] == "filename"  # NOT "Blu-ray"
```

## Step 2: Run test to verify it fails

```bash
uv run pytest tests/test_importer/test_service.py::test_db_record_stores_identification_source -v
```

Expected: FAIL -- `row[0]` is `"Blu-ray"` (the guessit media source) instead of
`"filename"`.

## Step 3: Implement

Two changes in `tapes/importer/service.py`:

**Change 1:** In `_process_file`, add one line after line 112:

```python
def _process_file(self, video, summary, session, *, index=0, total=0):
    result = self._pipeline.identify(video)

    # Stash identification source for DB record. Must be done before any
    # early return that skips the DB write. The key is namespaced to avoid
    # collision with guessit's "source" (media source like "Blu-ray").
    result.file_info["_identification_source"] = result.source

    # Already in DB -- skip
    if result.item is not None:
        ...
```

**Change 2:** In `_write_db_record` at line 325, change:

```python
# BEFORE (buggy):
match_source=file_info.get("source", "tmdb"),

# AFTER (fixed):
match_source=file_info.get("_identification_source") or "tmdb",
```

That's it. Two lines changed.

## Step 4: Run tests

```bash
uv run pytest tests/test_importer/test_service.py -v
```

Expected: ALL PASS including the new test.

## Step 5: Run full test suite

```bash
uv run pytest -x -q
```

Expected: All 312+ tests pass.

## Step 6: Commit

```
fix: store identification source in match_source DB field

match_source was getting guessit's media source ("Blu-ray", "WEB-DL")
instead of the identification method ("filename", "nfo", "tmdb").
Stash result.source into file_info under a namespaced key so
_write_db_record can read the correct value.
```

---

## Why this approach avoids conflicts

The two edit locations are:
- Line 113 (right after `self._pipeline.identify(video)`)
- Line 325 (inside `_write_db_record` method body)

Issue 003 edits lines 165 (`_move_companions` call), 176-242 (`_prompt_user`),
and 269-285 (`_move_companions` body). There is no line overlap between the two
issues. Git will auto-merge cleanly.

Both issues add tests at the end of `test_service.py`. If merged from separate
branches, git may show a trivial conflict at EOF -- resolve by keeping both test
functions.
