import logging
import re

import jellyfish
import requests

from tapes.metadata.base import MetadataSource, SearchResult

logger = logging.getLogger(__name__)

BASE_URL = "https://api.themoviedb.org/3"

_LEADING_ARTICLE = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)


class TMDBSource(MetadataSource):
    def __init__(self, token: str, timeout: int = 10):
        self._token = token
        self._timeout = timeout
        self._available: bool | None = None
        self._headers = {"Authorization": f"Bearer {token}"}

    def search(self, title: str, year: int | None, media_type: str) -> list[SearchResult]:
        if not title:
            return []

        endpoint = "search/tv" if media_type == "tv" else "search/movie"
        params = {"query": title}

        try:
            resp = requests.get(f"{BASE_URL}/{endpoint}", params=params, headers=self._headers, timeout=self._timeout)
            resp.raise_for_status()
            raw_results = resp.json().get("results", [])
        except requests.exceptions.HTTPError as e:
            logger.warning("TMDB search failed (HTTP %s): %s", e.response.status_code, e)
            return []
        except Exception as e:
            logger.warning("TMDB search failed: %s", e)
            return []

        results = []
        for item in raw_results[:5]:
            detail = self._fetch_detail(item["id"], media_type)
            if detail is None:
                continue
            result_year = _extract_year(item, media_type)
            confidence = _score(title, year, item, media_type, result_year)
            results.append(_build_result(item, detail, media_type, confidence))

        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    def get_by_id(self, tmdb_id: int, media_type: str) -> SearchResult | None:
        detail = self._fetch_detail(tmdb_id, media_type)
        if detail is None:
            return None
        return _build_result(detail, detail, media_type, confidence=0.95)

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            resp = requests.get(
                f"{BASE_URL}/configuration",
                headers=self._headers,
                timeout=self._timeout,
            )
            self._available = resp.status_code == 200
            if not self._available:
                logger.warning("TMDB API returned HTTP %s; check your API key", resp.status_code)
        except Exception as e:
            logger.warning("TMDB API unreachable: %s", e)
            self._available = False
        return self._available

    def _fetch_detail(self, tmdb_id: int, media_type: str) -> dict | None:
        endpoint = "tv" if media_type == "tv" else "movie"
        try:
            resp = requests.get(
                f"{BASE_URL}/{endpoint}/{tmdb_id}",
                params={"append_to_response": "credits"},
                headers=self._headers,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.debug("TMDB detail fetch failed for %s/%s: %s", endpoint, tmdb_id, e)
            return None


def _extract_year(item: dict, media_type: str) -> int | None:
    date_str = item.get("release_date") or item.get("first_air_date") or ""
    try:
        return int(date_str[:4]) if date_str else None
    except (ValueError, TypeError):
        return None


def _normalize_title(title: str) -> str:
    return _LEADING_ARTICLE.sub("", title).strip().lower()


def _title_similarity(query: str, result: str) -> float:
    return jellyfish.jaro_winkler_similarity(
        _normalize_title(query),
        _normalize_title(result),
    )


def _year_factor(query_year: int | None, result_year: int | None) -> float:
    if query_year is None:
        return 0.8
    if result_year is None:
        return 0.8
    distance = abs(query_year - result_year)
    if distance == 0:
        return 1.0
    if distance == 1:
        return 0.95
    if distance == 2:
        return 0.85
    return max(0.5, 1.0 - distance * 0.1)


def _score(query_title: str, query_year: int | None, item: dict, media_type: str, result_year: int | None) -> float:
    result_title = item.get("title") or item.get("name") or ""
    similarity = _title_similarity(query_title, result_title)
    year_f = _year_factor(query_year, result_year)
    return similarity * year_f


def _build_result(item: dict, detail: dict, media_type: str, confidence: float) -> SearchResult:
    # Director from credits
    director = None
    credits = detail.get("credits", {})
    crew = credits.get("crew", []) if credits else []
    for member in crew:
        if member.get("job") == "Director":
            director = member["name"]
            break
    # TV: use created_by as director equivalent
    if director is None and media_type == "tv":
        created_by = detail.get("created_by", [])
        if created_by:
            director = created_by[0].get("name")

    genres = detail.get("genres", [])
    genre = genres[0]["name"] if genres else None

    result_year = _extract_year(item, media_type)

    if media_type == "tv":
        return SearchResult(
            tmdb_id=item.get("id") or detail["id"],
            title=item.get("name") or detail.get("name", ""),
            year=result_year,
            media_type="tv",
            confidence=confidence,
            director=director,
            genre=genre,
            show=item.get("name") or detail.get("name"),
        )
    else:
        return SearchResult(
            tmdb_id=item.get("id") or detail["id"],
            title=item.get("title") or detail.get("title", ""),
            year=result_year,
            media_type="movie",
            confidence=confidence,
            director=director,
            genre=genre,
        )
