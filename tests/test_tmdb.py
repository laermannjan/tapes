"""Tests for tapes.tmdb module."""

from __future__ import annotations

import httpx
import respx

from tapes.tmdb import (
    BASE_URL,
    get_movie,
    get_season_episodes,
    get_show,
    search_multi,
)

TOKEN = "test-token-123"


class TestSearchMulti:
    @respx.mock
    def test_movie_results(self) -> None:
        respx.get(f"{BASE_URL}/search/multi").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 438631,
                            "media_type": "movie",
                            "title": "Dune",
                            "release_date": "2021-09-15",
                        }
                    ]
                },
            )
        )
        results = search_multi("Dune", TOKEN)
        assert len(results) == 1
        assert results[0] == {
            "tmdb_id": 438631,
            "title": "Dune",
            "year": 2021,
            "media_type": "movie",
        }

    @respx.mock
    def test_tv_results(self) -> None:
        respx.get(f"{BASE_URL}/search/multi").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 1396,
                            "media_type": "tv",
                            "name": "Breaking Bad",
                            "first_air_date": "2008-01-20",
                        }
                    ]
                },
            )
        )
        results = search_multi("Breaking Bad", TOKEN)
        assert len(results) == 1
        assert results[0] == {
            "tmdb_id": 1396,
            "title": "Breaking Bad",
            "year": 2008,
            "media_type": "episode",
        }

    @respx.mock
    def test_mixed_results_filters_person(self) -> None:
        respx.get(f"{BASE_URL}/search/multi").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 1,
                            "media_type": "movie",
                            "title": "Dune",
                            "release_date": "2021-09-15",
                        },
                        {
                            "id": 99,
                            "media_type": "person",
                            "name": "Denis Villeneuve",
                        },
                        {
                            "id": 2,
                            "media_type": "tv",
                            "name": "Dune: Prophecy",
                            "first_air_date": "2024-11-17",
                        },
                    ]
                },
            )
        )
        results = search_multi("Dune", TOKEN)
        assert len(results) == 2
        assert results[0]["media_type"] == "movie"
        assert results[1]["media_type"] == "episode"

    @respx.mock
    def test_max_3_results(self) -> None:
        respx.get(f"{BASE_URL}/search/multi").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {"id": i, "media_type": "movie", "title": f"Movie {i}", "release_date": "2021-01-01"}
                        for i in range(10)
                    ]
                },
            )
        )
        results = search_multi("Movie", TOKEN)
        assert len(results) == 3

    @respx.mock
    def test_empty_results(self) -> None:
        respx.get(f"{BASE_URL}/search/multi").mock(return_value=httpx.Response(200, json={"results": []}))
        results = search_multi("Nonexistent", TOKEN)
        assert results == []

    def test_empty_token_returns_empty(self) -> None:
        results = search_multi("Dune", "")
        assert results == []

    def test_empty_query_returns_empty(self) -> None:
        results = search_multi("", TOKEN)
        assert results == []

    @respx.mock
    def test_http_error_returns_empty(self) -> None:
        respx.get(f"{BASE_URL}/search/multi").mock(return_value=httpx.Response(500))
        results = search_multi("Dune", TOKEN)
        assert results == []

    @respx.mock
    def test_network_error_returns_empty(self) -> None:
        respx.get(f"{BASE_URL}/search/multi").mock(side_effect=httpx.ConnectError("Connection refused"))
        results = search_multi("Dune", TOKEN)
        assert results == []

    @respx.mock
    def test_year_param_passed(self) -> None:
        route = respx.get(f"{BASE_URL}/search/multi").mock(return_value=httpx.Response(200, json={"results": []}))
        search_multi("Dune", TOKEN, year=2021)
        assert route.called
        request = route.calls[0].request
        assert "year=2021" in str(request.url)

    @respx.mock
    def test_missing_release_date(self) -> None:
        respx.get(f"{BASE_URL}/search/multi").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 1,
                            "media_type": "movie",
                            "title": "Unknown",
                            "release_date": "",
                        }
                    ]
                },
            )
        )
        results = search_multi("Unknown", TOKEN)
        assert len(results) == 1
        assert results[0]["year"] is None


class TestGetMovie:
    @respx.mock
    def test_get_movie(self) -> None:
        respx.get(f"{BASE_URL}/movie/438631").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 438631,
                    "title": "Dune",
                    "release_date": "2021-09-15",
                },
            )
        )
        result = get_movie(438631, TOKEN)
        assert result == {
            "tmdb_id": 438631,
            "title": "Dune",
            "year": 2021,
            "media_type": "movie",
        }

    def test_empty_token(self) -> None:
        assert get_movie(438631, "") == {}

    @respx.mock
    def test_http_error(self) -> None:
        respx.get(f"{BASE_URL}/movie/999999").mock(return_value=httpx.Response(404))
        assert get_movie(999999, TOKEN) == {}


class TestGetShow:
    @respx.mock
    def test_get_show(self) -> None:
        respx.get(f"{BASE_URL}/tv/1396").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 1396,
                    "name": "Breaking Bad",
                    "first_air_date": "2008-01-20",
                    "seasons": [
                        {"season_number": 0},
                        {"season_number": 1},
                        {"season_number": 2},
                    ],
                },
            )
        )
        result = get_show(1396, TOKEN)
        assert result == {
            "tmdb_id": 1396,
            "title": "Breaking Bad",
            "year": 2008,
            "media_type": "episode",
            "seasons": [0, 1, 2],
        }

    def test_empty_token(self) -> None:
        assert get_show(1396, "") == {}

    @respx.mock
    def test_http_error(self) -> None:
        respx.get(f"{BASE_URL}/tv/999999").mock(return_value=httpx.Response(404))
        assert get_show(999999, TOKEN) == {}


class TestGetSeasonEpisodes:
    @respx.mock
    def test_get_episodes(self) -> None:
        respx.get(f"{BASE_URL}/tv/1396/season/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "episodes": [
                        {"episode_number": 1, "name": "Pilot"},
                        {"episode_number": 2, "name": "Cat's in the Bag..."},
                    ]
                },
            )
        )
        episodes = get_season_episodes(1396, 1, TOKEN, show_title="Breaking Bad", show_year=2008)
        assert len(episodes) == 2
        assert episodes[0] == {
            "tmdb_id": 1396,
            "title": "Breaking Bad",
            "year": 2008,
            "media_type": "episode",
            "season": 1,
            "episode": 1,
            "episode_title": "Pilot",
        }
        assert episodes[1]["episode"] == 2
        assert episodes[1]["episode_title"] == "Cat's in the Bag..."

    def test_empty_token(self) -> None:
        assert get_season_episodes(1396, 1, "") == []

    @respx.mock
    def test_http_error(self) -> None:
        respx.get(f"{BASE_URL}/tv/1396/season/1").mock(return_value=httpx.Response(404))
        assert get_season_episodes(1396, 1, TOKEN) == []
