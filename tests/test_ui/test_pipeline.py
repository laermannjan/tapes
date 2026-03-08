"""Tests for the auto-pipeline."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tapes.ui.pipeline import refresh_tmdb_source, run_auto_pipeline
from tapes.ui.tree_model import FileNode, FolderNode, Source, TreeModel

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
        return [{"tmdb_id": 1396, "title": "Breaking Bad", "year": 2008, "media_type": "episode"}]
    return []


def _mock_get_show(tmdb_id: int, token: str, **kwargs: object) -> dict:
    if tmdb_id == 1396:
        return {
            "tmdb_id": 1396, "title": "Breaking Bad", "year": 2008,
            "media_type": "episode", "seasons": [1, 2, 3, 4, 5],
        }
    return {}


def _mock_get_season_episodes(
    show_id: int, season_number: int, token: str,
    show_title: str = "", show_year: int | None = None,
    **kwargs: object,
) -> list[dict]:
    if show_id == 1396 and season_number == 1:
        return [
            {"tmdb_id": 1396, "title": "Breaking Bad", "year": 2008,
             "media_type": "episode", "season": 1, "episode": 1, "episode_title": "Pilot"},
            {"tmdb_id": 1396, "title": "Breaking Bad", "year": 2008,
             "media_type": "episode", "season": 1, "episode": 2, "episode_title": "Cat's in the Bag..."},
            {"tmdb_id": 1396, "title": "Breaking Bad", "year": 2008,
             "media_type": "episode", "season": 1, "episode": 3, "episode_title": "...And the Bag's in the River"},
        ]
    return []


def _make_config(token: str = ""):
    """Create a TapesConfig with the given token."""
    from tapes.config import TapesConfig
    return TapesConfig(metadata={"tmdb_token": token})


def _patch_tmdb():
    """Patch all tapes.tmdb functions used by pipeline."""
    return [
        patch("tapes.tmdb.search_multi", side_effect=_mock_search_multi),
        patch("tapes.tmdb.get_show", side_effect=_mock_get_show),
        patch("tapes.tmdb.get_season_episodes", side_effect=_mock_get_season_episodes),
    ]


@pytest.fixture()
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

    def test_title_only_not_auto_staged(self, mock_tmdb) -> None:
        """Without year in filename, confidence is below threshold; not auto-staged."""
        model = _make_model("Breaking.Bad.S01E01.720p.mkv")
        run_auto_pipeline(model, token=TOKEN)
        node = model.all_files()[0]
        assert node.staged is False
        # TMDB sources still added for user curation
        tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
        assert len(tmdb_sources) >= 1

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
        assert files[0].staged is True   # Dune
        assert files[1].staged is True   # Arrival
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

        with _patch_tmdb()[0], _patch_tmdb()[1], \
             patch("tapes.tmdb.get_season_episodes", side_effect=mock_empty_episodes):
            model = _make_model("Breaking.Bad.S01E01.mkv")
            run_auto_pipeline(model, token=TOKEN, confidence_threshold=0.5)
            node = model.all_files()[0]
            # Show match should still apply
            assert node.result["title"] == "Breaking Bad"
            assert node.staged is True


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

    def test_title_only_no_auto_accept(self, mock_tmdb) -> None:
        """Without year, confidence is 0.7 -- below threshold, no auto-accept."""
        node = FileNode(
            path=Path("/media/test.mkv"),
            result={"title": "Breaking Bad"},
            sources=[],
        )
        refresh_tmdb_source(node, token=TOKEN)
        # Year not merged because confidence < threshold
        assert node.result.get("year") is None
        assert node.staged is False
        # But TMDB source is still available for manual curation
        tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
        assert len(tmdb_sources) == 1

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
        async with app.run_test() as pilot:
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
            assert app._in_detail is True
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
            assert app._in_detail is True
            await pilot.press("r")
            for n in [node1, node2]:
                tmdb = [s for s in n.sources if s.name.startswith("TMDB")]
                assert len(tmdb) == 1


class TestTmdbCache:
    def test_exception_does_not_deadlock(self) -> None:
        """If fetch_fn raises, waiting threads should not hang."""
        import threading
        from tapes.ui.pipeline import _TmdbCache

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
        from tapes.ui.pipeline import extract_guessit_fields

        fields = extract_guessit_fields("Inception.2010.mkv")
        assert fields["title"] == "Inception"
        assert fields["year"] == 2010

    def test_extracts_tv_fields(self) -> None:
        from tapes.ui.pipeline import extract_guessit_fields

        fields = extract_guessit_fields("Breaking.Bad.S01E01.mkv")
        assert fields["title"] == "Breaking Bad"
        assert fields["season"] == 1
        assert fields["episode"] == 1

    def test_missing_fields_omitted(self) -> None:
        from tapes.ui.pipeline import extract_guessit_fields

        fields = extract_guessit_fields("something.mkv")
        assert "year" not in fields or fields.get("year") is None
