"""Tests for file operations (copy, move, link, dry-run)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tapes.file_ops import process_file, process_staged


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


class TestProcessFileUnknownOperation:
    def test_raises_value_error(self, tmp_path: Path) -> None:
        src = tmp_path / "source.mkv"
        src.write_text("data")
        dest = tmp_path / "dest.mkv"

        with pytest.raises(ValueError, match="Unknown operation"):
            process_file(src, dest, "rename")


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
