"""Tests for the inline commit view."""

from __future__ import annotations

from pathlib import Path

from tapes.categorize import categorize_staged
from tapes.tree_model import FileNode
from tapes.ui.commit_view import CommitView
from tests.test_ui.conftest import render_plain


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
        plain = render_plain(view)
        assert "Commit" in plain

    def test_renders_stats(self) -> None:
        files = [
            FileNode(path=Path("/a.mkv"), result={"media_type": "movie"}),
            FileNode(path=Path("/b.mkv"), result={"media_type": "movie"}),
        ]
        view = CommitView(files, "copy")
        plain = render_plain(view)
        assert "2 movies" in plain

    def test_renders_operation(self) -> None:
        files = [FileNode(path=Path("/a.mkv"), result={"media_type": "movie"})]
        view = CommitView(files, "move")
        plain = render_plain(view)
        assert "move" in plain

    def test_renders_hints(self) -> None:
        files = [FileNode(path=Path("/a.mkv"), result={"media_type": "movie"})]
        view = CommitView(files, "copy")
        plain = render_plain(view)
        assert "enter to confirm" in plain
        assert "esc to cancel" in plain

    def test_cycle_operation_wraps(self) -> None:
        files = [FileNode(path=Path("/a.mkv"), result={"media_type": "movie"})]
        view = CommitView(files, "hardlink")
        view.cycle_operation(1)
        assert view.operation == "copy"


class TestCommitViewLibraryPaths:
    def test_renders_movie_path(self) -> None:
        files = [FileNode(path=Path("/a.mkv"), result={"media_type": "movie"})]
        view = CommitView(files, "copy", movies_path="/media/Movies", tv_path="/media/TV")
        plain = render_plain(view)
        assert "movies" in plain
        assert "/media/Movies" in plain

    def test_renders_tv_path(self) -> None:
        files = [FileNode(path=Path("/a.mkv"), result={"media_type": "episode"})]
        view = CommitView(files, "copy", movies_path="/media/Movies", tv_path="/media/TV")
        plain = render_plain(view)
        assert "tv" in plain
        assert "/media/TV" in plain

    def test_empty_paths_show_not_set(self) -> None:
        files = [FileNode(path=Path("/a.mkv"), result={"media_type": "movie"})]
        view = CommitView(files, "copy")
        plain = render_plain(view)
        assert "(not set)" in plain

    def test_height_includes_library_lines(self) -> None:
        files = [FileNode(path=Path("/a.mkv"), result={"media_type": "movie"})]
        view_without = CommitView(files, "copy")
        view_with = CommitView(files, "copy", movies_path="/x", tv_path="/y")
        # Both should account for library path lines
        assert view_with.computed_height == view_without.computed_height


class TestCommitViewProgress:
    def test_progress_replaces_stats(self) -> None:
        files = [FileNode(path=Path("/a.mkv"), result={"media_type": "movie"})]
        view = CommitView(files, "copy")
        view.progress_text = "2/5 files ... movie.mkv"
        plain = render_plain(view)
        assert "2/5 files" in plain
        assert "movie.mkv" in plain
        # Stats should not appear
        assert "enter to confirm" not in plain

    def test_progress_shows_operation(self) -> None:
        files = [FileNode(path=Path("/a.mkv"), result={"media_type": "movie"})]
        view = CommitView(files, "move")
        view.progress_text = "1/3 files ... a.mkv"
        plain = render_plain(view)
        assert "move" in plain

    def test_progress_shows_esc_hint(self) -> None:
        files = [FileNode(path=Path("/a.mkv"), result={"media_type": "movie"})]
        view = CommitView(files, "copy")
        view.progress_text = "1/3 files ... a.mkv"
        plain = render_plain(view)
        assert "esc to interrupt" in plain

    def test_progress_height_is_compact(self) -> None:
        files = [FileNode(path=Path("/a.mkv"), result={"media_type": "movie"})]
        view = CommitView(files, "copy")
        normal_height = view.computed_height
        view.progress_text = "1/1 files ... a.mkv"
        assert view.computed_height < normal_height


class TestCommitViewHeight:
    def test_height_calculation(self) -> None:
        files = [FileNode(path=Path("/a.mkv"), result={"media_type": "movie"})]
        view = CommitView(files, "copy")
        # Must be at least 7 lines
        assert view.computed_height >= 7
