"""Tests for B2: hint note in multi-node metadata view for accepted shows."""

from __future__ import annotations

from pathlib import Path

from tapes.fields import EPISODE, MEDIA_TYPE, MEDIA_TYPE_EPISODE, SEASON, TITLE, TMDB_ID
from tapes.tree_model import Candidate, FileNode
from tapes.ui.metadata_view import MetadataView

MOVIE_TMPL = "{title}/{title}.{ext}"
TV_TMPL = "{title}/S{season:02d}E{episode:02d}.{ext}"


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
        mv = MetadataView(node, MOVIE_TMPL, TV_TMPL)
        mv.set_node(node)
        tab_bar = mv._render_tab_bar(80)
        text = tab_bar.plain
        assert "individual files" not in text.lower()

    def test_candidate_column_hidden_in_hint_mode(self) -> None:
        """When B2 hint is active, candidate column width should be 0."""
        nodes = [
            _make_episode_node("Game of Thrones", tmdb_id=1399),
            _make_episode_node("Game of Thrones", tmdb_id=1399),
        ]
        # Add episode candidates to the primary node

        nodes[0].candidates = [
            Candidate(
                name="TMDB #1",
                metadata={TITLE: "Game of Thrones", SEASON: 1, EPISODE: 1, MEDIA_TYPE: MEDIA_TYPE_EPISODE},
                score=0.95,
            ),
        ]
        mv = MetadataView(nodes[0], MOVIE_TMPL, TV_TMPL)
        mv.set_nodes(nodes)
        assert mv.show_level_hint
        # candidate_w should be 0 despite candidates existing
        _, _, cand_w = mv._compute_col_widths()
        assert cand_w == 0

    def test_accept_skipped_in_hint_mode(self) -> None:
        """Pressing enter in hint mode should not copy candidate fields."""

        nodes = [
            _make_episode_node("Game of Thrones", tmdb_id=1399),
            _make_episode_node("Game of Thrones", tmdb_id=1399),
        ]
        nodes[0].candidates = [
            Candidate(
                name="TMDB #1",
                metadata={TITLE: "Game of Thrones", SEASON: 1, EPISODE: 1, MEDIA_TYPE: MEDIA_TYPE_EPISODE},
                score=0.95,
            ),
        ]
        mv = MetadataView(nodes[0], MOVIE_TMPL, TV_TMPL)
        mv.set_nodes(nodes)
        mv.focus_column = "candidate"
        # accept_focused_column should be a no-op in hint mode
        mv.accept_focused_column()
        # episode should NOT have been copied to the nodes
        assert nodes[0].metadata.get(EPISODE) is None
        assert nodes[1].metadata.get(EPISODE) is None
