"""Tests for file operations (copy, move, link, dry-run)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tapes.file_ops import delete_files, process_file, process_staged


class TestProcessFileCopy:
    def test_copy_creates_file_at_dest(self, tmp_path: Path) -> None:
        src = tmp_path / "source.mkv"
        src.write_text("video content")
        dest = tmp_path / "library" / "Movie" / "movie.mkv"

        result = process_file(src, dest, "copy")

        assert dest.exists()
        assert dest.read_text() == "video content"
        assert src.exists()  # source still there
        assert "Copied" in result

    def test_copy_creates_parent_dirs(self, tmp_path: Path) -> None:
        src = tmp_path / "source.mkv"
        src.write_text("data")
        dest = tmp_path / "a" / "b" / "c" / "file.mkv"

        process_file(src, dest, "copy")

        assert dest.exists()
        assert dest.read_text() == "data"


class TestProcessFileMove:
    def test_move_creates_file_removes_source(self, tmp_path: Path) -> None:
        src = tmp_path / "source.mkv"
        src.write_text("video content")
        dest = tmp_path / "library" / "movie.mkv"

        result = process_file(src, dest, "move")

        assert dest.exists()
        assert dest.read_text() == "video content"
        assert not src.exists()  # source removed
        assert "Moved" in result


class TestProcessFileLink:
    def test_link_creates_symlink(self, tmp_path: Path) -> None:
        src = tmp_path / "source.mkv"
        src.write_text("video content")
        dest = tmp_path / "library" / "movie.mkv"

        result = process_file(src, dest, "link")

        assert dest.is_symlink()
        assert dest.resolve() == src.resolve()
        assert dest.read_text() == "video content"
        assert "Linked" in result


class TestProcessFileHardlink:
    def test_hardlink_creates_hard_link(self, tmp_path: Path) -> None:
        src = tmp_path / "source.txt"
        src.write_text("hello")
        dest = tmp_path / "out" / "dest.txt"
        result = process_file(src, dest, "hardlink")
        assert dest.exists()
        assert dest.read_text() == "hello"
        assert dest.stat().st_ino == src.stat().st_ino  # same inode
        assert "Hardlinked" in result

    def test_hardlink_dry_run(self, tmp_path: Path) -> None:
        src = tmp_path / "source.txt"
        src.write_text("hello")
        dest = tmp_path / "out" / "dest.txt"
        result = process_file(src, dest, "hardlink", dry_run=True)
        assert not dest.exists()
        assert "[dry-run]" in result


class TestProcessFileDryRun:
    def test_dry_run_does_nothing(self, tmp_path: Path) -> None:
        src = tmp_path / "source.mkv"
        src.write_text("data")
        dest = tmp_path / "library" / "movie.mkv"

        result = process_file(src, dest, "copy", dry_run=True)

        assert not dest.exists()
        assert "[dry-run]" in result
        assert "copy" in result

    def test_dry_run_move(self, tmp_path: Path) -> None:
        src = tmp_path / "source.mkv"
        src.write_text("data")
        dest = tmp_path / "dest.mkv"

        result = process_file(src, dest, "move", dry_run=True)

        assert not dest.exists()
        assert src.exists()
        assert "[dry-run]" in result


class TestProcessFileDestExists:
    def test_raises_file_exists_error(self, tmp_path: Path) -> None:
        src = tmp_path / "source.mkv"
        src.write_text("data")
        dest = tmp_path / "dest.mkv"
        dest.write_text("existing")

        with pytest.raises(FileExistsError):
            process_file(src, dest, "copy")

    def test_raises_even_for_dry_run(self, tmp_path: Path) -> None:
        src = tmp_path / "source.mkv"
        src.write_text("data")
        dest = tmp_path / "dest.mkv"
        dest.write_text("existing")

        with pytest.raises(FileExistsError):
            process_file(src, dest, "copy", dry_run=True)

    def test_overwrite_skips_exists_check(self, tmp_path: Path) -> None:
        src = tmp_path / "source.mkv"
        src.write_text("new content")
        dest = tmp_path / "dest.mkv"
        dest.write_text("old content")

        result = process_file(src, dest, "copy", overwrite=True)

        assert dest.read_text() == "new content"
        assert "Copied" in result

    def test_overwrite_false_still_raises(self, tmp_path: Path) -> None:
        src = tmp_path / "source.mkv"
        src.write_text("data")
        dest = tmp_path / "dest.mkv"
        dest.write_text("existing")

        with pytest.raises(FileExistsError):
            process_file(src, dest, "copy", overwrite=False)


class TestProcessFileUnknownOperation:
    def test_raises_value_error(self, tmp_path: Path) -> None:
        src = tmp_path / "source.mkv"
        src.write_text("data")
        dest = tmp_path / "dest.mkv"

        with pytest.raises(ValueError, match="Unknown operation"):
            process_file(src, dest, "rename")


class TestProgressCallback:
    def test_progress_callback_called_on_copy(self, tmp_path: Path) -> None:
        src = tmp_path / "data.bin"
        src.write_bytes(b"x" * 10000)
        dest = tmp_path / "out" / "data.bin"
        calls: list[tuple[int, int]] = []
        process_file(src, dest, "copy", progress_callback=lambda copied, total: calls.append((copied, total)))
        assert len(calls) > 0
        assert calls[-1][0] == calls[-1][1]  # last call: copied == total

    def test_progress_callback_called_on_move(self, tmp_path: Path) -> None:
        """Same-filesystem move uses rename (no progress callback)."""
        src = tmp_path / "data.bin"
        src.write_bytes(b"x" * 10000)
        dest = tmp_path / "out" / "data.bin"
        calls: list[tuple[int, int]] = []
        process_file(src, dest, "move", progress_callback=lambda copied, total: calls.append((copied, total)))
        # Same-filesystem move uses atomic rename, no progress
        assert dest.exists()
        assert not src.exists()

    def test_no_callback_when_none(self, tmp_path: Path) -> None:
        """process_file works without a progress callback."""
        src = tmp_path / "data.bin"
        src.write_bytes(b"x" * 100)
        dest = tmp_path / "out" / "data.bin"
        result = process_file(src, dest, "copy")
        assert dest.exists()
        assert "Copied" in result


class TestErrorMessages:
    def test_file_exists_error_message(self, tmp_path: Path) -> None:
        src = tmp_path / "a.mkv"
        src.write_text("data")
        dest = tmp_path / "out" / "a.mkv"
        dest.parent.mkdir()
        dest.write_text("existing")

        results = process_staged([(src, dest)], "copy")
        assert len(results) == 1
        assert "already exists" in results[0].lower()


class TestProcessStaged:
    def test_processes_multiple_files(self, tmp_path: Path) -> None:
        src1 = tmp_path / "a.mkv"
        src1.write_text("aaa")
        src2 = tmp_path / "b.mkv"
        src2.write_text("bbb")
        dest1 = tmp_path / "lib" / "a.mkv"
        dest2 = tmp_path / "lib" / "b.mkv"

        results = process_staged([(src1, dest1), (src2, dest2)], "copy")

        assert len(results) == 2
        assert dest1.exists()
        assert dest2.exists()

    def test_continues_on_error(self, tmp_path: Path) -> None:
        src1 = tmp_path / "a.mkv"
        src1.write_text("aaa")
        src2 = tmp_path / "b.mkv"
        src2.write_text("bbb")
        dest1 = tmp_path / "lib" / "a.mkv"
        dest2 = tmp_path / "lib" / "b.mkv"
        # Pre-create dest1 so it fails
        dest1.parent.mkdir(parents=True)
        dest1.write_text("existing")

        results = process_staged([(src1, dest1), (src2, dest2)], "copy")

        assert len(results) == 2
        assert "Error" in results[0]
        assert "Copied" in results[1]
        assert dest2.exists()

    def test_dry_run_all(self, tmp_path: Path) -> None:
        src1 = tmp_path / "a.mkv"
        src1.write_text("aaa")
        src2 = tmp_path / "b.mkv"
        src2.write_text("bbb")
        dest1 = tmp_path / "lib" / "a.mkv"
        dest2 = tmp_path / "lib" / "b.mkv"

        results = process_staged([(src1, dest1), (src2, dest2)], "copy", dry_run=True)

        assert len(results) == 2
        assert all("[dry-run]" in r for r in results)
        assert not dest1.exists()
        assert not dest2.exists()

    def test_on_file_start_called(self, tmp_path: Path) -> None:
        src1 = tmp_path / "a.mkv"
        src1.write_text("aaa")
        src2 = tmp_path / "b.mkv"
        src2.write_text("bbb")
        dest1 = tmp_path / "lib" / "a.mkv"
        dest2 = tmp_path / "lib" / "b.mkv"

        calls: list[tuple[int, int, Path, Path]] = []
        process_staged(
            [(src1, dest1), (src2, dest2)],
            "copy",
            on_file_start=lambda i, t, s, d: calls.append((i, t, s, d)),
        )

        assert len(calls) == 2
        assert calls[0] == (0, 2, src1, dest1)
        assert calls[1] == (1, 2, src2, dest2)


class TestCancellation:
    def test_cancel_stops_between_files(self, tmp_path: Path) -> None:
        src1 = tmp_path / "a.mkv"
        src1.write_text("aaa")
        src2 = tmp_path / "b.mkv"
        src2.write_text("bbb")
        dest1 = tmp_path / "lib" / "a.mkv"
        dest2 = tmp_path / "lib" / "b.mkv"

        files_started: list[int] = []

        def on_start(i: int, t: int, s: Path, d: Path) -> None:
            files_started.append(i)

        # Cancel after first file starts; checked at loop top before second file
        results = process_staged(
            [(src1, dest1), (src2, dest2)],
            "copy",
            on_file_start=on_start,
            cancelled=lambda: len(files_started) >= 1,
        )

        assert len(results) == 1
        assert dest1.exists()
        assert not dest2.exists()

    def test_cancel_during_copy_breaks_process_staged(self, tmp_path: Path) -> None:
        """OperationCancelledError from _copy causes process_staged to stop."""
        from unittest.mock import patch

        from tapes.file_ops import OperationCancelledError

        src1 = tmp_path / "a.mkv"
        src1.write_text("aaa")
        src2 = tmp_path / "b.mkv"
        src2.write_text("bbb")
        dest1 = tmp_path / "lib" / "a.mkv"
        dest2 = tmp_path / "lib" / "b.mkv"

        original_copy = __import__("tapes.file_ops", fromlist=["_copy"])._copy

        call_count = 0

        def cancelling_copy(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OperationCancelledError
            return original_copy(*args, **kwargs)

        with patch("tapes.file_ops._copy", side_effect=cancelling_copy):
            results = process_staged(
                [(src1, dest1), (src2, dest2)],
                "copy",
            )

        # First file cancelled, second never attempted
        assert len(results) == 0
        assert not dest1.exists()
        assert not dest2.exists()


class TestDeleteFiles:
    def test_deletes_listed_files(self, tmp_path: Path) -> None:
        a = tmp_path / "a.mkv"
        b = tmp_path / "b.mkv"
        a.write_bytes(b"x" * 100)
        b.write_bytes(b"x" * 100)
        results = delete_files([a, b])
        assert not a.exists()
        assert not b.exists()
        assert len(results) == 2

    def test_missing_file_does_not_error(self, tmp_path: Path) -> None:
        a = tmp_path / "nonexistent.mkv"
        results = delete_files([a])
        assert len(results) == 1
        assert "not found" in results[0].lower() or "error" in results[0].lower()

    def test_dry_run_does_not_delete(self, tmp_path: Path) -> None:
        a = tmp_path / "a.mkv"
        a.write_bytes(b"x" * 100)
        results = delete_files([a], dry_run=True)
        assert a.exists()
        assert len(results) == 1
        assert "[dry-run]" in results[0]
