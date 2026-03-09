# Pipeline Mental Model

How tapes identifies files and populates metadata. This is the
authoritative reference for the intended behavior. Audit code against
this, not the other way around.

---

## Overview

Each file goes through: **extract** (guessit) then **search** (TMDB)
then **score** then optionally **auto-accept** then optionally
**auto-stage**. Accept and stage are always separate decisions.

- **Accept** = write a match's fields into the file's result dict.
- **Stage** = mark the file ready to commit (copy/move/link).
- Auto-accept and auto-stage are convenience. The user can always do
  both manually.

---

## Decision Tree

```
FILE ENTERS PIPELINE
│
├─ Extract metadata from filename (guessit)
│   → result = {title, year?, season?, episode?, media_type?, ...}
│   → sources = []
│
├─ Do we have a title?
│   ├─ NO → done (nothing to search)
│   └─ YES
│       │
│       ├─ Do we already have a tmdb_id in result?
│       │   ├─ YES (from previous accept or manual edit)
│       │   │   ├─ media_type == "episode" → EPISODE QUERY
│       │   │   └─ media_type == "movie" → done (fully identified)
│       │   └─ NO → SHOW/MOVIE SEARCH
│       │
│       └─ SHOW/MOVIE SEARCH
│           │ search_multi(title, year?) → up to 3 results
│           │ score each via compute_similarity(result, candidate)
│           │ → Source objects with confidence scores
│           │ → sources ALWAYS added to node.sources
│           │
│           ├─ should_auto_accept(scores)?
│           │   │
│           │   ├─ YES → AUTO-ACCEPT show/movie
│           │   │   │ write best match's non-null fields into result
│           │   │   │ (title, year, tmdb_id, media_type)
│           │   │   │
│           │   │   ├─ media_type == "episode" → EPISODE QUERY
│           │   │   └─ media_type == "movie" → CAN-STAGE CHECK
│           │   │
│           │   └─ NO → done for now
│           │       user sees show-level sources in detail view
│           │       user manually accepts a match
│           │       → writes match fields into result (incl. tmdb_id)
│           │       → CAN-STAGE CHECK
│           │       user presses r to refresh
│           │       → tmdb_id now set → EPISODE QUERY runs
│           │
│           └─ EPISODE QUERY
│               │ requires: tmdb_id of the show (from result)
│               │
│               │ get_show(tmdb_id) → list of season numbers
│               │ for EVERY season:
│               │   get_season_episodes(show_id, season)
│               │   score each episode via compute_episode_similarity
│               │ collect ALL episodes across ALL seasons
│               │ sort by score, keep top 3
│               │ → episode sources ALWAYS added to node.sources
│               │
│               ├─ should_auto_accept(episode_scores)?
│               │   ├─ YES → AUTO-ACCEPT episode
│               │   │   │ write episode fields into result
│               │   │   │ (season, episode, episode_title, etc.)
│               │   │   └─ CAN-STAGE CHECK
│               │   │
│               │   └─ NO → done for now
│               │       user curates episode sources in detail view
│               │       user manually accepts → CAN-STAGE CHECK
│               │
│               └─ CAN-STAGE CHECK
│                   │ can_fill_template(result, template)?
│                   ├─ YES → auto-stage (node.staged = True)
│                   └─ NO → not staged (user fills gaps in detail view)
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

### Episode Similarity (`compute_episode_similarity`)

```
score = 0.25 * season_match + 0.65 * episode_match + 0.10 * title_match
```

- **season_match**: exact integer match = 1.0, else 0.0.
- **episode_match**: exact integer match = 1.0, else 0.0.
- **title_match**: blended string similarity (same as show title).
- Season + episode exact = 0.9, above tier 1 threshold.

### Auto-Accept Gate (`should_auto_accept`)

Two-tier decision:

1. **Tier 1** (strong match): best score >= 0.85 → accept.
2. **Tier 2** (clear winner): best >= 0.6 AND margin to
   second-best >= 0.15 → accept.

If neither tier passes, user must accept manually.

---

## User Interaction (Detail View)

```
USER OPENS DETAIL VIEW (enter on file or folder)
│
├─ sees: result column + source/match tab(s)
├─ tab: cycle sources
├─ shift+tab: toggle focus between result and match columns
├─ e: edit field inline
├─ backspace: clear field
├─ ctrl+r: reset field from filename (guessit)
│
├─ enter (accept):
│   │ if match column focused → apply source fields to result
│   │ if result column focused → keep result as-is
│   │ CAN-STAGE CHECK → auto-stage if template complete
│   └─ return to tree
│
├─ r (refresh):
│   │ re-query TMDB with current result
│   │ if tmdb_id set → EPISODE QUERY
│   │ if no tmdb_id → SHOW/MOVIE SEARCH
│   └─ new sources replace old ones
│
└─ esc (discard):
    └─ restore snapshot, return to tree
```

---

## Key Invariants

1. **Sources are always added.** Every TMDB query populates
   `node.sources`, whether auto-accept fires or not. The user
   must always be able to see what TMDB returned.

2. **Accept and stage are separate.** Auto-accept writes fields.
   Auto-stage checks template completeness. Neither implies the
   other.

3. **Episode query fetches all seasons.** No early stopping. Score
   every episode across every season, keep top 3. Simple, no
   branching.

4. **Episode query requires tmdb_id.** It runs when a show is
   identified (auto-accepted or user-accepted). Without tmdb_id
   there is nothing to query.

5. **Refresh re-enters the tree.** Pressing r re-queries TMDB
   using current result fields. If tmdb_id is set, it takes the
   shortcut to episode query. If not, it does a fresh show/movie
   search.
