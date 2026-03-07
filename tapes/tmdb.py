"""TMDB API client using httpx."""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.themoviedb.org/3"


def create_client(token: str) -> httpx.Client:
    """Create an httpx client with TMDB auth headers.

    Caller is responsible for closing the client.
    """
    return httpx.Client(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    )


def search_multi(
    query: str, token: str, year: int | None = None,
    *, client: httpx.Client | None = None,
) -> list[dict]:
    """Search /search/multi. Returns up to 3 results.

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

    try:
        if client is not None:
            resp = client.get("/search/multi", params=params)
            resp.raise_for_status()
        else:
            with create_client(token) as c:
                resp = c.get("/search/multi", params=params)
                resp.raise_for_status()
    except (httpx.HTTPError, httpx.HTTPStatusError) as exc:
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
            results.append(
                {
                    "tmdb_id": item["id"],
                    "title": title,
                    "year": yr,
                    "media_type": "movie",
                }
            )
        elif mt == "tv":
            title = item.get("name", "")
            first_air = item.get("first_air_date", "") or ""
            yr = int(first_air[:4]) if len(first_air) >= 4 else None
            results.append(
                {
                    "tmdb_id": item["id"],
                    "title": title,
                    "year": yr,
                    "media_type": "episode",
                }
            )
        # Skip "person" and other types

        if len(results) >= 3:
            break

    return results


def get_movie(
    tmdb_id: int, token: str,
    *, client: httpx.Client | None = None,
) -> dict:
    """GET /movie/{id}. Returns {tmdb_id, title, year, media_type: "movie"}."""
    if not token:
        return {}

    try:
        if client is not None:
            resp = client.get(f"/movie/{tmdb_id}")
            resp.raise_for_status()
        else:
            with create_client(token) as c:
                resp = c.get(f"/movie/{tmdb_id}")
                resp.raise_for_status()
    except (httpx.HTTPError, httpx.HTTPStatusError) as exc:
        logger.warning("TMDB get_movie failed: %s", exc)
        return {}

    data = resp.json()
    release_date = data.get("release_date", "") or ""
    yr = int(release_date[:4]) if len(release_date) >= 4 else None
    return {
        "tmdb_id": data["id"],
        "title": data.get("title", ""),
        "year": yr,
        "media_type": "movie",
    }


def get_show(
    tmdb_id: int, token: str,
    *, client: httpx.Client | None = None,
) -> dict:
    """GET /tv/{id}. Returns show info with seasons list."""
    if not token:
        return {}

    try:
        if client is not None:
            resp = client.get(f"/tv/{tmdb_id}")
            resp.raise_for_status()
        else:
            with create_client(token) as c:
                resp = c.get(f"/tv/{tmdb_id}")
                resp.raise_for_status()
    except (httpx.HTTPError, httpx.HTTPStatusError) as exc:
        logger.warning("TMDB get_show failed: %s", exc)
        return {}

    data = resp.json()
    first_air = data.get("first_air_date", "") or ""
    yr = int(first_air[:4]) if len(first_air) >= 4 else None
    seasons = [
        s["season_number"]
        for s in data.get("seasons", [])
        if s.get("season_number") is not None
    ]
    return {
        "tmdb_id": data["id"],
        "title": data.get("name", ""),
        "year": yr,
        "media_type": "episode",
        "seasons": seasons,
    }


def get_season_episodes(
    show_id: int,
    season_number: int,
    token: str,
    show_title: str = "",
    show_year: int | None = None,
    *, client: httpx.Client | None = None,
) -> list[dict]:
    """GET /tv/{show_id}/season/{season_number}. Returns list of episode dicts.

    Each episode dict has all fields needed for a Source:
    tmdb_id, title, year, media_type, season, episode, episode_title.
    """
    if not token:
        return []

    try:
        if client is not None:
            resp = client.get(f"/tv/{show_id}/season/{season_number}")
            resp.raise_for_status()
        else:
            with create_client(token) as c:
                resp = c.get(f"/tv/{show_id}/season/{season_number}")
                resp.raise_for_status()
    except (httpx.HTTPError, httpx.HTTPStatusError) as exc:
        logger.warning("TMDB get_season_episodes failed: %s", exc)
        return []

    data = resp.json()
    episodes: list[dict] = []
    for ep in data.get("episodes", []):
        episodes.append(
            {
                "tmdb_id": show_id,
                "title": show_title,
                "year": show_year,
                "media_type": "episode",
                "season": season_number,
                "episode": ep.get("episode_number"),
                "episode_title": ep.get("name", ""),
            }
        )
    return episodes
