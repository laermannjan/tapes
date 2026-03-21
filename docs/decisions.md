# Decisions

Architectural decisions, rejected approaches, and learnings. Updated when
design specs or implementation plans are retired. For the full historical
record, see `docs/legacy/`.

---

## Core architecture

### One-shot by default, persistent with polling
Each run is independent by default. No SQLite, no session tracking, no
persistent state between runs. With `--poll-interval`, the app stays alive
and picks up new files via periodic rescanning.

Rejected: SQLite database tracking imports (early design, 2026-03-04). Added
maintenance burden and complexity with no benefit for a CLI tool that processes
files in one pass. Session resumption after crash was considered and dropped as
over-engineering.

Consequence: users cannot pause and resume import sessions. No cross-run
duplicate detection.

### Every file is first-class
No special "companion" concept. Subtitles, artwork, NFOs are just files with
their own metadata and candidates.

Rejected: companion-centric pipeline where subtitles/artwork inherit metadata
from a "main" media file. Dropped because it created implicit coupling and
edge cases (which file is the "main" one?).

### Candidate-based metadata curation
Each file has a `metadata` dict (used for destination) and a list of
`Candidate` objects (guessit, TMDB matches). Users cherry-pick values from
candidates into metadata.

Rejected: automatic metadata merging from multiple sources. Prevented user
control and made conflicts invisible. Also rejected: single unified
"result + source layers" model, which created ambiguity about which layer
applies.

### guessit-driven metadata extraction
guessit is the primary source for title, year, season, episode, codec,
resolution. NFO and embedded tags are reference only.

Rejected: sidecar .nfo files as primary source (not all files have them,
complex multi-source resolution). Rejected: MediaInfo as primary (requires
binary install, doesn't extract episode/season info).

---

## Identification pipeline

### Two-stage TV episode query
For TV: (1) search for show or use tmdb_id, (2) query specific season(s),
(3) auto-accept or return top 3 episodes per season.

Rejected: single TMDB search for episode by title. TMDB episode search is
unreliable; constraining to show+season ensures correct matches. Rejected:
fan-out to all seasons immediately (inefficient).

Consequence: two network round-trips per file, but accurate episode matching.

### Similarity vs confidence are separate concerns
Similarity is pairwise match quality (displayed to user). Confidence is the
auto-accept decision (uses multi-candidate signal: high similarity OR clear
winner by prominence).

Rejected: single threshold on pairwise score. Cannot distinguish subset
matches from different-entity candidates by similarity alone. WRatio alone
scores "Breaking Bad" and "El Camino: A Breaking Bad Movie" identically,
destroying margin signal.

### Blended fuzzy algorithm
`STRICT_WEIGHT * ratio + (1 - STRICT_WEIGHT) * token_set_ratio` with
STRICT_WEIGHT=0.7.

Rejected: rapidfuzz WRatio alone (destroys margin signal). Rejected: pure
character-level Levenshtein (over-penalizes legitimate variation like articles
and word order). Rejected: pure token-set matching (scores subsets as high as
exact matches).

### Media-type penalty
When guessit's `media_type` disagrees with a TMDB candidate's, multiply
similarity by 0.7.

Rejected: hard reject on mismatch (shows/movies can share titles, user should
still be able to accept). Rejected: no penalty (causes false auto-accepts).

### Candidates cleared after acceptance
When a show/movie is accepted, `node.candidates` is cleared before the
episode query runs. Episode candidates appear fresh afterward.

Rejected: keeping show-level candidates visible after acceptance. Confuses
users when episode candidates suddenly mix in.

### No early stopping in episode scoring
Score all seasons of a show (or the specified season), return top 3. Don't
stop at first high-scoring match.

Rejected: early stop on first match above threshold. Prevents finding the
correct episode if guessit got the season number wrong.

---

## UI

### Inline views over modals
All views (tree, metadata, commit, help) are inline widgets toggled via
display CSS. Never modal overlays.

Rejected: modal screens stacked on main view. They trap focus, require complex
state management, and prevent seeing the tree while editing.

### Snapshot/restore for metadata editing
On entering metadata view, snapshot current metadata. Esc restores snapshot
(discard). Enter keeps edits (confirm).

Rejected: live updates as user types (unpredictable display changes). Rejected:
separate "edit mode" state (redundant; snapshot model is simpler).

### AppState enum over boolean flags
Single `AppState` enum (TREE, DETAIL, COMMIT, HELP, SEARCHING) instead of
independent boolean flags.

Rejected: boolean flags (_in_detail, _in_commit, _in_help, _searching). They
permit impossible states (e.g., in_detail=True AND in_commit=True
simultaneously).

### Staging is a readiness marker only
Staging marks a file ready for processing. It does not modify metadata, apply
candidates, or trigger side effects.

Rejected: staging triggers auto-accept (conflates concerns). Rejected: staging
requires template completeness (validation happens at commit time instead).

### Keybinding minimalism
Universal keys (enter, space, esc, tab, arrows) over mnemonic letters.
Common actions use consistent keys across modes.

Rejected: mnemonic keys (a=accept, c=commit). They vary per mode and create
cognitive load.

### Named placeholders for missing fields
Missing template fields render as red `{field_name?}` in the tree destination
preview, not generic `?` or omitted.

Rejected: generic `?` (doesn't show which field is missing). Rejected: omit
missing fields (destination path becomes misleading).

---

## Config and I/O

### Move = copy-then-delete
Same-device and cross-device moves both use `shutil.copy2` + `unlink`.
No application-level checksumming.

Rejected: `os.rename()` with cross-device fallback (kernel-specific atomicity
expectations don't hold across filesystems). Rejected: SHA-256 verification
after copy (unacceptable latency on large files; kernel copying via
copy_file_range/sendfile is reliable).

Consequence: move is never atomic (crash mid-operation leaves both copies).

### Two templates selected by media_type
`movie_template` and `tv_template`, selected by the `media_type` metadata
field. Users can edit `media_type` to switch templates.

Rejected: detection by file location or size heuristics (fragile, non-obvious).

### TMDB v4 bearer token
Read access token via `Authorization: Bearer` header. Config field:
`tmdb_token`, env var: `TMDB_TOKEN`.

Rejected: TMDB v3 API key (v4 is current, simpler HTTP structure).

### TMDB language support
Optional `language` config passed to all TMDB queries. TMDB returns both
localized and original titles; similarity scoring takes max of both.

### Web UI via textual-serve
Serve the existing Textual TUI over WebSocket. Same code, no custom frontend.

Rejected: REST API + custom web frontend (duplicate UI logic). Rejected:
desktop app wrapper like Electron/Tauri (over-engineered).

### Unified conflict detection with virtual nodes
Single algorithm handles all conflict types (staged-vs-staged,
staged-vs-existing on disk, three-way) by injecting virtual `ExistingFile`
nodes into the candidate list. Three policies: `auto` (largest file wins),
`skip` (existing file wins), `keep_all` (numeric suffixes). Replaces old
`duplicate_resolution` and `disambiguation` settings.

Rejected: separate detection paths for each conflict type (code duplication,
inconsistent behavior). Rejected: silent overwrites (data loss). Rejected:
blocking errors that halt the entire commit.

### FileStatus enum over boolean pair
Single `FileStatus` enum (PENDING/STAGED/REJECTED) replaces `staged: bool`
and `ignored: bool`. Eliminates impossible states. "Rejected" covers both
user rejection (x key) and system rejection (conflict loser). Pipeline
respects REJECTED - does not auto-stage rejected files.

Rejected: three independent booleans (staged/ignored/rejected). Kept as
enum for mutual exclusivity.

### Delete rejected
Optional `delete_rejected` setting deletes source files of all rejected
nodes on commit. In manual commit: all rejected files. In auto-commit:
only files rejected in the current batch (prevents deleting user's manual
rejections from other batches).

---

## CLI and modes

### Single command with composable flags
No subcommands. `tapes [PATH]` with orthogonal flags: `--serve`, `--auto-commit`,
`--headless`, `--one-shot`. Flags compose freely. All config flags available in
every mode.

Rejected: `tapes import` / `tapes serve` subcommands. The serve command
couldn't forward all import flags to the textual-serve subprocess. Single
command solves this by stripping `--serve*` from `sys.argv`.

### --serve via textual-serve subprocess
textual-serve only accepts a command string (no in-process App serving API).
`--serve` strips itself from argv and delegates. Subprocess inherits env vars,
so `TAPES_MODE__SERVE` is unset to prevent recursion.

Rejected: custom Textual Driver for in-process web serving (100+ lines,
fragile, loses session isolation). Rejected: hardcoded `"tapes"` as subprocess
command (breaks `python -m` invocation).

### Auto-commit with debounce
2-second debounce timer (configurable) groups rapid staging events. View state
guard defers firing during metadata/commit/help views. Pending flag ensures
deferred batches fire on return to tree view.

Rejected: immediate processing on every stage event (thrashing with TMDB
bursts). Rejected: periodic sweep (less responsive than debounce).

### Directory polling over filesystem events
Periodic `os.walk` rescanning (default 10 seconds, configurable, 0 to disable).
On changes, rebuilds tree from scratch and migrates state by path. Avoids
surgical insertion into compressed tree structure.

Rejected: watchdog/filesystem events (unreliable on NFS/SMB mounts, common
in Unraid). Rejected: surgical node insertion (complex due to
`_compress_single_child_dirs`).

### Headless via Textual's headless mode
`app.run(headless=True)` runs the full TUI lifecycle without terminal I/O.
All timers, workers, and events work identically. Zero code duplication
between TUI and headless modes.

`--headless` implies `--auto-commit`. `--one-shot` implies `--headless`
and `--poll-interval 0`.

Rejected: separate HeadlessRunner that replicates TreeApp orchestration
(code duplication, divergent behavior).

### TMDB token required
All modes require a TMDB token. Without identification, tapes can only
extract metadata from filenames - not enough value for any use case.

---

## Logging

### structlog with context binding
structlog replaces stdlib logging. Bound loggers (`log = logger.bind(file=...)`)
carry file identity through all subsequent calls, solving the concurrent TMDB
worker interleaving problem. JSON output (one object per line) enables
filtering with jq/grep.

Rejected: stdlib logging with custom JsonFormatter (no context binding, every
call repeats `extra={"file": ...}`). Rejected: python-json-logger (dependency
for ~30 lines of trivial code, but structlog's context binding provides
genuine value beyond formatting).

### Console output adapts to terminal
stdout uses `ConsoleRenderer` (colored, human-readable) when connected to a
terminal, `JSONRenderer` when piped. Log file always gets JSON. Enables
both interactive use and scripting.

### Event names follow pipeline vocabulary
Events use canonical pipeline terms: `extract` (guessit), `staged`/`not_staged`
(auto-accept gate), `committed` (file processing), `rejected` (conflict).
Not internal implementation names like `tmdb_match` or `processed`.
