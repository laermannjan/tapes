"""TMDB API client using httpx."""

from __future__ import annotations

import logging
from typing import Any

import httpx
import tenacity

from tapes.fields import (
    EPISODE,
    EPISODE_TITLE,
    MEDIA_TYPE,
    MEDIA_TYPE_EPISODE,
    MEDIA_TYPE_MOVIE,
    SEASON,
    TITLE,
    TMDB_ID,
    YEAR,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://api.themoviedb.org/3"
REQUEST_TIMEOUT_S = 10.0
MAX_TMDB_RESULTS = 3


def create_client(token: str, timeout: float = REQUEST_TIMEOUT_S) -> httpx.Client:
    """Create an httpx client with TMDB auth headers.

    Caller is responsible for closing the client.
    """
    return httpx.Client(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )


def _is_retryable(exc: BaseException) -> bool:
    """Return True for HTTP errors that warrant a retry."""
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {429, 500, 502, 503, 504}


def _retry_after_wait(retry_state: tenacity.RetryCallState) -> float:
    """Extract wait time from Retry-After header, falling back to exponential backoff."""
    exc = retry_state.outcome.exception()  # type: ignore[union-attr]
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
        retry_after = exc.response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
    return tenacity.wait_exponential(multiplier=1, min=1, max=30)(retry_state)


def _request(
    method: str,
    path: str,
    token: str,
    client: httpx.Client | None = None,
    max_retries: int = 3,
    **kwargs: Any,
) -> httpx.Response:
    """Make a TMDB API request, reusing client if provided."""
    retryer = tenacity.Retrying(
        retry=tenacity.retry_if_exception(_is_retryable),
        wait=_retry_after_wait,
        stop=tenacity.stop_after_attempt(max_retries),
        reraise=True,
    )
    for attempt in retryer:
        with attempt:
            if client is not None:
                resp = client.request(method, path, **kwargs)
                resp.raise_for_status()
                return resp
            with create_client(token) as c:
                resp = c.request(method, path, **kwargs)
                resp.raise_for_status()
                return resp
    raise RuntimeError("Unreachable: tenacity retry loop exited without return or raise")


def search_multi(
    query: str,
    token: str,
    year: int | None = None,
    *,
    language: str = "",
    client: httpx.Client | None = None,
    max_results: int = MAX_TMDB_RESULTS,
    max_retries: int = 3,
) -> list[dict]:
    """Search /search/multi. Returns up to ``max_results`` results.

    Each result dict has: tmdb_id, title, year, media_type ("movie" or "episode").
    Movies come from results with media_type=="movie".
    TV shows come from results with media_type=="tv" -- mapped to media_type="episode".
    Person results are filtered out.
    """
    if not token or not query:
        return []

    params: dict = {"query": query}
    if year is not None:
        params["year"] = year
    if language:
        params["language"] = language

    try:
        resp = _request("GET", "/search/multi", token, client=client, max_retries=max_retries, params=params)
    except httpx.HTTPError as exc:
        logger.warning("TMDB search_multi failed: %s", exc)
        return []

    data = resp.json()
    results: list[dict] = []

    for item in data.get("results", []):
        mt = item.get("media_type")
        if mt == "movie":
            title = item.get("title", "")
            release_date = item.get("release_date", "") or ""
            yr = int(release_date[:4]) if len(release_date) >= 4 else None
            original_title = item.get("original_title", title)
            results.append(
                {
                    TMDB_ID: item["id"],
                    TITLE: title,
                    "original_title": original_title,
                    YEAR: yr,
                    MEDIA_TYPE: MEDIA_TYPE_MOVIE,
                }
            )
        elif mt == "tv":
            title = item.get("name", "")
            first_air = item.get("first_air_date", "") or ""
            yr = int(first_air[:4]) if len(first_air) >= 4 else None
            original_title = item.get("original_name", title)
            results.append(
                {
                    TMDB_ID: item["id"],
                    TITLE: title,
                    "original_title": original_title,
                    YEAR: yr,
                    MEDIA_TYPE: MEDIA_TYPE_EPISODE,
                }
            )
        # Skip "person" and other types

        if len(results) >= max_results:
            break

    return results


def get_show(
    tmdb_id: int,
    token: str,
    *,
    language: str = "",
    client: httpx.Client | None = None,
    max_retries: int = 3,
) -> dict:
    """GET /tv/{id}. Returns show info with seasons list."""
    if not token:
        return {}

    params: dict = {}
    if language:
        params["language"] = language

    try:
        resp = _request("GET", f"/tv/{tmdb_id}", token, client=client, max_retries=max_retries, params=params)
    except httpx.HTTPError as exc:
        logger.warning("TMDB get_show failed: %s", exc)
        return {}

    data = resp.json()
    first_air = data.get("first_air_date", "") or ""
    yr = int(first_air[:4]) if len(first_air) >= 4 else None
    seasons = [s["season_number"] for s in data.get("seasons", []) if s.get("season_number") is not None]
    return {
        TMDB_ID: data["id"],
        TITLE: data.get("name", ""),
        YEAR: yr,
        MEDIA_TYPE: MEDIA_TYPE_EPISODE,
        "seasons": seasons,
    }


def get_season_episodes(
    show_id: int,
    season_number: int,
    token: str,
    show_title: str = "",
    show_year: int | None = None,
    *,
    language: str = "",
    client: httpx.Client | None = None,
    max_retries: int = 3,
) -> list[dict]:
    """GET /tv/{show_id}/season/{season_number}. Returns list of episode dicts.

    Each episode dict has all fields needed for a Source:
    tmdb_id, title, year, media_type, season, episode, episode_title.
    """
    if not token:
        return []

    params: dict = {}
    if language:
        params["language"] = language

    try:
        resp = _request(
            "GET", f"/tv/{show_id}/season/{season_number}", token, client=client, max_retries=max_retries, params=params
        )
    except httpx.HTTPError as exc:
        logger.warning("TMDB get_season_episodes failed: %s", exc)
        return []

    data = resp.json()
    return [
        {
            TMDB_ID: show_id,
            TITLE: show_title,
            YEAR: show_year,
            MEDIA_TYPE: MEDIA_TYPE_EPISODE,
            SEASON: season_number,
            EPISODE: ep.get("episode_number"),
            EPISODE_TITLE: ep.get("name", ""),
        }
        for ep in data.get("episodes", [])
    ]
