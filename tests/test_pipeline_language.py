"""Tests for language parameter threading through pipeline."""

from __future__ import annotations

from pathlib import Path

import respx

from tapes.pipeline import _query_tmdb_for_node
from tapes.tree_model import FileNode


class TestLanguageThreading:
    @respx.mock
    def test_language_passed_to_search(self) -> None:
        route = respx.get("https://api.themoviedb.org/3/search/multi").respond(json={"results": []})
        node = FileNode(path=Path("/a.mkv"), result={"title": "Test"})
        _query_tmdb_for_node(node, "tok", 0.85, language="de")
        assert route.called
        assert route.calls[0].request.url.params["language"] == "de"

    @respx.mock
    def test_empty_language_not_in_params(self) -> None:
        route = respx.get("https://api.themoviedb.org/3/search/multi").respond(json={"results": []})
        node = FileNode(path=Path("/a.mkv"), result={"title": "Test"})
        _query_tmdb_for_node(node, "tok", 0.85, language="")
        assert route.called
        assert "language" not in route.calls[0].request.url.params

    @respx.mock
    def test_language_passed_to_get_show(self) -> None:
        respx.get("https://api.themoviedb.org/3/search/multi").respond(
            json={
                "results": [
                    {
                        "id": 1,
                        "media_type": "tv",
                        "name": "Test",
                        "original_name": "Test",
                        "first_air_date": "2020-01-01",
                    }
                ]
            }
        )
        show_route = respx.get("https://api.themoviedb.org/3/tv/1").respond(
            json={"id": 1, "name": "Test", "first_air_date": "2020-01-01", "seasons": [{"season_number": 1}]}
        )
        respx.get("https://api.themoviedb.org/3/tv/1/season/1").respond(json={"episodes": []})
        node = FileNode(path=Path("/a.mkv"), result={"title": "Test", "season": 1, "episode": 1})
        _query_tmdb_for_node(node, "tok", 0.1, language="fr")
        assert show_route.called
        assert show_route.calls[0].request.url.params["language"] == "fr"
