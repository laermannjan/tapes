# I27: Similarity Scoring Redesign

Replaces hand-rolled Jaccard with rapidfuzz. Adds per-field matching
strategies, proper NULL handling, and tunable weights.

---

## Problem

The current `title_similarity` uses Jaccard (token set intersection/union).
This fails on common media-title patterns:

- "The Dark Knight" vs "Dark Knight" = 0.67 (article penalty)
- "Dune" vs "Dune: Part Two" = 0.33 (subset penalty)
- No tolerance for spelling variation or transliteration

Every false negative costs the user manual curation time.

## Design

### Two scoring contexts (unchanged)

Scoring serves two separate user decisions:

1. **Show/movie identification** -- "Which movie or show is this?"
   Compares guessit output against TMDB search results. Fields: title, year.
   Either auto-accepted (>= 0.85) or user picks from candidates.

2. **Episode identification** -- "Which episode of this show?"
   Runs after the show is locked (by auto-accept or user selection).
   Fields: season, episode, episode_title.

These are sequential. The show must be decided before episode scoring
begins. The scores are never combined.

### Per-field matching strategies

| Field | Strategy | Details |
|-------|----------|---------|
| title, episode_title | rapidfuzz `WRatio` | Adaptive fuzzy match (0--100, normalized to 0--1) |
| year | Integer distance | exact = 1.0, off-by-1 = 0.5, off-by-2+ = 0.0 |
| season, episode | Exact integer match | 1.0 or 0.0 |
| tmdb_id | Exact match override | Both present and equal: context score = 1.0 |

**Why `WRatio`:** It blends character-level, token-sort, and token-set
strategies internally, choosing the best per comparison. Handles word
order, articles, and subset/superset patterns without configuration.
The algorithm choice is exposed as a named constant for future tuning.

### Weights

| Context | title | year | season | episode | episode_title |
|---------|-------|------|--------|---------|---------------|
| Show/movie | 0.7 | 0.3 | -- | -- | -- |
| Episode | -- | -- | 0.25 | 0.65 | 0.10 |

All weights are named constants at the top of `similarity.py`.

### NULL handling: penalize

A missing field (absent from query or result) scores 0.0. Its weight
stays in the denominator. Fewer matched fields produce a lower maximum
score.

Rationale: three TMDB entries named "Dune" exist. Without a year, we
cannot distinguish them. A title-only match should not auto-accept.
With these weights, a perfect title match without year scores 0.7 --
below the 0.85 threshold. The user picks manually.

**Fallback note:** If penalizing proves too harsh for sparse filenames,
consider a coverage discount: `score * (coverage + (1 - coverage) * k)`
where `coverage = sum(active_weights) / sum(all_weights)`. This softens
the penalty without eliminating it.

### tmdb_id override

When `tmdb_id` is present in both query and result and they match:

- **Movie:** confidence = 1.0. Match is definitive.
- **TV show:** show identity is locked, skip show-level scoring.
  Episode scoring still runs to find the right episode.

This matters when the user manually sets `tmdb_id` in the detail view
and refreshes TMDB.

### Threshold

Stays at 0.85 (`DEFAULT_AUTO_ACCEPT_THRESHOLD` in `config.py`).

Sanity checks with the new scoring:

| Scenario | Score | Auto-accept? |
|----------|-------|-------------|
| Title exact + year exact | 1.0 | yes |
| Title exact + year off-by-1 | 0.85 | yes (boundary) |
| Title exact + no year | 0.7 | no |
| Title 90% + year exact | 0.93 | yes |
| Season + episode exact, no ep title | 0.90 | yes |
| Episode only, no season | 0.65 | no |

### Configuration constants

All tuning parameters live as named constants at the top of
`similarity.py`, grouped and documented. Easy to find, easy to tweak,
easy to pull into `config.py` when I29 (config overhaul) lands.

```python
SIMILARITY_ALGORITHM = "WRatio"

SHOW_TITLE_WEIGHT = 0.7
SHOW_YEAR_WEIGHT = 0.3

EPISODE_SEASON_WEIGHT = 0.25
EPISODE_NUMBER_WEIGHT = 0.65
EPISODE_TITLE_WEIGHT = 0.10

YEAR_TOLERANCE = 2
```

### Public API

Signatures unchanged. Callers do not change.

```python
def compute_confidence(query: dict, result: dict) -> float: ...
def compute_episode_confidence(query: dict, episode: dict) -> float: ...
```

`title_similarity` becomes an internal helper or is replaced entirely
by a `_string_similarity` function wrapping rapidfuzz.

### Dependency

Add `rapidfuzz` to `pyproject.toml`.
