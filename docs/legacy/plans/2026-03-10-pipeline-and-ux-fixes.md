# Pipeline Scoring and UX Fixes

Fixes six problems exposed by real-world files (`breaking_bad_720p.mp4`,
`GOT/s1/ep01-05.mkv`): incorrect auto-accept, confusing multi-node
candidate tabs, and invisible missing fields.

---

## A. Pipeline and Scoring

### A1. Media-type conflict penalty in scoring

`compute_similarity()` gains a media-type agreement factor. When
guessit's `media_type` disagrees with a TMDB candidate's `media_type`,
multiply the final score by `MEDIA_TYPE_PENALTY = 0.7`. When they agree
or guessit did not extract a `media_type`, apply no penalty.

The penalty uses values already present in the two dicts passed to
`compute_similarity(query, result)`: `query` contains guessit's
`media_type`, `result` contains the TMDB candidate's. No signature
change needed.

**Effect:** For `breaking_bad_720p.mp4` (guessit: movie), Breaking Bad
(show) drops from ~0.95 to ~0.67. El Camino (movie) keeps its ~0.65.
The scores converge, prominence falls below 0.15, and neither
auto-accepts. The user sees both candidates and picks.

**Where:** `tapes/similarity.py`, `compute_similarity()`. New constant
`MEDIA_TYPE_PENALTY = 0.7` alongside existing tuning parameters.
Multiplicative modifier on the existing `0.7 * title + 0.3 * year`
formula.

### A2. Media-type match gate on auto-accept

Before calling `should_auto_accept()`, check: does the best candidate's
`media_type` match the node's guessit `media_type`? On mismatch, skip
auto-accept entirely. Do not fall through to lower-ranked candidates.
All candidates are still added to `node.candidates` for manual
selection.

If guessit did not extract a `media_type` (value is absent/None), the
gate is skipped and auto-accept proceeds normally.

**Why both A1 and A2?** A1 improves ranking for manual selection
(El Camino appears above Breaking Bad for a movie file). A2 prevents
auto-accept even if A1's penalty is insufficient.

**Where:** `tapes/pipeline.py`, `_query_tmdb_for_node()`, before the
`should_auto_accept()` call.

### A3. Clear candidates after show/movie acceptance

When `tmdb_id` is written to a node's metadata (auto-accept or manual
accept), clear `node.candidates`. The episode query adds episode
candidates afterward. To pick a different show, the user clears
`tmdb_id` with backspace, which triggers a new TMDB query.

**Ordering:** The clear must happen before `_query_episodes` is invoked.
In the auto-accept path, the dispatched metadata-updater closure clears
candidates as part of its update, before the episode query dispatches
its own candidates-updater. In the manual-accept path (metadata view),
candidates are cleared synchronously on accept.

**Where:** Both the pipeline auto-accept path and the metadata view
manual-accept path. After writing `tmdb_id`, call
`node.candidates.clear()`.

---

## B. UX Fixes

### B1. Return to tree after show/movie acceptance in metadata view

When a show or movie is accepted while in the metadata view (auto-accept
via TMDB refresh or manual accept), close the metadata view and return
to the tree. The episode query runs in the background; results appear in
the tree destination preview.

This prevents the confusing state where episode candidates suddenly
appear in a folder-level metadata view.

**Where:** `tapes/ui/tree_app.py`, the accept path in metadata view.

### B2. Hint note in multi-node metadata view for accepted shows

When the user enters the metadata view for a multi-node selection where
`tmdb_id` is set and `media_type` is "episode": show no episode
candidate tabs. Display a hint instead:

- "Select individual files to match episodes"
- "Set season to improve episode matching" (only when season is missing)
- "Clear tmdb_id to select a different show"

This note appears only for already-accepted shows in multi-node mode.
When the show is not yet accepted, normal show-level candidate tabs
appear.

**Detection:** The hint triggers when `is_multi` is True and the shared
metadata has a `tmdb_id` set. This is distinct from "no candidates
found" (where `tmdb_id` is absent). The metadata view checks
`tmdb_id` presence, not candidate list emptiness.

**Where:** `tapes/ui/metadata_view.py` and `tapes/ui/metadata_render.py`,
candidate area rendering in multi-node mode.

### B3. Named missing-field indicators in tree destination preview

Missing mandatory template fields render as red `{field_name?}` in the
tree destination path. Example:

```
Game of Thrones (2011)/Season {season?}/Game of Thrones - S{season?}E01 - ...
```

In the metadata view grid, missing fields continue to show `???`.

**Where:** `tapes/templates.py`, `compute_dest()` -- change the
substitution for missing fields from `"?"` to `{field_name?}`.
Downstream in `tapes/ui/tree_render.py`,
`_append_with_yellow_placeholders` must be updated to recognize the new
`{field_name?}` pattern and style it red (`COLOR_ERROR` or a new
semantic token) instead of yellow.

---

## Documentation updates

Update `docs/pipeline-model.md` to reflect:

- A1: media-type penalty in scoring formula
- A2: media-type match gate before `should_auto_accept()`
- A3: candidates cleared after acceptance (replaces "candidates are
  always added" invariant with "candidates are always added on query;
  cleared on acceptance")

---

## Out of scope

- Caching TMDB queries (future optimization)
- Progress indicators for episode queries
- Season-aware folder workflow with automatic re-matching (keep it
  manual: user sets season, re-enters individual files)
