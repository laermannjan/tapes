# Issue 003: Fix companion file handling (modes + editing)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this fix.

**Two bugs in companion file handling during import:**

1. **Wrong operation mode for link/hardlink:** `_move_companions` only
   distinguishes "copy" vs everything-else. For "link" and "hardlink" modes, it
   falls through to `move_file()` instead of creating symlinks/hardlinks. This
   is inconsistent with how the video itself is handled in `_execute_file_op`.

2. **Companion editing not threaded to move step:** When the user presses `e`
   during interactive import to edit which companion files to include,
   `_prompt_user` stores the edited list in a local variable. But
   `_move_companions` re-classifies companions from scratch using
   `classify_companions(src_video)`, discarding the user's edits.

**Fix:** Update `_move_companions` to support all four modes and accept an
optional pre-selected companion list. Update `_prompt_user` to return the
companion selection alongside the candidate. Update `_process_file` to pass
companions through.

**Scope:** This ticket ONLY modifies methods `_move_companions`, `_prompt_user`,
and the `_process_file` call to `_move_companions` (line 165). Do NOT touch
`_write_db_record`, `_execute_file_op`, `_render_destination`, `filename.py`,
or any other code.

---

## Context

### Current `_move_companions` (`tapes/importer/service.py:269-285`)

```python
def _move_companions(self, src_video: Path, dest_video: Path) -> None:
    companions = classify_companions(src_video)        # re-classifies from scratch
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
                move_file(comp.path, new_path, verify=True)  # BUG: wrong for link/hardlink
        except Exception as e:
            logger.warning("Failed to move companion %s: %s", comp.path, e)
```

### Current `_execute_file_op` (for reference -- do NOT modify)

```python
def _execute_file_op(self, src: Path, dst: Path) -> None:
    mode = self._cfg.import_.mode
    dst.parent.mkdir(parents=True, exist_ok=True)
    if mode == "copy":
        copy_verify(src, dst)
    elif mode == "move":
        move_file(src, dst, verify=True)
    elif mode == "link":
        dst.symlink_to(src)
    elif mode == "hardlink":
        dst.hardlink_to(src)
```

### Current `_prompt_user` companion flow (`tapes/importer/service.py:176-242`)

```python
def _prompt_user(self, video, result, *, index, total):
    companions = classify_companions(video)        # classified here
    prompt = InteractivePrompt(candidates=result.candidates)
    while True:
        display_prompt(self._console, prompt, ..., companions=companions or None)
        action = read_action(prompt, has_companions=bool(companions))
        if action == "edit":
            companions = edit_companions(self._console, companions)  # edited here
            continue
        ...
        if action == PromptAction.ACCEPT:
            return prompt.candidates[0]            # companions discarded!
```

### Current `_process_file` companion call (line 165)

```python
self._execute_file_op(video, dest)
self._move_companions(video, dest)                 # re-classifies, ignores edits
```

---

## Files to modify

- **Modify:** `tapes/importer/service.py:165` (pass companions to `_move_companions`)
- **Modify:** `tapes/importer/service.py:176-242` (`_prompt_user` -- return companions)
- **Modify:** `tapes/importer/service.py:269-285` (`_move_companions` -- accept list, fix modes)
- **Test:** `tests/test_importer/test_service.py` (add tests at end of file)

Do NOT modify lines 112-113, 148-160, 287-332, or any file other than
`service.py` and `test_service.py`.

---

## Part A: Fix companion operation modes

### Step 1: Write failing test for link mode

Add to the END of `tests/test_importer/test_service.py`:

```python
def test_companion_files_linked_in_link_mode(tmp_path, repo, meta_source, cfg):
    """In link mode, companion files should be symlinked, not moved."""
    cfg.import_.mode = "link"
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
    srt_files = list(dest_dir.rglob("*.srt"))
    assert len(srt_files) == 1
    assert srt_files[0].is_symlink()
    # Source companion should still exist (not moved)
    assert sub.exists()


def test_companion_files_hardlinked_in_hardlink_mode(tmp_path, repo, meta_source, cfg):
    """In hardlink mode, companion files should be hardlinked, not moved."""
    cfg.import_.mode = "hardlink"
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
    srt_files = list(dest_dir.rglob("*.srt"))
    assert len(srt_files) == 1
    # Source companion should still exist (hardlinked, not moved)
    assert sub.exists()
    # Same inode
    assert srt_files[0].stat().st_ino == sub.stat().st_ino
```

### Step 2: Run tests to verify they fail

```bash
uv run pytest tests/test_importer/test_service.py::test_companion_files_linked_in_link_mode -v
uv run pytest tests/test_importer/test_service.py::test_companion_files_hardlinked_in_hardlink_mode -v
```

Expected: FAIL -- companions are moved instead of linked.

### Step 3: Implement mode fix in `_move_companions`

Replace the mode dispatch inside `_move_companions` (the try block body,
lines 279-283):

```python
def _move_companions(self, src_video: Path, dest_video: Path,
                     companions: list | None = None) -> None:
    """Move companion files alongside the imported video."""
    if companions is None:
        companions = classify_companions(src_video)
    dest_stem = dest_video.stem
    for comp in companions:
        if not comp.move_by_default:
            continue
        new_name = rename_companion(comp.path.name, dest_stem, comp.category)
        new_path = dest_video.parent / comp.relative_to_video.parent / new_name
        try:
            new_path.parent.mkdir(parents=True, exist_ok=True)
            mode = self._cfg.import_.mode
            if mode == "copy":
                copy_verify(comp.path, new_path)
            elif mode == "move":
                move_file(comp.path, new_path, verify=True)
            elif mode == "link":
                new_path.symlink_to(comp.path)
            elif mode == "hardlink":
                new_path.hardlink_to(comp.path)
        except Exception as e:
            logger.warning("Failed to process companion %s: %s", comp.path, e)
```

Note the signature now accepts an optional `companions` parameter. When `None`,
it falls back to `classify_companions` (preserving current auto-mode behavior).

### Step 4: Run mode tests

```bash
uv run pytest tests/test_importer/test_service.py::test_companion_files_linked_in_link_mode tests/test_importer/test_service.py::test_companion_files_hardlinked_in_hardlink_mode -v
```

Expected: PASS.

### Step 5: Run full service tests

```bash
uv run pytest tests/test_importer/test_service.py -v
```

Expected: ALL PASS (existing companion copy test still works).

---

## Part B: Thread companion editing through import

### Step 6: Write failing test for companion editing

Add to `tests/test_importer/test_service.py`:

```python
def test_edited_companions_passed_to_move(tmp_path, repo, meta_source, cfg):
    """User-edited companion selection should be used during move, not re-classified."""
    from tapes.companions.classifier import CompanionFile, Category

    video = _make_video(tmp_path)
    # Create a subtitle and a sample file
    sub = tmp_path / "movie.en.srt"
    sub.write_text("subtitle content")
    sample = tmp_path / "sample.mkv"
    sample.write_bytes(b"\x00" * 512)

    candidate = _make_candidate(confidence=0.50)
    mock_result = IdentificationResult(
        candidates=[candidate], file_info={}, requires_interaction=True,
    )

    # Simulate: user edits companions to EXCLUDE the subtitle (move_by_default=False)
    edited_companions = [
        CompanionFile(sub, Category.SUBTITLE, False, sub.relative_to(tmp_path)),
        # sample already has move_by_default=False from classifier
    ]

    service = ImportService(repo=repo, metadata_source=meta_source, config=cfg)
    with patch.object(service._pipeline, "identify", return_value=mock_result), \
         patch("tapes.importer.service.classify_companions", return_value=[
             CompanionFile(sub, Category.SUBTITLE, True, sub.relative_to(tmp_path)),
         ]), \
         patch("tapes.importer.service.display_prompt"), \
         patch("tapes.importer.service.read_action", side_effect=["edit", PromptAction.ACCEPT]), \
         patch("tapes.importer.service.edit_companions", return_value=edited_companions):
        summary = service.import_path(tmp_path)

    assert summary["imported"] == 1
    dest_dir = Path(cfg.library.movies)
    # Subtitle should NOT have been moved (user deselected it)
    srt_files = list(dest_dir.rglob("*.srt"))
    assert len(srt_files) == 0
```

### Step 7: Run test to verify it fails

```bash
uv run pytest tests/test_importer/test_service.py::test_edited_companions_passed_to_move -v
```

Expected: FAIL -- `_move_companions` re-classifies and moves the subtitle
regardless of the user's edit.

### Step 8: Implement companion threading

**Change 1: `_prompt_user` returns `(candidate, companions)` tuple**

Modify `_prompt_user` (lines 176-242) to track and return companion selections:

```python
def _prompt_user(self, video, result, *, index, total):
    """Show interactive prompt and return (candidate, companions) or (None, None)."""
    companions = classify_companions(video)
    prompt = InteractivePrompt(candidates=result.candidates)

    while True:
        display_prompt(
            self._console,
            prompt,
            index=index,
            total=total,
            filename=video.name,
            source=result.source,
            companions=companions or None,
        )
        action = read_action(prompt, has_companions=bool(companions))

        if action == "edit":
            companions = edit_companions(self._console, companions)
            continue

        if isinstance(action, tuple):
            _, idx = action
            return prompt.candidates[idx], companions

        if action == PromptAction.ACCEPT:
            return prompt.candidates[0], companions

        if action == PromptAction.ACCEPT_ALL:
            self._accept_all = True
            return prompt.candidates[0], companions

        if action == PromptAction.SKIP:
            return None, None

        if action == PromptAction.QUIT:
            raise _QuitImport()

        if action == PromptAction.MANUAL:
            default_title = result.file_info.get("title") or result.file_info.get("show") or ""
            default_year = result.file_info.get("year")
            default_media_type = "tv" if "season" in result.file_info else "movie"
            manual_result = manual_prompt(
                self._console,
                default_media_type=default_media_type,
                default_title=default_title,
                default_year=default_year,
            )
            return manual_result, companions

        if action == PromptAction.SEARCH:
            default_title = result.file_info.get("title") or result.file_info.get("show") or ""
            default_year = result.file_info.get("year")
            default_media_type = "tv" if "season" in result.file_info else "movie"

            mt, title, year = search_prompt(
                self._console,
                default_media_type=default_media_type,
                default_title=default_title,
                default_year=default_year,
            )
            search_results = self._meta.search(title, year, mt)
            if search_results:
                prompt = InteractivePrompt(candidates=search_results, is_search_result=True)
            else:
                prompt = InteractivePrompt(candidates=[], after_failed_search=True)
            continue
```

**Change 2: `_process_file` unpacks the tuple and passes companions**

In `_process_file`, update the `requires_interaction` block (lines 129-139)
and the `_move_companions` call (line 165):

```python
# Needs interaction
companions = None  # will be set by _prompt_user if interactive
if result.requires_interaction:
    # Accept-all mode: auto-accept top candidate if above threshold
    if (self._accept_all and result.candidates
            and result.candidates[0].confidence >= self._cfg.import_.confidence_threshold):
        candidate = result.candidates[0]
    else:
        candidate, companions = self._prompt_user(video, result, index=index, total=total)
        if candidate is None:
            summary.skipped += 1
            return
else:
    # Auto-accepted -- pick best candidate
    if not result.candidates:
        summary.unmatched.append(str(video))
        summary.skipped += 1
        return
    candidate = result.candidates[0]
```

And change the `_move_companions` call:

```python
try:
    self._execute_file_op(video, dest)
    self._move_companions(video, dest, companions=companions)
    ...
```

### Step 9: Run tests

```bash
uv run pytest tests/test_importer/test_service.py -v
```

Expected: ALL PASS including the new test.

### Step 10: Run full test suite

```bash
uv run pytest -x -q
```

Expected: All tests pass.

### Step 11: Commit

```
fix: companion file handling -- correct modes and thread user edits

- _move_companions now handles all four modes (copy/move/link/hardlink)
  consistently with _execute_file_op
- _prompt_user returns (candidate, companions) tuple so user's companion
  edits via the 'e' key are preserved through to the move step
- _move_companions accepts optional companions list; falls back to
  classify_companions when None (auto-accept path)
```

---

## Why this approach avoids conflicts

Edits are confined to:
- `_move_companions` method body and signature (lines 269-285)
- `_prompt_user` method (lines 176-242)
- `_process_file` lines 129-139 (companion variable) and line 165 (`_move_companions` call)

Issue 001 only touches `filename.py`.
Issue 002 only touches line 113 and `_write_db_record` body (line 325).
No line overlap with either.

Both Issues 002 and 003 add tests at the end of `test_service.py`. If merged
from separate branches, git may show a trivial conflict at EOF -- resolve by
keeping both test blocks.
