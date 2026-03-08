# Code Review: 2026-03-08

Comprehensive review covering performance, library usage, extensibility,
configurability, and code quality. Findings are referenced by issue tracker
entries (I17+).

---

## 1. Bugs

### 1.1 `hardlink` operation not implemented (I17)

`bottom_bar.py:20` lists `"hardlink"` as a valid operation. `file_ops.py:44-62`
only handles `"copy"`, `"move"`, and `"link"`. Selecting hardlink and committing
raises `ValueError` for every file. The error is caught by `process_staged`'s
bare `except Exception` so the user sees "Error processing..." messages instead
of a clear failure.

### 1.2 `_TmdbCache` failed keys permanently stuck (I18)

`pipeline.py:61-67`: If `fetch_fn()` raises, `event.set()` fires (preventing
deadlock) but nothing is stored in `_data` and the key stays in `_pending`.
Future requests for the same key find it in `_pending`, wait on the already-set
event, then raise `KeyError`. The key can never be retried, even if the network
recovers. A show that fails once during a transient blip is permanently broken
for the entire session.

### 1.3 Thread safety of node mutations during TMDB worker (I19)

`pipeline.py:120-128` and `pipeline.py:289-292,384-386`: Worker threads mutate
`node.result` and `node.sources` directly while the main UI thread reads them
for rendering. No lock protects node state. Python's GIL prevents memory
corruption but dict mutations during iteration can cause `RuntimeError`, and
partially-updated state can be rendered (show fields without episode fields).

---

## 2. Performance

### 2.1 Move operation reads source file 3x (I20)

`file_ops.py:48-56`: For a 4GB file: hash source (4GB read) + `shutil.copy2`
(4GB read + 4GB write) + hash dest (4GB read) = 12GB of I/O. A streaming
copy-and-hash approach would read source once while writing + hashing, then
verify dest separately: 8GB instead of 12GB. The hash buffer is also only 8KB
(`file_ops.py:14`), meaning ~500K loop iterations per 4GB file. Use
`hashlib.file_digest()` (Python 3.11+ stdlib) or at minimum 1MB chunks.

### 2.2 No TMDB rate limiting or retry (I21)

TMDB rate-limits at ~40 requests per 10 seconds. With 4 concurrent workers
querying search + show + episodes per file, a directory with 50 TV episodes from
different shows could fire ~150 requests in seconds. No rate limiter exists. No
retry logic for 429 or transient 5xx responses. Failures silently log and return
empty results, losing matches permanently.

### 2.3 Episode search iterates ALL seasons (I22)

`pipeline.py:343-372`: When the guessit-derived season doesn't match,
`_query_episodes` iterates ALL seasons of a show. A show with 20 seasons means
20 API calls per file. `best_match_found` at line 341 is assigned but never
read (dead code). Should cap season search at 2-3 beyond the guessed season.

### 2.4 `all_files()` rebuilds list on every call (I23)

`tree_model.py:118-120`: Recursively walks the entire tree every call. Called
from `staged_count`, `total_count`, `ignored_count`, `_update_footer`,
`_show_commit`, `_do_commit`, and pipeline functions. That's 2-3 full tree
walks per keystroke. For 500 files, thousands of node visits per keypress just
for the footer.

### 2.5 `template_field_names` regex on every rendered row (I24)

`tree_render.py:25-32`: Called via `compute_dest` for every visible file row on
every render frame. The template string never changes between frames. An
`@lru_cache` on `template_field_names` would eliminate all redundant regex work.

### 2.6 `_shared_result()` recomputed per field row (I24)

`detail_view.py:291`: Called once per field in `_render_field_row`, plus once in
`_compute_col_widths`. For 7 fields in multi-node mode, that's 8 calls to
`compute_shared_fields` per render. Should compute once in `_build_content`.

### 2.7 Scanner uses `rglob` + `is_file` instead of `os.walk` (I25)

`scanner.py:70-71`: `rglob("*")` returns all entries, then `is_file()` does an
additional `stat()` per entry. `os.walk` is faster because `scandir` already
knows file vs directory. It also enables pruning hidden directories in-place,
avoiding descent into `.git` with thousands of objects.

### 2.8 `_compute_arrow_col` scans all items on every refresh (I24)

`tree_view.py:149-174`: Iterates every visible item to find the widest filename.
Called from `_refresh_items` and `on_resize`. Could be cached until tree
structure changes.

### 2.9 `refresh_tmdb_source` creates 3 separate HTTP clients (I26)

`pipeline.py:176` calls `_query_tmdb_for_node` without passing a client. That
function calls `search_multi`, `get_show`, `get_season_episodes` -- each
creating and destroying a separate `httpx.Client`. Three TLS handshakes for one
refresh action.

---

## 3. Library Replacements

### 3.1 Similarity scoring: rapidfuzz instead of Jaccard (I27)

`similarity.py:11-25`: Hand-rolled Jaccard word-token similarity fails on
reordered titles ("The Dark Knight" vs "Dark Knight, The"), spelling differences,
and transliterated titles. `rapidfuzz` provides `token_set_ratio` / `WRatio`
with C-optimized performance. This is the core auto-accept decision and directly
affects whether users must manually curate every file.

### 3.2 `hashlib.file_digest()` instead of manual chunking (I20)

`file_ops.py:9-15`: Manual 8KB chunk reading when `hashlib.file_digest()` exists
since Python 3.11 (which is the project's minimum). Two lines instead of seven,
optimal buffer sizing internally.

### 3.3 `string.Formatter().parse()` instead of regex (I28)

`tree_render.py:25-32`: `template_field_names` uses a regex that incorrectly
extracts field names from `{{escaped_braces}}`. The stdlib
`string.Formatter().parse()` handles all `str.format` syntax correctly.

### 3.4 `pydantic-settings` for config (I29)

Only `TMDB_TOKEN` has env var fallback, done manually in `model_post_init`.
`pydantic-settings` gives env var override for every field, `.env` file support,
and precedence handling for free.

### 3.5 Consider `httpx.AsyncClient` + asyncio (I30)

The TMDB pipeline uses synchronous `httpx.Client` in a `ThreadPoolExecutor`.
Since Textual already runs an event loop, `httpx.AsyncClient` with
`asyncio.gather` would be more natural and avoid threading overhead.

---

## 4. Extensibility and Architecture

### 4.1 No metadata provider abstraction (I31)

TMDB is hardcoded in 6+ locations with no provider interface. `tmdb.py` (API
client), `pipeline.py` (direct calls + string-based source filtering),
`detail_view.py` (tab labels), `tree_app.py` (worker naming), `fields.py`
(`TMDB_ID`), `help_overlay.py` (help text). Adding TVDB requires touching all
of these. A `MetadataProvider` protocol with `search`/`get_details` methods
would decouple the pipeline from any specific provider.

### 4.2 Hardcoded 2-template system (I32)

`config.py:32-36` has only `movie_template` and `tv_template`.
`tree_render.py:select_template()` is a binary choice. `tree_app.py:333-340`
maps media types to library paths with if/elif. `commit_view.py:categorize_staged()`
has hardcoded categories. Changing to `templates: dict[str, str]` and
`library_paths: dict[str, str]` keyed by media_type would support audiobooks,
music, ebooks without code changes.

### 4.3 Business logic lives under `tapes/ui/` (I33)

`tree_model.py` and `pipeline.py` have zero Textual imports but live in
`tapes/ui/`. `compute_dest`, `select_template`, `template_field_names`,
`full_extension` in `tree_render.py` are data logic. `categorize_staged` in
`commit_view.py` is business logic. Moving these to `tapes/` proper makes the
shared-core vs UI-frontend boundary explicit and enables a web UI to reuse them.

### 4.4 TreeApp state machine is implicit (I34)

`tree_app.py:91-99`: Five boolean state flags (`_in_detail`, `_in_commit`,
`_in_help`, `_searching`, `_tmdb_querying`). Every action method starts with
2-4 guard checks. States are mutually exclusive but modeled as independent
booleans. An `enum AppState` with valid transitions would prevent impossible
states and eliminate 15+ repeated guard clauses.

### 4.5 `MEDIA_TYPE_EPISODE` conflates shows and episodes (I35)

`tmdb.py:94` maps TMDB `media_type: "tv"` to `MEDIA_TYPE_EPISODE`. Can't
distinguish "this result is a TV show" from "this is a specific episode." This
makes it harder to handle shows vs episodes differently in the pipeline.

---

## 5. Configurability

### 5.1 Missing CLI flags for common settings (I29)

A user wanting `tapes import /dir --operation move --library-movies /nas/movies`
must create a YAML file. No CLI flags for: operation mode, library paths,
templates, auto-accept threshold. For a one-shot tool, CLI flags for common
settings are expected.

### 5.2 No validation on `operation` field (I36)

`config.py:37`: `operation: str = "copy"` accepts any string. A typo like
`"copu"` passes config loading and only fails at `process_file` time. Should be
`Literal["copy", "move", "link", "hardlink"]`.

### 5.3 Hardcoded values that should be configurable (I37)

- `max_workers = 4` (pipeline.py:87)
- `timeout = 10.0` (tmdb.py:33)
- Max TMDB results: `3` (tmdb.py:98, pipeline.py:275, 376)
- `VIDEO_EXTENSIONS` (scanner.py:9)
- `SUBTITLE_EXTS`, `SIDECAR_EXTS` (commit_view.py:22-23)
- Scoring weights (similarity.py:66, 90-109)
- Color constants scattered across 6 files

---

## 6. Code Quality

### 6.1 tmdb.py request pattern duplicated 4x (I26)

`tmdb.py:55-65,112-119,143-150,189-195`: Every function has the same
`if client else create_client()` block. Extract `_ensure_client()` context
manager or a `_request()` helper.

### 6.2 Field extraction duplicated in pipeline.py (I38)

`pipeline.py:179-201` (`extract_guessit_fields`) and `pipeline.py:204-228`
(`_populate_node_guessit`) have nearly identical field extraction logic. Should
extract shared `_metadata_to_fields()` helper.

### 6.3 `cycle_operation` duplicated in BottomBar and CommitView (I38)

`bottom_bar.py:80-83` and `commit_view.py:167-170` are identical. Extract to a
shared function or mixin.

### 6.4 `ACCENT` constant defined in 4 files (I39)

`detail_view.py:34`, `commit_view.py:20`, `help_overlay.py:14`,
`bottom_bar.py:16` all define `ACCENT = "#B1B9F9"`. Should live in
`tree_render.py` alongside `MUTED`, `STAGED_COLOR`, etc.

### 6.5 Dead code (I40)

- `best_match_found` in `pipeline.py:341` -- assigned, never read
- `get_movie()` in `tmdb.py:104-132` -- never called anywhere
- `TreeModel.flatten()` in `tree_model.py:44-52` -- superseded by
  `flatten_with_depth`
- `accept_best_source` in `tree_model.py:212-225` -- tested but never called
  from production code
- `render_detail_header`, `render_detail_grid` in `detail_render.py` -- only
  used in tests, real TUI uses `DetailView.render()`
- `render_tree()` in `tree_view.py:243-260` -- "backward compatibility with M2"

### 6.6 TreeApp directly mutates CommitView private attrs (I34)

`tree_app.py:216-217`: `cv._files = staged` and `cv._categories = ...` bypass
encapsulation. Should be a public `set_staged(files)` method.

### 6.7 Error handling gaps (I41)

- `tmdb.py:63`: `HTTPError | HTTPStatusError` -- the latter is a subclass of
  the former, union is redundant
- `file_ops.py:88`: bare `except Exception` discards traceback
- `tree_app.py:123-126`: bare `except Exception: pass` on theme setting
- `_detail_snapshot` type is `list[tuple[FileNode, dict, list, bool]]` -- should
  be a named tuple or dataclass

### 6.8 Inconsistent field constant usage (I39)

`fields.py` defines constants but `commit_view.py:44` uses string literal
`"title"` and `commit_view.py:45` uses `"season"` instead of `TITLE`/`SEASON`.

### 6.9 Test coverage gaps (I42)

- No `test_cli.py` for CLI entry points
- No test for `MetadataConfig.model_post_init` env var fallback
- No test for `hardlink` operation (which is broken, see I17)
- No test for scroll indicators in TreeView
- No test for `_TmdbCache` retry behavior
- `_render_plain` helper duplicated in 3 test files

### 6.10 Magic numbers (I37)

- `tree_app.py:177`: `detail.styles.height = len(detail.fields) + 9`
- `tree_view.py:44`: `self._arrow_col: int = 40`
- `detail_view.py:139`: `label_w = max(..., default=6) + 4`
- `similarity.py:66`: `0.7 * title_score + 0.3 * year_score`
- `pipeline.py:275,376`: max 3 TMDB results
- `tmdb.py:33`: `timeout=10.0`
- `tree_app.py:520`: 1.0 second ctrl+c window
