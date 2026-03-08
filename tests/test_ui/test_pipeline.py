"""Tests for the auto-pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tapes.pipeline import refresh_tmdb_source, run_auto_pipeline
from tapes.tree_model import FileNode, FolderNode, Source, TreeModel
from tapes.ui.tree_app import AppMode

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
        assert node.result.get("title") is not None
        # Filename extraction is the base layer, not a source
        filename_sources = [s for s in node.sources if s.name == "from filename"]
        assert len(filename_sources) == 0

    def test_confident_match_auto_stages(self, mock_tmdb) -> None:
        model = _make_model("Dune.2021.1080p.BluRay.mkv")
        run_auto_pipeline(model, token=TOKEN)
        node = model.all_files()[0]
        assert node.staged is True
        tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
        assert len(tmdb_sources) == 1
        assert tmdb_sources[0].confidence == 1.0
        assert node.result["year"] == 2021

    def test_clear_winner_no_year_auto_staged(self, mock_tmdb) -> None:
        """Without year but clear winner (margin to second), auto-staged via tier 2."""
        model = _make_model("Breaking.Bad.S01E01.720p.mkv")
        run_auto_pipeline(model, token=TOKEN)
        node = model.all_files()[0]
        assert node.staged is True

    def test_title_only_auto_stages_with_low_threshold(self, mock_tmdb) -> None:
        """With a low threshold, title-only matches can auto-stage."""
        model = _make_model("Breaking.Bad.S01E01.720p.mkv")
        run_auto_pipeline(model, token=TOKEN, confidence_threshold=0.5)
        node = model.all_files()[0]
        assert node.staged is True
        assert node.result["year"] == 2008

    def test_no_tmdb_match_no_sources(self, mock_tmdb) -> None:
        model = _make_model("Unknown.Movie.2024.mkv")
        run_auto_pipeline(model, token=TOKEN)
        node = model.all_files()[0]
        assert len(node.sources) == 0
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
        assert node.result.get("title") == "Breaking Bad"
        assert node.result.get("season") == 1
        assert node.result.get("episode") == 1
        # No "from filename" source
        filename_sources = [s for s in node.sources if s.name == "from filename"]
        assert len(filename_sources) == 0

    def test_tmdb_episode_data_merged(self, mock_tmdb) -> None:
        """With low threshold, episode data is fetched and merged."""
        model = _make_model("Breaking.Bad.S01E01.mkv")
        run_auto_pipeline(model, token=TOKEN, confidence_threshold=0.5)
        node = model.all_files()[0]
        tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
        assert len(tmdb_sources) >= 1
        # At least one source should have episode_title
        ep_titles = [s.fields.get("episode_title") for s in tmdb_sources]
        assert "Pilot" in ep_titles

    def test_custom_confidence_threshold(self, mock_tmdb) -> None:
        model = _make_model("Breaking.Bad.S01E01.mkv")
        run_auto_pipeline(model, token=TOKEN, confidence_threshold=0.5)
        node = model.all_files()[0]
        assert node.staged is True

    def test_no_token_skips_tmdb(self) -> None:
        """Without a token, only guessit runs -- no sources at all."""
        model = _make_model("Dune.2021.mkv")
        run_auto_pipeline(model, token="")
        node = model.all_files()[0]
        assert len(node.sources) == 0
        assert node.staged is False


class TestTwoStageFlow:
    def test_movie_auto_accept_no_episode_stage(self, mock_tmdb) -> None:
        """Movie match should not trigger episode stage."""
        model = _make_model("Dune.2021.mkv")
        run_auto_pipeline(model, token=TOKEN)
        node = model.all_files()[0]
        assert node.result["media_type"] == "movie"
        assert node.staged is True
        # Should have exactly 1 TMDB source (movie, no episodes)
        tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
        assert len(tmdb_sources) == 1

    def test_tv_show_triggers_episode_stage(self, mock_tmdb) -> None:
        """TV show match should fetch episodes."""
        model = _make_model("Breaking.Bad.S01E01.mkv")
        # Episode confidence is 0.8 (ep=0.6 + season=0.2), so use lower threshold
        run_auto_pipeline(model, token=TOKEN, confidence_threshold=0.7)
        node = model.all_files()[0]
        assert node.result["media_type"] == "episode"
        # Should have episode-level TMDB sources
        tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
        assert len(tmdb_sources) >= 1
        # Best match should have episode data
        assert node.result.get("episode_title") == "Pilot"

    def test_tv_show_no_episode_match(self) -> None:
        """TV show match with no matching episode keeps show-level sources.

        Uses low threshold because guessit doesn't extract year from
        'Breaking.Bad.S01E01.mkv', so show confidence is 0.7 (below 0.85).
        """

        def mock_empty_episodes(*args, **kwargs):
            return []

        with (
            _patch_tmdb()[0],
            _patch_tmdb()[1],
            patch("tapes.tmdb.get_season_episodes", side_effect=mock_empty_episodes),
        ):
            model = _make_model("Breaking.Bad.S01E01.mkv")
            run_auto_pipeline(model, token=TOKEN, confidence_threshold=0.5)
            node = model.all_files()[0]
            # Show match should still apply
            assert node.result["title"] == "Breaking Bad"
            assert node.staged is True


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
        assert node.result["title"] == "Breaking Bad"

    def test_ambiguous_candidates_no_auto_accept(self, mock_tmdb) -> None:
        """The Office without year: two equally-named shows, no clear winner."""
        model = _make_model("The.Office.S01E01.mkv")
        run_auto_pipeline(model, token=TOKEN)
        node = model.all_files()[0]
        assert node.staged is False
        # Both sources available for user curation
        tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
        assert len(tmdb_sources) == 2


# ---------------------------------------------------------------------------
# Refresh TMDB source
# ---------------------------------------------------------------------------


class TestRefreshTmdbSource:
    def test_updates_tmdb_source(self, mock_tmdb) -> None:
        node = FileNode(
            path=Path("/media/Dune.mkv"),
            result={"title": "Dune", "year": 2021},
            sources=[],
        )
        refresh_tmdb_source(node, token=TOKEN)
        tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
        assert len(tmdb_sources) == 1
        assert tmdb_sources[0].confidence == 1.0

    def test_updates_tmdb_source_no_year(self, mock_tmdb) -> None:
        """Without year, confidence is penalized (0.7, not 1.0)."""
        node = FileNode(
            path=Path("/media/Dune.mkv"),
            result={"title": "Dune"},
            sources=[],
        )
        refresh_tmdb_source(node, token=TOKEN)
        tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
        assert len(tmdb_sources) == 1
        assert tmdb_sources[0].confidence == pytest.approx(0.7)

    def test_replaces_existing_tmdb_source(self, mock_tmdb) -> None:
        node = FileNode(
            path=Path("/media/Dune.mkv"),
            result={"title": "Dune", "year": 2021},
            sources=[
                Source(name="TMDB #1", fields={"title": "Old"}, confidence=0.5),
            ],
        )
        refresh_tmdb_source(node, token=TOKEN)
        tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
        assert len(tmdb_sources) == 1
        assert tmdb_sources[0].fields["title"] == "Dune"
        assert tmdb_sources[0].confidence == 1.0

    def test_no_match_removes_tmdb_source(self, mock_tmdb) -> None:
        node = FileNode(
            path=Path("/media/Unknown.mkv"),
            result={"title": "Nonexistent"},
            sources=[
                Source(name="TMDB #1", fields={"title": "Old"}, confidence=0.5),
            ],
        )
        refresh_tmdb_source(node, token=TOKEN)
        tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
        assert len(tmdb_sources) == 0

    def test_confident_auto_accepts_with_year(self, mock_tmdb) -> None:
        node = FileNode(
            path=Path("/media/Dune.mkv"),
            result={"title": "Dune", "year": 2021},
            sources=[],
        )
        refresh_tmdb_source(node, token=TOKEN)
        assert node.result.get("year") == 2021
        assert node.staged is True

    def test_clear_winner_auto_accepts_via_margin(self, mock_tmdb) -> None:
        """Breaking Bad without year: tier 2 auto-accept (clear margin to El Camino)."""
        node = FileNode(
            path=Path("/media/test.mkv"),
            result={"title": "Breaking Bad"},
            sources=[],
        )
        refresh_tmdb_source(node, token=TOKEN)
        # Tier 2 accepts: 0.7 >= 0.6 and margin ~0.22 >= 0.15
        assert node.result.get("year") == 2008
        assert node.staged is True

    def test_no_token_skips(self) -> None:
        node = FileNode(
            path=Path("/media/Dune.mkv"),
            result={"title": "Dune"},
            sources=[],
        )
        refresh_tmdb_source(node, token="")
        tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
        assert len(tmdb_sources) == 0


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
            assert len(node.sources) >= 1
            assert node.staged is True


@pytest.mark.skipif(not HAS_PILOT, reason="textual pilot not available")
class TestRefreshQueryIntegration:
    @pytest.mark.asyncio()
    async def test_r_in_tree_refreshes_per_file(self, mock_tmdb) -> None:
        from tapes.ui.tree_app import TreeApp

        node = FileNode(
            path=Path("/media/Dune.mkv"),
            result={"title": "Dune", "year": 2021},
            sources=[],
        )
        root = FolderNode(name="root", children=[node])
        model = TreeModel(root=root)
        config_obj = _make_config(TOKEN)
        _tmpl = "{title} ({year}).{ext}"
        app = TreeApp(model=model, movie_template=_tmpl, tv_template=_tmpl, config=config_obj)

        async with app.run_test() as pilot:
            await pilot.press("r")
            tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
            assert len(tmdb_sources) == 1
            assert tmdb_sources[0].confidence == 1.0

    @pytest.mark.asyncio()
    async def test_r_in_detail_refreshes_current_node(self, mock_tmdb) -> None:
        from tapes.ui.tree_app import TreeApp

        node = FileNode(
            path=Path("/media/Arrival.mkv"),
            result={"title": "Arrival", "year": 2016},
            sources=[],
        )
        root = FolderNode(name="root", children=[node])
        model = TreeModel(root=root)
        config_obj = _make_config(TOKEN)
        _tmpl = "{title} ({year}).{ext}"
        app = TreeApp(model=model, movie_template=_tmpl, tv_template=_tmpl, config=config_obj)

        async with app.run_test() as pilot:
            await pilot.press("enter")
            assert app.mode == AppMode.DETAIL
            await pilot.press("r")
            tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
            assert len(tmdb_sources) == 1
            assert node.result.get("year") == 2016

    @pytest.mark.asyncio()
    async def test_r_in_tree_range_refreshes_all(self, mock_tmdb) -> None:
        from tapes.ui.tree_app import TreeApp

        node1 = FileNode(
            path=Path("/media/Dune.mkv"),
            result={"title": "Dune"},
            sources=[],
        )
        node2 = FileNode(
            path=Path("/media/Arrival.mkv"),
            result={"title": "Arrival"},
            sources=[],
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
            for n in [node1, node2]:
                tmdb = [s for s in n.sources if s.name.startswith("TMDB")]
                assert len(tmdb) == 1

    @pytest.mark.asyncio()
    async def test_r_in_multi_detail_refreshes_all_nodes(self, mock_tmdb) -> None:
        from tapes.ui.tree_app import TreeApp

        node1 = FileNode(
            path=Path("/media/Dune.mkv"),
            result={"title": "Dune"},
            sources=[],
        )
        node2 = FileNode(
            path=Path("/media/Arrival.mkv"),
            result={"title": "Arrival"},
            sources=[],
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
            assert app.mode == AppMode.DETAIL
            await pilot.press("r")
            for n in [node1, node2]:
                tmdb = [s for s in n.sources if s.name.startswith("TMDB")]
                assert len(tmdb) == 1


class TestTmdbCache:
    def test_exception_does_not_deadlock(self) -> None:
        """If fetch_fn raises, waiting threads should not hang."""
        import threading

        from tapes.pipeline import _TmdbCache

        cache = _TmdbCache()

        def bad_fetch():
            raise RuntimeError("TMDB down")

        # First call should raise
        with pytest.raises(RuntimeError):
            cache.get_or_fetch(("key",), bad_fetch)

        # Second call with same key should also raise (not deadlock)
        results: list[str] = []

        def try_fetch():
            try:
                cache.get_or_fetch(("key",), bad_fetch)
            except (RuntimeError, KeyError):
                results.append("raised")

        t = threading.Thread(target=try_fetch)
        t.start()
        t.join(timeout=2.0)
        assert not t.is_alive(), "Thread deadlocked waiting for failed fetch"


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
        tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
        assert len(tmdb_sources) <= 1

    def test_run_tmdb_pass_default_max_results_keeps_all(self, mock_tmdb) -> None:
        """Default max_results=3 keeps all candidates when fewer than 3."""
        from tapes.pipeline import run_guessit_pass, run_tmdb_pass

        model = _make_model("The.Office.S01E01.mkv")
        run_guessit_pass(model)
        run_tmdb_pass(model, token=TOKEN)
        node = model.all_files()[0]
        tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
        assert len(tmdb_sources) == 2

    def test_run_auto_pipeline_forwards_max_results(self, mock_tmdb) -> None:
        """max_results flows from run_auto_pipeline through to sources."""
        model = _make_model("The.Office.S01E01.mkv")
        run_auto_pipeline(model, token=TOKEN, max_results=1)
        node = model.all_files()[0]
        tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
        assert len(tmdb_sources) <= 1

    def test_refresh_forwards_max_results(self, mock_tmdb) -> None:
        """refresh_tmdb_source respects max_results."""
        node = FileNode(
            path=Path("/media/The.Office.mkv"),
            result={"title": "The Office"},
            sources=[],
        )
        refresh_tmdb_source(node, token=TOKEN, max_results=1)
        tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
        assert len(tmdb_sources) <= 1

    def test_margin_threshold_prevents_auto_accept(self, mock_tmdb) -> None:
        """High margin_threshold prevents tier 2 auto-accept."""
        # Breaking Bad without year: tier 2 normally accepts (margin ~0.22).
        # Set margin_threshold=0.99 so tier 2 won't fire.
        model = _make_model("Breaking.Bad.S01E01.mkv")
        run_auto_pipeline(model, token=TOKEN, margin_threshold=0.99)
        node = model.all_files()[0]
        # Should NOT auto-accept because tier 1 needs 0.85 (no year = ~0.7)
        # and tier 2 is blocked by margin_threshold=0.99
        assert node.staged is False

    def test_min_margin_prevents_auto_accept(self, mock_tmdb) -> None:
        """High min_margin prevents tier 2 auto-accept."""
        # Breaking Bad without year: margin ~0.22. Set min_margin=0.5 to block.
        model = _make_model("Breaking.Bad.S01E01.mkv")
        run_auto_pipeline(model, token=TOKEN, min_margin=0.5)
        node = model.all_files()[0]
        assert node.staged is False

    def test_margin_params_allow_auto_accept(self, mock_tmdb) -> None:
        """Lenient margin params allow tier 2 auto-accept."""
        model = _make_model("Breaking.Bad.S01E01.mkv")
        run_auto_pipeline(model, token=TOKEN, margin_threshold=0.5, min_margin=0.1)
        node = model.all_files()[0]
        assert node.staged is True

    def test_refresh_forwards_margin_params(self, mock_tmdb) -> None:
        """refresh_tmdb_source forwards margin_threshold and min_margin."""
        node = FileNode(
            path=Path("/media/test.mkv"),
            result={"title": "Breaking Bad"},
            sources=[],
        )
        # With strict margin params, tier 2 auto-accept should be blocked
        refresh_tmdb_source(node, token=TOKEN, margin_threshold=0.99, min_margin=0.99)
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
        run_auto_pipeline(model, token=TOKEN, confidence_threshold=0.5, max_results=1)
        node = model.all_files()[0]
        tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
        # Even though 3 episodes are available, only max_results=1 kept
        assert len(tmdb_sources) == 1
