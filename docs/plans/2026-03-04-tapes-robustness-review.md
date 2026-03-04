# Tapes Robustness Review

**Date:** 2026-03-04
**Reviewer:** Claude (design review)
**Documents reviewed:**
- `docs/plans/2026-03-04-tapes-design.md`
- `docs/plans/2026-03-04-tapes-implementation.md`
- `docs/plans/2026-03-04-tapes-review-findings.md`

---

## 1. Executive Summary

The design document is unusually thorough for a v0.1 plan. The identification pipeline, interactive prompt flows, and crash-safe move sequence are well-specified. However, five of the nine top-level commands (`move`, `check`, `fix`, `log`, `info`) are described only at the CLI synopsis level with no step-by-step specification, error handling, or state-machine definition. The implementation plan diverges from the design in critical areas: the DB schema in the implementation plan lacks the `sessions`, `operations`, `seasons`, `schema_version` tables and the `confidence`, `mtime`, `size`, `imported_at`, `director`, `genre`, `edition` columns that the design document requires, meaning crash recovery, session logging, and several query features will silently not work if the implementation plan is followed as-is. The biggest systemic risk is that the design assumes DB-and-disk consistency but provides no mechanism to enforce or restore it outside of `tapes check`, which is itself underspecified.

---

## 2. Primary Mission Restatement

Tapes exists to take a directory of unsorted movie and TV show files, identify each file using a multi-signal pipeline (filename parsing, NFO sidecars, OpenSubtitles hash, MediaInfo, TMDB), and rename/move them into a clean, Plex/Jellyfin-compatible directory structure via user-configurable templates. A SQLite database tracks what has been imported, enabling library queries and integrity checks. Everything else (NFO writing, artwork, subtitles, transcoding) is secondary and plugin-based.

---

## 3. Command Robustness Ratings

| Command   | Rating | Rationale |
|-----------|--------|-----------|
| `import`  | :yellow_circle: | Best-specified command. Interactive flows, confidence scoring, and crash recovery are documented. Gaps: no specification of what happens when destination file already exists (collision handling); implementation plan DB schema does not match design (missing `sessions`/`operations` tables, missing `confidence`/`mtime`/`size`/`imported_at`/`director`/`genre`/`edition` columns); `--no-db` mode interaction with session resume is unaddressed; `accept-all` (`a` key) behaviour when some remaining groups are below threshold is not defined. |
| `move`    | :red_circle: | Described at synopsis level only. No step-by-step specification. Unaddressed: What if destination already exists? What if a file in the DB no longer exists on disk? What if the template change makes two files map to the same destination? Is a session created? Can it be resumed? What happens on partial failure? Does it handle companion files? |
| `check`   | :red_circle: | High-level description only. Unaddressed: What is an "orphaned file" - any file in the library root not in the DB? How does it handle files placed there by other tools (Plex metadata, thumbs, etc.)? The root-mismatch matching algorithm ("matches by TMDB ID + episode info") has no fallback for files without TMDB IDs (manual imports). What if multiple DB records match a single file? What output format? Does it write changes or just report? |
| `query`   | :yellow_circle: | Service layer is implemented in the plan. Gaps: `missing:episodes` is described in the design but the implementation plan's `_parse_expression` does not handle it (it only handles `field:value`); query parser breaks on quoted strings (acknowledged as P1 #15 but deferred); range queries (`year:>2000`) are mentioned in the CLI examples but not implemented in `_parse_expression`. |
| `info`    | :yellow_circle: | Design says it runs the identification pipeline for non-imported files. Not implemented in the plan (stub only). Gap: no specification of output format; no specification of what fields are shown; no handling of "file does not exist" error. |
| `fields`  | :yellow_circle: | Two modes (list all / inspect file) are described. Not implemented in the plan (stub only). Minor gap: the conditional template syntax `{edition: - $}` is mentioned in the design but the template engine in the implementation does not support it. |
| `stats`   | :green_circle: | Simple aggregation query. Implementation matches design. Only gap: no handling of empty library (should print a helpful message rather than zeros). |
| `modify`  | :red_circle: | Synopsis-level only. Unaddressed: What does the interactive flow look like? Does it re-run the identification pipeline, or just TMDB search? Does it rename the file on disk or only update the DB? What if `<path>` is a directory with mixed content? What if the file is not in the DB? Does it create a session? What does `--write` do for a directory - regenerate all NFOs under it? |
| `log`     | :yellow_circle: | Two views are specified (summary and full). Gap: `tapes log <session-id>` has no specification of what happens if the session ID does not exist. The implementation plan does not create the `sessions` or `operations` tables, so this command cannot work as-is. |

---

## 4. Half-Baked Commands

### 4.1 `tapes move`

**What it should do, step by step:** Re-read every DB record, re-render the template with current config, compare the current path to the new path, and move files that differ. Update DB paths.

**Unspecified scenarios:**
1. **Destination collision:** Two items render to the same path after a template change (e.g., removing `{edition}` from the template causes "Dune (2021) - Director's Cut.mkv" and "Dune (2021) - Theatrical.mkv" to both become "Dune (2021).mkv"). No collision detection or resolution is specified.
2. **Missing source file:** A DB record points to a file that no longer exists on disk. Does `move` skip it, delete the DB record, or error?
3. **Partial failure:** If file 150 of 247 fails (permissions, disk full), what state is the library in? Is there a session/rollback mechanism?
4. **Companion files:** Does `move` also move `.nfo`, `.srt`, `poster.jpg` alongside the video? The import service moves companions, but `move` is not specified to do so.
5. **Library root change detection:** The design says `move` detects root changes and prompts. But what if only the template changed and not the root? Does it still prompt? What if both changed simultaneously?
6. **Dry-run output format:** What does `--dry-run` print? A table of old-path to new-path? How many? All 247, or only the ones that would change?
7. **Interaction with `--no-db` imports:** Files imported with `--no-db` are not in the DB. `move` will not know about them. This could leave orphaned files in the old structure.

### 4.2 `tapes check`

**What it should do, step by step:** For each DB record, verify the file exists at the recorded path. For each file in the library root, verify it has a DB record.

**Unspecified scenarios:**
1. **Non-video files in library root:** Plex creates `.bundle` directories, Jellyfin creates `metadata/` directories, and users may place `poster.jpg` or `folder.jpg` files. Are these "orphaned"? The design does not define what file extensions to consider.
2. **Action on findings:** `check` reports problems. Does it offer to fix them? Or is it read-only, with `fix` being the repair tool? The root-mismatch scenario says it prompts to "Update database paths? [Y/n]" -- so `check` does mutate the DB in at least one case, but this is not generalised.
3. **Files with no TMDB ID:** Manual imports (`match_source = "manual"`) may not have a TMDB ID. The root-mismatch matching algorithm uses "TMDB ID + episode info" -- these records cannot be matched.
4. **Size/mtime drift:** A file at the right path but with a different size or mtime (re-encoded in place) is not addressed. `check` only validates path existence.

### 4.3 `tapes modify`

**What it should do, step by step:** Look up the given path in the DB, show the current metadata, allow the user to search TMDB or supply an ID, update the DB record.

**Unspecified scenarios:**
1. **File not in DB:** What if the user runs `tapes fix /some/file.mkv` and the file is not in the database? Does it import it? Does it error? Does it run the pipeline?
2. **Directory argument:** The design says `<path>` can be a season directory or show directory. How does this work? Does it re-identify every file under it? Does it assume they all belong to the same show?
3. **Rename on disk:** The design says "Nothing on disk changes unless `--write` is passed to regenerate NFO files." But what about the file path itself? If the title changes from "Dun" to "Dune", should the file be renamed? This is a critical ambiguity -- `fix` updates metadata but the file stays at the wrong path unless the user also runs `tapes move`.
4. **Interactive flow:** The design says `tapes fix <path>` is "interactive -- shows current match, search" but does not specify the prompt keys, the display format, or the flow. Is it the same as the import interactive flow?
5. **`--write` scope for directories:** If `--write` is passed with a show directory, does it regenerate NFOs for every episode? Does it also regenerate `tvshow.nfo`?

### 4.4 `tapes log`

**Missing specification:**
1. **Session ID format:** Is it an integer? Auto-incrementing? How does the user discover valid session IDs? Is there a `tapes log --list` to show all sessions?
2. **Invalid session ID:** No error handling specified for `tapes log 999` when session 999 does not exist.
3. **Empty session history:** What does `tapes log` show when no imports have been done?

### 4.5 `tapes info`

**Missing specification:**
1. **Output format:** No specification of what fields are displayed or in what format (table, key-value, JSON?).
2. **Multiple files:** Can you pass multiple paths? A directory?
3. **Error handling:** What if the file does not exist? What if the identification pipeline finds no match?

---

## 5. Assumed Workflows / Hidden Dependencies

### 5.1 TMDB API key must be configured before anything works

The `create_app()` factory reads `TMDB_API_KEY` from the environment and passes it to `TMDBSource`. If the key is empty or missing, every TMDB query will fail with a 401. The review findings (#21) flag this but defer it. **Risk:** A user installs tapes, runs `tapes import`, and gets cryptic "no match found" for every file with no indication that the API key is missing.

**Recommendation:** Validate at startup. Emit a clear error: "TMDB API key not configured. Set TMDB_API_KEY or add tmdb_api_key to your config."

### 5.2 Library paths must be configured before import

If `[library] movies` or `[library] tv` is not set, `ImportService.import_file()` returns `{"status": "skipped", "reason": "no library path configured"}`. This is silent -- the user sees "skipped" with no actionable message.

**Recommendation:** Validate at the CLI layer before entering the import loop. Emit a clear error.

### 5.3 `tapes fix` must be followed by `tapes move` to rename files on disk

If a user corrects a wrong match with `tapes fix`, the DB is updated but the file remains at its old (wrong) path. The user must know to run `tapes move` afterwards to rename the file. This is a hidden two-step workflow.

**Recommendation:** Either (a) `tapes fix` should offer to rename the file, or (b) the `fix` output should explicitly say "Run `tapes move` to rename files on disk."

### 5.4 `tapes move` only works for DB-tracked files

Files imported with `--no-db` are invisible to `move`. If a user mixes `--no-db` and regular imports, `tapes move` will move some files but leave others in place, creating an inconsistent library.

**Recommendation:** Document this clearly. Consider warning when `--no-db` is used that "these files will not be tracked and cannot be reorganised with `tapes move`."

### 5.5 Session resume assumes the source files are still available

If a session is interrupted and the user deletes or moves the source files before resuming, `pending` operations will fail. The design does not address this.

**Recommendation:** On resume, verify source files exist for `pending` and `copying` operations before starting. Report missing sources and allow the user to skip them.

### 5.6 OpenSubtitles requires credentials but this is not enforced

The implementation plan lists `OSDB_USERNAME` and `OSDB_PASSWORD` as environment variables, but the OpenSubtitles hash lookup is only implemented as a hash computation (Task 6) with no API client. The design describes it as step 5 of the identification pipeline and calls it "a key design differentiator." If the API client is not implemented, the pipeline silently skips this step with no indication.

**Recommendation:** Either implement the OpenSubtitles API client in v0.1 or explicitly remove step 5 from the pipeline and document that it is planned for a future release.

### 5.7 `pymediainfo` requires MediaInfo to be installed on the system

`pymediainfo` is a Python wrapper around the `libmediainfo` shared library. If `libmediainfo` is not installed on the system, `pymediainfo` will import but `MediaInfo.parse()` will fail. The implementation handles import failure (`MEDIAINFO_AVAILABLE = False`) but not the case where the library imports but the system library is missing.

**Recommendation:** Test that `MediaInfo.parse()` actually works at startup (with a dummy call or version check) and warn if it does not.

---

## 6. State Consistency Issues

The system has three sources of truth: files on disk, the SQLite database, and the session log (also in SQLite). Here are the inconsistent states that can arise and how each command handles them.

### 6.1 File exists on disk, not in DB

**How it happens:** `--no-db` import; manual file placement; external tools; `tapes fix` on a non-imported file.
- `import`: Will re-identify and re-import (duplicate if copy mode).
- `move`: Invisible. Will not be moved.
- `check`: Reported as "orphaned" (if in library root).
- `query`/`stats`: Invisible.
- `fix`: Unspecified. Likely errors.
- **Risk:** Moderate. `check` catches this, but the user must know to run it.

### 6.2 DB record exists, file missing from disk

**How it happens:** User manually deletes file; disk failure; interrupted move where source was deleted but DB not updated.
- `import`: Will re-import if source is re-scanned. Old DB record persists (path conflict if UNIQUE on path).
- `move`: Will attempt to move a non-existent file. Unspecified error handling.
- `check`: Reports as "missing file."
- `query`: Returns the record (stale).
- `fix`: Will display stale metadata. If `--write` is used, NFO write will fail.
- `log`: Unaffected (session data is independent).
- **Risk:** High for `move`. `move` must check file existence before operating.

### 6.3 File exists at a different path than DB records

**How it happens:** User manually renames or moves a file; library root change without running `check` or `move`.
- `import`: DB lookup by `(path, mtime, size)` will miss it (different path). File will be re-imported as new, creating a duplicate DB record with a different path.
- `move`: Will try to move from the old (wrong) path. Fails silently or errors.
- `check`: Reports as both "missing file" (old path) and "orphaned file" (new path).
- **Risk:** High. Re-import creates duplicates. No guard against this.

### 6.4 Session in `in_progress` state but all operations are `done`

**How it happens:** Crash between completing the last operation and updating the session state to `completed`.
- `import` (new run): Detects interrupted session, offers to resume. Resume finds nothing to do. Should auto-complete the session.
- **Risk:** Low. Annoying but not data-losing.

### 6.5 Operation in `copying` state, partial file at destination

**How it happens:** Crash during file copy.
- Resume: Design says "re-copy from source (partial destination discarded)." But the implementation must actually delete the partial file before re-copying. This is not specified.
- **Risk:** Medium. If the partial file is not deleted, the copy may fail or produce a corrupt file.

### 6.6 Operation in `db_written` state, source not yet deleted (move mode)

**How it happens:** Crash after DB write but before source deletion.
- Resume: Design says "complete the remaining steps." This means deleting the source. But if the source has been modified since the copy (unlikely but possible), the checksum will not match. No re-verification is specified for resume.
- **Risk:** Low. Edge case, but should be documented.

### 6.7 DB schema version mismatch

**How it happens:** User downgrades tapes to an older version after a migration.
- The design specifies forward migrations only. A downgrade will encounter a `schema_version` higher than expected. No handling is specified.
- **Risk:** Low but should fail gracefully with a clear error rather than crashing on an unknown column.

---

## 7. Feature Trimming Recommendations

| Feature / Component | Verdict | Rationale |
|---------------------|---------|-----------|
| `import` command | **KEEP** | Core mission. |
| Identification pipeline (guessit + TMDB) | **KEEP** | Core to identification. |
| Interactive import UI | **KEEP** | Core to user experience. |
| Template engine + filename sanitization | **KEEP** | Core to file organisation. |
| SQLite database + items table | **KEEP** | Core to library tracking. |
| Session log (sessions + operations tables) | **KEEP** | Essential for crash recovery in move mode. |
| `move` command | **KEEP** | Core -- reorganise after template change. |
| `check` command | **KEEP** | Essential for library integrity. |
| `fix` command | **KEEP** | Essential for correcting wrong matches. |
| `query` command | **KEEP** | Core secondary mission (queryable library). |
| `stats` command | **KEEP** | Trivial to implement, high user value. |
| `fields` command | **KEEP** | Essential for template authoring. |
| `info` command | **KEEP** | Essential for debugging identification. |
| `log` command | **KEEP** | Essential for auditing imports. |
| `missing:episodes` query | **DEFER** | Requires the `seasons` table to be populated from TMDB, which adds complexity to the import path. A simpler "list episodes by show" query covers 80% of the use case. |
| NFO plugin | **DEFER** | Not core to rename/organise. Users who need NFOs are a subset. Can be added in v0.2 without design changes. The plugin architecture is already in place. |
| Artwork plugin | **DEFER** | Not core to rename/organise. Purely enrichment. |
| Subtitles plugin | **DEFER** | Not core to rename/organise. Requires OpenSubtitles API client that is not yet implemented. |
| Scrub plugin | **DEFER** | Useful (strip embedded metadata before re-tagging), but dangerous if underspecified. Must define: which fields are stripped, FFmpeg dependency handling, failure handling. Defer to v0.2. |
| Convert plugin | **DEFER** | FFmpeg wrapper for transcoding. Not core to rename/organise. Complex domain (codec compatibility, quality, hardware acceleration). Defer to v0.2 or later as a standalone plugin package. |
| OpenSubtitles hash identification (pipeline step 5) | **DEFER** | The `opensubtitlescom` PyPI library supports hash-based lookup but was last updated January 2024. The hash computation stays in the pipeline for future use. The API client call is deferred to post-v0.1. |
| MediaInfo identification (pipeline step 6) | **KEEP** | Already implemented in the plan. Provides codec/resolution/audio fields for templates. |
| Plugin system (EventBus + entry points) | **KEEP** | Already implemented. Minimal cost. Enables future extensibility. |
| Per-media-type plugin config | **DEFER** | Adds config parsing complexity for a feature that only matters when plugins are active. Base plugin config is sufficient for v0.1. |
| `--no-db` mode | **KEEP** | Low implementation cost (skip DB writes). Valuable for one-off renaming jobs. |
| Companion file handling | **KEEP** | Users expect `.srt` and `.nfo` files to move with the video. |
| xattr cache | **CUT** | The design document explicitly dropped this in favour of DB lookup. But the implementation plan (Task 9) still creates `tapes/identification/xattr_cache.py` and uses it in the pipeline. This is dead code that contradicts the design. Remove it. |

---

## 8. Assumptions Inventory

| # | Assumption | What happens if violated | Guarded? |
|---|-----------|------------------------|----------|
| 1 | User has a TMDB API key | Every identification fails with no useful error | No (deferred to implementation) |
| 2 | User has `libmediainfo` installed on the system | MediaInfo step silently skipped; codec/resolution/audio fields empty | Partially (import failure caught, but runtime failure not tested) |
| 3 | Library paths are on a local or reliably-mounted filesystem | File operations may fail mid-copy; checksums may be slow; symlinks may not work on SMB | No |
| 4 | File paths are valid UTF-8 | `Path` operations and DB storage may fail for non-UTF-8 filenames (common on legacy systems) | No |
| 5 | User has write permission to the library directories | File operations fail. No pre-check. | No |
| 6 | Source files are not modified during import | Checksum verification (move mode) would fail, but the error is not clearly reported to the user | Partially |
| 7 | One tapes process runs at a time | Concurrent imports would create session conflicts, duplicate DB records, and file collisions | No (no file locking or DB locking) |
| 8 | Filenames follow common naming conventions | guessit cannot parse non-standard filenames; pipeline falls through to interactive | Yes (interactive fallback) |
| 9 | TMDB is reachable and responsive | Identification fails for all pipeline-dependent steps. Rate limiting (40 req/10s) mentioned in review findings but not implemented. | No |
| 10 | The DB file is not corrupted | SQLite is robust but not immune. No backup or integrity check of the DB file itself. | No |
| 11 | The user's Python version is 3.11+ | `tomllib` (stdlib) is 3.11+. Will fail on older Python with an import error. | Partially (`requires-python = ">=3.11"` in pyproject.toml) |
| 12 | Template fields contain filesystem-safe characters after sanitization | The `[replace]` table handles common cases but not all edge cases (e.g., filenames that are entirely dots, reserved Windows names like `CON`, `PRN`, `NUL`) | Partially |
| 13 | Enough disk space for copy+verify in move mode | Copy succeeds, source is not deleted, but no pre-check for available space | No |
| 14 | No other tool modifies library files between tapes operations | `check` can detect drift, but `import` and `move` assume consistency | Partially |
| 15 | Each video file maps to exactly one TMDB entity | A compilation or bonus features disc would confuse the pipeline | No (no concept of "extra" or "bonus" files) |
| 16 | Season/episode numbering is consistent with TMDB | Different numbering schemes (absolute episode numbers, special episodes) will cause mismatches | No |
| 17 | `guessit` returns `episode` as an integer | guessit returns a list for multi-episode files (e.g., `[1, 2]`). The design says multi-episode is manual-only, but the pipeline does not guard against guessit returning a list. | No (acknowledged in review finding #5 but not guarded in implementation) |
| 18 | The config file is valid TOML | `tomllib` will raise an error. The error message will be a raw Python traceback with no user-friendly guidance. | No |

---

## 9. Recommended Immediate Actions

Ordered by impact and cost to fix. Do these before implementation starts.

### P0: Must fix

1. **Reconcile the implementation plan's DB schema with the design's DB schema.** The implementation plan (Task 4) creates an `items` table that is missing: `confidence`, `mtime`, `size`, `imported_at`, `director`, `genre`, `edition` columns, and entirely missing the `sessions`, `operations`, `seasons`, and `schema_version` tables. The session log, crash recovery, and several query features depend on these. Either update the implementation plan's schema to match the design, or explicitly cut the features that depend on the missing structures.

2. **Remove xattr_cache from the implementation plan.** The design document explicitly says "xattr is not used" (review finding #8) but the implementation plan (Task 9) creates and imports `xattr_cache.py`. This is a direct contradiction. Remove the file and all references to it in `pipeline.py`.

3. **Specify `tapes move` end-to-end.** At minimum: destination collision handling, missing-file handling, companion file handling, session/atomicity story, partial failure behaviour, dry-run output format. This is a data-moving command that operates on the entire library -- it cannot be underspecified.

4. **Specify `tapes fix` end-to-end.** At minimum: behaviour when the file is not in the DB, interactive flow details, whether it renames files on disk, directory argument semantics.

5. **Add TMDB API key validation at startup.** A single `if not api_key: sys.exit("Error: ...")` in the application factory. This costs minutes and prevents the most common first-run failure.

### P1: Should fix

6. **Specify `tapes check` end-to-end.** Define what constitutes an "orphaned file" (video files only? any file?), what actions are available (report only vs. interactive repair), and how manual-import records (no TMDB ID) are handled during root-mismatch matching.

7. **Add destination collision handling to `import`.** When two files render to the same destination path (e.g., two copies of the same movie), the second `shutil.copy2` will silently overwrite the first. Define the behaviour: skip, rename with suffix, prompt the user, or error.

8. **Guard against guessit returning a list for multi-episode files.** The pipeline's `parsed["episode"]` may be `[1, 2]` instead of `1`. This will crash the template engine when it tries `{episode:02d}` on a list. Add a type check: if `isinstance(episode, list)`, either take the first element or flag for manual handling.

9. **Add file locking or single-instance guard.** Two concurrent `tapes import` processes on the same library will corrupt the database and create file collisions. A simple PID lockfile at the DB path would suffice.

10. **Add disk space pre-check for move mode.** Before starting a copy-verify-delete cycle, check that the destination filesystem has enough free space. This prevents half-copied files on a full disk.

### P2: Nice to have

11. **Define `tapes info` output format.** Even a brief specification ("key: value pairs, one per line, same fields as the items table") prevents implementation-time bikeshedding.

12. **Handle Windows reserved filenames in sanitization.** The `[replace]` table handles illegal characters but not reserved names (`CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`, `LPT1`-`LPT9`). On Windows, creating a file named `CON.mkv` will fail.

13. **Add a `tapes log --list` subcommand.** Without it, the user has no way to discover valid session IDs for `tapes log <session-id>`.

14. **Add a user-friendly error for invalid TOML config.** Catch `tomllib.TOMLDecodeError` and print the line number and a hint, rather than a raw traceback.

15. **Add `--verbose` / `--quiet` global flags.** The design has no verbosity control. During large imports, users may want less output; during debugging, more.

16. **Document the `tapes fix` then `tapes move` workflow.** If the decision is to keep `fix` as metadata-only, the user must be told to run `move` afterwards. Print this in the `fix` command output.
