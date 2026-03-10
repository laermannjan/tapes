"""Tests for the auto-pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tapes.pipeline import refresh_tmdb_source, run_auto_pipeline
from tapes.tree_model import Candidate, FileNode, FolderNode, TreeModel
from tapes.ui.tree_app import AppState

TOKEN = "test-token"


def _make_model(*filenames: str) -> TreeModel:
    """Build a TreeModel from filename strings."""
    root = FolderNode(
        name="root",
        children=[FileNode(path=Path(f"/media/{fn}")) for fn in filenames],
    )
    return TreeModel(root=root)


# --- Mock TMDB responses for pipeline tests ---


def _mock_search_multi(query: str, token: str, year: int | None = None, **kwargs: object) -> list[dict]:
    """Mock search_multi returning known results."""
    q = query.lower()
    if "dune" in q:
        return [{"tmdb_id": 438631, "title": "Dune", "year": 2021, "media_type": "movie"}]
    if "arrival" in q:
        return [{"tmdb_id": 329865, "title": "Arrival", "year": 2016, "media_type": "movie"}]
    if "interstellar" in q:
        return [{"tmdb_id": 157336, "title": "Interstellar", "year": 2014, "media_type": "movie"}]
    if "breaking bad" in q:
        return [
            {"tmdb_id": 1396, "title": "Breaking Bad", "year": 2008, "media_type": "episode"},
            {"tmdb_id": 559969, "title": "El Camino: A Breaking Bad Movie", "year": 2019, "media_type": "movie"},
        ]
    if "the office" in q:
        return [
            {"tmdb_id": 2316, "title": "The Office", "year": 2005, "media_type": "episode"},
            {"tmdb_id": 2996, "title": "The Office", "year": 2001, "media_type": "episode"},
        ]
    return []


def _mock_get_show(tmdb_id: int, token: str, **kwargs: object) -> dict:
    if tmdb_id == 1396:
        return {
            "tmdb_id": 1396,
            "title": "Breaking Bad",
            "year": 2008,
            "media_type": "episode",
            "seasons": [1, 2, 3, 4, 5],
        }
    return {}


def _mock_get_season_episodes(
    show_id: int,
    season_number: int,
    token: str,
    show_title: str = "",
    show_year: int | None = None,
    **kwargs: object,
) -> list[dict]:
    if show_id == 1396 and season_number == 1:
        return [
            {
                "tmdb_id": 1396,
                "title": "Breaking Bad",
                "year": 2008,
                "media_type": "episode",
                "season": 1,
                "episode": 1,
                "episode_title": "Pilot",
            },
            {
                "tmdb_id": 1396,
                "title": "Breaking Bad",
                "year": 2008,
                "media_type": "episode",
                "season": 1,
                "episode": 2,
                "episode_title": "Cat's in the Bag...",
            },
            {
                "tmdb_id": 1396,
                "title": "Breaking Bad",
                "year": 2008,
                "media_type": "episode",
                "season": 1,
                "episode": 3,
                "episode_title": "...And the Bag's in the River",
            },
        ]
    return []


def _make_config(token: str = ""):
    """Create a TapesConfig with the given token."""
    from tapes.config import TapesConfig

    return TapesConfig(metadata={"tmdb_token": token})  # ty: ignore[invalid-argument-type]  # Pydantic dict coercion


def _patch_tmdb():
    """Patch all tapes.tmdb functions used by pipeline."""
    return [
        patch("tapes.tmdb.search_multi", side_effect=_mock_search_multi),
        patch("tapes.tmdb.get_show", side_effect=_mock_get_show),
        patch("tapes.tmdb.get_season_episodes", side_effect=_mock_get_season_episodes),
    ]


@pytest.fixture
def mock_tmdb():
    """Patch all tapes.tmdb functions used by pipeline."""
    patches = _patch_tmdb()
    with patches[0], patches[1], patches[2]:
        yield


class TestRunAutoPipeline:
    def test_populates_result_no_filename_source(self, mock_tmdb) -> None:
        model = _make_model("Dune.2021.1080p.BluRay.mkv")
        run_auto_pipeline(model, token=TOKEN)
        node = model.all_files()[0]
        assert node.metadata.get("title") is not None
        # Filename extraction is the base layer, not a source
        filename_sources = [s for s in node.candidates if s.name == "from filename"]
        assert len(filename_sources) == 0

    def test_confident_match_auto_stages(self, mock_tmdb) -> None:
        model = _make_model("Dune.2021.1080p.BluRay.mkv")
        run_auto_pipeline(model, token=TOKEN)
        node = model.all_files()[0]
        assert node.staged is True
        # A3: candidates cleared after auto-accept (movie identified, no stale candidates)
        assert len(node.candidates) == 0
        assert node.metadata["year"] == 2021

    def test_clear_winner_no_year_auto_staged(self, mock_tmdb) -> None:
        """Without year but clear winner (prominent gap to second), auto-staged."""
        model = _make_model("Breaking.Bad.S01E01.720p.mkv")
        run_auto_pipeline(model, token=TOKEN)
        node = model.all_files()[0]
        assert node.staged is True

    def test_title_only_auto_stages_with_low_threshold(self, mock_tmdb) -> None:
        """With a low threshold, title-only matches can auto-stage."""
        model = _make_model("Breaking.Bad.S01E01.720p.mkv")
        run_auto_pipeline(model, token=TOKEN, min_score=0.5)
        node = model.all_files()[0]
        assert node.staged is True
        assert node.metadata["year"] == 2008

    def test_no_tmdb_match_no_sources(self, mock_tmdb) -> None:
        model = _make_model("Unknown.Movie.2024.mkv")
        run_auto_pipeline(model, token=TOKEN)
        node = model.all_files()[0]
        assert len(node.candidates) == 0
        assert node.staged is False

    def test_multiple_files_processed(self, mock_tmdb) -> None:
        model = _make_model(
            "Dune.2021.mkv",
            "Arrival.2016.mkv",
            "Unknown.Movie.mkv",
        )
        run_auto_pipeline(model, token=TOKEN)
        files = model.all_files()
        assert files[0].staged is True  # Dune
        assert files[1].staged is True  # Arrival
        assert files[2].staged is False  # Unknown

    def test_guessit_populates_result_directly(self, mock_tmdb) -> None:
        model = _make_model("Breaking.Bad.S01E01.720p.BluRay.x264.mkv")
        run_auto_pipeline(model, token=TOKEN)
        node = model.all_files()[0]
        # guessit populates result directly (base layer), not as a source
        assert node.metadata.get("title") == "Breaking Bad"
        assert node.metadata.get("season") == 1
        assert node.metadata.get("episode") == 1
        # No "from filename" source
        filename_sources = [s for s in node.candidates if s.name == "from filename"]
        assert len(filename_sources) == 0

    def test_tmdb_episode_data_merged(self, mock_tmdb) -> None:
        """With low threshold, episode data is fetched and merged."""
        model = _make_model("Breaking.Bad.S01E01.mkv")
        run_auto_pipeline(model, token=TOKEN, min_score=0.5)
        node = model.all_files()[0]
        tmdb_candidates = [s for s in node.candidates if s.name.startswith("TMDB")]
        assert len(tmdb_candidates) >= 1
        # At least one source should have episode_title
        ep_titles = [s.metadata.get("episode_title") for s in tmdb_candidates]
        assert "Pilot" in ep_titles

    def test_custom_min_score(self, mock_tmdb) -> None:
        model = _make_model("Breaking.Bad.S01E01.mkv")
        run_auto_pipeline(model, token=TOKEN, min_score=0.5)
        node = model.all_files()[0]
        assert node.staged is True

    def test_no_token_skips_tmdb(self) -> None:
        """Without a token, only guessit runs -- no sources at all."""
        model = _make_model("Dune.2021.mkv")
        run_auto_pipeline(model, token="")
        node = model.all_files()[0]
        assert len(node.candidates) == 0
        assert node.staged is False


class TestTwoStageFlow:
    def test_movie_auto_accept_no_episode_stage(self, mock_tmdb) -> None:
        """Movie match should not trigger episode stage."""
        model = _make_model("Dune.2021.mkv")
        run_auto_pipeline(model, token=TOKEN)
        node = model.all_files()[0]
        assert node.metadata["media_type"] == "movie"
        assert node.staged is True
        # A3: candidates cleared after auto-accept (movie identified)
        assert len(node.candidates) == 0

    def test_tv_show_triggers_episode_stage(self, mock_tmdb) -> None:
        """TV show match should fetch episodes."""
        model = _make_model("Breaking.Bad.S01E01.mkv")
        # Episode confidence is 0.8 (ep=0.6 + season=0.2), so use lower threshold
        run_auto_pipeline(model, token=TOKEN, min_score=0.7)
        node = model.all_files()[0]
        assert node.metadata["media_type"] == "episode"
        # Should have episode-level TMDB sources
        tmdb_candidates = [s for s in node.candidates if s.name.startswith("TMDB")]
        assert len(tmdb_candidates) >= 1
        # Best match should have episode data
        assert node.metadata.get("episode_title") == "Pilot"

    def test_auto_accepted_tv_show_has_episode_sources_only(self, mock_tmdb) -> None:
        """Auto-accepted TV show should have only episode-level TMDB sources.
        A3: show-level candidates are cleared after auto-accept; episode query
        adds fresh episode-specific candidates afterward."""
        model = _make_model("Breaking.Bad.S01E01.mkv")
        run_auto_pipeline(model, token=TOKEN, min_score=0.5)
        node = model.all_files()[0]
        tmdb_candidates = [s for s in node.candidates if s.name.startswith("TMDB")]
        show_candidates = [s for s in tmdb_candidates if "episode_title" not in s.metadata]
        episode_sources = [s for s in tmdb_candidates if "episode_title" in s.metadata]
        # A3: show-level candidates cleared, only episode candidates remain
        assert len(show_candidates) == 0, f"Expected no show-level sources, got: {show_candidates}"
        assert len(episode_sources) >= 1, f"Expected episode sources, got: {tmdb_candidates}"

    def test_tv_show_no_episode_match(self) -> None:
        """TV show match with no matching episode keeps show-level sources.

        Uses low min_score because guessit doesn't extract year from
        'Breaking.Bad.S01E01.mkv', so show score is 0.7.
        """

        def mock_empty_episodes(*args, **kwargs):
            return []

        with (
            _patch_tmdb()[0],
            _patch_tmdb()[1],
            patch("tapes.tmdb.get_season_episodes", side_effect=mock_empty_episodes),
        ):
            model = _make_model("Breaking.Bad.S01E01.mkv")
            run_auto_pipeline(model, token=TOKEN, min_score=0.5)
            node = model.all_files()[0]
            # Show match should still apply
            assert node.metadata["title"] == "Breaking Bad"
            assert node.staged is True


class TestMultipleSourcesNoAutoAccept:
    """When auto-accept doesn't fire, all search results should become sources."""

    def test_low_confidence_shows_all_sources(self, mock_tmdb) -> None:
        """The Office returns 2 results. With a very high threshold, auto-accept
        doesn't fire and both should appear as TMDB sources on the node."""
        model = _make_model("The.Office.S01E01.mkv")
        # Very high threshold so auto-accept doesn't fire
        run_auto_pipeline(model, token=TOKEN, min_score=0.99)
        node = model.all_files()[0]
        tmdb_candidates = [s for s in node.candidates if s.name.startswith("TMDB")]
        assert len(tmdb_candidates) == 2, f"Expected 2 sources, got {len(tmdb_candidates)}: {tmdb_candidates}"
        assert node.staged is False

    def test_can_stage_fail_still_gets_episode_sources(self, mock_tmdb) -> None:
        """When show auto-accepts but can_stage fails (incomplete template),
        the episode query should still run so the user gets episode-level sources."""
        model = _make_model("Breaking.Bad.S01E01.mkv")

        def _always_reject(node, merged):
            return False

        run_auto_pipeline(model, token=TOKEN, min_score=0.5, can_stage=_always_reject)
        node = model.all_files()[0]
        tmdb_candidates = [s for s in node.candidates if s.name.startswith("TMDB")]
        # Should have episode-level sources, not just show-level
        ep_titles = [s.metadata.get("episode_title") for s in tmdb_candidates]
        assert any(ep_titles), f"Expected episode sources with episode_title, got: {tmdb_candidates}"
        assert len(tmdb_candidates) >= 2, f"Expected multiple episode sources, got {len(tmdb_candidates)}"


class TestTwoTierAutoAccept:
    """Tests for margin-based auto-accept (tier 2)."""

    def test_clear_winner_with_year_auto_accepts(self, mock_tmdb) -> None:
        """Breaking Bad with year: tier 1 auto-accept (similarity ~1.0)."""
        model = _make_model("Breaking.Bad.2008.S01E01.mkv")
        run_auto_pipeline(model, token=TOKEN)
        node = model.all_files()[0]
        assert node.staged is True

    def test_clear_winner_no_year_auto_accepts_via_margin(self, mock_tmdb) -> None:
        """Breaking Bad without year: tier 2 auto-accept.

        Best similarity ~0.7 (exact title, no year) vs second ~0.48
        (subset match). Margin ~0.22 >= 0.15, so tier 2 accepts.
        """
        model = _make_model("Breaking.Bad.S01E01.mkv")
        run_auto_pipeline(model, token=TOKEN)
        node = model.all_files()[0]
        assert node.staged is True
        assert node.metadata["title"] == "Breaking Bad"

    def test_ambiguous_candidates_no_auto_accept(self, mock_tmdb) -> None:
        """The Office without year: two equally-named shows, no clear winner."""
        model = _make_model("The.Office.S01E01.mkv")
        run_auto_pipeline(model, token=TOKEN)
        node = model.all_files()[0]
        assert node.staged is False
        # Both sources available for user curation
        tmdb_candidates = [s for s in node.candidates if s.name.startswith("TMDB")]
        assert len(tmdb_candidates) == 2


# ---------------------------------------------------------------------------
# Refresh TMDB source
# ---------------------------------------------------------------------------


class TestRefreshTmdbBatch:
    """Tests for batch refresh with cache and dedup."""

    def test_batch_refreshes_multiple_nodes(self, mock_tmdb) -> None:
        """All nodes in the batch get refreshed and auto-accepted."""
        from tapes.pipeline import refresh_tmdb_batch

        node1 = FileNode(
            path=Path("/media/Dune.mkv"),
            metadata={"title": "Dune", "year": 2021},
            candidates=[Candidate(name="TMDB #1", metadata={"title": "Old"}, score=0.5)],
        )
        node2 = FileNode(
            path=Path("/media/Arrival.mkv"),
            metadata={"title": "Arrival", "year": 2016},
            candidates=[],
        )
        refresh_tmdb_batch([node1, node2], token=TOKEN)
        # A3: auto-accept fires for both movies, clearing candidates
        for n in [node1, node2]:
            assert len(n.candidates) == 0
            assert n.metadata.get("tmdb_id") is not None
            assert n.staged is True

    def test_batch_deduplicates_queries(self, mock_tmdb) -> None:
        """Nodes with same title/year share a single search_multi call."""
        from tapes.pipeline import refresh_tmdb_batch

        node1 = FileNode(
            path=Path("/media/show.s01e01.mkv"),
            metadata={"title": "Breaking Bad", "season": 1, "episode": 1, "media_type": "episode"},
            candidates=[],
        )
        node2 = FileNode(
            path=Path("/media/show.s01e01.nfo"),
            metadata={"title": "Breaking Bad", "season": 1, "episode": 1, "media_type": "episode"},
            candidates=[],
        )
        with patch("tapes.tmdb.search_multi", side_effect=_mock_search_multi) as mock_search:
            refresh_tmdb_batch([node1, node2], token=TOKEN)
            # Cache dedup: search_multi called once, not twice
            assert mock_search.call_count == 1

    def test_batch_clears_existing_tmdb_candidates(self, mock_tmdb) -> None:
        """Existing TMDB sources are cleared before refresh."""
        from tapes.pipeline import refresh_tmdb_batch

        node = FileNode(
            path=Path("/media/Dune.mkv"),
            metadata={"title": "Dune", "year": 2021},
            candidates=[Candidate(name="TMDB #1", metadata={"title": "Old"}, score=0.1)],
        )
        refresh_tmdb_batch([node], token=TOKEN)
        tmdb_candidates = [s for s in node.candidates if s.name.startswith("TMDB")]
        assert all(s.metadata.get("title") != "Old" for s in tmdb_candidates)

    def test_batch_reports_progress(self, mock_tmdb) -> None:
        """on_progress callback is invoked after each node."""
        from tapes.pipeline import refresh_tmdb_batch

        progress_calls: list[tuple[int, int]] = []

        def on_progress(done: int, total: int) -> None:
            progress_calls.append((done, total))

        nodes = [
            FileNode(path=Path(f"/media/file{i}.mkv"), metadata={"title": "Dune", "year": 2021}, candidates=[])
            for i in range(3)
        ]
        refresh_tmdb_batch(nodes, token=TOKEN, on_progress=on_progress)
        assert len(progress_calls) == 3
        assert progress_calls[-1] == (3, 3)


class TestRefreshTmdbSource:
    def test_updates_tmdb_source(self, mock_tmdb) -> None:
        node = FileNode(
            path=Path("/media/Dune.mkv"),
            metadata={"title": "Dune", "year": 2021},
            candidates=[],
        )
        refresh_tmdb_source(node, token=TOKEN)
        # A3: auto-accept fires (score 1.0) and clears candidates
        assert len(node.candidates) == 0
        assert node.metadata.get("tmdb_id") == 438631
        assert node.staged is True

    def test_updates_tmdb_source_no_year(self, mock_tmdb) -> None:
        """Without year, confidence is penalized (0.7, not 1.0) but still auto-accepts."""
        node = FileNode(
            path=Path("/media/Dune.mkv"),
            metadata={"title": "Dune"},
            candidates=[],
        )
        refresh_tmdb_source(node, token=TOKEN)
        # A3: auto-accept fires (single candidate, score 0.7 >= 0.6) and clears candidates
        assert len(node.candidates) == 0
        assert node.metadata.get("tmdb_id") == 438631
        assert node.staged is True

    def test_replaces_existing_tmdb_source(self, mock_tmdb) -> None:
        node = FileNode(
            path=Path("/media/Dune.mkv"),
            metadata={"title": "Dune", "year": 2021},
            candidates=[
                Candidate(name="TMDB #1", metadata={"title": "Old"}, score=0.5),
            ],
        )
        refresh_tmdb_source(node, token=TOKEN)
        # A3: auto-accept fires and clears candidates
        assert len(node.candidates) == 0
        assert node.metadata.get("tmdb_id") == 438631

    def test_no_match_removes_tmdb_source(self, mock_tmdb) -> None:
        node = FileNode(
            path=Path("/media/Unknown.mkv"),
            metadata={"title": "Nonexistent"},
            candidates=[
                Candidate(name="TMDB #1", metadata={"title": "Old"}, score=0.5),
            ],
        )
        refresh_tmdb_source(node, token=TOKEN)
        tmdb_candidates = [s for s in node.candidates if s.name.startswith("TMDB")]
        assert len(tmdb_candidates) == 0

    def test_confident_auto_accepts_with_year(self, mock_tmdb) -> None:
        node = FileNode(
            path=Path("/media/Dune.mkv"),
            metadata={"title": "Dune", "year": 2021},
            candidates=[],
        )
        refresh_tmdb_source(node, token=TOKEN)
        assert node.metadata.get("year") == 2021
        assert node.staged is True

    def test_clear_winner_auto_accepts_via_margin(self, mock_tmdb) -> None:
        """Breaking Bad without year: tier 2 auto-accept (clear margin to El Camino)."""
        node = FileNode(
            path=Path("/media/test.mkv"),
            metadata={"title": "Breaking Bad"},
            candidates=[],
        )
        refresh_tmdb_source(node, token=TOKEN)
        # Tier 2 accepts: 0.7 >= 0.6 and margin ~0.22 >= 0.15
        assert node.metadata.get("year") == 2008
        assert node.staged is True

    def test_no_token_skips(self) -> None:
        node = FileNode(
            path=Path("/media/Dune.mkv"),
            metadata={"title": "Dune"},
            candidates=[],
        )
        refresh_tmdb_source(node, token="")
        tmdb_candidates = [s for s in node.candidates if s.name.startswith("TMDB")]
        assert len(tmdb_candidates) == 0


try:
    from textual.pilot import Pilot  # noqa: F401

    HAS_PILOT = True
except ImportError:
    HAS_PILOT = False


@pytest.mark.skipif(not HAS_PILOT, reason="textual pilot not available")
class TestAutoPipelineIntegration:
    @pytest.mark.asyncio()
    async def test_auto_pipeline_runs_on_mount(self, mock_tmdb) -> None:
        from tapes.ui.tree_app import TreeApp

        model = _make_model("Dune.2021.1080p.BluRay.mkv")
        config_obj = _make_config(TOKEN)
        _tmpl = "{title} ({year}).{ext}"
        app = TreeApp(
            model=model,
            movie_template=_tmpl,
            tv_template=_tmpl,
            auto_pipeline=True,
            config=config_obj,
        )
        async with app.run_test() as _pilot:
            await app.workers.wait_for_complete()
            node = model.all_files()[0]
            # A3: auto-accept fires for Dune (movie), clearing candidates
            assert len(node.candidates) == 0
            assert node.metadata.get("tmdb_id") == 438631
            assert node.staged is True


@pytest.mark.skipif(not HAS_PILOT, reason="textual pilot not available")
class TestRefreshQueryIntegration:
    @pytest.mark.asyncio()
    async def test_r_in_tree_refreshes_per_file(self, mock_tmdb) -> None:
        from tapes.ui.tree_app import TreeApp

        node = FileNode(
            path=Path("/media/Dune.mkv"),
            metadata={"title": "Dune", "year": 2021},
            candidates=[],
        )
        root = FolderNode(name="root", children=[node])
        model = TreeModel(root=root)
        config_obj = _make_config(TOKEN)
        _tmpl = "{title} ({year}).{ext}"
        app = TreeApp(model=model, movie_template=_tmpl, tv_template=_tmpl, config=config_obj)

        async with app.run_test() as pilot:
            await pilot.press("r")
            await app.workers.wait_for_complete()
            # A3: auto-accept fires for Dune (movie), clearing candidates
            assert len(node.candidates) == 0
            assert node.metadata.get("tmdb_id") == 438631
            assert node.staged is True

    @pytest.mark.asyncio()
    async def test_r_in_detail_refreshes_current_node(self, mock_tmdb) -> None:
        from tapes.ui.tree_app import TreeApp

        node = FileNode(
            path=Path("/media/Arrival.mkv"),
            metadata={"title": "Arrival", "year": 2016},
            candidates=[],
        )
        folder = FolderNode(name="folder", children=[node])
        root = FolderNode(name="root", children=[folder])
        model = TreeModel(root=root)
        config_obj = _make_config(TOKEN)
        _tmpl = "{title} ({year}).{ext}"
        app = TreeApp(model=model, movie_template=_tmpl, tv_template=_tmpl, config=config_obj)

        async with app.run_test() as pilot:
            # Enter metadata view via folder
            await pilot.press("enter")
            assert app.state == AppState.METADATA
            await pilot.press("r")
            await app.workers.wait_for_complete()
            # A3: auto-accept fires for Arrival (movie), clearing candidates
            assert len(node.candidates) == 0
            assert node.metadata.get("tmdb_id") == 329865
            assert node.metadata.get("year") == 2016

    @pytest.mark.asyncio()
    async def test_r_in_tree_range_refreshes_all(self, mock_tmdb) -> None:
        from tapes.ui.tree_app import TreeApp

        node1 = FileNode(
            path=Path("/media/Dune.mkv"),
            metadata={"title": "Dune"},
            candidates=[],
        )
        node2 = FileNode(
            path=Path("/media/Arrival.mkv"),
            metadata={"title": "Arrival"},
            candidates=[],
        )
        root = FolderNode(name="root", children=[node1, node2])
        model = TreeModel(root=root)
        config_obj = _make_config(TOKEN)
        _tmpl = "{title} ({year}).{ext}"
        app = TreeApp(model=model, movie_template=_tmpl, tv_template=_tmpl, config=config_obj)

        async with app.run_test() as pilot:
            await pilot.press("v")
            await pilot.press("j")
            await pilot.press("r")
            await app.workers.wait_for_complete()
            # A3: auto-accept fires for both movies, clearing candidates
            for n in [node1, node2]:
                assert len(n.candidates) == 0
                assert n.metadata.get("tmdb_id") is not None
                assert n.staged is True

    @pytest.mark.asyncio()
    async def test_r_in_multi_detail_refreshes_all_nodes(self, mock_tmdb) -> None:
        from tapes.ui.tree_app import TreeApp

        node1 = FileNode(
            path=Path("/media/Dune.mkv"),
            metadata={"title": "Dune"},
            candidates=[],
        )
        node2 = FileNode(
            path=Path("/media/Arrival.mkv"),
            metadata={"title": "Arrival"},
            candidates=[],
        )
        root = FolderNode(name="root", children=[node1, node2])
        model = TreeModel(root=root)
        config_obj = _make_config(TOKEN)
        _tmpl = "{title} ({year}).{ext}"
        app = TreeApp(model=model, movie_template=_tmpl, tv_template=_tmpl, config=config_obj)

        async with app.run_test() as pilot:
            await pilot.press("v")
            await pilot.press("j")
            await pilot.press("enter")
            assert app.state == AppState.METADATA
            await pilot.press("r")
            await app.workers.wait_for_complete()
            # A3: auto-accept fires for both movies, clearing candidates
            for n in [node1, node2]:
                assert len(n.candidates) == 0
                assert n.metadata.get("tmdb_id") is not None
                assert n.staged is True

    @pytest.mark.asyncio()
    async def test_r_in_metadata_runs_async_with_progress(self, mock_tmdb) -> None:
        """Pressing 'r' in metadata view runs refresh asynchronously."""
        from tapes.ui.tree_app import TreeApp

        node1 = FileNode(
            path=Path("/media/Dune.mkv"),
            metadata={"title": "Dune", "year": 2021},
            candidates=[],
        )
        node2 = FileNode(
            path=Path("/media/Arrival.mkv"),
            metadata={"title": "Arrival", "year": 2016},
            candidates=[],
        )
        root = FolderNode(name="root", children=[node1, node2])
        model = TreeModel(root=root)
        config_obj = _make_config(TOKEN)
        _tmpl = "{title} ({year}).{ext}"
        app = TreeApp(model=model, movie_template=_tmpl, tv_template=_tmpl, config=config_obj)

        async with app.run_test() as pilot:
            # Enter multi-file metadata view
            await pilot.press("v")
            await pilot.press("j")
            await pilot.press("enter")
            assert app.state == AppState.METADATA
            # Press 'r' -- should not block
            await pilot.press("r")
            await app.workers.wait_for_complete()
            # A3: auto-accept fires for both movies, clearing candidates
            for n in [node1, node2]:
                assert len(n.candidates) == 0
                assert n.metadata.get("tmdb_id") is not None
                assert n.staged is True


@pytest.mark.skipif(not HAS_PILOT, reason="textual pilot not available")
class TestMultiMetadataAcceptTriggersEpisodeQuery:
    """Accepting a show candidate in multi-file metadata view must trigger episode queries
    for ALL files, not just the cursor node."""

    @pytest.mark.asyncio()
    async def test_accept_candidate_refreshes_all_files(self, mock_tmdb) -> None:
        """Select 3 episode files, open multi-file metadata view, accept show candidate.
        All 3 files should get episode data from the refresh, not just the last."""
        from tapes.ui.tree_app import TreeApp

        # 3 episode files with show-level TMDB sources but no tmdb_id in result.
        # Simulates: auto-pipeline found Breaking Bad but didn't auto-accept.
        show_candidate = Candidate(
            name="TMDB #1",
            metadata={"tmdb_id": 1396, "title": "Breaking Bad", "year": 2008, "media_type": "episode"},
            score=0.7,
        )
        node1 = FileNode(
            path=Path("/media/Breaking.Bad.S01E01.mkv"),
            metadata={"title": "Breaking Bad", "season": 1, "episode": 1, "media_type": "episode"},
            candidates=[
                Candidate(
                    name=show_candidate.name,
                    metadata=dict(show_candidate.metadata),
                    score=show_candidate.score,
                ),
            ],
        )
        node2 = FileNode(
            path=Path("/media/Breaking.Bad.S01E02.mkv"),
            metadata={"title": "Breaking Bad", "season": 1, "episode": 2, "media_type": "episode"},
            candidates=[
                Candidate(
                    name=show_candidate.name,
                    metadata=dict(show_candidate.metadata),
                    score=show_candidate.score,
                ),
            ],
        )
        node3 = FileNode(
            path=Path("/media/Breaking.Bad.S01E03.mkv"),
            metadata={"title": "Breaking Bad", "season": 1, "episode": 3, "media_type": "episode"},
            candidates=[
                Candidate(
                    name=show_candidate.name,
                    metadata=dict(show_candidate.metadata),
                    score=show_candidate.score,
                ),
            ],
        )
        root = FolderNode(name="root", children=[node1, node2, node3])
        model = TreeModel(root=root)
        config_obj = _make_config(TOKEN)
        tv_tmpl = "{title} ({year})/Season {season:02d}/{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"
        app = TreeApp(
            model=model,
            movie_template="{title} ({year}).{ext}",
            tv_template=tv_tmpl,
            config=config_obj,
        )

        async with app.run_test() as pilot:
            # Select all 3 files: start range, move down twice
            await pilot.press("v")
            await pilot.press("j")
            await pilot.press("j")
            # Open multi-file metadata view
            await pilot.press("enter")
            assert app.state == AppState.METADATA
            # Accept the candidate (focus_column defaults to "candidate")
            # This writes tmdb_id/title/year/media_type to all 3 nodes
            await pilot.press("enter")
            # Wait for TMDB refresh workers to complete
            await app.workers.wait_for_complete()
            # ALL nodes should have episode_title (from episode query)
            for node in [node1, node2, node3]:
                assert node.metadata.get("tmdb_id") == 1396, f"{node.path}: missing tmdb_id"
                assert node.metadata.get("episode_title") is not None, (
                    f"{node.path}: missing episode_title -- episode query didn't run"
                )
                assert node.staged is True, f"{node.path}: not staged after episode accept"


class TestTmdbCache:
    def test_failure_returns_none_not_deadlock(self) -> None:
        """If fetch_fn raises, waiting threads get None (not deadlock)."""
        import threading

        from tapes.pipeline import _TmdbCache

        cache = _TmdbCache()

        def bad_fetch():
            raise RuntimeError("TMDB down")

        # First call returns None on failure
        result = cache.get_or_fetch(("key",), bad_fetch)
        assert result is None

        # Second call with same key also returns None (not deadlock)
        results: list[object] = []

        def try_fetch():
            r = cache.get_or_fetch(("key",), bad_fetch)
            results.append(r)

        t = threading.Thread(target=try_fetch)
        t.start()
        t.join(timeout=2.0)
        assert not t.is_alive(), "Thread deadlocked waiting for failed fetch"
        assert results == [None]


class TestExtractGuessitFields:
    def test_extracts_title_and_year(self) -> None:
        from tapes.pipeline import extract_guessit_fields

        fields = extract_guessit_fields("Inception.2010.mkv")
        assert fields["title"] == "Inception"
        assert fields["year"] == 2010

    def test_extracts_tv_fields(self) -> None:
        from tapes.pipeline import extract_guessit_fields

        fields = extract_guessit_fields("Breaking.Bad.S01E01.mkv")
        assert fields["title"] == "Breaking Bad"
        assert fields["season"] == 1
        assert fields["episode"] == 1

    def test_missing_fields_omitted(self) -> None:
        from tapes.pipeline import extract_guessit_fields

        fields = extract_guessit_fields("something.mkv")
        assert "year" not in fields or fields.get("year") is None


# ---------------------------------------------------------------------------
# Config parameter forwarding
# ---------------------------------------------------------------------------


class TestConfigForwarding:
    """Tests that pipeline functions forward config values to tmdb and similarity."""

    def test_run_tmdb_pass_forwards_max_results(self, mock_tmdb) -> None:
        """max_results param limits TMDB source count."""
        from tapes.pipeline import run_tmdb_pass

        # The Office returns 2 candidates. With max_results=1 only 1 should be kept.
        model = _make_model("The.Office.S01E01.mkv")
        # Run guessit first to populate result
        from tapes.pipeline import run_guessit_pass

        run_guessit_pass(model)
        run_tmdb_pass(model, token=TOKEN, max_results=1)
        node = model.all_files()[0]
        tmdb_candidates = [s for s in node.candidates if s.name.startswith("TMDB")]
        assert len(tmdb_candidates) <= 1

    def test_run_tmdb_pass_default_max_results_keeps_all(self, mock_tmdb) -> None:
        """Default max_results=3 keeps all candidates when fewer than 3."""
        from tapes.pipeline import run_guessit_pass, run_tmdb_pass

        model = _make_model("The.Office.S01E01.mkv")
        run_guessit_pass(model)
        run_tmdb_pass(model, token=TOKEN)
        node = model.all_files()[0]
        tmdb_candidates = [s for s in node.candidates if s.name.startswith("TMDB")]
        assert len(tmdb_candidates) == 2

    def test_run_auto_pipeline_forwards_max_results(self, mock_tmdb) -> None:
        """max_results flows from run_auto_pipeline through to sources."""
        model = _make_model("The.Office.S01E01.mkv")
        run_auto_pipeline(model, token=TOKEN, max_results=1)
        node = model.all_files()[0]
        tmdb_candidates = [s for s in node.candidates if s.name.startswith("TMDB")]
        assert len(tmdb_candidates) <= 1

    def test_refresh_forwards_max_results(self, mock_tmdb) -> None:
        """refresh_tmdb_source respects max_results."""
        node = FileNode(
            path=Path("/media/The.Office.mkv"),
            metadata={"title": "The Office"},
            candidates=[],
        )
        refresh_tmdb_source(node, token=TOKEN, max_results=1)
        tmdb_candidates = [s for s in node.candidates if s.name.startswith("TMDB")]
        assert len(tmdb_candidates) <= 1

    def test_high_min_prominence_prevents_auto_accept(self, mock_tmdb) -> None:
        """High min_prominence prevents auto-accept."""
        # Breaking Bad without year: prominence ~0.22.
        # Set min_prominence=0.99 so it won't accept.
        model = _make_model("Breaking.Bad.S01E01.mkv")
        run_auto_pipeline(model, token=TOKEN, min_prominence=0.99)
        node = model.all_files()[0]
        assert node.staged is False

    def test_moderate_min_prominence_prevents_auto_accept(self, mock_tmdb) -> None:
        """Moderate min_prominence prevents auto-accept when prominence is small."""
        # Breaking Bad without year: prominence ~0.22. Set min_prominence=0.5 to block.
        model = _make_model("Breaking.Bad.S01E01.mkv")
        run_auto_pipeline(model, token=TOKEN, min_prominence=0.5)
        node = model.all_files()[0]
        assert node.staged is False

    def test_lenient_min_prominence_allows_auto_accept(self, mock_tmdb) -> None:
        """Lenient min_prominence allows auto-accept."""
        model = _make_model("Breaking.Bad.S01E01.mkv")
        run_auto_pipeline(model, token=TOKEN, min_prominence=0.1)
        node = model.all_files()[0]
        assert node.staged is True

    def test_refresh_forwards_min_prominence(self, mock_tmdb) -> None:
        """refresh_tmdb_source forwards min_prominence."""
        node = FileNode(
            path=Path("/media/test.mkv"),
            metadata={"title": "Breaking Bad"},
            candidates=[],
        )
        # With strict min_prominence, auto-accept should be blocked
        refresh_tmdb_source(node, token=TOKEN, min_prominence=0.99)
        assert node.staged is False

    def test_tmdb_timeout_forwarded_to_create_client(self, mock_tmdb) -> None:
        """tmdb_timeout is passed to tmdb.create_client."""
        from tapes import tmdb
        from tapes.pipeline import run_guessit_pass, run_tmdb_pass

        model = _make_model("Dune.2021.mkv")
        run_guessit_pass(model)
        with patch("tapes.tmdb.create_client", wraps=tmdb.create_client) as mock_create:
            run_tmdb_pass(model, token=TOKEN, tmdb_timeout=42.0)
            mock_create.assert_called_once_with(TOKEN, timeout=42.0)

    def test_tmdb_retries_forwarded_to_search(self, mock_tmdb) -> None:
        """tmdb_retries is forwarded to tmdb.search_multi via max_retries."""
        from tapes.pipeline import run_guessit_pass, run_tmdb_pass

        model = _make_model("Dune.2021.mkv")
        run_guessit_pass(model)
        with patch("tapes.tmdb.search_multi", side_effect=_mock_search_multi) as mock_search:
            run_tmdb_pass(model, token=TOKEN, tmdb_retries=7)
            assert mock_search.call_count == 1
            call_kwargs = mock_search.call_args
            assert call_kwargs.kwargs.get("max_retries") == 7

    def test_episode_max_results_limits_sources(self, mock_tmdb) -> None:
        """max_results limits episode sources in stage 2."""
        model = _make_model("Breaking.Bad.S01E01.mkv")
        # Low threshold to trigger episode stage
        run_auto_pipeline(model, token=TOKEN, min_score=0.5, max_results=1)
        node = model.all_files()[0]
        tmdb_candidates = [s for s in node.candidates if s.name.startswith("TMDB")]
        episode_sources = [s for s in tmdb_candidates if "episode_title" in s.metadata]
        show_candidates = [s for s in tmdb_candidates if "episode_title" not in s.metadata]
        # Even though 3 episodes are available, only max_results=1 kept
        assert len(episode_sources) == 1
        # A3: show-level candidates cleared after auto-accept
        assert len(show_candidates) == 0


class TestTmdbIdShortcut:
    """When tmdb_id is already set, skip show search and go to episodes."""

    def test_skips_search_when_tmdb_id_set_for_tv(self, mock_tmdb) -> None:
        """With tmdb_id + media_type=episode, skip search_multi, query episodes directly."""
        node = FileNode(
            path=Path("/media/Breaking.Bad.S01E02.mkv"),
            metadata={
                "title": "Breaking Bad",
                "year": 2008,
                "tmdb_id": 1396,
                "media_type": "episode",
                "season": 1,
                "episode": 2,
            },
            candidates=[],
        )
        with patch("tapes.tmdb.search_multi", side_effect=_mock_search_multi) as mock_search:
            refresh_tmdb_source(node, token=TOKEN)
            mock_search.assert_not_called()
        # Should still have episode sources from direct episode query
        tmdb_candidates = [s for s in node.candidates if s.name.startswith("TMDB")]
        assert len(tmdb_candidates) >= 1
        # Best episode should be S01E02
        assert node.metadata.get("episode") == 2
        assert node.metadata.get("episode_title") == "Cat's in the Bag..."

    def test_skips_search_when_tmdb_id_set_for_movie(self, mock_tmdb) -> None:
        """With tmdb_id + media_type=movie, skip entirely (movie fully identified)."""
        node = FileNode(
            path=Path("/media/Dune.mkv"),
            metadata={
                "title": "Dune",
                "year": 2021,
                "tmdb_id": 438631,
                "media_type": "movie",
            },
            candidates=[],
        )
        with patch("tapes.tmdb.search_multi", side_effect=_mock_search_multi) as mock_search:
            refresh_tmdb_source(node, token=TOKEN)
            mock_search.assert_not_called()
        # No sources added (movie already identified)
        assert len(node.candidates) == 0

    def test_normal_flow_without_tmdb_id(self, mock_tmdb) -> None:
        """Without tmdb_id, normal search_multi flow is used."""
        node = FileNode(
            path=Path("/media/Dune.mkv"),
            metadata={"title": "Dune", "year": 2021},
            candidates=[],
        )
        with patch("tapes.tmdb.search_multi", side_effect=_mock_search_multi) as mock_search:
            refresh_tmdb_source(node, token=TOKEN)
            mock_search.assert_called_once()


class TestEpisodeConfidenceGate:
    """Episode application should respect confidence threshold."""

    def test_low_confidence_episode_not_applied(self, mock_tmdb) -> None:
        """When episode confidence is low, don't overwrite result fields."""
        node = FileNode(
            path=Path("/media/Breaking.Bad.S03E05.mkv"),
            metadata={
                "title": "Breaking Bad",
                "year": 2008,
                "tmdb_id": 1396,
                "media_type": "episode",
                "season": 3,
                "episode": 5,
            },
            candidates=[],
        )
        # Mock returns only season 1 episodes. Season 3 won't match,
        # so episode confidence will be low (season mismatch).
        refresh_tmdb_source(node, token=TOKEN)
        # Season/episode should NOT be overwritten to S01E01
        assert node.metadata["season"] == 3
        assert node.metadata["episode"] == 5
        # But episode sources should still be added for curation
        tmdb_candidates = [s for s in node.candidates if s.name.startswith("TMDB")]
        assert len(tmdb_candidates) >= 1

    def test_high_confidence_episode_applied(self, mock_tmdb) -> None:
        """When episode confidence is high, apply as before."""
        node = FileNode(
            path=Path("/media/Breaking.Bad.S01E01.mkv"),
            metadata={
                "title": "Breaking Bad",
                "year": 2008,
                "tmdb_id": 1396,
                "media_type": "episode",
                "season": 1,
                "episode": 1,
            },
            candidates=[],
        )
        refresh_tmdb_source(node, token=TOKEN)
        assert node.metadata.get("episode_title") == "Pilot"
        assert node.staged is True

    def test_low_confidence_episode_not_staged(self, mock_tmdb) -> None:
        """When episode confidence is low, node should not be staged."""
        node = FileNode(
            path=Path("/media/Breaking.Bad.S03E05.mkv"),
            metadata={
                "title": "Breaking Bad",
                "year": 2008,
                "tmdb_id": 1396,
                "media_type": "episode",
                "season": 3,
                "episode": 5,
            },
            candidates=[],
        )
        refresh_tmdb_source(node, token=TOKEN)
        assert node.staged is False


class TestEpisodeQueryAllSeasons:
    """Invariant #3: episode query fetches ALL seasons, no early stopping."""

    def test_queries_all_seasons(self, mock_tmdb) -> None:
        """Episode query must call get_season_episodes for every season,
        even when a confident match is found in the first season tried."""
        node = FileNode(
            path=Path("/media/Breaking.Bad.S01E01.mkv"),
            metadata={
                "title": "Breaking Bad",
                "year": 2008,
                "tmdb_id": 1396,
                "media_type": "episode",
                "season": 1,
                "episode": 1,
            },
            candidates=[],
        )
        # Override get_season_episodes to count calls per season
        with patch("tapes.tmdb.get_season_episodes", side_effect=_mock_get_season_episodes) as mock_eps:
            refresh_tmdb_source(node, token=TOKEN)
            # get_show returns seasons [1,2,3,4,5]. ALL must be queried.
            assert mock_eps.call_count == 5, f"Expected 5 season queries (one per season), got {mock_eps.call_count}"


class TestAcceptCurrentCandidate:
    """Tests for MetadataView.accept_current_candidate preserving per-file fields."""

    def test_preserves_fields_not_in_source(self) -> None:
        """Accepting a show-level source should not wipe season/episode."""
        from tapes.ui.metadata_view import MetadataView

        node = FileNode(
            path=Path("/media/Breaking.Bad.S01E01.mkv"),
            metadata={
                "title": "breaking bad",
                "season": 1,
                "episode": 1,
                "media_type": "episode",
            },
            candidates=[
                Candidate(
                    name="TMDB #1",
                    metadata={"tmdb_id": 1396, "title": "Breaking Bad", "year": 2008, "media_type": "episode"},
                    score=0.7,
                ),
            ],
        )
        dv = MetadataView(node, movie_template="{title}.{ext}", tv_template="{title}.{ext}")
        dv._size = (120, 40)  # fake size for field computation
        dv.fields = ["title", "year", "season", "episode", "media_type", "tmdb_id"]
        dv.candidate_index = 0
        dv.accept_current_candidate()
        # Show-level fields applied
        assert node.metadata["tmdb_id"] == 1396
        assert node.metadata["title"] == "Breaking Bad"
        assert node.metadata["year"] == 2008
        # Per-file fields preserved (not popped)
        assert node.metadata["season"] == 1
        assert node.metadata["episode"] == 1

    def test_preserves_per_file_fields_multi_node(self) -> None:
        """Multi-node: each node keeps its own season/episode."""
        from tapes.ui.metadata_view import MetadataView

        node1 = FileNode(
            path=Path("/media/show.s01e01.mkv"),
            metadata={"title": "show", "season": 1, "episode": 1, "media_type": "episode"},
            candidates=[
                Candidate(
                    name="TMDB #1",
                    metadata={"tmdb_id": 100, "title": "Show", "year": 2020, "media_type": "episode"},
                    score=0.7,
                ),
            ],
        )
        node2 = FileNode(
            path=Path("/media/show.s02e05.mkv"),
            metadata={"title": "show", "season": 2, "episode": 5, "media_type": "episode"},
            candidates=[],
        )
        dv = MetadataView(node1, movie_template="{title}.{ext}", tv_template="{title}.{ext}")
        dv._size = (120, 40)
        dv.file_nodes = [node1, node2]
        dv.fields = ["title", "year", "season", "episode", "media_type", "tmdb_id"]
        dv.candidate_index = 0
        dv.accept_current_candidate()
        # Show-level fields applied to both
        assert node1.metadata["tmdb_id"] == 100
        assert node2.metadata["tmdb_id"] == 100
        # Per-file season/episode preserved
        assert node1.metadata["season"] == 1
        assert node1.metadata["episode"] == 1
        assert node2.metadata["season"] == 2
        assert node2.metadata["episode"] == 5

    def test_sets_fields_present_in_source(self) -> None:
        """Fields present in the source should be set on all nodes."""
        from tapes.ui.metadata_view import MetadataView

        node = FileNode(
            path=Path("/media/test.mkv"),
            metadata={"title": "old title"},
            candidates=[
                Candidate(
                    name="TMDB #1",
                    metadata={"title": "New Title", "year": 2020},
                    score=0.9,
                ),
            ],
        )
        dv = MetadataView(node, movie_template="{title}.{ext}", tv_template="{title}.{ext}")
        dv._size = (120, 40)
        dv.fields = ["title", "year"]
        dv.candidate_index = 0
        dv.accept_current_candidate()
        assert node.metadata["title"] == "New Title"
        assert node.metadata["year"] == 2020
