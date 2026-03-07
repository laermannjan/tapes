# Tapes Design Review Findings

**Date:** 2026-03-04
**Status:** All items triaged — see resolution notes below.

Legend: ✓ **Resolved in design** · → **Deferred to implementation**

---

## P0 — Must Fix Before Implementation

### 1. Crash-safe file moves ✓
If tapes moves a file but crashes before writing the DB record, the file is
orphaned at the destination with no record of it. The source is gone (move mode)
and tapes has no way to recover.

**Resolution:** Design updated. Move mode uses copy → SHA-256 checksum verify →
write DB record → delete source → update DB record. Granular per-file state
machine (`pending → copying → copied → db_written → source_deleted → done`)
stored in the `operations` table enables interrupted-session resume. Source file
is intact through step 3.

---

### 2. Confidence scoring is undefined ✓
The design specified `confidence_threshold = 0.9` but nothing computed a score.

**Resolution:** Concrete scoring table added to the Identification Pipeline
section (osdb hash = 0.97, exact ID = 0.95, exact title + year = 0.90, etc.).
Score is computed and attached to every candidate. Auto-accept gap logic (gap ≥
0.2 between top and second candidate) also specified.

---

### 3. No undo / import session log ✓
No way to reverse a wrong import. With move mode, originals are gone.

**Resolution:** Session log implemented via `sessions` and `operations` DB
tables. `tapes log` shows a summary view (counts + unmatched files);
`tapes log --full` shows every file operation. Full undo is not implemented —
the session log is the audit trail; users must manually reverse wrong operations.
Move mode keeps the source intact until the DB record is written, limiting the
blast radius.

---

### 4. Illegal filenames on Windows ✓
Titles with colons, question marks, etc. produce illegal filenames on Windows.

**Resolution:** Default `[replace]` table sanitizes all Windows-illegal
characters. Configurable — users can override. Applied after template rendering,
before path construction. Documented in Filename Sanitization section.

---

### 5. Multi-episode files (S01E01E02) ✓
guessit returns a list of episode numbers for multi-episode files. The pipeline
assumes a single integer and will crash.

**Resolution:** Multi-episode handling is manual-only in v0.1. When the user
enters metadata for a TV episode, they use the syntax `s01e01-e02`. Tapes
produces the `S01E01E02` filename convention. Auto-detection deferred to a
future release.

---

## P1 — Should Fix Before v0.1

### 6. No import summary after bulk operations ✓
After importing hundreds of files, the user sees nothing.

**Resolution:** `tapes log` default view shows counts (N imported, N skipped,
N unmatched, N errors) plus a list of unmatched files. The summary is also
printed at the end of every import run.

---

### 7. Re-import duplicate detection ✓
Copy mode leaves originals. Re-running import on the same source duplicates
everything.

**Resolution:** Step 1 of the identification pipeline does a DB lookup by
(path, mtime, size). If the file is already known, it is skipped immediately.
This covers re-import of unchanged files. Changed files (different mtime or
size) are treated as new.

---

### 8. xattr cache is non-functional on Windows ✓
The xattr module uses a Linux/macOS API.

**Resolution:** xattr is dropped entirely. The DB lookup by (path, mtime, size)
in step 1 of the identification pipeline covers the same use case without any
platform-specific dependency.

---

### 9. Special editions / multiple versions ✓
"Dune (2021) Director's Cut" and "Dune (2021) Theatrical" produce the same
destination path.

**Resolution:** `{edition}` template field added. guessit already extracts
edition markers. Conditional syntax `{edition: - $}` renders as empty string
when absent. Documented in Templates section.

---

### 10. No quit option mid-import ✓
Interactive flow had no way to exit gracefully.

**Resolution:** `q` key added to the interactive prompt. On quit, tapes emits
`import_complete` for processed files and prints the session summary.

---

### 11. Silent error swallowing ✓
TMDB being down looked identical to "no match found."

**Resolution:** Design specifies distinguishing "no match" from "error during
lookup." Errors are logged with exception type and message. Rate limiting for
TMDB (~40 req/10s) and retry with backoff on transient errors to be implemented.

---

### 12. Unidentifiable files have no path forward ✓
Skip was the only option for unmatched files.

**Resolution:** `m` key added to the interactive prompt for manual metadata
entry. User supplies media type, title, year (and optionally more fields).
`match_source = "manual"` stored in DB. `s` key (search) is also fully
specified — collects structured fields, queries TMDB, shows ranked candidates.
Both flows documented in the Interactive Import Flow section.

---

### 13. DB schema missing columns for query use cases ✓
Design showed queries like `director:"David Lynch"` and `genre:thriller` but the
schema had no `director` or `genre` columns.

**Resolution:** New Database Schema section added to the design doc. `items`
table includes `director TEXT` and `genre TEXT` columns. `seasons` table stores
expected episode counts per show/season (sourced from TMDB) to support
`missing:episodes` queries.

---

### 14. Implementation plan Task 18 is too large →
"Wire CLI to services" is the most complex task with the least detail.

**Resolution:** Deferred to the implementation plan. Task 18 should be split
into: (a) application factory + tests, (b) import command integration,
(c) query/stats/info integration, (d) fix/log/check/move command integration.

---

### 15. Query parser breaks on quoted strings →
`director:"David Lynch"` splits on the space.

**Resolution:** Deferred to implementation. Use a proper tokeniser
(`shlex.split` or a dedicated regex) rather than `str.split`.

---

### 16. NFO scanner doesn't walk up directories ✓
`tvshow.nfo` lives at `The Wire/tvshow.nfo` but scanner only checked the
episode file's immediate parent.

**Resolution:** Design updated. Identification pipeline step 2 explicitly walks
up to 2 directory levels looking for `tvshow.nfo`.

---

### 17. OpenSubtitles hash lookup is never implemented →
Hash computation exists in the implementation plan but the API call to query
OpenSubtitles is missing.

**Resolution:** Deferred to implementation. A dedicated task must be added to
the implementation plan: implement the OpenSubtitles API client and integrate
the hash lookup into the identification pipeline at step 5. This is a key
design differentiator.

---

## P2 — Nice to Have

### 18. Library relocation command ✓
No way to update DB paths after moving the library to a new drive.

**Resolution:** `tapes check` detects library root mismatches and offers to
bulk-update DB paths. `tapes move` re-applies templates and physically moves
files. Both commands handle root changes. Documented in Library Integrity
section.

---

### 19. Reorganise after template change ✓
Changing the template does not rename existing files.

**Resolution:** `tapes move` re-applies the current templates to all library
files and updates DB paths. `--dry-run` available to preview first.

---

### 20. Plugin config detection is fragile →
Any TOML section with an `enabled` key is treated as a plugin.

**Resolution:** Deferred to implementation. Whitelist known non-plugin
top-level keys (`library`, `import`, `metadata`, `templates`, `replace`) and
treat all other sections with `enabled` as plugins.

---

### 21. TMDB API key validation at startup →
Missing or empty key causes silent 401 failures.

**Resolution:** Deferred to implementation. Validate at startup; emit a clear
error message. Config already supports `tmdb_api_key`; env var `TMDB_API_KEY`
also accepted.

---

### 22. EventBus error isolation ✓
A buggy plugin handler killed the import for that file.

**Resolution:** Design updated. `EventBus.emit` wraps each listener call in
`try/except Exception`. Errors are logged (handler name, event name, exception
type and message). The import continues for the current file and all subsequent
files.

---

### 23. No --config CLI flag ✓
`TAPES_CONFIG` env var existed but no `--config` CLI option.

**Resolution:** `--config <path>` added as a global CLI flag (applies to all
commands). Documented in the CLI Flags vs Config section.

---

### 24. No DB migration strategy ✓
`CREATE TABLE IF NOT EXISTS` won't add new columns to existing databases.

**Resolution:** `schema_version` table added to the database schema. On startup,
tapes reads the version and runs pending migration scripts from `tapes/migrations/`
in order. `CREATE TABLE IF NOT EXISTS` for initial creation; `ALTER TABLE` for
additive changes. Documented in the Database Schema section.

---

### 25. No .gitignore →
Task 1 creates the project but no `.gitignore`.

**Resolution:** Deferred to implementation. Add `.gitignore` in Task 1.

---

### 26. tapes info should work on non-imported files ✓
Unclear whether `tapes info` queries DB only or runs the pipeline.

**Resolution:** Design specifies that `tapes info <file>` runs the
identification pipeline when the file is not in the DB. This is the more
useful behaviour and is consistent with `tapes fields <file>`.

---

### 27. "Accept all remaining" option for bulk imports ✓
No way to accept all remaining high-confidence matches at once.

**Resolution:** `a` key added to the interactive prompt. Accepts all remaining
groups that score ≥ `confidence_threshold` without further prompting.

---

### 28. Companion file matcher is too greedy →
`S01E01` prefix matches `S01E01E02.mkv` (a different video).

**Resolution:** Deferred to implementation. Use exact stem matching: stem
followed by `.` or end of string.
