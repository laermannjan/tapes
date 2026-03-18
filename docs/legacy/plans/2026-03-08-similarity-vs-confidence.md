# Similarity vs Confidence: Scoring Redesign Phase 2

Follow-up to I27. The initial implementation (rapidfuzz, NULL penalty,
tmdb_id override) exposed a deeper problem: "similarity" and
"confidence" are different things, and our algorithm choice (WRatio)
collapses the distinction.

**Status:** implemented.

---

## The distinction

**Similarity** answers: "How well does this candidate match my query?"
Pairwise. Compares one (query, result) pair. Displayed to the user in
the detail view source tabs as a percentage.

**Confidence** answers: "How sure are we this is THE right match?"
Requires both high similarity AND separation from alternatives.
Drives the auto-accept decision.

Today these are the same number. They should not be.

---

## The WRatio problem

WRatio picks the best score from `ratio`, `token_sort_ratio`, and
`token_set_ratio`. For subsets, `token_set_ratio` dominates: it
extracts shared tokens, compares them against themselves, and returns
a perfect score.

TMDB search for "Breaking Bad" returns:

1. "Breaking Bad" -- exact match, WRatio 100
2. "El Camino: A Breaking Bad Movie" -- different entity, but shared
   tokens {"breaking", "bad"} form a perfect subset. WRatio 100.

Both score identically. The margin between the correct match and a
different entity is zero. No downstream logic can recover this lost
signal.

This destroys the confidence calculation. Without meaningful separation
in similarity scores, we cannot distinguish "one clear winner" from
"multiple equally plausible candidates."

---

## Fix: blended similarity algorithm

Replace WRatio with a weighted blend of strict and lenient algorithms:

```
similarity = STRICT_WEIGHT * ratio + (1 - STRICT_WEIGHT) * token_set_ratio
```

`fuzz.ratio` is strict: character-level Levenshtein, penalizes length
differences. `fuzz.token_set_ratio` is lenient: subset-tolerant, handles
articles and word order.

The blend creates separation where WRatio cannot:

| Comparison                                         | ratio | token_set | blend (0.7) |
|----------------------------------------------------|-------|-----------|-------------|
| "Breaking Bad" vs "Breaking Bad"                   |   100 |       100 |         100 |
| "Breaking Bad" vs "El Camino: A Breaking Bad Movie"|   ~50 |       100 |         ~65 |
| "The Dark Knight" vs "Dark Knight"                 |   ~88 |       100 |         ~92 |
| "Dune" vs "Dune Part Two"                          |   ~57 |       100 |         ~70 |
| "Dune" vs "Arrival"                                |   ~30 |       ~40 |         ~33 |

"Breaking Bad" (exact) now scores 100 vs 65 for the subset match.
That 35-point margin is a usable signal.

### The STRICT_WEIGHT constant

`STRICT_WEIGHT` controls the balance between separation and tolerance.

- **Higher (toward 1.0):** more separation between exact and partial
  matches. Handles subsets and different-length titles well. Risk:
  legitimate minor variations (articles, punctuation) score lower.
- **Lower (toward 0.0):** more tolerant of word order, articles, extra
  words. Risk: subsets score nearly as high as exact matches, reducing
  separation.
- **0.7 is the starting point.** Gives strong separation (~35 points
  between exact and subset) while keeping article tolerance high (~92
  for "The Dark Knight" vs "Dark Knight").

Validate against real TMDB results before finalizing. The right value
is whichever creates enough margin for the confidence function to
distinguish clear winners from ambiguous matches.

---

## Confidence: multi-candidate auto-accept

The auto-accept decision moves from a single threshold check to a
two-tier gate. The similarity score (displayed to user) stays unchanged.
Only the pipeline's accept logic changes.

### Tier 1: high similarity

```
best_similarity >= AUTO_ACCEPT_THRESHOLD (0.85)
```

Strong absolute match. Year present and correct, or very high title
similarity. No further check needed.

### Tier 2: clear winner

```
best_similarity >= MARGIN_ACCEPT_THRESHOLD
AND (best_similarity - second_best) >= MIN_ACCEPT_MARGIN
AND len(candidates) >= 2
```

The similarity alone is below auto-accept, but the best candidate is
clearly better than all alternatives. Requires multiple candidates to
compare against -- a single weak match has no competitors to beat.

### Scenarios

| Scenario                       | Best | 2nd  | Tier 1? | Tier 2?             | Result      |
|--------------------------------|------|------|---------|---------------------|-------------|
| "Dune" + year 2021             | 1.0  | 0.7  | yes     | --                  | auto-accept |
| "Dune" no year                 | 0.7  | 0.7  | no      | margin 0            | user picks  |
| "Breaking Bad" no year         | 0.7  | ~0.45| no      | margin ~0.25, yes   | auto-accept |
| "The Office" no year           | 0.7  | 0.7  | no      | margin 0            | user picks  |
| Wrong query, one weak match    | 0.4  | --   | no      | below threshold     | user picks  |
| Wrong query, one decent match  | 0.6  | --   | no      | only 1 candidate    | user picks  |

### New constants

```python
# Blended similarity
STRICT_WEIGHT = 0.7  # see "The STRICT_WEIGHT constant" above

# Two-tier auto-accept
MARGIN_ACCEPT_THRESHOLD = 0.6   # minimum similarity for tier 2
MIN_ACCEPT_MARGIN = 0.15        # minimum gap between best and second
```

---

## Architecture

`compute_confidence` is renamed to `compute_similarity`. It stays
pairwise. Returns a similarity score for one (query, result) pair.

A new function in the pipeline handles the auto-accept decision:

```python
def should_auto_accept(
    similarities: list[float],
    threshold: float = AUTO_ACCEPT_THRESHOLD,
    margin_threshold: float = MARGIN_ACCEPT_THRESHOLD,
    min_margin: float = MIN_ACCEPT_MARGIN,
) -> bool:
    if not similarities:
        return False
    best = similarities[0]  # sorted descending
    if best >= threshold:
        return True
    if len(similarities) >= 2 and best >= margin_threshold:
        margin = best - similarities[1]
        if margin >= min_margin:
            return True
    return False
```

The displayed confidence in the detail view source tabs remains the
pairwise similarity score. The user sees honest match quality. The
auto-accept decision uses the richer multi-candidate signal internally.

---

## Implementation notes

- Validate STRICT_WEIGHT and margin thresholds against real TMDB
  results for a representative set of filenames (the test_media
  directory is a good start).
- The `_string_similarity` function changes from `WRatio` to the blend.
  The `SIMILARITY_ALGORITHM` constant is replaced by `STRICT_WEIGHT`.
- `compute_confidence` renamed to `compute_similarity` throughout.
  `compute_episode_confidence` renamed to `compute_episode_similarity`.
- `should_auto_accept` lives in the pipeline, not in similarity.py,
  because it needs all candidates -- a pipeline concern.
- Episode scoring is unaffected. Episode titles are short and rarely
  subsets of each other. WRatio or the blend both work fine, but the
  blend is simpler to use everywhere.
