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

def _mock_search_multi(query: str, token: str, year: int | None = None) -> list[dict]:
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


def _mock_get_show(tmdb_id: int, token: str) -> dict:
    if tmdb_id == 1396:
        return {
            "tmdb_id": 1396, "title": "Breaking Bad", "year": 2008,
            "media_type": "episode", "seasons": [1, 2, 3, 4, 5],
        }
    return {}


def _mock_get_season_episodes(
    show_id: int, season_number: int, token: str,
    show_title: str = "", show_year: int | None = None,
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


def _patch_tmdb():
    """Patch all tapes.tmdb functions used by pipeline."""
    return [
        patch("tapes.tmdb.search_multi", side_effect=_mock_search_multi),
        patch("tapes.tmdb.get_show", side_effect=_mock_get_show),
        patch("tapes.tmdb.get_season_episodes", side_effect=_mock_get_season_episodes),
    ]


class TestRunAutoPipeline:
    def test_populates_result_and_filename_source(self) -> None:
        with _patch_tmdb()[0], _patch_tmdb()[1], _patch_tmdb()[2]:
            model = _make_model("Dune.2021.1080p.BluRay.mkv")
            run_auto_pipeline(model, token=TOKEN)
            node = model.all_files()[0]
            assert node.result.get("title") is not None
            assert len(node.sources) >= 1
            assert node.sources[0].name == "from filename"

    def test_confident_match_auto_stages(self) -> None:
        with _patch_tmdb()[0], _patch_tmdb()[1], _patch_tmdb()[2]:
            model = _make_model("Dune.2021.1080p.BluRay.mkv")
            run_auto_pipeline(model, token=TOKEN)
            node = model.all_files()[0]
            assert node.staged is True
            tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
            assert len(tmdb_sources) == 1
            assert tmdb_sources[0].confidence == 1.0
            assert node.result["year"] == 2021

    def test_confident_match_title_only_auto_stages(self) -> None:
        with _patch_tmdb()[0], _patch_tmdb()[1], _patch_tmdb()[2]:
            model = _make_model("Breaking.Bad.S01E01.720p.mkv")
            run_auto_pipeline(model, token=TOKEN)
            node = model.all_files()[0]
            assert node.staged is True
            tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
            assert len(tmdb_sources) >= 1

    def test_confident_match_result_overwritten_by_tmdb(self) -> None:
        with _patch_tmdb()[0], _patch_tmdb()[1], _patch_tmdb()[2]:
            model = _make_model("Breaking.Bad.S01E01.720p.mkv")
            run_auto_pipeline(model, token=TOKEN)
            node = model.all_files()[0]
            assert node.result["year"] == 2008
            assert node.staged is True

    def test_no_tmdb_match_only_filename_source(self) -> None:
        with _patch_tmdb()[0], _patch_tmdb()[1], _patch_tmdb()[2]:
            model = _make_model("Unknown.Movie.2024.mkv")
            run_auto_pipeline(model, token=TOKEN)
            node = model.all_files()[0]
            assert len(node.sources) == 1
            assert node.sources[0].name == "from filename"
            assert node.staged is False

    def test_multiple_files_processed(self) -> None:
        with _patch_tmdb()[0], _patch_tmdb()[1], _patch_tmdb()[2]:
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

    def test_filename_source_fields_from_guessit(self) -> None:
        with _patch_tmdb()[0], _patch_tmdb()[1], _patch_tmdb()[2]:
            model = _make_model("Breaking.Bad.S01E01.720p.BluRay.x264.mkv")
            run_auto_pipeline(model, token=TOKEN)
            node = model.all_files()[0]
            src = node.sources[0]
            assert src.name == "from filename"
            assert src.fields.get("title") == "Breaking Bad"
            assert src.fields.get("season") == 1
            assert src.fields.get("episode") == 1

    def test_tmdb_episode_data_merged(self) -> None:
        with _patch_tmdb()[0], _patch_tmdb()[1], _patch_tmdb()[2]:
            model = _make_model("Breaking.Bad.S01E01.mkv")
            run_auto_pipeline(model, token=TOKEN)
            node = model.all_files()[0]
            tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
            assert len(tmdb_sources) >= 1
            # At least one source should have episode_title
            ep_titles = [s.fields.get("episode_title") for s in tmdb_sources]
            assert "Pilot" in ep_titles

    def test_custom_confidence_threshold(self) -> None:
        with _patch_tmdb()[0], _patch_tmdb()[1], _patch_tmdb()[2]:
            model = _make_model("Breaking.Bad.S01E01.mkv")
            run_auto_pipeline(model, token=TOKEN, confidence_threshold=0.5)
            node = model.all_files()[0]
            assert node.staged is True

    def test_no_token_skips_tmdb(self) -> None:
        """Without a token, only guessit runs -- no TMDB sources."""
        model = _make_model("Dune.2021.mkv")
        run_auto_pipeline(model, token="")
        node = model.all_files()[0]
        assert len(node.sources) == 1
        assert node.sources[0].name == "from filename"
        assert node.staged is False


class TestTwoStageFlow:
    def test_movie_auto_accept_no_episode_stage(self) -> None:
        """Movie match should not trigger episode stage."""
        with _patch_tmdb()[0], _patch_tmdb()[1], _patch_tmdb()[2]:
            model = _make_model("Dune.2021.mkv")
            run_auto_pipeline(model, token=TOKEN)
            node = model.all_files()[0]
            assert node.result["media_type"] == "movie"
            assert node.staged is True
            # Should have exactly 1 TMDB source (movie, no episodes)
            tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
            assert len(tmdb_sources) == 1

    def test_tv_show_triggers_episode_stage(self) -> None:
        """TV show match should fetch episodes."""
        with _patch_tmdb()[0], _patch_tmdb()[1], _patch_tmdb()[2]:
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
        """TV show match with no matching episode keeps show-level sources."""
        def mock_empty_episodes(*args, **kwargs):
            return []

        with _patch_tmdb()[0], _patch_tmdb()[1], \
             patch("tapes.tmdb.get_season_episodes", side_effect=mock_empty_episodes):
            model = _make_model("Breaking.Bad.S01E01.mkv")
            run_auto_pipeline(model, token=TOKEN)
            node = model.all_files()[0]
            # Show match should still apply
            assert node.result["title"] == "Breaking Bad"
            assert node.staged is True


# ---------------------------------------------------------------------------
# Refresh TMDB source
# ---------------------------------------------------------------------------


class TestRefreshTmdbSource:
    def test_updates_tmdb_source(self) -> None:
        with _patch_tmdb()[0], _patch_tmdb()[1], _patch_tmdb()[2]:
            node = FileNode(
                path=Path("/media/Dune.mkv"),
                result={"title": "Dune"},
                sources=[Source(name="from filename", fields={"title": "Dune"})],
            )
            refresh_tmdb_source(node, token=TOKEN)
            tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
            assert len(tmdb_sources) == 1
            assert tmdb_sources[0].confidence == 1.0

    def test_replaces_existing_tmdb_source(self) -> None:
        with _patch_tmdb()[0], _patch_tmdb()[1], _patch_tmdb()[2]:
            node = FileNode(
                path=Path("/media/Dune.mkv"),
                result={"title": "Dune"},
                sources=[
                    Source(name="from filename", fields={"title": "Dune"}),
                    Source(name="TMDB #1", fields={"title": "Old"}, confidence=0.5),
                ],
            )
            refresh_tmdb_source(node, token=TOKEN)
            tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
            assert len(tmdb_sources) == 1
            assert tmdb_sources[0].fields["title"] == "Dune"
            assert tmdb_sources[0].confidence == 1.0

    def test_keeps_filename_source(self) -> None:
        with _patch_tmdb()[0], _patch_tmdb()[1], _patch_tmdb()[2]:
            node = FileNode(
                path=Path("/media/Dune.mkv"),
                result={"title": "Dune"},
                sources=[
                    Source(name="from filename", fields={"title": "Dune"}),
                    Source(name="TMDB #1", fields={"title": "Old"}, confidence=0.5),
                ],
            )
            refresh_tmdb_source(node, token=TOKEN)
            filename_sources = [s for s in node.sources if s.name == "from filename"]
            assert len(filename_sources) == 1

    def test_no_match_removes_tmdb_source(self) -> None:
        with _patch_tmdb()[0], _patch_tmdb()[1], _patch_tmdb()[2]:
            node = FileNode(
                path=Path("/media/Unknown.mkv"),
                result={"title": "Nonexistent"},
                sources=[
                    Source(name="from filename", fields={"title": "Nonexistent"}),
                    Source(name="TMDB #1", fields={"title": "Old"}, confidence=0.5),
                ],
            )
            refresh_tmdb_source(node, token=TOKEN)
            tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
            assert len(tmdb_sources) == 0

    def test_confident_auto_accepts(self) -> None:
        with _patch_tmdb()[0], _patch_tmdb()[1], _patch_tmdb()[2]:
            node = FileNode(
                path=Path("/media/Dune.mkv"),
                result={"title": "Dune"},
                sources=[Source(name="from filename", fields={"title": "Dune"})],
            )
            refresh_tmdb_source(node, token=TOKEN)
            assert node.result.get("year") == 2021

    def test_title_only_match_auto_accepts(self) -> None:
        with _patch_tmdb()[0], _patch_tmdb()[1], _patch_tmdb()[2]:
            node = FileNode(
                path=Path("/media/test.mkv"),
                result={"title": "Breaking Bad"},
                sources=[Source(name="from filename", fields={"title": "Breaking Bad"})],
            )
            refresh_tmdb_source(node, token=TOKEN)
            assert node.result.get("year") == 2008

    def test_no_token_skips(self) -> None:
        node = FileNode(
            path=Path("/media/Dune.mkv"),
            result={"title": "Dune"},
            sources=[Source(name="from filename", fields={"title": "Dune"})],
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
    async def test_auto_pipeline_runs_on_mount(self) -> None:
        from tapes.ui.tree_app import TreeApp

        with _patch_tmdb()[0], _patch_tmdb()[1], _patch_tmdb()[2]:
            model = _make_model("Dune.2021.1080p.BluRay.mkv")
            config_obj = _make_config(TOKEN)
            app = TreeApp(
                model=model,
                template="{title} ({year}).{ext}",
                auto_pipeline=True,
                config=config_obj,
            )
            async with app.run_test() as pilot:
                node = model.all_files()[0]
                assert len(node.sources) >= 1
                assert node.staged is True


@pytest.mark.skipif(not HAS_PILOT, reason="textual pilot not available")
class TestRefreshQueryIntegration:
    @pytest.mark.asyncio()
    async def test_r_in_tree_refreshes_per_file(self) -> None:
        from tapes.ui.tree_app import TreeApp

        with _patch_tmdb()[0], _patch_tmdb()[1], _patch_tmdb()[2]:
            node = FileNode(
                path=Path("/media/Dune.mkv"),
                result={"title": "Dune"},
                sources=[Source(name="from filename", fields={"title": "Dune"})],
            )
            root = FolderNode(name="root", children=[node])
            model = TreeModel(root=root)
            config_obj = _make_config(TOKEN)
            app = TreeApp(model=model, template="{title} ({year}).{ext}", config=config_obj)

            async with app.run_test() as pilot:
                await pilot.press("r")
                tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
                assert len(tmdb_sources) == 1
                assert tmdb_sources[0].confidence == 1.0

    @pytest.mark.asyncio()
    async def test_r_in_detail_refreshes_current_node(self) -> None:
        from tapes.ui.tree_app import TreeApp

        with _patch_tmdb()[0], _patch_tmdb()[1], _patch_tmdb()[2]:
            node = FileNode(
                path=Path("/media/Arrival.mkv"),
                result={"title": "Arrival"},
                sources=[Source(name="from filename", fields={"title": "Arrival"})],
            )
            root = FolderNode(name="root", children=[node])
            model = TreeModel(root=root)
            config_obj = _make_config(TOKEN)
            app = TreeApp(model=model, template="{title} ({year}).{ext}", config=config_obj)

            async with app.run_test() as pilot:
                await pilot.press("enter")
                assert app._in_detail is True
                await pilot.press("r")
                tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
                assert len(tmdb_sources) == 1
                assert node.result.get("year") == 2016

    @pytest.mark.asyncio()
    async def test_r_in_tree_range_refreshes_all(self) -> None:
        from tapes.ui.tree_app import TreeApp

        with _patch_tmdb()[0], _patch_tmdb()[1], _patch_tmdb()[2]:
            node1 = FileNode(
                path=Path("/media/Dune.mkv"),
                result={"title": "Dune"},
                sources=[Source(name="from filename", fields={"title": "Dune"})],
            )
            node2 = FileNode(
                path=Path("/media/Arrival.mkv"),
                result={"title": "Arrival"},
                sources=[Source(name="from filename", fields={"title": "Arrival"})],
            )
            root = FolderNode(name="root", children=[node1, node2])
            model = TreeModel(root=root)
            config_obj = _make_config(TOKEN)
            app = TreeApp(model=model, template="{title} ({year}).{ext}", config=config_obj)

            async with app.run_test() as pilot:
                await pilot.press("v")
                await pilot.press("j")
                await pilot.press("r")
                for n in [node1, node2]:
                    tmdb = [s for s in n.sources if s.name.startswith("TMDB")]
                    assert len(tmdb) == 1

    @pytest.mark.asyncio()
    async def test_r_in_multi_detail_refreshes_all_nodes(self) -> None:
        from tapes.ui.tree_app import TreeApp

        with _patch_tmdb()[0], _patch_tmdb()[1], _patch_tmdb()[2]:
            node1 = FileNode(
                path=Path("/media/Dune.mkv"),
                result={"title": "Dune"},
                sources=[Source(name="from filename", fields={"title": "Dune"})],
            )
            node2 = FileNode(
                path=Path("/media/Arrival.mkv"),
                result={"title": "Arrival"},
                sources=[Source(name="from filename", fields={"title": "Arrival"})],
            )
            root = FolderNode(name="root", children=[node1, node2])
            model = TreeModel(root=root)
            config_obj = _make_config(TOKEN)
            app = TreeApp(model=model, template="{title} ({year}).{ext}", config=config_obj)

            async with app.run_test() as pilot:
                await pilot.press("v")
                await pilot.press("j")
                await pilot.press("enter")
                assert app._in_detail is True
                await pilot.press("r")
                for n in [node1, node2]:
                    tmdb = [s for s in n.sources if s.name.startswith("TMDB")]
                    assert len(tmdb) == 1


def _make_config(token: str = ""):
    """Create a TapesConfig with the given token."""
    from tapes.config import TapesConfig
    return TapesConfig(metadata={"tmdb_token": token})
