# Pipeline Mental Model

How tapes identifies files and populates metadata. This is the
authoritative reference for the intended behavior. Audit code against
this, not the other way around.

See `docs/vocabulary.md` for canonical terminology.

---

## Overview

Each file goes through: **extract** (guessit) then **search** (TMDB)
then **score** then optionally **auto-accept** then optionally
**auto-stage**. Accept and stage are always separate decisions.

- **Accept** = write a candidate's metadata into the file's metadata dict.
- **Stage** = mark the file ready to commit (copy/move/link).
- Auto-accept and auto-stage are convenience. The user can always do
  both manually.

---

## Decision Tree

```
FILE ENTERS PIPELINE
|
|- Extract metadata from filename (guessit)
|   -> node.metadata = {title, year?, season?, episode?, media_type?, ...}
|   -> node.candidates = []
|
|- Do we have a title?
|   |- NO -> done (nothing to search)
|   +- YES
|       |
|       |- Do we already have a tmdb_id in metadata?
|       |   |- YES (from previous accept or manual edit)
|       |   |   |- media_type == "episode" -> EPISODE QUERY
|       |   |   +- media_type == "movie" -> done (fully identified)
|       |   +- NO -> SHOW/MOVIE SEARCH
|       |
|       +- SHOW/MOVIE SEARCH
|           | search_multi(title, year?) -> up to 3 results
|           | score each via compute_similarity(metadata, tmdb_result)
|           | -> Candidate objects with scores
|           | -> candidates ALWAYS added to node.candidates
|           |
|           |- should_auto_accept(scores)?
|           |   |
|           |   |- YES -> AUTO-ACCEPT show/movie
|           |   |   | write best candidate's non-null metadata into node.metadata
|           |   |   | (title, year, tmdb_id, media_type)
|           |   |   |
|           |   |   |- media_type == "episode" -> EPISODE QUERY
|           |   |   +- media_type == "movie" -> CAN-STAGE CHECK
|           |   |
|           |   +- NO -> done for now
|           |       user sees show-level candidates in metadata view
|           |       user manually accepts a candidate
|           |       -> writes candidate metadata into node.metadata (incl. tmdb_id)
|           |       -> CAN-STAGE CHECK
|           |       user presses r to refresh
|           |       -> tmdb_id now set -> EPISODE QUERY runs
|           |
|           +- EPISODE QUERY
|               | requires: tmdb_id of the show (from node.metadata)
|               |
|               | get_show(tmdb_id) -> list of season numbers
|               | for EVERY season:
|               |   get_season_episodes(show_id, season)
|               |   score each episode via compute_episode_similarity
|               | collect ALL episodes across ALL seasons
|               | sort by score, keep top 3
|               | -> episode candidates ALWAYS added to node.candidates
|               |
|               |- should_auto_accept(episode_scores)?
|               |   |- YES -> AUTO-ACCEPT episode
|               |   |   | write episode metadata into node.metadata
|               |   |   | (season, episode, episode_title, etc.)
|               |   |   +- CAN-STAGE CHECK
|               |   |
|               |   +- NO -> done for now
|               |       user curates episode candidates in metadata view
|               |       user manually accepts -> CAN-STAGE CHECK
|               |
|               +- CAN-STAGE CHECK
|                   | can_fill_template(metadata, template)?
|                   |- YES -> auto-stage (node.staged = True)
|                   +- NO -> not staged (user fills gaps in metadata view)
```

---

## Scoring

### Show/Movie Similarity (`compute_similarity`)

```
score = 0.7 * title_score + 0.3 * year_score
```

- **title_score**: blended `0.7 * ratio + 0.3 * token_set_ratio`
  (via rapidfuzz). Compared against both `title` and
  `original_title`; takes max.
- **year_score**: exact = 1.0, off-by-1 = 0.5, else 0.0.
  Missing year = 0.0 (penalized).
- If `tmdb_id` matches exactly: override title_score to 1.0.
- **media_type penalty**: if the query's `media_type` and the result's
  `media_type` disagree, the score is multiplied by `MEDIA_TYPE_PENALTY`
  (0.7). When they agree or either is absent, no penalty is applied.

### Episode Similarity (`compute_episode_similarity`)

```
score = 0.25 * season_match + 0.65 * episode_match + 0.10 * title_match
```

- **season_match**: exact integer match = 1.0, else 0.0.
- **episode_match**: exact integer match = 1.0, else 0.0.
- **title_match**: blended string similarity (same as show title).
- Season + episode exact = 0.9, above auto-accept threshold.

### Auto-Accept Gate (`should_auto_accept`)

Before evaluating score thresholds, the pipeline checks that the best
candidate's `media_type` matches the node's guessit `media_type`. If
they disagree, auto-accept is skipped entirely. If guessit did not
extract a `media_type`, the gate is skipped.

When the media-type gate passes, two score conditions are evaluated:

- **min_score**: best candidate's score must be >= `min_score`
  (default 0.6).
- **min_prominence**: gap between best and second-best scores must
  be >= `min_prominence` (default 0.15). A single candidate has
  infinite prominence and always passes this check.

All conditions must be met. If not, user must accept manually.

---

## User Interaction (MetadataView)

```
USER OPENS METADATA VIEW (enter on file or folder)
|
|- sees: metadata column + candidate/match tab(s)
|- tab: cycle candidates
|- shift+tab: toggle focus between metadata and candidate columns
|- e: edit field inline
|- backspace: clear field
|- ctrl+r: reset field from filename (guessit)
|
|- enter (accept):
|   | if candidate column focused -> apply candidate metadata to node.metadata
|   | if metadata column focused -> keep metadata as-is
|   | CAN-STAGE CHECK -> auto-stage if template complete
|   +- return to tree
|
|- r (refresh):
|   | re-query TMDB with current metadata
|   | if tmdb_id set -> EPISODE QUERY
|   | if no tmdb_id -> SHOW/MOVIE SEARCH
|   +- new candidates replace old ones
|
+- esc (discard):
    +- restore snapshot, return to tree
```

---

## Key Invariants

1. **Candidates are always added; cleared on acceptance.** Every TMDB
   query populates `node.candidates`, whether auto-accept fires or not.
   The user must always be able to see what TMDB returned. On acceptance
   (auto or manual), prior candidates are cleared. Episode candidates are
   added afterward by the subsequent episode query.

2. **Accept and stage are separate.** Auto-accept writes metadata.
   Auto-stage checks template completeness. Neither implies the
   other.

3. **Episode query fetches all seasons.** No early stopping. Score
   every episode across every season, keep top 3. Simple, no
   branching.

4. **Episode query requires tmdb_id.** It runs when a show is
   identified (auto-accepted or user-accepted). Without tmdb_id
   there is nothing to query.

5. **Refresh re-enters the tree.** Pressing r re-queries TMDB
   using current metadata fields. If tmdb_id is set, it takes the
   shortcut to episode query. If not, it does a fresh show/movie
   search.
