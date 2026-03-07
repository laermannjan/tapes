"""Simple token-based scoring for comparing metadata fields.

This is intentionally basic and will be revisited for more sophisticated
matching (Levenshtein, phonetic, transliteration, etc.).
"""
from __future__ import annotations

from tapes.fields import EPISODE, EPISODE_TITLE, SEASON, TITLE, YEAR


def title_similarity(a: str, b: str) -> float:
    """Compute Jaccard similarity between two title strings.

    Lowercases both, splits into word tokens, and returns
    intersection / union of the token sets. Returns 0.0-1.0.
    """
    if not a or not b:
        return 0.0
    tokens_a = set(a.lower().split())
    tokens_b = set(b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def compute_confidence(query: dict, result: dict) -> float:
    """Compute a weighted confidence score between query and result metadata.

    Fields used:
    - title (weight 0.7): Jaccard token similarity
    - year (weight 0.3): exact = 1.0, off by 1 = 0.5, else 0.0

    If no title in either dict, returns 0.0.
    If no year in either dict, title similarity alone (weight 1.0).
    Returns 0.0-1.0.
    """
    query_title = query.get(TITLE)
    result_title = result.get(TITLE)

    if not query_title or not result_title:
        return 0.0

    title_score = title_similarity(str(query_title), str(result_title))

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
        score += 0.1 * title_similarity(str(q_title), str(e_title))

    return min(score, 1.0)
