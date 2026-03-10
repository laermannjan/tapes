"""Tests for A3: clear candidates after show/movie acceptance."""

from __future__ import annotations

from pathlib import Path

from tapes.fields import TITLE, TMDB_ID
from tapes.pipeline import _make_metadata_updater
from tapes.tree_model import Candidate, FileNode


class TestMakeMetadataUpdaterClearCandidates:
    def test_clear_candidates_true(self) -> None:
        node = FileNode(path=Path("test.mp4"))
        node.candidates = [
            Candidate(name="TMDB #1", metadata={"title": "Stale"}, score=0.5),
            Candidate(name="TMDB #2", metadata={"title": "Also Stale"}, score=0.3),
        ]
        updater = _make_metadata_updater(
            node,
            {TITLE: "Fresh", TMDB_ID: 123},
            stage=False,
            clear_candidates=True,
        )
        updater()
        assert node.metadata[TITLE] == "Fresh"
        assert node.metadata[TMDB_ID] == 123
        assert len(node.candidates) == 0

    def test_clear_candidates_false_default(self) -> None:
        node = FileNode(path=Path("test.mp4"))
        node.candidates = [
            Candidate(name="TMDB #1", metadata={"title": "Keep"}, score=0.5),
        ]
        updater = _make_metadata_updater(node, {TITLE: "New"}, stage=False)
        updater()
        assert len(node.candidates) == 1

    def test_clear_candidates_with_staging(self) -> None:
        node = FileNode(path=Path("test.mp4"))
        node.candidates = [
            Candidate(name="TMDB #1", metadata={"title": "Old"}, score=0.8),
        ]
        updater = _make_metadata_updater(
            node,
            {TITLE: "Accepted", TMDB_ID: 456},
            stage=True,
            clear_candidates=True,
        )
        updater()
        assert node.staged is True
        assert node.metadata[TITLE] == "Accepted"
        assert len(node.candidates) == 0

    def test_clear_candidates_false_explicit(self) -> None:
        node = FileNode(path=Path("test.mp4"))
        node.candidates = [
            Candidate(name="TMDB #1", metadata={"title": "Keep"}, score=0.5),
        ]
        updater = _make_metadata_updater(
            node,
            {TITLE: "New"},
            stage=False,
            clear_candidates=False,
        )
        updater()
        assert len(node.candidates) == 1
