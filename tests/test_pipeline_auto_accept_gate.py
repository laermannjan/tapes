"""Tests for the media-type match gate on auto-accept (A2).

The gate in _query_tmdb_for_node blocks auto-accept when the best
TMDB candidate's media_type disagrees with the node's guessit media_type.
If guessit did not extract a media_type, the gate is skipped.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import respx

from tapes.fields import MEDIA_TYPE, MEDIA_TYPE_EPISODE, MEDIA_TYPE_MOVIE, TITLE, TMDB_ID, YEAR
from tapes.pipeline import PipelineParams, _query_tmdb_for_node
from tapes.tmdb import BASE_URL
from tapes.tree_model import FileNode

TOKEN = "test-token-for-gate"

# Use very permissive thresholds so auto-accept fires on score alone.
EASY_PARAMS = PipelineParams(token=TOKEN, min_score=0.3, min_prominence=0.0)


def _make_node(filename: str, metadata: dict) -> FileNode:
    return FileNode(path=Path(filename), metadata=dict(metadata))


class TestMediaTypeMatchGate:
    """A2: media-type match gate on auto-accept."""

    @respx.mock
    def test_matching_media_type_auto_accepts(self) -> None:
        """Movie query + movie result -> auto-accept fires -> tmdb_id set."""
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

        node = _make_node("Dune.2021.mp4", {TITLE: "Dune", YEAR: 2021, MEDIA_TYPE: MEDIA_TYPE_MOVIE})
        _query_tmdb_for_node(node, EASY_PARAMS)

        # Auto-accept should fire: tmdb_id written to metadata
        assert node.metadata.get(TMDB_ID) == 438631
        # A3: candidates cleared after auto-accept
        assert len(node.candidates) == 0

    @respx.mock
    def test_mismatching_media_type_blocks_auto_accept(self) -> None:
        """Movie query + tv result -> auto-accept blocked -> tmdb_id NOT set."""
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

        # Node guessit says "movie", but TMDB returns a TV show (media_type="episode")
        node = _make_node("breaking_bad_720p.mp4", {TITLE: "Breaking Bad", MEDIA_TYPE: MEDIA_TYPE_MOVIE})
        _query_tmdb_for_node(node, EASY_PARAMS)

        # Auto-accept should NOT fire: tmdb_id not in metadata
        assert TMDB_ID not in node.metadata
        # But candidates should still be populated
        assert len(node.candidates) >= 1
        assert node.candidates[0].metadata.get(TMDB_ID) == 1396

    @respx.mock
    def test_no_media_type_in_node_skips_gate(self) -> None:
        """No media_type from guessit -> gate skipped -> auto-accept proceeds."""
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

        # Node has no media_type -- gate should be skipped
        node = _make_node("breaking_bad.mp4", {TITLE: "Breaking Bad"})

        # Mock get_show and get_season_episodes for the episode query that
        # follows auto-accept of a TV show candidate.
        respx.get(f"{BASE_URL}/tv/1396").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 1396,
                    "name": "Breaking Bad",
                    "first_air_date": "2008-01-20",
                    "seasons": [],
                },
            )
        )

        _query_tmdb_for_node(node, EASY_PARAMS)

        # Auto-accept should fire since gate is skipped
        assert node.metadata.get(TMDB_ID) == 1396
        # A3: candidates cleared after auto-accept (no episodes since seasons=[])
        assert len(node.candidates) == 0

    @respx.mock
    def test_episode_node_vs_movie_result_blocks(self) -> None:
        """Episode query + movie result -> auto-accept blocked."""
        respx.get(f"{BASE_URL}/search/multi").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 99999,
                            "media_type": "movie",
                            "title": "Some Show The Movie",
                            "release_date": "2020-01-01",
                        }
                    ]
                },
            )
        )

        node = _make_node("some.show.s01e01.mp4", {TITLE: "Some Show", MEDIA_TYPE: MEDIA_TYPE_EPISODE})
        _query_tmdb_for_node(node, EASY_PARAMS)

        # Auto-accept should NOT fire
        assert TMDB_ID not in node.metadata
        # Candidates still populated
        assert len(node.candidates) >= 1
