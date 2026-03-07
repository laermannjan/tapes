# Interactive Matching (M3.5) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire the remaining interactive matching flows so tapes can handle poorly-named files through user-driven search, manual metadata entry, and proper CLI flag propagation.

**Architecture:** Six gaps to close. Tasks 1-2 are config plumbing (flags flow from CLI to service). Tasks 3-4 add the search and manual entry flows in `interactive.py` + wire them into `ImportService._prompt_user`. Task 5 changes how no-candidate files are handled (prompt instead of silent skip). Task 6 moves companion files during import. Task 7 enforces threshold on accept-all.

**Tech Stack:** Python 3.11+, Rich (console I/O), TMDB API via `TMDBSource`, pytest + responses for mocks.

---

### Task 1: Wire `--interactive` flag from CLI to service

The `--interactive` flag is accepted by the CLI but never propagated. When set, ALL files should go through the interactive prompt regardless of confidence.

**Files:**
- Modify: `tapes/cli/commands/import_.py:31-36`
- Modify: `tapes/importer/service.py:44-63`
- Modify: `tapes/identification/pipeline.py:91-103`
- Test: `tests/test_importer/test_service.py`

**Step 1: Write the failing test**

```python
# In tests/test_importer/test_service.py

def test_interactive_flag_forces_prompt(tmp_path, repo, meta_source, cfg):
    """--interactive forces prompt even for high-confidence matches."""
    cfg.import_.interactive = True
    _make_video(tmp_path)
    candidate = _make_candidate(confidence=0.95)
    mock_result = IdentificationResult(
        candidates=[candidate], file_info={}, requires_interaction=False,
    )
    service = ImportService(repo=repo, metadata_source=meta_source, config=cfg)
    with patch.object(service._pipeline, "identify", return_value=mock_result), \
         patch("tapes.importer.service.classify_companions", return_value=[]), \
         patch("tapes.importer.service.display_prompt"), \
         patch("tapes.importer.service.read_action", return_value=PromptAction.ACCEPT):
        summary = service.import_path(tmp_path)

    assert summary["imported"] == 1
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_importer/test_service.py::test_interactive_flag_forces_prompt -v`
Expected: FAIL -- currently high-confidence files skip the prompt entirely.

**Step 3: Implement**

In `tapes/cli/commands/import_.py`, add after line 36:
```python
if interactive:
    cfg.import_.interactive = True
if no_db:
    cfg.import_.no_db = True
```

In `tapes/importer/service.py`, modify `_process_file` around line 122. After selecting a candidate from auto-accept, check if interactive mode is on:
```python
# Before auto-accepting, check if --interactive forces review
if not result.requires_interaction and self._cfg.import_.interactive:
    result = IdentificationResult(
        candidates=result.candidates,
        file_info=result.file_info,
        source=result.source,
        requires_interaction=True,
    )
```

Insert this block at the start of `_process_file`, right after `result = self._pipeline.identify(video)` and the DB-skip check (after line 113).

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_importer/test_service.py -v`
Expected: All tests PASS including the new one.

**Step 5: Commit**

```
feat: wire --interactive flag through to import service
```

---

### Task 2: Wire `--no-db` flag from CLI to service

When `--no-db` is set, skip DB cache lookup and DB writes. Files are still identified, renamed, and moved -- just no SQLite interaction.

**Files:**
- Modify: `tapes/config/schema.py:11-15`
- Modify: `tapes/cli/commands/import_.py` (already added in Task 1)
- Modify: `tapes/importer/service.py:65-97` and `247-280`
- Test: `tests/test_importer/test_service.py`

**Step 1: Write the failing test**

```python
def test_no_db_skips_db_record(tmp_path, repo, meta_source, cfg):
    """--no-db imports file without writing to DB."""
    cfg.import_.no_db = True
    video = _make_video(tmp_path)
    candidate = _make_candidate()
    mock_result = IdentificationResult(candidates=[candidate], file_info={})

    service = ImportService(repo=repo, metadata_source=meta_source, config=cfg)
    with patch.object(service._pipeline, "identify", return_value=mock_result):
        summary = service.import_path(tmp_path)

    assert summary["imported"] == 1
    # DB should have no records
    assert repo.find_by_path_stat(str(video), 0, 0) is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_importer/test_service.py::test_no_db_skips_db_record -v`

**Step 3: Implement**

Add `no_db: bool = False` to `ImportConfig` in `tapes/config/schema.py`:
```python
class ImportConfig(BaseModel):
    mode: Literal["copy", "move", "link", "hardlink"] = "copy"
    confidence_threshold: float = 0.9
    interactive: bool = False
    no_db: bool = False
    dry_run: bool = False
```

In `tapes/importer/service.py`, modify `import_path`:
- Skip session creation when no_db: `session = ImportSession.create(...) if not summary.dry_run and not self._cfg.import_.no_db else None`
- In the pipeline constructor, pass `no_db` so DB cache is skipped.

In `_process_file`, skip DB check when no_db:
```python
# Already in DB -- skip (unless --no-db)
if result.item is not None and not self._cfg.import_.no_db:
    summary.skipped += 1
    return
```

In `_process_file`, skip DB write when no_db:
```python
if not self._cfg.import_.no_db:
    self._write_db_record(video, dest, candidate, result.file_info)
```

In `IdentificationPipeline.__init__`, add `no_db` param:
```python
def __init__(self, repo, metadata_source, confidence_threshold=0.9, no_db=False):
    ...
    self._no_db = no_db
```

In `identify`, skip DB cache when no_db:
```python
if not self._no_db:
    cached = self._repo.find_by_path_stat(...)
    if cached:
        return IdentificationResult(item=cached, source="db_cache")
```

Wire in service constructor:
```python
self._pipeline = IdentificationPipeline(
    repo=repo,
    metadata_source=metadata_source,
    confidence_threshold=config.import_.confidence_threshold,
    no_db=getattr(config.import_, 'no_db', False),
)
```

**Step 4: Run all tests**

Run: `uv run pytest tests/test_importer/test_service.py tests/test_identification/ -v`

**Step 5: Commit**

```
feat: wire --no-db flag to skip DB cache and writes
```

---

### Task 3: Implement interactive search flow (`s` key)

Pressing `s` should collect media type, title, and year, query TMDB, and show results for the user to pick from.

**Files:**
- Modify: `tapes/importer/interactive.py` -- add `search_prompt()` function
- Modify: `tapes/importer/service.py:168-208` -- wire search into `_prompt_user`
- Test: `tests/test_importer/test_interactive.py`
- Test: `tests/test_importer/test_service.py`

**Step 1: Write failing tests for the search prompt UI**

```python
# In tests/test_importer/test_interactive.py

from tapes.importer.interactive import search_prompt

def test_search_prompt_collects_fields():
    """search_prompt collects media_type, title, year."""
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    with patch("builtins.input", side_effect=["movie", "The Matrix", "1999"]):
        media_type, title, year = search_prompt(con)
    assert media_type == "movie"
    assert title == "The Matrix"
    assert year == 1999


def test_search_prompt_empty_year():
    """Year is optional, returns None when empty."""
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    with patch("builtins.input", side_effect=["tv", "Breaking Bad", ""]):
        media_type, title, year = search_prompt(con)
    assert media_type == "tv"
    assert title == "Breaking Bad"
    assert year is None


def test_search_prompt_defaults_media_type():
    """Empty media type defaults to 'movie'."""
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    with patch("builtins.input", side_effect=["", "Dune", "2021"]):
        media_type, title, year = search_prompt(con)
    assert media_type == "movie"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_importer/test_interactive.py::test_search_prompt_collects_fields -v`

**Step 3: Implement `search_prompt` in `tapes/importer/interactive.py`**

Add at the end of the file:
```python
def search_prompt(
    console: Console,
    *,
    default_media_type: str = "movie",
    default_title: str = "",
    default_year: int | None = None,
) -> tuple[str, str, int | None]:
    """Collect structured search fields from the user.

    Returns (media_type, title, year).
    """
    year_default = str(default_year) if default_year else ""
    mt_prompt = f"Media type [movie/tv] ({default_media_type}): "
    title_prompt = f"Title ({default_title}): " if default_title else "Title: "
    year_prompt = f"Year (optional) ({year_default}): " if year_default else "Year (optional): "

    mt = input(mt_prompt).strip().lower() or default_media_type
    if mt not in ("movie", "tv"):
        mt = default_media_type
    title = input(title_prompt).strip() or default_title
    raw_year = input(year_prompt).strip() or year_default
    year = int(raw_year) if raw_year else None

    return mt, title, year
```

**Step 4: Write failing test for search flow in service**

```python
# In tests/test_importer/test_service.py

def test_interactive_search_flow(tmp_path, repo, meta_source, cfg):
    """Pressing 's' triggers search, returns TMDB results, user accepts."""
    _make_video(tmp_path)
    candidate = _make_candidate(confidence=0.50)
    search_candidate = _make_candidate(title="The Matrix Reloaded", year=2003, confidence=0.92)
    mock_result = IdentificationResult(
        candidates=[candidate], file_info={}, requires_interaction=True,
    )
    meta_source.search.return_value = [search_candidate]

    call_count = [0]
    def fake_read_action(prompt, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return PromptAction.SEARCH
        return PromptAction.ACCEPT

    service = ImportService(repo=repo, metadata_source=meta_source, config=cfg)
    with patch.object(service._pipeline, "identify", return_value=mock_result), \
         patch("tapes.importer.service.classify_companions", return_value=[]), \
         patch("tapes.importer.service.display_prompt"), \
         patch("tapes.importer.service.read_action", side_effect=fake_read_action), \
         patch("tapes.importer.service.search_prompt", return_value=("movie", "Matrix", 1999)):
        summary = service.import_path(tmp_path)

    assert summary["imported"] == 1
    meta_source.search.assert_called_once_with("Matrix", 1999, "movie")
```

**Step 5: Implement search flow in `_prompt_user`**

In `tapes/importer/service.py`, replace the catch-all return at line 208 and add search handling:

```python
from tapes.importer.interactive import (
    InteractivePrompt,
    PromptAction,
    display_prompt,
    edit_companions,
    read_action,
    search_prompt,
)

# In _prompt_user, replace the end of the while loop:
if action == PromptAction.SEARCH:
    # Collect search fields from user
    default_title = result.file_info.get("title") or result.file_info.get("show") or ""
    default_year = result.file_info.get("year")
    media_type, title, year = search_prompt(
        self._console,
        default_title=default_title,
        default_year=default_year,
    )
    # Query TMDB
    search_results = self._meta.search(title, year, media_type)
    if search_results:
        prompt = InteractivePrompt(
            candidates=search_results, is_search_result=True,
        )
    else:
        prompt = InteractivePrompt(
            candidates=[], after_failed_search=True,
        )
    continue  # re-display prompt with new results

if action == PromptAction.MANUAL:
    # placeholder -- implemented in Task 4
    return None
```

**Step 6: Run all tests**

Run: `uv run pytest tests/test_importer/ -v`

**Step 7: Commit**

```
feat: implement interactive search flow (s key)
```

---

### Task 4: Implement manual metadata entry (`m` key)

Pressing `m` should collect fields directly and create a synthetic `SearchResult` with `[manual]` source.

**Files:**
- Modify: `tapes/importer/interactive.py` -- add `manual_prompt()` function
- Modify: `tapes/importer/service.py` -- wire manual into `_prompt_user`
- Test: `tests/test_importer/test_interactive.py`
- Test: `tests/test_importer/test_service.py`

**Step 1: Write failing tests**

```python
# In tests/test_importer/test_interactive.py

from tapes.importer.interactive import manual_prompt

def test_manual_prompt_movie():
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    with patch("builtins.input", side_effect=["movie", "Inception", "2010", "n"]):
        result = manual_prompt(con)
    assert result.title == "Inception"
    assert result.year == 2010
    assert result.media_type == "movie"
    assert result.tmdb_id == 0
    assert result.confidence == 1.0


def test_manual_prompt_tv():
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    with patch("builtins.input", side_effect=["tv", "Breaking Bad", "2008", "y", "Breaking Bad", "1", "1", "Pilot"]):
        result = manual_prompt(con)
    assert result.media_type == "tv"
    assert result.show == "Breaking Bad"
    assert result.season == 1
    assert result.episode == 1
    assert result.episode_title == "Pilot"
```

**Step 2: Run to verify failure**

Run: `uv run pytest tests/test_importer/test_interactive.py::test_manual_prompt_movie -v`

**Step 3: Implement `manual_prompt`**

```python
def manual_prompt(
    console: Console,
    *,
    default_media_type: str = "movie",
    default_title: str = "",
    default_year: int | None = None,
) -> SearchResult:
    """Collect metadata fields directly from the user.

    Returns a synthetic SearchResult with tmdb_id=0 and confidence=1.0.
    """
    from tapes.metadata.base import SearchResult

    year_default = str(default_year) if default_year else ""
    mt = input(f"Media type [movie/tv] ({default_media_type}): ").strip().lower() or default_media_type
    if mt not in ("movie", "tv"):
        mt = default_media_type
    title = input(f"Title ({default_title}): " if default_title else "Title: ").strip() or default_title
    raw_year = input(f"Year (optional) ({year_default}): " if year_default else "Year (optional): ").strip() or year_default
    year = int(raw_year) if raw_year else None

    show = None
    season = None
    episode = None
    episode_title = None

    if mt == "tv":
        more = input("More fields? [y/N]: ").strip().lower()
        if more == "y":
            show = input("Show name: ").strip() or title
            season = _int_or_none(input("Season: ").strip())
            episode = _int_or_none(input("Episode: ").strip())
            episode_title = input("Episode title (optional): ").strip() or None
    else:
        more = input("More fields? [y/N]: ").strip().lower()

    return SearchResult(
        tmdb_id=0,
        title=title,
        year=year,
        media_type=mt,
        confidence=1.0,
        show=show,
        season=season,
        episode=episode,
        episode_title=episode_title,
    )


def _int_or_none(s: str) -> int | None:
    try:
        return int(s)
    except (ValueError, TypeError):
        return None
```

**Step 4: Wire into `_prompt_user` in service.py**

Replace the manual placeholder:
```python
if action == PromptAction.MANUAL:
    default_title = result.file_info.get("title") or result.file_info.get("show") or ""
    default_year = result.file_info.get("year")
    manual_result = manual_prompt(
        self._console,
        default_title=default_title,
        default_year=default_year,
    )
    return manual_result
```

Add import: `from tapes.importer.interactive import ... manual_prompt`

**Step 5: Write service test**

```python
def test_interactive_manual_entry(tmp_path, repo, meta_source, cfg):
    """Pressing 'm' collects manual metadata and imports."""
    _make_video(tmp_path)
    mock_result = IdentificationResult(
        candidates=[], file_info={"title": "unknown"}, requires_interaction=True,
    )
    manual_sr = SearchResult(
        tmdb_id=0, title="My Movie", year=2020, media_type="movie", confidence=1.0,
    )

    call_count = [0]
    def fake_read_action(prompt, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return PromptAction.MANUAL
        return PromptAction.ACCEPT  # should not be reached

    service = ImportService(repo=repo, metadata_source=meta_source, config=cfg)
    with patch.object(service._pipeline, "identify", return_value=mock_result), \
         patch("tapes.importer.service.classify_companions", return_value=[]), \
         patch("tapes.importer.service.display_prompt"), \
         patch("tapes.importer.service.read_action", side_effect=fake_read_action), \
         patch("tapes.importer.service.manual_prompt", return_value=manual_sr):
        summary = service.import_path(tmp_path)

    assert summary["imported"] == 1
```

**Step 6: Run all tests**

Run: `uv run pytest tests/test_importer/ -v`

**Step 7: Commit**

```
feat: implement manual metadata entry (m key)
```

---

### Task 5: Prompt user when no candidates found

Currently, files with `requires_interaction=True` and no candidates are silently skipped. Instead, show the "no match found" prompt so the user can search or enter metadata manually.

**Files:**
- Modify: `tapes/importer/service.py:122-126`
- Test: `tests/test_importer/test_service.py`

**Step 1: Write failing test**

```python
def test_no_candidates_prompts_user(tmp_path, repo, meta_source, cfg):
    """Files with requires_interaction and no candidates show prompt."""
    _make_video(tmp_path)
    mock_result = IdentificationResult(
        candidates=[], file_info={"title": "mystery"}, requires_interaction=True,
    )

    service = ImportService(repo=repo, metadata_source=meta_source, config=cfg)
    with patch.object(service._pipeline, "identify", return_value=mock_result), \
         patch("tapes.importer.service.classify_companions", return_value=[]), \
         patch("tapes.importer.service.display_prompt") as mock_display, \
         patch("tapes.importer.service.read_action", return_value=PromptAction.SKIP):
        summary = service.import_path(tmp_path)

    # The prompt should have been displayed (not silently skipped)
    assert mock_display.call_count == 1
    assert summary["skipped"] == 1
```

**Step 2: Run to verify failure**

Run: `uv run pytest tests/test_importer/test_service.py::test_no_candidates_prompts_user -v`
Expected: FAIL -- currently the code returns early at line 124 without prompting.

**Step 3: Implement**

In `tapes/importer/service.py`, modify the `requires_interaction` block (lines 122-126). Remove the early return for empty candidates:

```python
# Needs interaction
if result.requires_interaction:
    # Accept-all mode: auto-accept top candidate (if above threshold)
    if self._accept_all and result.candidates:
        candidate = result.candidates[0]
    else:
        candidate = self._prompt_user(video, result, index=index, total=total)
        if candidate is None:
            summary.skipped += 1
            return
```

This removes the check `if not result.candidates: skip` and lets `_prompt_user` handle the no-candidates case (the InteractivePrompt already knows how to show "no match found" and default to search).

**Step 4: Run tests**

Run: `uv run pytest tests/test_importer/test_service.py -v`

**Step 5: Commit**

```
feat: prompt user when no TMDB candidates found
```

---

### Task 6: Move companion files during import

Currently companions are classified and displayed but not moved alongside the video during import.

**Files:**
- Modify: `tapes/importer/service.py:157-166`
- Test: `tests/test_importer/test_service.py`

**Step 1: Write failing test**

```python
def test_companion_files_moved_during_import(tmp_path, repo, meta_source, cfg):
    """Companion files are moved alongside the video during import."""
    video = _make_video(tmp_path)
    sub = tmp_path / "movie.en.srt"
    sub.write_text("subtitle content")
    candidate = _make_candidate()
    mock_result = IdentificationResult(candidates=[candidate], file_info={})

    service = ImportService(repo=repo, metadata_source=meta_source, config=cfg)
    with patch.object(service._pipeline, "identify", return_value=mock_result):
        summary = service.import_path(tmp_path)

    assert summary["imported"] == 1
    dest_dir = Path(cfg.library.movies)
    # Subtitle should be renamed and moved alongside video
    srt_files = list(dest_dir.rglob("*.srt"))
    assert len(srt_files) == 1
    assert "The Matrix (1999)" in srt_files[0].name
```

**Step 2: Run to verify failure**

Run: `uv run pytest tests/test_importer/test_service.py::test_companion_files_moved_during_import -v`

**Step 3: Implement**

Add a `_move_companions` method to ImportService and call it after the video file operation:

```python
from tapes.companions.classifier import classify_companions, rename_companion

# In _process_file, after self._execute_file_op(video, dest) succeeds:
def _process_file(self, ...):
    ...
    # Execute file operation
    op_id = session.add_operation(str(video), self._cfg.import_.mode) if session else None
    try:
        self._execute_file_op(video, dest)
        self._move_companions(video, dest)
        if not self._cfg.import_.no_db:
            self._write_db_record(video, dest, candidate, result.file_info)
        if session:
            session.update_operation(op_id, state="done", dest_path=str(dest))
        summary.imported += 1
    except Exception as e:
        if session:
            session.update_operation(op_id, state="failed", error=str(e))
        raise

def _move_companions(self, src_video: Path, dest_video: Path) -> None:
    """Move companion files alongside the imported video."""
    companions = classify_companions(src_video)
    dest_stem = dest_video.stem
    for comp in companions:
        if not comp.move_by_default:
            continue
        new_name = rename_companion(comp.path.name, dest_stem, comp.category)
        new_path = dest_video.parent / comp.relative_to_video.parent / new_name
        try:
            new_path.parent.mkdir(parents=True, exist_ok=True)
            if self._cfg.import_.mode == "copy":
                copy_verify(comp.path, new_path)
            else:
                move_file(comp.path, new_path, verify=True)
        except Exception as e:
            logger.warning("Failed to move companion %s: %s", comp.path, e)
```

Note: in the interactive flow, the user may have edited the companion selection. Thread the selected companions through `_prompt_user` return value. For auto-accepted files, use `classify_companions` defaults.

**Step 4: Run all tests**

Run: `uv run pytest tests/test_importer/ -v`

**Step 5: Commit**

```
feat: move companion files alongside video during import
```

---

### Task 7: Enforce confidence threshold on accept-all

Currently accept-all (`a` key) auto-accepts everything unconditionally. Per design, it should only auto-accept files whose top candidate is above the confidence threshold.

**Files:**
- Modify: `tapes/importer/service.py:128-131`
- Test: `tests/test_importer/test_service.py`

**Step 1: Write failing test**

```python
def test_accept_all_respects_threshold(tmp_path, repo, meta_source, cfg):
    """Accept-all only auto-accepts candidates above confidence threshold."""
    cfg.import_.confidence_threshold = 0.8
    _make_video(tmp_path, name="good.mkv")
    _make_video(tmp_path, name="bad.mkv")

    good_candidate = _make_candidate(confidence=0.85)
    bad_candidate = _make_candidate(title="Unknown", confidence=0.50)
    results = [
        IdentificationResult(candidates=[good_candidate], file_info={}, requires_interaction=True),
        IdentificationResult(candidates=[bad_candidate], file_info={}, requires_interaction=True),
    ]

    call_count = [0]
    def fake_identify(path):
        idx = call_count[0]
        call_count[0] += 1
        return results[idx]

    prompt_count = [0]
    def fake_read_action(prompt, **kwargs):
        prompt_count[0] += 1
        if prompt_count[0] == 1:
            return PromptAction.ACCEPT_ALL
        return PromptAction.SKIP  # second file should be prompted

    service = ImportService(repo=repo, metadata_source=meta_source, config=cfg)
    with patch.object(service._pipeline, "identify", side_effect=fake_identify), \
         patch("tapes.importer.service.classify_companions", return_value=[]), \
         patch("tapes.importer.service.display_prompt"), \
         patch("tapes.importer.service.read_action", side_effect=fake_read_action):
        summary = service.import_path(tmp_path)

    assert summary["imported"] == 1
    assert summary["skipped"] == 1
    # Second file should have been prompted (not auto-accepted)
    assert prompt_count[0] == 2
```

**Step 2: Run to verify failure**

Run: `uv run pytest tests/test_importer/test_service.py::test_accept_all_respects_threshold -v`

**Step 3: Implement**

In `_process_file`, modify the accept-all check (around line 129):

```python
# Accept-all mode: auto-accept top candidate only if above threshold
if self._accept_all and result.candidates:
    if result.candidates[0].confidence >= self._cfg.import_.confidence_threshold:
        candidate = result.candidates[0]
    else:
        candidate = self._prompt_user(video, result, index=index, total=total)
        if candidate is None:
            summary.skipped += 1
            return
else:
    candidate = self._prompt_user(video, result, index=index, total=total)
    if candidate is None:
        summary.skipped += 1
        return
```

**Step 4: Run all tests**

Run: `uv run pytest tests/test_importer/ -v`

**Step 5: Commit**

```
feat: accept-all respects confidence threshold
```

---

### Final: Run full test suite

Run: `uv run pytest -v`
Expected: All tests pass (existing + new).

Update CLAUDE.md milestones and test count.
