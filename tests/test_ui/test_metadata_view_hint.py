"""Tests for B2: hint note in multi-node metadata view for accepted shows."""

from __future__ import annotations

from pathlib import Path

from tapes.fields import MEDIA_TYPE, MEDIA_TYPE_EPISODE, SEASON, TITLE, TMDB_ID
from tapes.tree_model import FileNode
from tapes.ui.metadata_view import MetadataView


def _make_episode_node(title: str, tmdb_id: int | None = None, season: int | None = None) -> FileNode:
    node = FileNode(path=Path("test.mkv"))
    metadata: dict = {TITLE: title, MEDIA_TYPE: MEDIA_TYPE_EPISODE}
    if tmdb_id is not None:
        metadata[TMDB_ID] = tmdb_id
    if season is not None:
        metadata[SEASON] = season
    node.metadata = metadata
    return node


class TestMultiNodeHint:
    def test_shows_hint_for_accepted_show_multi_node(self) -> None:
        nodes = [
            _make_episode_node("Game of Thrones", tmdb_id=1399),
            _make_episode_node("Game of Thrones", tmdb_id=1399),
        ]
        mv = MetadataView(nodes[0], "{title}/{title}.{ext}", "{title}/S{season:02d}E{episode:02d}.{ext}")
        mv.set_nodes(nodes)
        tab_bar = mv._render_tab_bar(80)
        text = tab_bar.plain
        assert "individual files" in text.lower()
        assert "clear tmdb_id" in text.lower()

    def test_shows_season_hint_when_season_missing(self) -> None:
        nodes = [
            _make_episode_node("Game of Thrones", tmdb_id=1399),
            _make_episode_node("Game of Thrones", tmdb_id=1399),
        ]
        mv = MetadataView(nodes[0], "{title}/{title}.{ext}", "{title}/S{season:02d}E{episode:02d}.{ext}")
        mv.set_nodes(nodes)
        tab_bar = mv._render_tab_bar(80)
        text = tab_bar.plain
        assert "season" in text.lower()

    def test_no_season_hint_when_season_present(self) -> None:
        nodes = [
            _make_episode_node("Game of Thrones", tmdb_id=1399, season=1),
            _make_episode_node("Game of Thrones", tmdb_id=1399, season=1),
        ]
        mv = MetadataView(nodes[0], "{title}/{title}.{ext}", "{title}/S{season:02d}E{episode:02d}.{ext}")
        mv.set_nodes(nodes)
        tab_bar = mv._render_tab_bar(80)
        text = tab_bar.plain
        assert "individual files" in text.lower()
        assert "set season" not in text.lower()
        assert "clear tmdb_id" in text.lower()

    def test_no_hint_for_unaccepted_show(self) -> None:
        nodes = [
            _make_episode_node("Game of Thrones"),
            _make_episode_node("Game of Thrones"),
        ]
        mv = MetadataView(nodes[0], "{title}/{title}.{ext}", "{title}/S{season:02d}E{episode:02d}.{ext}")
        mv.set_nodes(nodes)
        tab_bar = mv._render_tab_bar(80)
        text = tab_bar.plain
        assert "individual files" not in text.lower()

    def test_no_hint_for_single_node(self) -> None:
        node = _make_episode_node("Game of Thrones", tmdb_id=1399)
        mv = MetadataView(node, "{title}/{title}.{ext}", "{title}/S{season:02d}E{episode:02d}.{ext}")
        mv.set_node(node)
        tab_bar = mv._render_tab_bar(80)
        text = tab_bar.plain
        assert "individual files" not in text.lower()
