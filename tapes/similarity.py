"""Similarity scoring for metadata matching.

Uses rapidfuzz for string similarity. Each field has its own matching
strategy (fuzzy, integer distance, exact) and weight.
"""

from __future__ import annotations

import structlog
from rapidfuzz import fuzz, utils

from tapes.config import DEFAULT_MIN_SCORE
from tapes.fields import EPISODE, EPISODE_TITLE, MEDIA_TYPE, SEASON, TITLE, TMDB_ID, YEAR

logger = structlog.get_logger()

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

# Auto-accept: prominence = gap between best and second-best
DEFAULT_MIN_PROMINENCE = 0.15

# Media-type conflict: penalize when guessit and TMDB disagree on media_type
MEDIA_TYPE_PENALTY = 0.7


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
    blend = STRICT_WEIGHT * strict + (1 - STRICT_WEIGHT) * lenient
    logger.debug("string_sim", a=a, b=b, ratio=strict, tset=lenient, blend=blend)
    return blend


def compute_similarity(query: dict, result: dict) -> float:
    """Compute weighted similarity between query and result metadata.

    Fields:
    - tmdb_id: exact match overrides to 1.0
    - title: rapidfuzz string similarity (weight SHOW_TITLE_WEIGHT)
    - year: integer distance (weight SHOW_YEAR_WEIGHT)

    Missing fields score 0.0 (penalized, not redistributed).
    Returns 0.0-1.0.
    """
    q_id = query.get(TMDB_ID)
    r_id = result.get(TMDB_ID)
    if q_id is not None and r_id is not None and q_id == r_id:
        return 1.0

    q_title = query.get(TITLE)
    r_title = result.get(TITLE)
    if not q_title or not r_title:
        return 0.0

    title_score = _string_similarity(str(q_title), str(r_title))

    r_original = result.get("original_title")
    if r_original and r_original != r_title:
        original_score = _string_similarity(str(q_title), str(r_original))
        title_score = max(title_score, original_score)

    year_score = 0.0
    q_year = query.get(YEAR)
    r_year = result.get(YEAR)
    if q_year is not None and r_year is not None:
        try:
            diff = abs(int(q_year) - int(r_year))
            year_score = max(0.0, 1.0 - diff / YEAR_TOLERANCE)
        except (ValueError, TypeError):
            pass

    total = SHOW_TITLE_WEIGHT * title_score + SHOW_YEAR_WEIGHT * year_score

    q_type = query.get(MEDIA_TYPE)
    r_type = result.get(MEDIA_TYPE)
    if q_type and r_type and q_type != r_type:
        total *= MEDIA_TYPE_PENALTY

    logger.debug(
        "similarity",
        query=q_title,
        result=r_title,
        title_score=title_score,
        year_score=year_score,
        total=total,
    )
    return total


def compute_episode_similarity(query: dict, episode: dict) -> float:
    """Score an episode match against a query.

    Fields:
    - season: exact integer match (weight EPISODE_SEASON_WEIGHT)
    - episode: exact integer match (weight EPISODE_NUMBER_WEIGHT)
    - episode_title: rapidfuzz similarity (weight EPISODE_TITLE_WEIGHT)

    Missing fields score 0.0 (penalized).
    Season + episode match = 0.9, above the default min_score threshold.
    Returns 0.0-1.0.
    """
    score = 0.0

    q_season = query.get(SEASON)
    e_season = episode.get(SEASON)
    if q_season is not None and e_season is not None:
        try:
            if int(q_season) == int(e_season):
                score += EPISODE_SEASON_WEIGHT
        except (ValueError, TypeError):
            pass

    q_ep = query.get(EPISODE)
    e_ep = episode.get(EPISODE)
    if q_ep is not None and e_ep is not None:
        try:
            if int(q_ep) == int(e_ep):
                score += EPISODE_NUMBER_WEIGHT
        except (ValueError, TypeError):
            pass

    q_title = query.get(EPISODE_TITLE, "")
    e_title = episode.get(EPISODE_TITLE, "")
    if q_title and e_title:
        score += EPISODE_TITLE_WEIGHT * _string_similarity(str(q_title), str(e_title))

    score = min(score, 1.0)
    logger.debug(
        "episode_sim",
        query_ep=f"S{query.get(SEASON, '?')}E{query.get(EPISODE, '?')}",
        result_ep=f"S{episode.get(SEASON, '?')}E{episode.get(EPISODE, '?')}",
        score=score,
    )
    return score


def should_auto_accept(
    scores: list[float],
    min_score: float = DEFAULT_MIN_SCORE,
    min_prominence: float = DEFAULT_MIN_PROMINENCE,
) -> bool:
    """Decide whether to auto-accept the best candidate.

    Auto-accepts when the best score is above min_score AND the candidate
    is prominent (margin to second-best >= min_prominence). A single
    candidate has infinite prominence.
    """
    if not scores:
        return False
    best = scores[0]
    if best < min_score:
        logger.debug(
            "auto_accept_check",
            best=best,
            min_score=min_score,
            accepted=False,
            reason="below_min_score",
        )
        return False
    if len(scores) == 1:
        logger.debug(
            "auto_accept_check",
            best=best,
            min_score=min_score,
            accepted=True,
            reason="single_candidate",
        )
        return True  # single candidate, infinite prominence
    prominence = best - scores[1]
    if prominence >= min_prominence:
        logger.debug(
            "auto_accept_check",
            best=best,
            prominence=prominence,
            min_prominence=min_prominence,
            accepted=True,
        )
        return True
    logger.debug(
        "auto_accept_check",
        best=best,
        prominence=prominence,
        min_prominence=min_prominence,
        accepted=False,
        reason="low_prominence",
    )
    return False
