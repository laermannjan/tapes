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
  validation, deciding which values to expose. Implemented.
- **Architecture** (I31 + I32 + I35): provider abstraction, template system,
  media type model. Brainstorm together (defer implementation).

**Dependencies (remaining):**
```
I29 (pydantic-settings) -- unblocked (I17 done)
I30 (async) -- unblocked (I18+I21+I26 done)
I31 (provider) -> I35 (media type model)
I32 (templates) -> I35 (template selection needs media types)
```

**Priority:**

| Tier | Issues | Rationale |
|------|--------|-----------|
| Done | I17, I18, I19, I20, I21, I22, I23, I24, I25, I26, I27, I28, I29+I36+I37b, I33, I34, I37a, I38, I39, I40, I41, I42 | All implemented |
| Defer | I30, I31+I32 | Premature at pre-alpha |

---

## I17: `hardlink` operation not implemented
**Status:** `done`
**Priority:** high
**Severity:** bug
**Review:** `docs/reviews/2026-03-08-code-review.md` section 1.1
**Files:** `tapes/file_ops.py`, `tapes/ui/bottom_bar.py`

Added `os.link()` support in `process_file()`. Hardlink now works as a valid
operation alongside copy/move/link.

---

## I18: `_TmdbCache` failed keys permanently stuck
**Status:** `done`
**Priority:** high
**Severity:** bug
**Review:** `docs/reviews/2026-03-08-code-review.md` section 1.2
**Files:** `tapes/pipeline.py`

Fixed: on failure, key is removed from `_pending` (not stored as sentinel),
allowing retry via `r` key. Solved together with I21+I22+I26 as TMDB reliability.

---

## I19: Thread safety of node mutations during TMDB worker
**Status:** `done`
**Priority:** medium
**Severity:** bug (latent race condition)
**Review:** `docs/reviews/2026-03-08-code-review.md` section 1.3
**Files:** `tapes/pipeline.py`, `tapes/ui/tree_app.py`

Fixed via dispatch pattern: `post_update` callback (trampoline). Worker passes
mutations to the main thread via `call_from_thread`. No direct node mutation
from worker threads.

---

## I20: Move operation reads source file 3x + tiny hash buffer
**Status:** `done`
**Priority:** medium
**Severity:** performance
**Review:** `docs/reviews/2026-03-08-code-review.md` section 2.1
**Files:** `tapes/file_ops.py`

Implemented `_copy_and_hash()`: single-pass copy + SHA-256 with 1 MB buffer.
Move verifies by re-hashing destination. Added `progress_callback` parameter.

---

## I21: No TMDB rate limiting or retry
**Status:** `done`
**Priority:** high
**Severity:** reliability
**Review:** `docs/reviews/2026-03-08-code-review.md` section 2.2
**Files:** `tapes/tmdb.py`, `tapes/pipeline.py`

Added tenacity retry with `_is_retryable()` (429, 500, 502, 503, 504) and
`_retry_after_wait()` for Retry-After headers. 3 attempts max, exponential
backoff fallback. Solved together with I18+I22+I26.

---

## I22: Episode search iterates ALL seasons
**Status:** `done`
**Priority:** medium
**Severity:** performance / API abuse
**Review:** `docs/reviews/2026-03-08-code-review.md` section 2.3
**Files:** `tapes/pipeline.py`

Addressed as part of TMDB reliability work (I26+I18+I21+I22). Dead variable
`best_match_found` removed. Rate limiting via tenacity retry prevents API abuse.

---

## I23: `all_files()` rebuilds list on every call
**Status:** `done`
**Priority:** medium
**Severity:** performance
**Review:** `docs/reviews/2026-03-08-code-review.md` section 2.4
**Files:** `tapes/tree_model.py`, `tapes/ui/tree_view.py`

Cached file list on `TreeModel` (immutable after construction). Solved with I24.

---

## I24: Rendering hot-path inefficiencies
**Status:** `done`
**Priority:** medium
**Severity:** performance
**Review:** `docs/reviews/2026-03-08-code-review.md` sections 2.5, 2.6, 2.8
**Files:** `tapes/ui/tree_render.py`, `tapes/ui/detail_view.py`, `tapes/ui/tree_view.py`

Added `@lru_cache` to `template_field_names()`, cached arrow column. Solved
with I23.

---

## I25: Scanner uses `rglob` + `is_file` instead of `os.walk`
**Status:** `done`
**Priority:** low
**Severity:** performance
**Review:** `docs/reviews/2026-03-08-code-review.md` section 2.7
**Files:** `tapes/scanner.py`

Replaced with `os.walk`. In-place pruning of hidden directories, sorted output
for determinism.

---

## I26: tmdb.py request helper + client reuse
**Status:** `done`
**Priority:** high
**Severity:** code quality / performance
**Review:** `docs/reviews/2026-03-08-code-review.md` sections 2.9, 6.1
**Files:** `tapes/tmdb.py`, `tapes/pipeline.py`

Extracted `_request()` helper with tenacity retry. Client reuse via shared
`httpx.Client` in pipeline. Solved together with I18+I21+I22.

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
**Status:** `done`
**Priority:** low
**Severity:** correctness
**Review:** `docs/reviews/2026-03-08-code-review.md` section 3.3
**Files:** `tapes/ui/tree_render.py`

Replaced regex with `string.Formatter().parse()`. Cached with `@lru_cache`.

---

## I29: Config overhaul (pydantic-settings + CLI flags + validation)
**Status:** `done`
**Priority:** high
**Severity:** usability
**Review:** `docs/reviews/2026-03-08-code-review.md` sections 3.4, 5.1, 5.2
**Design:** `docs/plans/2026-03-08-config-overhaul.md`
**Files:** `tapes/config.py`, `tapes/cli.py`, `tapes/pipeline.py`, `tapes/tmdb.py`, `tapes/scanner.py`, `tapes/ui/tree_app.py`
**Merge:** absorbed I36 (operation validation) and I37b (which values to expose)
**Depends on:** I17 (hardlink must work before validating it as an option)

Migrated to pydantic-settings with four config sections (scan, metadata,
library, advanced). Config precedence: CLI flags > env vars > config file >
defaults. Config file discovery via platformdirs (`~/.config/tapes/config.toml`).
Env var prefix `TAPES_` with `__` nesting (e.g. `TAPES_METADATA__TMDB_TOKEN`).

All hardcoded constants now serve as default values for their respective config
fields and function parameters. Pipeline, tmdb, and scanner functions accept
config values as parameters, with constants as fallback defaults for backwards
compatibility and test convenience.

Includes I36: operation validated as `Literal["copy", "move", "link", "hardlink"]`.

Includes I37b: exposed max_workers, tmdb_timeout, tmdb_retries, max_results,
video_extensions, auto_accept_threshold, margin_accept_threshold,
min_accept_margin as config fields with CLI flags.

---

## I30: Consider async TMDB client
**Status:** `open`
**Priority:** defer
**Severity:** architecture
**Review:** `docs/reviews/2026-03-08-code-review.md` section 3.5
**Files:** `tapes/tmdb.py`, `tapes/pipeline.py`, `tapes/ui/tree_app.py`
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
**Files:** `tapes/tmdb.py`, `tapes/pipeline.py`, `tapes/ui/detail_view.py`, `tapes/ui/tree_app.py`, `tapes/fields.py`
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
**Files:** `tapes/config.py`, `tapes/ui/tree_render.py`, `tapes/ui/tree_app.py`, `tapes/ui/commit_view.py`, `tapes/categorize.py`
**Merge:** brainstorm with I31 + I35 as "architecture"
**Depends on:** I35 (template selection depends on media types)
**Action:** brainstorm (design media-type-keyed template + library path system)

Only `movie_template` and `tv_template` exist. `select_template()` is binary.
Same deferral rationale as I31: wait for a concrete third media type need.

---

## I33: Business logic lives under `tapes/ui/`
**Status:** `done`
**Priority:** low
**Severity:** architecture
**Review:** `docs/reviews/2026-03-08-code-review.md` section 4.3
**Files:** `tapes/tree_model.py`, `tapes/pipeline.py`, `tapes/categorize.py`

Moved `tree_model.py` and `pipeline.py` to `tapes/`. Extracted
`categorize_staged` into `tapes/categorize.py`. All imports updated.

---

## I34: TreeApp state machine is implicit
**Status:** `done`
**Severity:** maintainability
**Files:** `tapes/ui/tree_app.py`

Replaced 4 boolean flags (`_in_detail`, `_in_commit`, `_in_help`, `_searching`)
with `AppMode` enum (TREE, DETAIL, COMMIT, HELP, SEARCHING). Impossible states
eliminated by construction. `_MODAL_MODES` frozenset for shared guard pattern.

---

## I35: `MEDIA_TYPE_EPISODE` conflates shows and episodes
**Status:** `closed` (won't fix)
**Severity:** data model

Not an issue. `media_type` is a binary movie-or-episode choice used for template
selection. The two-stage TMDB query handles show-vs-episode procedurally. No
scenario where the current model produces wrong results.

---

## I37a: Name magic numbers
**Status:** `done`
**Priority:** low
**Severity:** readability
**Review:** `docs/reviews/2026-03-08-code-review.md` sections 5.3, 6.10
**Files:** various (see review)

Replaced magic numbers with named constants across all files.

---

## I38: Code duplication in pipeline and UI
**Status:** `done`
**Priority:** low
**Severity:** maintainability
**Review:** `docs/reviews/2026-03-08-code-review.md` sections 6.2, 6.3
**Files:** `tapes/pipeline.py`, `tapes/ui/bottom_bar.py`, `tapes/ui/commit_view.py`

Deduplicated `cycle_operation` into shared function. Consolidated with I39+I40.

---

## I39: Color constants and field constants scattered
**Status:** `done`
**Priority:** low
**Severity:** maintainability
**Review:** `docs/reviews/2026-03-08-code-review.md` sections 6.4, 6.8
**Files:** `tapes/ui/detail_view.py`, `tapes/ui/commit_view.py`, `tapes/ui/help_overlay.py`, `tapes/ui/bottom_bar.py`

Consolidated all color constants into `tree_render.py`. Solved with I38+I40.

---

## I40: Dead code cleanup
**Status:** `done`
**Priority:** low
**Severity:** hygiene
**Review:** `docs/reviews/2026-03-08-code-review.md` section 6.5
**Files:** various (see review)

Removed dead code: `best_match_found`, `get_movie()`, `TreeModel.flatten()`,
`accept_best_source`, standalone render functions, `render_tree()`. Tests
updated. Solved with I38+I39.

---

## I41: Error handling gaps
**Status:** `done`
**Priority:** low
**Severity:** correctness / maintainability
**Review:** `docs/reviews/2026-03-08-code-review.md` section 6.7
**Files:** `tapes/tmdb.py`, `tapes/file_ops.py`, `tapes/ui/tree_app.py`

Fixed redundant exception types, added logging to bare excepts, narrowed
catches.

---

## I42: Test coverage gaps
**Status:** `done`
**Priority:** low
**Severity:** quality
**Review:** `docs/reviews/2026-03-08-code-review.md` section 6.9
**Files:** `tests/`

Added CLI smoke tests, config env var tests, hardlink tests, cache retry tests.
Remaining gaps (scroll indicator widget tests, `_render_plain` extraction) are
tracked as future work.

---

## I43: Stronger templating engine
**Status:** `open`
**Priority:** medium
**Severity:** usability
**Files:** `tapes/templates.py`

Python's `str.format_map()` only supports the format spec mini-language
(padding, alignment, number formatting). Users cannot apply transforms like
lowercase, title case, or slug-style normalization in templates. For example,
`{title.lower()}` does not work - it looks for a field literally named
`title.lower()`.

Need to define a good scope based on actual use cases, not arbitrary
extensibility. Common needs:
- Case conversion (lower, upper, title)
- Whitespace normalization (replace spaces with dots or hyphens)
- Stripping or replacing specific characters

Possible approaches: custom format spec extensions (`{title:lower}`),
a small set of built-in filters, or a lightweight template engine like
Jinja2. Evaluate trade-offs between power and complexity before choosing.

---
