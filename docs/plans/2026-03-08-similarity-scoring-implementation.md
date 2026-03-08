# I27: Similarity Scoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace Jaccard similarity with rapidfuzz, add tmdb_id override, penalize missing fields.

**Architecture:** Rewrite `tapes/similarity.py` with named constants, a rapidfuzz-backed `_string_similarity` helper, and updated `compute_confidence` / `compute_episode_confidence`. Public API signatures unchanged. Tests rewritten to match new behavior.

**Tech Stack:** rapidfuzz (new dependency), pytest

**Design doc:** `docs/plans/2026-03-08-similarity-scoring-design.md`

---

### Task 1: Add rapidfuzz dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add rapidfuzz to dependencies**

In `pyproject.toml`, add `"rapidfuzz>=3,<4"` to the `dependencies` list:

```toml
dependencies = [
    "typer>=0.15,<1",
    "rich>=14,<15",
    "guessit>=3.8,<4",
    "pydantic>=2.6,<3",
    "pyyaml>=6,<7",
    "textual>=8,<9",
    "httpx>=0.27,<1",
    "rapidfuzz>=3,<4",
]
```

**Step 2: Install**

Run: `uv sync`
Expected: rapidfuzz installed successfully

**Step 3: Verify import**

Run: `uv run python -c "from rapidfuzz import fuzz; print(fuzz.WRatio('Dune', 'Dune'))"`
Expected: `100.0`

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add rapidfuzz for similarity scoring (I27)"
```

---

### Task 2: _string_similarity helper

Replace `title_similarity` (Jaccard) with `_string_similarity` (rapidfuzz).

**Files:**
- Modify: `tapes/similarity.py`
- Modify: `tests/test_similarity.py`

**Step 1: Write tests for _string_similarity**

Replace `TestTitleSimilarity` in `tests/test_similarity.py`. Remove the
import of `title_similarity`, add import of `_string_similarity`:

```python
from tapes.similarity import (
    _string_similarity,
    compute_confidence,
    compute_episode_confidence,
)


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
        # "The Dark Knight" vs "Dark Knight" -- article shouldn't tank score
        score = _string_similarity("The Dark Knight", "Dark Knight")
        assert score > 0.8

    def test_subset_scores_high(self) -> None:
        # "Dune" vs "Dune: Part Two" -- subset should score well
        score = _string_similarity("Dune", "Dune Part Two")
        assert score > 0.6

    def test_no_overlap_scores_low(self) -> None:
        score = _string_similarity("Dune", "Arrival")
        assert score < 0.5

    def test_word_order_irrelevant(self) -> None:
        score = _string_similarity("Batman v Superman", "Superman v Batman")
        assert score > 0.9

    def test_exact_beats_partial(self) -> None:
        exact = _string_similarity("Dune", "Dune")
        partial = _string_similarity("Dune", "Dune Part Two")
        assert exact > partial
```

**Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_similarity.py::TestStringSimilarity -v`
Expected: FAIL -- `_string_similarity` does not exist yet

**Step 3: Implement _string_similarity**

At the top of `tapes/similarity.py`, replace the module docstring and add
the constants, imports, algorithm map, and `_string_similarity`. Remove
`title_similarity`. Update both `compute_confidence` and
`compute_episode_confidence` to call `_string_similarity` instead of
`title_similarity`:

```python
"""Weighted confidence scoring for metadata matching.

Uses rapidfuzz for string similarity. Each field has its own matching
strategy (fuzzy, integer distance, exact) and weight.
"""
from __future__ import annotations

from rapidfuzz import fuzz

from tapes.fields import EPISODE, EPISODE_TITLE, SEASON, TITLE, TMDB_ID, YEAR

# ---------------------------------------------------------------------------
# Configuration -- all tuning parameters in one place
# ---------------------------------------------------------------------------

# Algorithm: "ratio", "token_sort_ratio", "token_set_ratio", "WRatio"
SIMILARITY_ALGORITHM = "WRatio"

# Show/movie scoring weights (must sum to 1.0)
SHOW_TITLE_WEIGHT = 0.7
SHOW_YEAR_WEIGHT = 0.3

# Episode scoring weights (must sum to 1.0)
EPISODE_SEASON_WEIGHT = 0.25
EPISODE_NUMBER_WEIGHT = 0.65
EPISODE_TITLE_WEIGHT = 0.10

# Year tolerance: exact=1.0, off-by-1=0.5, off-by-2+=0.0
YEAR_TOLERANCE = 2

# ---------------------------------------------------------------------------
# Algorithm map
# ---------------------------------------------------------------------------

_ALGORITHM_MAP = {
    "ratio": fuzz.ratio,
    "token_sort_ratio": fuzz.token_sort_ratio,
    "token_set_ratio": fuzz.token_set_ratio,
    "WRatio": fuzz.WRatio,
}


def _string_similarity(a: str, b: str) -> float:
    """Compute string similarity using rapidfuzz (0.0-1.0).

    Algorithm is controlled by SIMILARITY_ALGORITHM constant.
    """
    if not a or not b:
        return 0.0
    fn = _ALGORITHM_MAP[SIMILARITY_ALGORITHM]
    return fn(a, b) / 100.0
```

In the same file, update the two existing `title_similarity(...)` call
sites in `compute_confidence` and `compute_episode_confidence` to call
`_string_similarity(...)` instead. Do not change the logic yet -- that
happens in tasks 3 and 4.

**Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_similarity.py::TestStringSimilarity -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add tapes/similarity.py tests/test_similarity.py
git commit -m "refactor: replace Jaccard with rapidfuzz _string_similarity (I27)"
```

---

### Task 3: compute_confidence rewrite

Add tmdb_id override, NULL-penalize missing year, use named weight
constants.

**Files:**
- Modify: `tapes/similarity.py`
- Modify: `tests/test_similarity.py`

**Step 1: Rewrite TestComputeConfidence tests**

Replace `TestComputeConfidence` in `tests/test_similarity.py`:

```python
class TestComputeConfidence:
    def test_exact_title_and_year(self) -> None:
        score = compute_confidence(
            {"title": "Dune", "year": 2021},
            {"title": "Dune", "year": 2021},
        )
        assert score == pytest.approx(1.0)

    def test_title_match_year_off_by_one(self) -> None:
        score = compute_confidence(
            {"title": "Dune", "year": 2021},
            {"title": "Dune", "year": 2020},
        )
        # 0.7 * 1.0 + 0.3 * 0.5 = 0.85
        assert score == pytest.approx(0.85)

    def test_title_match_year_mismatch(self) -> None:
        score = compute_confidence(
            {"title": "Dune", "year": 2021},
            {"title": "Dune", "year": 1984},
        )
        # 0.7 * 1.0 + 0.3 * 0.0 = 0.7
        assert score == pytest.approx(0.7)

    def test_no_year_in_query_penalized(self) -> None:
        score = compute_confidence(
            {"title": "Dune"},
            {"title": "Dune", "year": 2021},
        )
        # NULL year scores 0.0: 0.7 * 1.0 + 0.3 * 0.0 = 0.7
        assert score == pytest.approx(0.7)

    def test_no_year_in_result_penalized(self) -> None:
        score = compute_confidence(
            {"title": "Dune", "year": 2021},
            {"title": "Dune"},
        )
        assert score == pytest.approx(0.7)

    def test_no_year_below_auto_accept(self) -> None:
        """Missing year must keep score below auto-accept threshold."""
        score = compute_confidence(
            {"title": "Dune"},
            {"title": "Dune"},
        )
        assert score < DEFAULT_AUTO_ACCEPT_THRESHOLD

    def test_no_title_in_query(self) -> None:
        assert compute_confidence({"year": 2021}, {"title": "Dune", "year": 2021}) == 0.0

    def test_no_title_in_result(self) -> None:
        assert compute_confidence({"title": "Dune", "year": 2021}, {"year": 2021}) == 0.0

    def test_both_empty_dicts(self) -> None:
        assert compute_confidence({}, {}) == 0.0

    def test_none_title_in_query(self) -> None:
        assert compute_confidence({"title": None}, {"title": "Dune"}) == 0.0

    def test_none_title_in_result(self) -> None:
        assert compute_confidence({"title": "Dune"}, {"title": None}) == 0.0

    def test_article_difference_with_year(self) -> None:
        score = compute_confidence(
            {"title": "Dark Knight", "year": 2008},
            {"title": "The Dark Knight", "year": 2008},
        )
        # rapidfuzz handles articles well; score should auto-accept
        assert score > DEFAULT_AUTO_ACCEPT_THRESHOLD

    def test_no_overlap_title_same_year(self) -> None:
        score = compute_confidence(
            {"title": "Dune", "year": 2021},
            {"title": "Arrival", "year": 2021},
        )
        # Low title similarity + year match
        assert score < 0.7

    def test_tmdb_id_match_overrides(self) -> None:
        score = compute_confidence(
            {"title": "Wrong", "year": 1900, "tmdb_id": 12345},
            {"title": "Different", "year": 2024, "tmdb_id": 12345},
        )
        assert score == 1.0

    def test_tmdb_id_mismatch_scores_normally(self) -> None:
        score = compute_confidence(
            {"title": "Dune", "year": 2021, "tmdb_id": 111},
            {"title": "Dune", "year": 2021, "tmdb_id": 222},
        )
        # Different IDs, fall through to normal scoring
        assert score == pytest.approx(1.0)

    def test_tmdb_id_only_in_query_no_override(self) -> None:
        score = compute_confidence(
            {"title": "Dune", "year": 2021, "tmdb_id": 12345},
            {"title": "Dune", "year": 2021},
        )
        # tmdb_id absent from result, score normally
        assert score == pytest.approx(1.0)

    def test_tmdb_id_only_in_result_no_override(self) -> None:
        score = compute_confidence(
            {"title": "Dune", "year": 2021},
            {"title": "Dune", "year": 2021, "tmdb_id": 12345},
        )
        assert score == pytest.approx(1.0)
```

**Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_similarity.py::TestComputeConfidence -v`
Expected: FAIL on `test_no_year_in_query_penalized`,
`test_no_year_in_result_penalized`, `test_no_year_below_auto_accept`,
`test_tmdb_id_match_overrides` (old implementation redistributes NULL
year weight and has no tmdb_id handling)

**Step 3: Rewrite compute_confidence**

Replace `compute_confidence` in `tapes/similarity.py`:

```python
def compute_confidence(query: dict, result: dict) -> float:
    """Compute weighted confidence between query and result metadata.

    Fields:
    - tmdb_id: exact match overrides to 1.0
    - title: rapidfuzz string similarity (weight SHOW_TITLE_WEIGHT)
    - year: integer distance (weight SHOW_YEAR_WEIGHT)

    Missing fields score 0.0 (penalized, not redistributed).
    Returns 0.0-1.0.
    """
    # tmdb_id override: definitive identification
    q_id = query.get(TMDB_ID)
    r_id = result.get(TMDB_ID)
    if q_id is not None and r_id is not None and q_id == r_id:
        return 1.0

    # Title is required -- without it, no basis for comparison
    q_title = query.get(TITLE)
    r_title = result.get(TITLE)
    if not q_title or not r_title:
        return 0.0

    title_score = _string_similarity(str(q_title), str(r_title))

    # Year scoring -- missing year scores 0.0 (penalized)
    year_score = 0.0
    q_year = query.get(YEAR)
    r_year = result.get(YEAR)
    if q_year is not None and r_year is not None:
        try:
            diff = abs(int(q_year) - int(r_year))
            year_score = max(0.0, 1.0 - diff / YEAR_TOLERANCE)
        except (ValueError, TypeError):
            pass

    return SHOW_TITLE_WEIGHT * title_score + SHOW_YEAR_WEIGHT * year_score
```

**Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_similarity.py::TestComputeConfidence -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add tapes/similarity.py tests/test_similarity.py
git commit -m "feat: rewrite compute_confidence with rapidfuzz, tmdb_id override, NULL penalize (I27)"
```

---

### Task 4: compute_episode_confidence update

Switch to named constants and rapidfuzz for episode_title. The integer
matching logic is unchanged.

**Files:**
- Modify: `tapes/similarity.py`
- Modify: `tests/test_similarity.py`

**Step 1: Update TestComputeEpisodeConfidence tests**

Most tests are unchanged. Update `test_episode_title_partial` and add
a behavioral test:

```python
class TestComputeEpisodeConfidence:
    def test_exact_episode_and_season(self) -> None:
        score = compute_episode_confidence(
            {"season": 1, "episode": 1},
            {"season": 1, "episode": 1},
        )
        assert score == pytest.approx(0.9)

    def test_episode_match_only(self) -> None:
        score = compute_episode_confidence(
            {"episode": 3},
            {"season": 1, "episode": 3},
        )
        assert score == pytest.approx(0.65)

    def test_season_match_only(self) -> None:
        score = compute_episode_confidence(
            {"season": 2},
            {"season": 2, "episode": 5},
        )
        assert score == pytest.approx(0.25)

    def test_no_match(self) -> None:
        score = compute_episode_confidence(
            {"season": 1, "episode": 1},
            {"season": 2, "episode": 5},
        )
        assert score == pytest.approx(0.0)

    def test_episode_title_exact(self) -> None:
        score = compute_episode_confidence(
            {"season": 1, "episode": 1, "episode_title": "Pilot"},
            {"season": 1, "episode": 1, "episode_title": "Pilot"},
        )
        assert score == pytest.approx(1.0)

    def test_episode_title_partial(self) -> None:
        score = compute_episode_confidence(
            {"season": 1, "episode": 1, "episode_title": "The Pilot Episode"},
            {"season": 1, "episode": 1, "episode_title": "Pilot"},
        )
        # Season (0.25) + episode (0.65) + title_weight * WRatio > 0.95
        assert score > 0.95
        assert score <= 1.0

    def test_empty_query(self) -> None:
        assert compute_episode_confidence({}, {"season": 1, "episode": 1}) == pytest.approx(0.0)

    def test_wrong_episode_right_season(self) -> None:
        score = compute_episode_confidence(
            {"season": 1, "episode": 1},
            {"season": 1, "episode": 5},
        )
        assert score == pytest.approx(0.25)

    def test_capped_at_1(self) -> None:
        score = compute_episode_confidence(
            {"season": 1, "episode": 1, "episode_title": "Pilot"},
            {"season": 1, "episode": 1, "episode_title": "Pilot"},
        )
        assert score <= 1.0

    def test_missing_season_in_query(self) -> None:
        """No season in query -- still matches on episode."""
        score = compute_episode_confidence(
            {"episode": 5},
            {"season": 2, "episode": 5},
        )
        assert score == pytest.approx(0.65)

    def test_no_episode_title_no_penalty_beyond_weight(self) -> None:
        """Missing episode_title contributes 0.0 (weight 0.10)."""
        with_title = compute_episode_confidence(
            {"season": 1, "episode": 1, "episode_title": "Pilot"},
            {"season": 1, "episode": 1, "episode_title": "Pilot"},
        )
        without_title = compute_episode_confidence(
            {"season": 1, "episode": 1},
            {"season": 1, "episode": 1},
        )
        assert with_title - without_title == pytest.approx(0.10)
```

**Step 2: Run tests, verify failures**

Run: `uv run pytest tests/test_similarity.py::TestComputeEpisodeConfidence -v`
Expected: `test_episode_title_partial` may fail (different score from
Jaccard). Others should pass since integer logic is unchanged.

**Step 3: Rewrite compute_episode_confidence**

Replace `compute_episode_confidence` in `tapes/similarity.py`:

```python
def compute_episode_confidence(query: dict, episode: dict) -> float:
    """Score an episode match against a query.

    Fields:
    - season: exact integer match (weight EPISODE_SEASON_WEIGHT)
    - episode: exact integer match (weight EPISODE_NUMBER_WEIGHT)
    - episode_title: rapidfuzz similarity (weight EPISODE_TITLE_WEIGHT)

    Missing fields score 0.0 (penalized).
    Season + episode match = 0.9, above the 0.85 auto-accept threshold.
    Returns 0.0-1.0.
    """
    score = 0.0

    # Season number (exact match)
    q_season = query.get(SEASON)
    e_season = episode.get(SEASON)
    if q_season is not None and e_season is not None:
        try:
            if int(q_season) == int(e_season):
                score += EPISODE_SEASON_WEIGHT
        except (ValueError, TypeError):
            pass

    # Episode number (exact match, most important)
    q_ep = query.get(EPISODE)
    e_ep = episode.get(EPISODE)
    if q_ep is not None and e_ep is not None:
        try:
            if int(q_ep) == int(e_ep):
                score += EPISODE_NUMBER_WEIGHT
        except (ValueError, TypeError):
            pass

    # Episode title (fuzzy match)
    q_title = query.get(EPISODE_TITLE, "")
    e_title = episode.get(EPISODE_TITLE, "")
    if q_title and e_title:
        score += EPISODE_TITLE_WEIGHT * _string_similarity(str(q_title), str(e_title))

    return min(score, 1.0)
```

**Step 4: Run all similarity tests**

Run: `uv run pytest tests/test_similarity.py -v`
Expected: all PASS

**Step 5: Run full test suite**

Run: `uv run pytest`
Expected: all 452+ tests PASS (no callers changed, API is the same)

**Step 6: Commit**

```bash
git add tapes/similarity.py tests/test_similarity.py
git commit -m "feat: update episode scoring with rapidfuzz and named constants (I27)"
```
