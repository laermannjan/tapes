"""Weighted confidence scoring for metadata matching.

Uses rapidfuzz for string similarity. Each field has its own matching
strategy (fuzzy, integer distance, exact) and weight.
"""
from __future__ import annotations

from rapidfuzz import fuzz, utils

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
    return fn(a, b, processor=utils.default_process) / 100.0


def compute_confidence(query: dict, result: dict) -> float:
    """Compute a weighted confidence score between query and result metadata.

    Fields used:
    - title (weight 0.7): fuzzy string similarity (rapidfuzz)
    - year (weight 0.3): exact = 1.0, off by 1 = 0.5, else 0.0

    If no title in either dict, returns 0.0.
    If no year in either dict, title similarity alone (weight 1.0).
    Returns 0.0-1.0.
    """
    query_title = query.get(TITLE)
    result_title = result.get(TITLE)

    if not query_title or not result_title:
        return 0.0

    title_score = _string_similarity(str(query_title), str(result_title))

    query_year = query.get(YEAR)
    result_year = result.get(YEAR)

    if query_year is None or result_year is None:
        return title_score

    # Year scoring
    try:
        diff = abs(int(query_year) - int(result_year))
    except (ValueError, TypeError):
        return title_score

    if diff == 0:
        year_score = 1.0
    elif diff == 1:
        year_score = 0.5
    else:
        year_score = 0.0

    return 0.7 * title_score + 0.3 * year_score


def compute_episode_confidence(query: dict, episode: dict) -> float:
    """Score an episode match against a query.

    Considers:
    - Season number match (exact = 0.25 boost)
    - Episode number match (exact = 0.65 boost)
    - Episode title similarity (weight 0.1, if available in query)

    Season + episode match = 0.9, well above the 0.85 threshold.
    This is important because guessit never provides episode_title,
    so the title bonus rarely applies during auto-pipeline.

    Returns 0.0-1.0.
    """
    score = 0.0

    # Season number match
    q_season = query.get(SEASON)
    e_season = episode.get(SEASON)
    if q_season is not None and e_season is not None:
        try:
            if int(q_season) == int(e_season):
                score += 0.25
        except (ValueError, TypeError):
            pass

    # Episode number match (most important)
    q_ep = query.get(EPISODE)
    e_ep = episode.get(EPISODE)
    if q_ep is not None and e_ep is not None:
        try:
            if int(q_ep) == int(e_ep):
                score += 0.65
        except (ValueError, TypeError):
            pass

    # Episode title similarity (if query has episode_title)
    q_title = query.get(EPISODE_TITLE, "")
    e_title = episode.get(EPISODE_TITLE, "")
    if q_title and e_title:
        score += 0.1 * _string_similarity(str(q_title), str(e_title))

    return min(score, 1.0)
