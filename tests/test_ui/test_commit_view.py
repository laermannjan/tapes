"""Tests for the inline commit view."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from tapes.ui.commit_view import CommitView, categorize_staged
from tapes.ui.tree_model import FileNode


def _render_plain(widget, width: int = 80, height: int = 20) -> str:
    fake_size = SimpleNamespace(width=width, height=height)
    with patch.object(
        type(widget), "size", new_callable=lambda: PropertyMock(return_value=fake_size)
    ):
        rendered = widget.render()
    return rendered.plain


class TestCategorizeStaged:
    def test_movies(self) -> None:
        files = [
            FileNode(path=Path("/a.mkv"), result={"media_type": "movie"}),
            FileNode(path=Path("/b.mkv"), result={"media_type": "movie"}),
        ]
        cats = categorize_staged(files)
        assert cats["movies"] == 2

    def test_episodes(self) -> None:
        files = [
            FileNode(
                path=Path("/a.mkv"),
                result={"media_type": "episode", "title": "Show", "season": 1},
            ),
            FileNode(
                path=Path("/b.mkv"),
                result={"media_type": "episode", "title": "Show", "season": 2},
            ),
            FileNode(
                path=Path("/c.mkv"),
                result={"media_type": "episode", "title": "Other", "season": 1},
            ),
        ]
        cats = categorize_staged(files)
        assert cats["episodes"] == 3
        assert cats["shows"] == 2
        assert cats["seasons"] == 3

    def test_subtitles(self) -> None:
        files = [
            FileNode(path=Path("/a.srt"), result={}),
            FileNode(path=Path("/b.ass"), result={}),
        ]
        cats = categorize_staged(files)
        assert cats["subtitles"] == 2

    def test_sidecars(self) -> None:
        files = [
            FileNode(path=Path("/a.nfo"), result={}),
            FileNode(path=Path("/b.xml"), result={}),
            FileNode(path=Path("/c.jpg"), result={}),
        ]
        cats = categorize_staged(files)
        assert cats["sidecars"] == 3

    def test_other(self) -> None:
        files = [
            FileNode(path=Path("/a.txt"), result={}),
        ]
        cats = categorize_staged(files)
        assert cats["other"] == 1

    def test_total(self) -> None:
        files = [
            FileNode(path=Path("/a.mkv"), result={"media_type": "movie"}),
            FileNode(path=Path("/b.srt"), result={}),
        ]
        cats = categorize_staged(files)
        assert cats["total"] == 2


class TestCommitViewRender:
    def test_renders_separator(self) -> None:
        files = [FileNode(path=Path("/a.mkv"), result={"media_type": "movie"})]
        view = CommitView(files, "copy")
        plain = _render_plain(view)
        assert "Commit" in plain

    def test_renders_stats(self) -> None:
        files = [
            FileNode(path=Path("/a.mkv"), result={"media_type": "movie"}),
            FileNode(path=Path("/b.mkv"), result={"media_type": "movie"}),
        ]
        view = CommitView(files, "copy")
        plain = _render_plain(view)
        assert "2 movies" in plain

    def test_renders_operation(self) -> None:
        files = [FileNode(path=Path("/a.mkv"), result={"media_type": "movie"})]
        view = CommitView(files, "move")
        plain = _render_plain(view)
        assert "move" in plain

    def test_renders_hints(self) -> None:
        files = [FileNode(path=Path("/a.mkv"), result={"media_type": "movie"})]
        view = CommitView(files, "copy")
        plain = _render_plain(view)
        assert "enter confirm" in plain
        assert "esc cancel" in plain

    def test_cycle_operation_wraps(self) -> None:
        files = [FileNode(path=Path("/a.mkv"), result={"media_type": "movie"})]
        view = CommitView(files, "hardlink")
        view.cycle_operation(1)
        assert view.operation == "copy"


class TestCommitViewHeight:
    def test_height_calculation(self) -> None:
        files = [FileNode(path=Path("/a.mkv"), result={"media_type": "movie"})]
        view = CommitView(files, "copy")
        # Must be at least 7 lines
        assert view.computed_height >= 7
