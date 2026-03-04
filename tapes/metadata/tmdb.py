import requests
from tapes.metadata.base import MetadataSource, SearchResult

BASE_URL = "https://api.themoviedb.org/3"

# Confidence scoring per design doc
_EXACT_YEAR = 0.90
_YEAR_OFF_BY_ONE = 0.75
_EXACT_NO_YEAR = 0.70
_NO_MATCH_YEAR = 0.50


class TMDBSource(MetadataSource):
    def __init__(self, api_key: str, timeout: int = 10):
        self._key = api_key
        self._timeout = timeout

    def search(self, title: str, year: int | None, media_type: str) -> list[SearchResult]:
        if not title:
            return []

        endpoint = "search/tv" if media_type == "tv" else "search/movie"
        params = {"api_key": self._key, "query": title}
        if year:
            params["year" if media_type == "movie" else "first_air_date_year"] = year

        try:
            resp = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=self._timeout)
            resp.raise_for_status()
            raw_results = resp.json().get("results", [])
        except Exception:
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
        try:
            resp = requests.get(
                f"{BASE_URL}/configuration",
                params={"api_key": self._key},
                timeout=self._timeout,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def _fetch_detail(self, tmdb_id: int, media_type: str) -> dict | None:
        endpoint = "tv" if media_type == "tv" else "movie"
        try:
            resp = requests.get(
                f"{BASE_URL}/{endpoint}/{tmdb_id}",
                params={"api_key": self._key, "append_to_response": "credits"},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None


def _extract_year(item: dict, media_type: str) -> int | None:
    date_str = item.get("release_date") or item.get("first_air_date") or ""
    try:
        return int(date_str[:4]) if date_str else None
    except (ValueError, TypeError):
        return None


def _score(query_title: str, query_year: int | None, item: dict, media_type: str, result_year: int | None) -> float:
    result_title = item.get("title") or item.get("name") or ""
    title_match = result_title.lower() == query_title.lower()

    if not title_match:
        return _NO_MATCH_YEAR

    if query_year is None:
        return _EXACT_NO_YEAR

    if result_year == query_year:
        return _EXACT_YEAR

    if result_year and abs(result_year - query_year) == 1:
        return _YEAR_OFF_BY_ONE

    return _EXACT_NO_YEAR


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
