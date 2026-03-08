"""Similarity scoring for metadata matching.

Uses rapidfuzz for string similarity. Each field has its own matching
strategy (fuzzy, integer distance, exact) and weight.
"""
from __future__ import annotations

from rapidfuzz import fuzz, utils

from tapes.config import DEFAULT_AUTO_ACCEPT_THRESHOLD
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

# Two-tier auto-accept thresholds
MARGIN_ACCEPT_THRESHOLD = 0.6   # minimum similarity for tier 2
MIN_ACCEPT_MARGIN = 0.15        # minimum gap between best and second


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


def compute_similarity(query: dict, result: dict) -> float:
    """Compute weighted similarity between query and result metadata.

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


def compute_episode_similarity(query: dict, episode: dict) -> float:
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
