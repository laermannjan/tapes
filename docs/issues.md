# Issue Tracker

Status labels: `open` | `in-progress` | `done`

Design doc: `docs/plans/2026-03-08-detail-view-redesign.md`
Code review: `docs/reviews/2026-03-08-code-review.md`

---

## I01: Modal background color incorrect
**Status:** `done`
**Severity:** visual
**Files:** `tapes/ui/commit_modal.py`, `tapes/ui/help_overlay.py`

The modal panels use `background: #1a1a2e` in their CSS. This creates visible
contrast against the terminal background. Should inherit terminal bg instead.

**Decision log:**
- Remove explicit `background` from modal CSS. The `textual-ansi` theme handles transparency.

---

## I02: Detail view columns always split 50/50
**Status:** `done`
**Severity:** visual / layout
**Files:** `tapes/ui/detail_view.py`

The detail view splits columns 50/50. All three column areas (field names,
values, source values) should auto-size based on longest content + padding.

**Decision log:**
- Auto-size all three columns. Measure longest field name, longest value, longest source value.
- Subsumes I03 (padding) and I04 (separator). No vertical separator, use whitespace.

---

## I03: Detail view field name padding is incorrect
**Status:** `done` (subsumed by I02)
**Severity:** visual
**Files:** `tapes/ui/detail_view.py`, `tapes/ui/detail_render.py`

Fixed label width of 16 doesn't adapt to actual field name lengths.

**Decision log:**
- Handled by I02 auto-sizing. Label column width = longest field name + padding.

---

## I04: Detail view column separator looks thick
**Status:** `done` (subsumed by redesign)
**Severity:** visual
**Files:** `tapes/ui/detail_view.py`

The `┃` separator renders too thick.

**Decision log:**
- Eliminated entirely. Use 3+ spaces between columns (Claude Code style). No vertical separators.

---

## I05: tmdb_id field missing from detail view
**Status:** `done`
**Severity:** functional
**Files:** `tapes/ui/detail_render.py`

`tmdb_id` is not in the template so it never appears in the grid.

**Decision log:**
- Inject `tmdb_id` as the first field in `get_display_fields()`, always.

---

## I06: Detail view column headers don't look like headers
**Status:** `done` (subsumed by redesign)
**Severity:** visual
**Files:** `tapes/ui/detail_view.py`

Headers look like regular field values.

**Decision log:**
- Replaced by tab-based design. "Info" as window title in purple. TMDB sources
  as tabs (active = inverted, inactive = default white). No "result" header;
  field names and editable values have no column label.

---

## I07: File path missing in detail view
**Status:** `done`
**Severity:** functional
**Files:** `tapes/ui/detail_view.py`, `tapes/ui/detail_render.py`

Only filename shown, not full relative path.

**Decision log:**
- Show full path relative to scan root. Same styling as tree view row.

---

## I08: Detail view dimming inconsistent with tree view
**Status:** `done`
**Severity:** visual
**Files:** `tapes/ui/detail_view.py`

Filename/destination styling in detail header doesn't match tree view rows.

**Decision log:**
- Use identical styling: filename normal, arrow muted, destination via `render_dest()`.

---

## I09: Tree view should dim when detail view is focused
**Status:** `done`
**Severity:** visual
**Files:** `tapes/ui/tree_app.py`, `tapes/ui/tree_view.py`

Tree stays full contrast when detail is focused.

**Decision log:**
- Add CSS or class toggle to dim tree content when detail is expanded.
  Use muted color (~`#555555`) for all tree text when unfocused.

---

## I10: Inline editing doesn't work
**Status:** `done`
**Severity:** critical / functional
**Files:** `tapes/ui/detail_view.py`, `tapes/ui/tree_app.py`

Edit mode only triggers when no sources exist. Raw text accumulator is fragile.

**Decision log:**
- Rework as part of detail view redesign. `Enter` on a field in the left column
  (editable values) starts inline edit. When sources exist, `Enter` edits (not
  applies). Applying from source tab uses a different key or workflow. Consider
  Textual Input widget for proper text editing.

---

## I11: Commit modal should show operation selection, not file list
**Status:** `done`
**Severity:** UX / functional
**Files:** `tapes/ui/commit_modal.py`, `tapes/ui/tree_app.py`

Modal lists all staged files redundantly.

**Decision log:**
- Replace with: file count + operation selector (cycle: copy/move/link/hardlink).
- `h/l` or `←/→` to cycle operation. Default from config.
- Returns (confirmed: bool, operation: str).

---

## I12: Missing values inconsistently shown as dot vs question mark
**Status:** `done`
**Severity:** visual consistency
**Files:** `tapes/ui/detail_render.py`

`display_val()` returns `·` for None, but destinations use `?`.

**Decision log:**
- Always `?`. Change `display_val()` and audit all `\u00b7` usage in render code.

---

## I13: Focused detail view header should be one line
**Status:** `done`
**Severity:** visual
**Files:** `tapes/ui/detail_view.py`, `tapes/ui/detail_render.py`

Filename and destination on separate lines wastes vertical space.

**Decision log:**
- Single line: `path/to/file.mkv → destination`. Same format as tree view rows.

---

## I14: Unfocused detail view shows too much metadata
**Status:** `done`
**Severity:** UX
**Files:** `tapes/ui/detail_render.py`

Compact preview dumps title, year, type, season, episode.

**Decision log:**
- Show only: `tmdb: {id}  {confidence}%`. Confidence only when tmdb_id is set.
  If no tmdb_id: `tmdb: ?`.

---

## I15: Editing a metadata field should clear tmdb_id
**Status:** `done`
**Severity:** functional
**Files:** `tapes/ui/detail_view.py`

Manual edit doesn't invalidate the TMDB identification.

**Decision log:**
- `_commit_edit()` removes `tmdb_id` from result (unless editing tmdb_id itself).

---

## I16: TMDB blue and confidence green clash visually
**Status:** `done`
**Severity:** visual
**Files:** `tapes/ui/detail_view.py`, `tapes/ui/detail_render.py`

Blue TMDB label + green confidence look discordant.

**Decision log:**
- TMDB label: default white (not colored). Active tab is inverted with accent color.
- Confidence >=80%: muted. 50-79%: ember. <50%: red.
- Only the match indicator `[1/3]` uses accent color (via tab design).

---

<!-- ================================================================== -->
<!-- Code review findings: 2026-03-08                                   -->
<!-- Review doc: docs/reviews/2026-03-08-code-review.md                 -->
<!-- Triage: 2026-03-08                                                 -->
<!-- ================================================================== -->

<!-- -------------------------------------------------------------- -->
<!-- Triage overview                                                 -->
<!-- -------------------------------------------------------------- -->

### Triage: merges, dependencies, priority

**Merged tasks:**
- **TMDB reliability** (I18 + I21 + I26): cache fix, retry, rate limiting,
  client reuse. Solve together; can't retry without fixing the cache, can't
  rate-limit without a shared client.
- **Render caching** (I23 + I24): `all_files()` caching + hot-path caching
  (`template_field_names`, `_shared_result`, `_compute_arrow_col`).
- **Code hygiene** (I38 + I39 + I40): deduplication, constant consolidation,
  dead code removal. One cleanup pass.
- **Config & validation** (I29 + I36 + I37b): pydantic-settings, operation
  validation, deciding which values to expose. One brainstorm + implementation.
- **Architecture** (I31 + I32 + I35): provider abstraction, template system,
  media type model. Brainstorm together (defer implementation).

**Dependencies:**
```
I17 (hardlink) -> I36 (operation validation) -> I29 (pydantic-settings)
I17 -> I42 (test coverage for hardlink)
I26 (client reuse) -> I18+I21 (retry needs shared client, retry fixes cache)
I18+I21 -> I30 (async would restructure all TMDB client code)
I31 (provider) -> I35 (media type model)
I32 (templates) -> I35 (template selection needs media types)
I33 (move logic out of ui/) -> I38 (some duplication resolves when code moves)
I40 (dead code) -> I42 (test updates after removal)
```

**Priority:**

| Tier | Issues | Rationale |
|------|--------|-----------|
| High (UX-critical) | I27, I18+I21+I26, I17 | Core matching, reliability, broken feature |
| Medium (quality) | I22, I23+I24, I20, I19 | Speed, stability |
| Low (cleanup) | I28, I25, I33, I37a, I38+I39+I40, I41, I42 | Code quality, no user-facing change |
| Defer | I29+I36+I37b, I30, I31+I32+I35, I34 | Premature at pre-alpha |

---

## I17: `hardlink` operation not implemented
**Status:** `open`
**Priority:** high
**Severity:** bug
**Review:** `docs/reviews/2026-03-08-code-review.md` section 1.1
**Files:** `tapes/file_ops.py`, `tapes/ui/bottom_bar.py`
**Depends on:** nothing
**Blocks:** I36, I42
**Action:** fix

`bottom_bar.py:20` lists `"hardlink"` as a valid operation but
`file_ops.process_file()` only handles copy/move/link. Selecting hardlink and
committing raises `ValueError` for every file. Add `os.link()` support.

---

## I18: `_TmdbCache` failed keys permanently stuck
**Status:** `open`
**Priority:** high
**Severity:** bug
**Review:** `docs/reviews/2026-03-08-code-review.md` section 1.2
**Files:** `tapes/ui/pipeline.py`
**Depends on:** I26 (shared client needed first)
**Merge:** solve with I21 + I26 as "TMDB reliability"
**Action:** fix

If `fetch_fn()` raises, the event fires but nothing is stored in `_data` and
the key stays in `_pending` forever. Future requests for the same key get
`KeyError` instead of retrying.

**Revised approach:** Remove the key from `_pending` on failure (not sentinel).
This lets the user's `r` key (refresh TMDB) actually retry the fetch. A sentinel
hides the failure; enabling retry fixes the user experience.

---

## I19: Thread safety of node mutations during TMDB worker
**Status:** `open`
**Priority:** medium
**Severity:** bug (latent race condition)
**Review:** `docs/reviews/2026-03-08-code-review.md` section 1.3
**Files:** `tapes/ui/pipeline.py`, `tapes/ui/tree_app.py`
**Action:** fix

Worker threads mutate `node.result` and `node.sources` while the main UI thread
reads them for rendering. No lock protects node state. Dict mutation during
iteration can cause `RuntimeError`. Options: add a per-node lock, copy-on-write
updates via `call_from_thread`, or batch updates.

---

## I20: Move operation reads source file 3x + tiny hash buffer
**Status:** `open`
**Priority:** medium
**Severity:** performance
**Review:** `docs/reviews/2026-03-08-code-review.md` section 2.1
**Files:** `tapes/file_ops.py`
**Action:** fix

Hash source + copy + hash dest = 3 full reads of multi-GB files. Streaming
copy-and-hash halves the I/O. Hash buffer is 8KB (500K iterations per 4GB file).
Use `hashlib.file_digest()` (Python 3.11+ stdlib) for optimal buffering, and
combine the copy + hash into a single pass.

**UX note:** When implementing, consider adding a progress callback. A 4GB file
copy with no feedback feels broken.

---

## I21: No TMDB rate limiting or retry
**Status:** `open`
**Priority:** high
**Severity:** reliability
**Review:** `docs/reviews/2026-03-08-code-review.md` section 2.2
**Files:** `tapes/tmdb.py`, `tapes/ui/pipeline.py`
**Depends on:** I26 (shared client needed for rate limiter)
**Merge:** solve with I18 + I26 as "TMDB reliability"
**Action:** brainstorm (design rate limiter + retry strategy)

TMDB rate-limits at ~40 req/10s. 4 concurrent workers can exceed this. No retry
on 429 or 5xx. Transient failures silently lose matches. Need to decide:
token-bucket vs sliding-window rate limiter, exponential backoff strategy,
whether to use `tenacity` or hand-roll, sync vs async implications.

**UX note:** Rate limiting that visibly slows the pipeline needs progress
feedback in the bottom bar. Transparent throttling is fine; unexplained pauses
are not.

---

## I22: Episode search iterates ALL seasons
**Status:** `open`
**Priority:** medium
**Severity:** performance / API abuse
**Review:** `docs/reviews/2026-03-08-code-review.md` section 2.3
**Files:** `tapes/ui/pipeline.py`
**Action:** brainstorm

`_query_episodes` tries every season when the guessed season doesn't match.
Also remove dead variable `best_match_found` (assigned but never read).

**Revised approach:** The original review suggested capping at 2-3 seasons.
This is wrong for UX: if guessit gives a corrupt season number, capping means
missing a valid match. For a one-shot tool with no retry, "no match" when a
match exists is worse than extra API calls. Instead: search guessed season
first, then nearby (+/-1), then all remaining, combined with I21's rate
limiting. Show progress ("querying TMDB S3...") so it doesn't feel hung.

---

## I23: `all_files()` rebuilds list on every call
**Status:** `open`
**Priority:** medium
**Severity:** performance
**Review:** `docs/reviews/2026-03-08-code-review.md` section 2.4
**Files:** `tapes/ui/tree_model.py`, `tapes/ui/tree_view.py`
**Merge:** solve with I24 as "render caching"
**Action:** fix

Full tree walk 2-3 times per keystroke for footer stats. Cache the file list on
`TreeModel` (structure never changes after build). Or maintain incremental
counters for staged/ignored/total.

---

## I24: Rendering hot-path inefficiencies
**Status:** `open`
**Priority:** medium
**Severity:** performance
**Review:** `docs/reviews/2026-03-08-code-review.md` sections 2.5, 2.6, 2.8
**Files:** `tapes/ui/tree_render.py`, `tapes/ui/detail_view.py`, `tapes/ui/tree_view.py`
**Merge:** solve with I23 as "render caching"
**Action:** fix

Three related caching opportunities:
1. `template_field_names()` -- add `@lru_cache` (regex on every row render)
2. `_shared_result()` -- compute once in `_build_content`, pass to field rows
3. `_compute_arrow_col()` -- cache until tree structure changes

---

## I25: Scanner uses `rglob` + `is_file` instead of `os.walk`
**Status:** `open`
**Priority:** low
**Severity:** performance
**Review:** `docs/reviews/2026-03-08-code-review.md` section 2.7
**Files:** `tapes/scanner.py`
**Action:** fix

`rglob("*")` + `is_file()` double-stats every entry. `os.walk` is faster and
enables pruning hidden directories in-place (avoid descending into `.git`).

---

## I26: tmdb.py request helper + client reuse
**Status:** `open`
**Priority:** high
**Severity:** code quality / performance
**Review:** `docs/reviews/2026-03-08-code-review.md` sections 2.9, 6.1
**Files:** `tapes/tmdb.py`, `tapes/ui/pipeline.py`
**Blocks:** I18, I21
**Merge:** solve with I18 + I21 as "TMDB reliability"
**Action:** fix

The `if client else create_client()` pattern is duplicated 4 times.
`refresh_tmdb_source` creates 3 separate clients for one refresh. Extract an
`_ensure_client()` context manager and pass the client through in
`refresh_tmdb_source`.

---

## I27: Use rapidfuzz for similarity scoring
**Status:** `done`
**Priority:** high
**Severity:** accuracy
**Review:** `docs/reviews/2026-03-08-code-review.md` section 3.1
**Files:** `tapes/similarity.py`
**Design:** `docs/plans/2026-03-08-similarity-scoring-design.md`
**Plan:** `docs/plans/2026-03-08-similarity-scoring-implementation.md`

Replaced hand-rolled Jaccard with rapidfuzz WRatio. Added per-field
matching strategies (fuzzy strings, integer distance, exact match),
tmdb_id override for definitive identification, NULL-field penalty
(missing fields score 0.0), and named constants for all tuning
parameters. All weights and algorithm choice configurable via module
constants.

---

## I28: Use `string.Formatter().parse()` for template fields
**Status:** `open`
**Priority:** low
**Severity:** correctness
**Review:** `docs/reviews/2026-03-08-code-review.md` section 3.3
**Files:** `tapes/ui/tree_render.py`
**Action:** fix

Current regex incorrectly extracts names from `{{escaped_braces}}`. stdlib
`string.Formatter().parse()` handles all `str.format` syntax. One-line change.

---

## I29: Config overhaul (pydantic-settings + CLI flags + validation)
**Status:** `open`
**Priority:** defer
**Severity:** usability
**Review:** `docs/reviews/2026-03-08-code-review.md` sections 3.4, 5.1, 5.2
**Files:** `tapes/config.py`, `tapes/cli.py`
**Merge:** absorbs I36 (operation validation) and I37b (which values to expose)
**Depends on:** I17 (hardlink must work before validating it as an option)
**Action:** brainstorm (decide config precedence, which CLI flags to add)

Only `TMDB_TOKEN` has env var fallback. No CLI flags for operation, library
paths, templates, threshold. Need to decide: env prefix, which settings get
CLI flags, precedence order (CLI > env > config > defaults).

Includes I36: `operation: str = "copy"` accepts any string. Change to
`Literal["copy", "move", "link", "hardlink"]`.

Includes I37b: decide which hardcoded values (max_workers, timeout,
video extensions) warrant config exposure. See I37a for the naming pass.

---

## I30: Consider async TMDB client
**Status:** `open`
**Priority:** defer
**Severity:** architecture
**Review:** `docs/reviews/2026-03-08-code-review.md` section 3.5
**Files:** `tapes/tmdb.py`, `tapes/ui/pipeline.py`, `tapes/ui/tree_app.py`
**Depends on:** I18+I21+I26 (get sync client right first)
**Action:** brainstorm (evaluate sync threads vs async, impact on pipeline)

Textual runs an event loop. Currently using synchronous httpx.Client in
ThreadPoolExecutor. `httpx.AsyncClient` with `asyncio.gather` would be more
natural. Need to evaluate: migration effort, impact on `_TmdbCache`, whether
Textual workers handle async natively, backwards compatibility of pipeline API.

---

## I31: No metadata provider abstraction
**Status:** `open`
**Priority:** defer
**Severity:** architecture
**Review:** `docs/reviews/2026-03-08-code-review.md` section 4.1
**Files:** `tapes/tmdb.py`, `tapes/ui/pipeline.py`, `tapes/ui/detail_view.py`, `tapes/ui/tree_app.py`, `tapes/fields.py`
**Merge:** brainstorm with I32 + I35 as "architecture"
**Depends on:** I35 (media type model)
**Action:** brainstorm (design MetadataProvider protocol, plan migration)

TMDB hardcoded in 6+ locations. Blocks adding TVDB, MusicBrainz, or any
alternative source.

**UX note:** Premature at pre-alpha. The tool works with TMDB and two media
types today. Build abstractions when there's an actual second provider to
integrate. Keep as future architecture note, not active work.

---

## I32: Hardcoded 2-template system
**Status:** `open`
**Priority:** defer
**Severity:** architecture
**Review:** `docs/reviews/2026-03-08-code-review.md` section 4.2
**Files:** `tapes/config.py`, `tapes/ui/tree_render.py`, `tapes/ui/tree_app.py`, `tapes/ui/commit_view.py`
**Merge:** brainstorm with I31 + I35 as "architecture"
**Depends on:** I35 (template selection depends on media types)
**Action:** brainstorm (design media-type-keyed template + library path system)

Only `movie_template` and `tv_template` exist. `select_template()` is binary.
Same deferral rationale as I31: wait for a concrete third media type need.

---

## I33: Business logic lives under `tapes/ui/`
**Status:** `open`
**Priority:** low
**Severity:** architecture
**Review:** `docs/reviews/2026-03-08-code-review.md` section 4.3
**Files:** `tapes/ui/tree_model.py`, `tapes/ui/pipeline.py`, `tapes/ui/tree_render.py`, `tapes/ui/commit_view.py`
**Blocks:** I38 (some duplication resolves when code moves)
**Action:** fix

`tree_model.py` and `pipeline.py` have zero Textual imports. `compute_dest`,
`select_template`, `template_field_names`, `full_extension` are data logic.
`categorize_staged` is business logic. Move to `tapes/` proper. Update all
imports. This enables web UI or API reuse without pulling in Textual.

---

## I34: TreeApp state machine is implicit
**Status:** `open`
**Priority:** defer
**Severity:** maintainability
**Review:** `docs/reviews/2026-03-08-code-review.md` section 4.4
**Files:** `tapes/ui/tree_app.py`
**Action:** brainstorm (design state enum + transitions, plan refactor)

Five boolean flags, 15+ guard clauses. Mutually exclusive states modeled as
independent booleans. Also: TreeApp directly mutates CommitView private attrs
(`cv._files`, `cv._categories`). Worth doing for maintainability, but not
blocking any user-facing work.

---

## I35: `MEDIA_TYPE_EPISODE` conflates shows and episodes
**Status:** `open`
**Priority:** defer
**Severity:** data model
**Review:** `docs/reviews/2026-03-08-code-review.md` section 4.5
**Files:** `tapes/fields.py`, `tapes/tmdb.py`
**Merge:** brainstorm with I31 + I32 as "architecture"
**Blocks:** I31, I32
**Action:** investigate first, then brainstorm if needed

TMDB `media_type: "tv"` is mapped to `MEDIA_TYPE_EPISODE`. Can't distinguish
show-level results from episode-level results at the data level.

**Revised approach:** Before designing a fix, find a concrete scenario where
this causes a wrong result or broken UI. The two-stage TV query already handles
the distinction procedurally. If no real bug exists, close this issue.

---

## I37a: Name magic numbers
**Status:** `open`
**Priority:** low
**Severity:** readability
**Review:** `docs/reviews/2026-03-08-code-review.md` sections 5.3, 6.10
**Files:** various (see review)
**Action:** fix

Replace magic numbers with named constants. No config exposure, just
readability. Examples:
- `tree_app.py:177`: `+9` -> `DETAIL_CHROME_LINES = 9`
- `similarity.py:66`: `0.7` / `0.3` -> `TITLE_WEIGHT` / `YEAR_WEIGHT`
- `pipeline.py:275,376`: `3` -> `MAX_TMDB_RESULTS`
- `tmdb.py:33`: `10.0` -> `REQUEST_TIMEOUT_S`
- `tree_view.py:44`: `40` -> `DEFAULT_ARROW_COL`

Whether any of these should be user-configurable is deferred to I29 + I37b.

---

## I38: Code duplication in pipeline and UI
**Status:** `open`
**Priority:** low
**Severity:** maintainability
**Review:** `docs/reviews/2026-03-08-code-review.md` sections 6.2, 6.3
**Files:** `tapes/ui/pipeline.py`, `tapes/ui/bottom_bar.py`, `tapes/ui/commit_view.py`
**Merge:** solve with I39 + I40 as "code hygiene"
**Depends on:** I33 (moving code may resolve some duplication)
**Action:** fix

1. `extract_guessit_fields` and `_populate_node_guessit` duplicate field
   extraction -- extract `_metadata_to_fields()` helper.
2. `cycle_operation` identical in BottomBar and CommitView -- extract shared
   function.

---

## I39: Color constants and field constants scattered
**Status:** `open`
**Priority:** low
**Severity:** maintainability
**Review:** `docs/reviews/2026-03-08-code-review.md` sections 6.4, 6.8
**Files:** `tapes/ui/detail_view.py`, `tapes/ui/commit_view.py`, `tapes/ui/help_overlay.py`, `tapes/ui/bottom_bar.py`
**Merge:** solve with I38 + I40 as "code hygiene"
**Action:** fix

`ACCENT = "#B1B9F9"` defined in 4 files. Move to `tree_render.py` alongside
`MUTED`, `STAGED_COLOR`. Also: `commit_view.py` uses string literals `"title"`,
`"season"` instead of `TITLE`/`SEASON` constants from `fields.py`.

---

## I40: Dead code cleanup
**Status:** `open`
**Priority:** low
**Severity:** hygiene
**Review:** `docs/reviews/2026-03-08-code-review.md` section 6.5
**Files:** various (see review)
**Merge:** solve with I38 + I39 as "code hygiene"
**Blocks:** I42 (test updates needed after removal)
**Action:** fix

Remove:
- `best_match_found` in `pipeline.py:341` (assigned, never read)
- `get_movie()` in `tmdb.py` (never called)
- `TreeModel.flatten()` in `tree_model.py` (superseded by `flatten_with_depth`)
- `accept_best_source` in `tree_model.py` (tested but never called)
- `render_detail_header`, `render_detail_grid` in `detail_render.py` (test-only,
  real TUI uses `DetailView.render()`)
- `render_tree()` in `tree_view.py` ("backward compat with M2")

For `detail_render.py` functions: delete them and their tests. Replace with
widget-level behavioral assertions per `docs/testing.md`. Do not write
standalone render functions that approximate widget behavior.

---

## I41: Error handling gaps
**Status:** `open`
**Priority:** low
**Severity:** correctness / maintainability
**Review:** `docs/reviews/2026-03-08-code-review.md` section 6.7
**Files:** `tapes/tmdb.py`, `tapes/file_ops.py`, `tapes/ui/tree_app.py`
**Action:** fix

1. `tmdb.py:63`: `HTTPError | HTTPStatusError` is redundant (subclass).
2. `file_ops.py:88`: bare `except Exception` discards traceback -- add logging.
3. `tree_app.py:123-126`: bare `except Exception: pass` on theme -- narrow the
   catch or log a warning.
4. `_detail_snapshot` type: `list[tuple[FileNode, dict, list, bool]]` should be
   a NamedTuple or dataclass for readability.

---

## I42: Test coverage gaps
**Status:** `open`
**Priority:** low
**Severity:** quality
**Review:** `docs/reviews/2026-03-08-code-review.md` section 6.9
**Files:** `tests/`
**Depends on:** I17 (hardlink test), I18 (cache retry test), I40 (test updates)
**Action:** fix

Missing tests:
- CLI entry points (`import_cmd`, `tree_cmd`)
- `MetadataConfig.model_post_init` env var fallback
- `hardlink` operation (blocked on I17)
- Scroll indicators in TreeView
- `_TmdbCache` retry behavior (relates to I18)
- Extract `_render_plain` helper from 3 duplicate test sites
- Widget-level behavioral tests to replace `detail_render.py` standalone
  function tests (see `docs/testing.md`)

---
