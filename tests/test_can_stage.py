"""Tests for can_fill_template and pipeline can_stage integration."""

from __future__ import annotations

from pathlib import Path

from tapes.fields import EPISODE, EPISODE_TITLE, MEDIA_TYPE, SEASON, TITLE, TMDB_ID, YEAR
from tapes.templates import can_fill_template
from tapes.tree_model import FileNode, FolderNode, TreeModel

MOVIE_TEMPLATE = "{title} ({year})/{title} ({year}).{ext}"
TV_TEMPLATE = "{title} ({year})/Season {season:02d}/{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"


class TestCanFillTemplate:
    def test_movie_all_fields_present(self) -> None:
        node = FileNode(path=Path("movie.mkv"))
        node.metadata = {MEDIA_TYPE: "movie", TITLE: "Inception", YEAR: 2010}
        assert can_fill_template(node, node.metadata, MOVIE_TEMPLATE, TV_TEMPLATE) is True

    def test_movie_missing_year(self) -> None:
        node = FileNode(path=Path("movie.mkv"))
        node.metadata = {MEDIA_TYPE: "movie", TITLE: "Inception"}
        assert can_fill_template(node, node.metadata, MOVIE_TEMPLATE, TV_TEMPLATE) is False

    def test_movie_missing_title(self) -> None:
        node = FileNode(path=Path("movie.mkv"))
        node.metadata = {MEDIA_TYPE: "movie", YEAR: 2010}
        assert can_fill_template(node, node.metadata, MOVIE_TEMPLATE, TV_TEMPLATE) is False

    def test_tv_all_fields_present(self) -> None:
        node = FileNode(path=Path("episode.mkv"))
        node.metadata = {
            MEDIA_TYPE: "episode",
            TITLE: "Breaking Bad",
            YEAR: 2008,
            SEASON: 1,
            EPISODE: 1,
            EPISODE_TITLE: "Pilot",
        }
        assert can_fill_template(node, node.metadata, MOVIE_TEMPLATE, TV_TEMPLATE) is True

    def test_tv_missing_episode_title(self) -> None:
        node = FileNode(path=Path("episode.mkv"))
        node.metadata = {
            MEDIA_TYPE: "episode",
            TITLE: "Breaking Bad",
            YEAR: 2008,
            SEASON: 1,
            EPISODE: 1,
        }
        assert can_fill_template(node, node.metadata, MOVIE_TEMPLATE, TV_TEMPLATE) is False

    def test_tv_missing_season(self) -> None:
        node = FileNode(path=Path("episode.mkv"))
        node.metadata = {
            MEDIA_TYPE: "episode",
            TITLE: "Breaking Bad",
            YEAR: 2008,
            EPISODE: 1,
            EPISODE_TITLE: "Pilot",
        }
        assert can_fill_template(node, node.metadata, MOVIE_TEMPLATE, TV_TEMPLATE) is False

    def test_ext_excluded_from_check(self) -> None:
        """ext comes from the filename, not from metadata."""
        node = FileNode(path=Path("movie.mkv"))
        # No 'ext' in result, but should still pass because ext is excluded
        node.metadata = {MEDIA_TYPE: "movie", TITLE: "Inception", YEAR: 2010}
        assert can_fill_template(node, node.metadata, MOVIE_TEMPLATE, TV_TEMPLATE) is True

    def test_uses_merged_result(self) -> None:
        """can_fill_template checks the merged dict, not node.metadata."""
        node = FileNode(path=Path("movie.mkv"))
        node.metadata = {MEDIA_TYPE: "movie", TITLE: "Inception"}
        merged = {MEDIA_TYPE: "movie", TITLE: "Inception", YEAR: 2010}
        assert can_fill_template(node, merged, MOVIE_TEMPLATE, TV_TEMPLATE) is True

    def test_none_value_treated_as_missing(self) -> None:
        node = FileNode(path=Path("movie.mkv"))
        node.metadata = {MEDIA_TYPE: "movie", TITLE: "Inception", YEAR: None}
        assert can_fill_template(node, node.metadata, MOVIE_TEMPLATE, TV_TEMPLATE) is False


class TestCanStagePipelineIntegration:
    """Test that the pipeline respects can_stage to prevent auto-staging."""

    def _make_model(self, filename: str) -> tuple[TreeModel, FileNode]:
        node = FileNode(path=Path(filename))
        model = TreeModel(root=FolderNode(name="root", children=[node]))
        return model, node

    def test_movie_not_staged_when_year_missing(self) -> None:
        """Pipeline applies fields but doesn't stage when template can't be filled."""
        import httpx
        import respx

        from tapes.pipeline import run_auto_pipeline

        model, file_node = self._make_model("Inception.mkv")

        # TMDB returns a movie match without a year
        with respx.mock:
            respx.get("https://api.themoviedb.org/3/search/multi").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "results": [
                            {
                                "id": 27205,
                                "media_type": "movie",
                                "title": "Inception",
                                "release_date": "",
                                "vote_count": 100,
                            }
                        ]
                    },
                )
            )

            def _can_stage(n: FileNode, merged: dict) -> bool:
                return can_fill_template(n, merged, MOVIE_TEMPLATE, TV_TEMPLATE)

            run_auto_pipeline(
                model,
                token="fake-token",  # noqa: S106
                confidence_threshold=0.5,
                can_stage=_can_stage,
            )

        # Fields should be applied (title from TMDB)
        assert file_node.metadata.get(TITLE) == "Inception"
        assert file_node.metadata.get(TMDB_ID) == 27205
        # But NOT staged because year is missing
        assert file_node.staged is False

    def test_movie_staged_when_all_fields_present(self) -> None:
        """Pipeline stages the file when template can be filled."""
        import httpx
        import respx

        from tapes.pipeline import run_auto_pipeline

        model, file_node = self._make_model("Inception.mkv")

        with respx.mock:
            respx.get("https://api.themoviedb.org/3/search/multi").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "results": [
                            {
                                "id": 27205,
                                "media_type": "movie",
                                "title": "Inception",
                                "release_date": "2010-07-16",
                                "vote_count": 100,
                            }
                        ]
                    },
                )
            )

            def _can_stage(n: FileNode, merged: dict) -> bool:
                return can_fill_template(n, merged, MOVIE_TEMPLATE, TV_TEMPLATE)

            run_auto_pipeline(
                model,
                token="fake-token",  # noqa: S106
                confidence_threshold=0.5,
                can_stage=_can_stage,
            )

        assert file_node.metadata.get(TITLE) == "Inception"
        assert file_node.metadata.get(YEAR) == 2010
        assert file_node.staged is True
