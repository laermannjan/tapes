# Similarity vs Confidence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Split similarity (pairwise match quality) from confidence (auto-accept decision) by replacing WRatio with a blended algorithm, renaming functions, and adding a multi-candidate `should_auto_accept`.

**Architecture:** `_string_similarity` switches from WRatio to `0.7 * ratio + 0.3 * token_set_ratio` for better separation. `compute_confidence` / `compute_episode_confidence` are renamed to `compute_similarity` / `compute_episode_similarity`. A new `should_auto_accept(similarities)` function implements two-tier auto-accept (high similarity OR clear winner). The pipeline calls `should_auto_accept` instead of a simple threshold check.

**Tech Stack:** rapidfuzz (already installed), pytest

**Design doc:** `docs/plans/2026-03-08-similarity-vs-confidence.md`

---

### Task 1: Blended similarity algorithm

Replace WRatio with a weighted blend of `fuzz.ratio` (strict) and `fuzz.token_set_ratio` (lenient). This creates separation between exact matches and subset matches.

**Files:**
- Modify: `tapes/similarity.py:1-51` (constants, imports, `_string_similarity`)
- Modify: `tests/test_similarity.py:14-53` (`TestStringSimilarity`)

**Step 1: Update tests for blended behavior**

In `tests/test_similarity.py`, update `TestStringSimilarity`:
- Relax `test_word_order_irrelevant` from `> 0.9` to `> 0.7` (blend trades some word-order tolerance for separation)
- Add `test_exact_separates_from_subset` to verify the key property (exact match scores significantly higher than subset match)

```python
class TestStringSimilarity:
    def test_exact_match(self) -> None:
        assert _string_similarity("Dune", "Dune") == pytest.approx(1.0)

    def test_case_insensitive(self) -> None:
        assert _string_similarity("dune", "DUNE") == pytest.approx(1.0)

    def test_empty_a(self) -> None:
        assert _string_similarity("", "Dune") == 0.0

    def test_empty_b(self) -> None:
        assert _string_similarity("Dune", "") == 0.0

    def test_both_empty(self) -> None:
        assert _string_similarity("", "") == 0.0

    def test_multi_word_exact(self) -> None:
        assert _string_similarity("Breaking Bad", "Breaking Bad") == pytest.approx(1.0)

    def test_article_difference_scores_high(self) -> None:
        score = _string_similarity("The Dark Knight", "Dark Knight")
        assert score > 0.8

    def test_subset_scores_high(self) -> None:
        score = _string_similarity("Dune", "Dune Part Two")
        assert score > 0.6

    def test_no_overlap_scores_low(self) -> None:
        score = _string_similarity("Dune", "Arrival")
        assert score < 0.5

    def test_word_order_tolerant(self) -> None:
        score = _string_similarity("Batman v Superman", "Superman v Batman")
        assert score > 0.7

    def test_exact_beats_partial(self) -> None:
        exact = _string_similarity("Dune", "Dune")
        partial = _string_similarity("Dune", "Dune Part Two")
        assert exact > partial

    def test_exact_separates_from_subset(self) -> None:
        """Key property: exact match scores much higher than subset match."""
        exact = _string_similarity("Breaking Bad", "Breaking Bad")
        subset = _string_similarity("Breaking Bad", "El Camino A Breaking Bad Movie")
        assert exact - subset > 0.2
```

**Step 2: Run tests to see current state**

Run: `uv run pytest tests/test_similarity.py::TestStringSimilarity -v`
Expected: `test_exact_separates_from_subset` FAILS (WRatio gives both ~1.0)

**Step 3: Implement blended algorithm**

In `tapes/similarity.py`, replace the algorithm constant, map, and `_string_similarity`:

```python
"""Similarity scoring for metadata matching.

Uses rapidfuzz for string similarity. Each field has its own matching
strategy (fuzzy, integer distance, exact) and weight.
"""
from __future__ import annotations

from rapidfuzz import fuzz, utils

from tapes.fields import EPISODE, EPISODE_TITLE, SEASON, TITLE, TMDB_ID, YEAR

# ---------------------------------------------------------------------------
# Configuration -- all tuning parameters in one place
# ---------------------------------------------------------------------------

# Blended similarity: ratio (strict) + token_set_ratio (lenient)
# Higher STRICT_WEIGHT = more separation between exact and partial matches
# Lower STRICT_WEIGHT = more tolerant of word order, articles, extra words
STRICT_WEIGHT = 0.7

# Show/movie scoring weights (must sum to 1.0)
SHOW_TITLE_WEIGHT = 0.7
SHOW_YEAR_WEIGHT = 0.3

# Episode scoring weights (must sum to 1.0)
EPISODE_SEASON_WEIGHT = 0.25
EPISODE_NUMBER_WEIGHT = 0.65
EPISODE_TITLE_WEIGHT = 0.10

# Year tolerance: exact=1.0, off-by-1=0.5, off-by-2+=0.0
YEAR_TOLERANCE = 2


def _string_similarity(a: str, b: str) -> float:
    """Compute string similarity using a blend of strict and lenient algorithms.

    Blend: STRICT_WEIGHT * ratio + (1 - STRICT_WEIGHT) * token_set_ratio

    ratio is strict (character-level, penalizes length differences).
    token_set_ratio is lenient (subset-tolerant, handles articles/word order).
    The blend creates separation where WRatio cannot.
    """
    if not a or not b:
        return 0.0
    strict = fuzz.ratio(a, b, processor=utils.default_process) / 100.0
    lenient = fuzz.token_set_ratio(a, b, processor=utils.default_process) / 100.0
    return STRICT_WEIGHT * strict + (1 - STRICT_WEIGHT) * lenient
```

Remove the `SIMILARITY_ALGORITHM` constant and the `_ALGORITHM_MAP` dict entirely.

**Step 4: Run tests**

Run: `uv run pytest tests/test_similarity.py::TestStringSimilarity -v`
Expected: all PASS

**Step 5: Run full test suite to check for regressions**

Run: `uv run pytest tests/test_similarity.py -v`
Expected: all PASS (the blend should preserve existing compute_confidence test behavior -- see design doc table)

**Step 6: Commit**

```bash
git add tapes/similarity.py tests/test_similarity.py
git commit -m "feat: replace WRatio with blended similarity algorithm

ratio (strict) + token_set_ratio (lenient) weighted by STRICT_WEIGHT.
Creates separation between exact and subset matches (e.g. 'Breaking Bad'
exact=100 vs subset=~65)."
```

---

### Task 2: Rename compute_confidence -> compute_similarity

Pure mechanical rename. No behavior change.

**Files:**
- Modify: `tapes/similarity.py:1,54-91` (module docstring, function name + docstring)
- Modify: `tapes/ui/pipeline.py:20,276` (import + call site)
- Modify: `tests/test_similarity.py:7-10,55-162` (import + test class + all calls)

**Step 1: Rename in similarity.py**

In `tapes/similarity.py`:
- Change `def compute_confidence(` to `def compute_similarity(`
- Update the docstring: "Compute weighted similarity" instead of "confidence"

**Step 2: Rename in pipeline.py**

In `tapes/ui/pipeline.py`:
- Line 20: change import from `compute_confidence` to `compute_similarity`
- Line 276: change call from `compute_confidence(` to `compute_similarity(`

**Step 3: Rename in tests**

In `tests/test_similarity.py`:
- Import: change `compute_confidence` to `compute_similarity`
- Rename class `TestComputeConfidence` to `TestComputeSimilarity`
- Replace all `compute_confidence(` calls with `compute_similarity(`

**Step 4: Run tests**

Run: `uv run pytest tests/test_similarity.py -v`
Expected: all PASS

**Step 5: Run full suite**

Run: `uv run pytest`
Expected: all PASS

**Step 6: Commit**

```bash
git add tapes/similarity.py tapes/ui/pipeline.py tests/test_similarity.py
git commit -m "refactor: rename compute_confidence to compute_similarity"
```

---

### Task 3: Rename compute_episode_confidence -> compute_episode_similarity

Same mechanical rename for the episode function.

**Files:**
- Modify: `tapes/similarity.py:93` (function name)
- Modify: `tapes/ui/pipeline.py:20,361` (import + call site)
- Modify: `tests/test_similarity.py:7-10,164-244` (import + test class + all calls)

**Step 1: Rename in similarity.py**

Change `def compute_episode_confidence(` to `def compute_episode_similarity(`.

**Step 2: Rename in pipeline.py**

- Import: change `compute_episode_confidence` to `compute_episode_similarity`
- Line 361: change call to `compute_episode_similarity(`

**Step 3: Rename in tests**

- Import: change `compute_episode_confidence` to `compute_episode_similarity`
- Rename class `TestComputeEpisodeConfidence` to `TestComputeEpisodeSimilarity`
- Replace all `compute_episode_confidence(` calls with `compute_episode_similarity(`

**Step 4: Run tests**

Run: `uv run pytest tests/test_similarity.py -v`
Expected: all PASS

**Step 5: Run full suite**

Run: `uv run pytest`
Expected: all PASS

**Step 6: Commit**

```bash
git add tapes/similarity.py tapes/ui/pipeline.py tests/test_similarity.py
git commit -m "refactor: rename compute_episode_confidence to compute_episode_similarity"
```

---

### Task 4: Add should_auto_accept function

New two-tier auto-accept decision function. Lives in `similarity.py` (pure function over floats, easily testable).

**Files:**
- Modify: `tapes/similarity.py` (add constants + function)
- Modify: `tests/test_similarity.py` (add test class)

**Step 1: Write tests**

Add to `tests/test_similarity.py`:

```python
from tapes.similarity import (
    _string_similarity,
    compute_similarity,
    compute_episode_similarity,
    should_auto_accept,
)


class TestShouldAutoAccept:
    """Two-tier auto-accept: high similarity OR clear winner."""

    def test_empty_list(self) -> None:
        assert should_auto_accept([]) is False

    def test_high_similarity_single(self) -> None:
        """Tier 1: best >= threshold."""
        assert should_auto_accept([0.95]) is True

    def test_high_similarity_multiple(self) -> None:
        assert should_auto_accept([0.90, 0.85]) is True

    def test_at_threshold_boundary(self) -> None:
        assert should_auto_accept([0.85]) is True

    def test_below_threshold_single_candidate(self) -> None:
        """Single candidate below threshold -- no tier 2 (needs >= 2)."""
        assert should_auto_accept([0.7]) is False

    def test_clear_winner_above_margin_threshold(self) -> None:
        """Tier 2: below threshold but clear separation from second."""
        assert should_auto_accept([0.7, 0.45]) is True  # margin 0.25 >= 0.15

    def test_no_winner_equal_scores(self) -> None:
        """Two equally good candidates -- no clear winner."""
        assert should_auto_accept([0.7, 0.7]) is False  # margin 0

    def test_no_winner_small_margin(self) -> None:
        """Margin too small for tier 2."""
        assert should_auto_accept([0.7, 0.60]) is False  # margin 0.10 < 0.15

    def test_below_margin_threshold(self) -> None:
        """Best below margin threshold -- tier 2 does not apply."""
        assert should_auto_accept([0.5, 0.2]) is False

    def test_three_candidates_clear_winner(self) -> None:
        assert should_auto_accept([0.75, 0.55, 0.30]) is True  # margin 0.20

    def test_three_candidates_no_winner(self) -> None:
        assert should_auto_accept([0.75, 0.70, 0.30]) is False  # margin 0.05

    def test_custom_thresholds(self) -> None:
        assert should_auto_accept(
            [0.6, 0.3],
            threshold=0.9,
            margin_threshold=0.5,
            min_margin=0.2,
        ) is True  # margin 0.3 >= 0.2, best 0.6 >= 0.5

    def test_must_be_sorted_descending(self) -> None:
        """Caller must sort descending. Function trusts the order."""
        # [0.45, 0.7] is mis-sorted; function reads [0]=0.45 as best
        assert should_auto_accept([0.45, 0.7]) is False
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_similarity.py::TestShouldAutoAccept -v`
Expected: FAIL -- `should_auto_accept` does not exist yet

**Step 3: Implement should_auto_accept**

Add to `tapes/similarity.py`, after the existing constants block:

```python
# Two-tier auto-accept thresholds
MARGIN_ACCEPT_THRESHOLD = 0.6   # minimum similarity for tier 2
MIN_ACCEPT_MARGIN = 0.15        # minimum gap between best and second


def should_auto_accept(
    similarities: list[float],
    threshold: float = DEFAULT_AUTO_ACCEPT_THRESHOLD,
    margin_threshold: float = MARGIN_ACCEPT_THRESHOLD,
    min_margin: float = MIN_ACCEPT_MARGIN,
) -> bool:
    """Decide whether to auto-accept the best candidate.

    Two-tier gate:
    - Tier 1: best similarity >= threshold (strong absolute match)
    - Tier 2: best >= margin_threshold AND margin to second >= min_margin
              AND at least 2 candidates (need alternatives to compare against)

    Args:
        similarities: Scores sorted descending. Caller must sort.
        threshold: Tier 1 absolute threshold.
        margin_threshold: Minimum similarity for tier 2 to apply.
        min_margin: Minimum gap between best and second-best for tier 2.
    """
    if not similarities:
        return False
    best = similarities[0]
    if best >= threshold:
        return True
    if len(similarities) >= 2 and best >= margin_threshold:
        margin = best - similarities[1]
        if margin >= min_margin:
            return True
    return False
```

This needs `DEFAULT_AUTO_ACCEPT_THRESHOLD` imported from `tapes.config`. Add the import at the top of `similarity.py`:

```python
from tapes.config import DEFAULT_AUTO_ACCEPT_THRESHOLD
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_similarity.py::TestShouldAutoAccept -v`
Expected: all PASS

**Step 5: Run full similarity tests**

Run: `uv run pytest tests/test_similarity.py -v`
Expected: all PASS

**Step 6: Commit**

```bash
git add tapes/similarity.py tests/test_similarity.py
git commit -m "feat: add should_auto_accept with two-tier gate

Tier 1: similarity >= 0.85 (strong absolute match).
Tier 2: similarity >= 0.6 AND margin to second-best >= 0.15
(clear winner among multiple candidates)."
```

---

### Task 5: Wire should_auto_accept into pipeline

Replace the simple threshold check in `_query_tmdb_for_node` with `should_auto_accept`. Add multi-result mock tests to verify tier 2 behavior.

**Files:**
- Modify: `tapes/ui/pipeline.py:20,276-300` (import + auto-accept logic)
- Modify: `tests/test_ui/test_pipeline.py` (add multi-result tests)

**Step 1: Add multi-result mock and tests**

In `tests/test_ui/test_pipeline.py`, update `_mock_search_multi` to return multiple results for "breaking bad":

```python
def _mock_search_multi(query: str, token: str, year: int | None = None, **kwargs: object) -> list[dict]:
    """Mock search_multi returning known results."""
    q = query.lower()
    if "dune" in q:
        return [{"tmdb_id": 438631, "title": "Dune", "year": 2021, "media_type": "movie"}]
    if "arrival" in q:
        return [{"tmdb_id": 329865, "title": "Arrival", "year": 2016, "media_type": "movie"}]
    if "interstellar" in q:
        return [{"tmdb_id": 157336, "title": "Interstellar", "year": 2014, "media_type": "movie"}]
    if "breaking bad" in q:
        return [
            {"tmdb_id": 1396, "title": "Breaking Bad", "year": 2008, "media_type": "episode"},
            {"tmdb_id": 559969, "title": "El Camino: A Breaking Bad Movie", "year": 2019, "media_type": "movie"},
        ]
    if "the office" in q:
        return [
            {"tmdb_id": 2316, "title": "The Office", "year": 2005, "media_type": "episode"},
            {"tmdb_id": 2996, "title": "The Office", "year": 2001, "media_type": "episode"},
        ]
    return []
```

Add new test class:

```python
class TestTwoTierAutoAccept:
    """Tests for margin-based auto-accept (tier 2)."""

    def test_clear_winner_auto_accepts(self, mock_tmdb) -> None:
        """Breaking Bad with year: tier 1 auto-accept (similarity ~1.0)."""
        model = _make_model("Breaking.Bad.2008.S01E01.mkv")
        run_auto_pipeline(model, token=TOKEN)
        node = model.all_files()[0]
        assert node.staged is True

    def test_clear_winner_no_year_auto_accepts_via_margin(self, mock_tmdb) -> None:
        """Breaking Bad without year: tier 2 auto-accept.

        Best similarity ~0.7 (exact title, no year) vs second ~0.45
        (subset match). Margin ~0.25 >= 0.15, so tier 2 accepts.
        """
        model = _make_model("Breaking.Bad.S01E01.mkv")
        run_auto_pipeline(model, token=TOKEN)
        node = model.all_files()[0]
        assert node.staged is True
        assert node.result["title"] == "Breaking Bad"

    def test_ambiguous_candidates_no_auto_accept(self, mock_tmdb) -> None:
        """The Office without year: two equally-named shows, no clear winner."""
        model = _make_model("The.Office.S01E01.mkv")
        run_auto_pipeline(model, token=TOKEN)
        node = model.all_files()[0]
        assert node.staged is False
        # Both sources available for user curation
        tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
        assert len(tmdb_sources) == 2
```

**Step 2: Run new tests to see failures**

Run: `uv run pytest tests/test_ui/test_pipeline.py::TestTwoTierAutoAccept -v`
Expected: FAIL -- current pipeline uses simple threshold, not should_auto_accept

**Step 3: Update pipeline imports**

In `tapes/ui/pipeline.py` line 20, add `should_auto_accept` to the import:

```python
from tapes.similarity import compute_similarity, compute_episode_similarity, should_auto_accept
```

**Step 4: Update _query_tmdb_for_node auto-accept logic**

In `tapes/ui/pipeline.py`, replace the auto-accept block in `_query_tmdb_for_node` (around lines 283-300):

Current:
```python
    # Find best source
    best = max(tmdb_sources, key=lambda s: s.confidence)

    if best.confidence >= threshold:
        # Auto-accept: apply non-empty fields to result
        for field, val in best.fields.items():
            if val is not None:
                node.result[field] = val
        node.staged = True

        # Stage 2: if TV show, fetch episodes
        if best.fields.get(MEDIA_TYPE) == MEDIA_TYPE_EPISODE:
            _query_episodes(node, token, threshold, best.fields, cache=cache, client=client)
            return

    # Add show-level TMDB sources (not episode sources yet)
    node.sources.extend(tmdb_sources)
```

New:
```python
    # Sort by similarity for should_auto_accept (expects descending order)
    tmdb_sources.sort(key=lambda s: s.confidence, reverse=True)
    similarities = [s.confidence for s in tmdb_sources]
    best = tmdb_sources[0]

    if should_auto_accept(similarities, threshold=threshold):
        # Auto-accept: apply non-empty fields to result
        for field, val in best.fields.items():
            if val is not None:
                node.result[field] = val
        node.staged = True

        # Stage 2: if TV show, fetch episodes
        if best.fields.get(MEDIA_TYPE) == MEDIA_TYPE_EPISODE:
            _query_episodes(node, token, threshold, best.fields, cache=cache, client=client)
            return

    # Add show-level TMDB sources (not episode sources yet)
    node.sources.extend(tmdb_sources)
```

**Step 5: Update existing test that now behaves differently**

The existing `test_title_only_not_auto_staged` test uses "Breaking.Bad.S01E01.720p.mkv". With the updated mock (which now returns 2 results), and with the blended algorithm giving ~0.7 for "Breaking Bad" exact and ~0.45 for "El Camino...", tier 2 will now auto-accept. This is the **intended new behavior**.

Update `test_title_only_not_auto_staged` to reflect the new behavior:

```python
    def test_title_only_clear_winner_auto_staged(self, mock_tmdb) -> None:
        """Without year but clear winner (margin to second), auto-staged via tier 2."""
        model = _make_model("Breaking.Bad.S01E01.720p.mkv")
        run_auto_pipeline(model, token=TOKEN)
        node = model.all_files()[0]
        assert node.staged is True
```

If any existing test still expects the old "not auto-staged" behavior for a single-candidate scenario, verify it uses a query that returns only 1 TMDB result and has similarity below 0.85.

**Step 6: Run all pipeline tests**

Run: `uv run pytest tests/test_ui/test_pipeline.py -v`
Expected: all PASS

**Step 7: Run full test suite**

Run: `uv run pytest`
Expected: all PASS

**Step 8: Commit**

```bash
git add tapes/ui/pipeline.py tests/test_ui/test_pipeline.py
git commit -m "feat: wire should_auto_accept into pipeline

Pipeline now uses two-tier auto-accept instead of simple threshold.
Clear winners (e.g. Breaking Bad vs El Camino) auto-accept even
without year in filename."
```

---

### Task 6: Update docs and design doc status

**Files:**
- Modify: `docs/plans/2026-03-08-similarity-vs-confidence.md:8`

**Step 1: Update status**

Change line 8 from:
```
**Status:** design only. Not yet implemented.
```
to:
```
**Status:** implemented.
```

**Step 2: Commit**

```bash
git add docs/plans/2026-03-08-similarity-vs-confidence.md
git commit -m "docs: mark similarity-vs-confidence design as implemented"
```
