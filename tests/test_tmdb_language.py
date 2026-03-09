"""Tests for TMDB language parameter support."""

from __future__ import annotations

import respx

from tapes.tmdb import get_season_episodes, get_show, search_multi


class TestLanguageParam:
    @respx.mock
    def test_search_multi_passes_language(self) -> None:
        route = respx.get("https://api.themoviedb.org/3/search/multi").respond(json={"results": []})
        search_multi("Inception", "tok", language="de")
        assert route.called
        assert route.calls[0].request.url.params["language"] == "de"

    @respx.mock
    def test_search_multi_omits_language_when_empty(self) -> None:
        route = respx.get("https://api.themoviedb.org/3/search/multi").respond(json={"results": []})
        search_multi("Inception", "tok", language="")
        assert route.called
        assert "language" not in route.calls[0].request.url.params

    @respx.mock
    def test_search_multi_no_language_param_by_default(self) -> None:
        route = respx.get("https://api.themoviedb.org/3/search/multi").respond(json={"results": []})
        search_multi("Inception", "tok")
        assert route.called
        assert "language" not in route.calls[0].request.url.params

    @respx.mock
    def test_get_show_passes_language(self) -> None:
        route = respx.get("https://api.themoviedb.org/3/tv/123").respond(
            json={"id": 123, "name": "Test", "seasons": []}
        )
        get_show(123, "tok", language="fr")
        assert route.called
        assert route.calls[0].request.url.params["language"] == "fr"

    @respx.mock
    def test_get_season_episodes_passes_language(self) -> None:
        route = respx.get("https://api.themoviedb.org/3/tv/123/season/1").respond(json={"episodes": []})
        get_season_episodes(123, 1, "tok", language="de-DE")
        assert route.called
        assert route.calls[0].request.url.params["language"] == "de-DE"


class TestOriginalTitle:
    @respx.mock
    def test_movie_includes_original_title(self) -> None:
        respx.get("https://api.themoviedb.org/3/search/multi").respond(
            json={
                "results": [
                    {
                        "id": 1,
                        "media_type": "movie",
                        "title": "Matrix",
                        "original_title": "The Matrix",
                        "release_date": "1999-03-31",
                    }
                ]
            }
        )
        results = search_multi("Matrix", "tok", language="de")
        assert results[0]["original_title"] == "The Matrix"

    @respx.mock
    def test_tv_includes_original_name(self) -> None:
        respx.get("https://api.themoviedb.org/3/search/multi").respond(
            json={
                "results": [
                    {
                        "id": 2,
                        "media_type": "tv",
                        "name": "Tatort",
                        "original_name": "Tatort",
                        "first_air_date": "1970-11-29",
                    }
                ]
            }
        )
        results = search_multi("Tatort", "tok", language="de")
        assert results[0]["original_title"] == "Tatort"
