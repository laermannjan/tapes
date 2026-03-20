"""Tests for tapes.conflicts - unified conflict detection and resolution."""

from __future__ import annotations

from pathlib import Path

from tapes.conflicts import (
    ConflictReport,
    ExistingFile,
    Problem,
    _file_size,
    _suffixed_name,
    detect_conflicts,
)
from tapes.tree_model import FileNode, FileStatus


def _touch(path: Path, content: bytes = b"") -> Path:
    """Create a file with given content, ensuring parent dirs exist."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _node(path: Path) -> FileNode:
    """Create a staged FileNode at the given path."""
    node = FileNode(path=path)
    node.status = FileStatus.STAGED
    return node


class TestExistingFile:
    """ExistingFile virtual node."""

    def test_existing_file_dataclass(self) -> None:
        ef = ExistingFile(path=Path("/lib/movie.mkv"), size=1000)
        assert ef.is_existing is True
        assert ef.size == 1000
        assert ef.path == Path("/lib/movie.mkv")


class TestAutoResolution:
    """conflict_resolution='auto': largest file wins, existing wins ties."""

    def test_no_conflicts(self, tmp_path: Path) -> None:
        """Distinct destinations produce no conflicts."""
        _touch(tmp_path / "a.mkv", b"aaaa")
        _touch(tmp_path / "b.mkv", b"bbbb")
        node_a = _node(tmp_path / "a.mkv")
        node_b = _node(tmp_path / "b.mkv")
        dest_a = tmp_path / "lib" / "A.mkv"
        dest_b = tmp_path / "lib" / "B.mkv"

        report = detect_conflicts(
            [(node_a, dest_a), (node_b, dest_b)],
            conflict_resolution="auto",
        )

        assert len(report.resolved) == 0
        assert len(report.problems) == 0
        assert len(report.valid_pairs) == 2
        assert node_a.staged
        assert node_b.staged

    def test_staged_vs_staged_largest_wins(self, tmp_path: Path) -> None:
        """Larger staged file wins over smaller one at the same dest."""
        _touch(tmp_path / "a.mkv", b"x" * 200)
        _touch(tmp_path / "b.mkv", b"x" * 100)
        node_a = _node(tmp_path / "a.mkv")
        node_b = _node(tmp_path / "b.mkv")
        dest = tmp_path / "lib" / "movie.mkv"

        report = detect_conflicts(
            [(node_a, dest), (node_b, dest)],
            conflict_resolution="auto",
        )

        assert node_a.staged
        assert node_b.rejected
        assert len(report.valid_pairs) == 1
        assert report.valid_pairs[0][0] is node_a

    def test_staged_vs_existing_staged_wins(self, tmp_path: Path) -> None:
        """Staged file larger than existing wins and marks overwrite."""
        _touch(tmp_path / "a.mkv", b"x" * 200)
        node_a = _node(tmp_path / "a.mkv")
        dest = tmp_path / "lib" / "movie.mkv"
        _touch(dest, b"x" * 100)  # existing is smaller

        report = detect_conflicts(
            [(node_a, dest)],
            conflict_resolution="auto",
        )

        assert node_a.staged
        assert len(report.valid_pairs) == 1
        # Should log the overwrite
        assert any("Overwrite" in r.description for r in report.resolved)
        assert dest in report.overwrite_dests

    def test_staged_vs_existing_existing_wins(self, tmp_path: Path) -> None:
        """Existing file larger than staged wins - staged gets rejected."""
        _touch(tmp_path / "a.mkv", b"x" * 100)
        node_a = _node(tmp_path / "a.mkv")
        dest = tmp_path / "lib" / "movie.mkv"
        _touch(dest, b"x" * 200)  # existing is larger

        report = detect_conflicts(
            [(node_a, dest)],
            conflict_resolution="auto",
        )

        assert node_a.rejected
        assert len(report.valid_pairs) == 0

    def test_tie_existing_wins(self, tmp_path: Path) -> None:
        """Same size: existing file wins ties."""
        _touch(tmp_path / "a.mkv", b"x" * 100)
        node_a = _node(tmp_path / "a.mkv")
        dest = tmp_path / "lib" / "movie.mkv"
        _touch(dest, b"x" * 100)  # same size

        detect_conflicts(
            [(node_a, dest)],
            conflict_resolution="auto",
        )

        assert node_a.rejected

    def test_staged_vs_staged_tiebreak_by_index(self, tmp_path: Path) -> None:
        """Equal-size staged files: first-in-scan-order wins."""
        _touch(tmp_path / "z_second.mkv", b"x" * 100)
        _touch(tmp_path / "a_first.mkv", b"x" * 100)
        # z_second is passed first in the pairs list
        node_z = _node(tmp_path / "z_second.mkv")
        node_a = _node(tmp_path / "a_first.mkv")
        dest = tmp_path / "lib" / "movie.mkv"

        report = detect_conflicts(
            [(node_z, dest), (node_a, dest)],
            conflict_resolution="auto",
        )

        # node_z was passed first (index 0), so it wins the tiebreak
        assert node_z.staged
        assert node_a.rejected
        assert len(report.valid_pairs) == 1
        assert report.valid_pairs[0][0] is node_z

    def test_three_way_two_staged_plus_existing(self, tmp_path: Path) -> None:
        """Two staged + one existing at the same dest - largest wins overall."""
        _touch(tmp_path / "a.mkv", b"x" * 300)
        _touch(tmp_path / "b.mkv", b"x" * 100)
        node_a = _node(tmp_path / "a.mkv")
        node_b = _node(tmp_path / "b.mkv")
        dest = tmp_path / "lib" / "movie.mkv"
        _touch(dest, b"x" * 200)  # existing is medium

        report = detect_conflicts(
            [(node_a, dest), (node_b, dest)],
            conflict_resolution="auto",
        )

        # node_a is largest (300), wins
        assert node_a.staged
        assert node_b.rejected
        assert len(report.valid_pairs) == 1
        assert report.valid_pairs[0][0] is node_a
        # Existing file beaten - should log overwrite
        assert any("Overwrite" in r.description for r in report.resolved)
        assert dest in report.overwrite_dests


class TestSkipResolution:
    """conflict_resolution='skip': existing always wins; staged-vs-staged uses auto."""

    def test_existing_always_wins(self, tmp_path: Path) -> None:
        """Even if staged is larger, existing wins in skip mode."""
        _touch(tmp_path / "a.mkv", b"x" * 200)
        node_a = _node(tmp_path / "a.mkv")
        dest = tmp_path / "lib" / "movie.mkv"
        _touch(dest, b"x" * 100)

        report = detect_conflicts(
            [(node_a, dest)],
            conflict_resolution="skip",
        )

        assert node_a.rejected
        assert len(report.valid_pairs) == 0

    def test_no_existing_falls_back_to_auto(self, tmp_path: Path) -> None:
        """Without existing file, skip mode falls back to auto resolution."""
        _touch(tmp_path / "a.mkv", b"x" * 200)
        _touch(tmp_path / "b.mkv", b"x" * 100)
        node_a = _node(tmp_path / "a.mkv")
        node_b = _node(tmp_path / "b.mkv")
        dest = tmp_path / "lib" / "movie.mkv"

        detect_conflicts(
            [(node_a, dest), (node_b, dest)],
            conflict_resolution="skip",
        )

        assert node_a.staged  # largest wins (auto fallback)
        assert node_b.rejected


class TestKeepAllResolution:
    """conflict_resolution='keep_all': all files kept with suffixes."""

    def test_all_get_processed_with_suffixes(self, tmp_path: Path) -> None:
        """Two staged files at the same dest - first keeps name, second gets suffix."""
        _touch(tmp_path / "a.mkv", b"x" * 100)
        _touch(tmp_path / "b.mkv", b"x" * 100)
        node_a = _node(tmp_path / "a.mkv")
        node_b = _node(tmp_path / "b.mkv")
        dest = tmp_path / "lib" / "Dune (2021).mkv"

        report = detect_conflicts(
            [(node_a, dest), (node_b, dest)],
            conflict_resolution="keep_all",
        )

        assert node_a.staged
        assert node_b.staged
        assert len(report.valid_pairs) == 2
        dests = {d.name for _, d in report.valid_pairs}
        assert "Dune (2021).mkv" in dests
        assert "Dune (2021) 2.mkv" in dests

    def test_existing_keeps_clean_name(self, tmp_path: Path) -> None:
        """When an existing file is present, all staged get suffixes."""
        _touch(tmp_path / "a.mkv", b"x" * 100)
        node_a = _node(tmp_path / "a.mkv")
        dest = tmp_path / "lib" / "Dune (2021).mkv"
        _touch(dest, b"x" * 100)

        report = detect_conflicts(
            [(node_a, dest)],
            conflict_resolution="keep_all",
        )

        assert node_a.staged
        assert len(report.valid_pairs) == 1
        assert report.valid_pairs[0][1].name == "Dune (2021) 2.mkv"


class TestWritabilityCheck:
    """Writability: destination directory must be writable."""

    def test_writable_passes(self, tmp_path: Path) -> None:
        """Writable destination directories pass through."""
        _touch(tmp_path / "movie.mkv", b"data")
        node = _node(tmp_path / "movie.mkv")
        dest = tmp_path / "lib" / "Movie.mkv"

        report = detect_conflicts([(node, dest)], conflict_resolution="auto")

        assert len(report.problems) == 0
        assert len(report.valid_pairs) == 1
        assert node.staged

    def test_unwritable_destination_rejects(self, tmp_path: Path) -> None:
        """Unwritable destination is reported as problem, node rejected."""
        _touch(tmp_path / "movie.mkv", b"data")
        node = _node(tmp_path / "movie.mkv")
        # Create a read-only directory.
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o555)
        dest = readonly_dir / "sub" / "Movie.mkv"

        try:
            report = detect_conflicts([(node, dest)], conflict_resolution="auto")

            assert len(report.problems) == 1
            assert "not writable" in report.problems[0].description.lower()
            assert node in report.problems[0].rejected_nodes
            assert node.rejected
            assert len(report.valid_pairs) == 0
        finally:
            readonly_dir.chmod(0o755)


class TestRejectedCount:
    """ConflictReport.rejected_count property."""

    def test_rejected_count_sums_across_problems(self, tmp_path: Path) -> None:
        """rejected_count sums all rejected nodes across problems."""
        report = ConflictReport(
            problems=[
                Problem(description="p1", rejected_nodes=[FileNode(path=tmp_path / "a.mkv")]),
                Problem(
                    description="p2",
                    rejected_nodes=[
                        FileNode(path=tmp_path / "b.mkv"),
                        FileNode(path=tmp_path / "c.mkv"),
                    ],
                ),
            ],
        )
        assert report.rejected_count == 3

    def test_rejected_count_empty(self) -> None:
        """rejected_count is 0 when no problems."""
        report = ConflictReport()
        assert report.rejected_count == 0


class TestSuffixedName:
    """_suffixed_name preserves full extensions."""

    def test_simple_extension(self) -> None:
        result = _suffixed_name(Path("/lib/Movie.mkv"), 2)
        assert result == Path("/lib/Movie 2.mkv")

    def test_compound_extension(self) -> None:
        result = _suffixed_name(Path("/lib/movie.en.srt"), 2)
        assert result == Path("/lib/movie 2.en.srt")

    def test_forced_en_srt(self) -> None:
        result = _suffixed_name(Path("/lib/Movie.forced.en.srt"), 3)
        assert result == Path("/lib/Movie 3.forced.en.srt")


class TestFileSize:
    """_file_size returns -1 on error."""

    def test_returns_actual_size(self, tmp_path: Path) -> None:
        _touch(tmp_path / "a.mkv", b"x" * 42)
        node = FileNode(path=tmp_path / "a.mkv")
        assert _file_size(node) == 42

    def test_returns_neg1_on_oserror(self, tmp_path: Path) -> None:
        node = FileNode(path=tmp_path / "nonexistent.mkv")
        assert _file_size(node) == -1

    def test_neg1_sort_behavior(self, tmp_path: Path) -> None:
        """File with OSError (-1 size) loses to any real file in auto mode."""
        _touch(tmp_path / "good.mkv", b"x" * 10)
        node_good = _node(tmp_path / "good.mkv")
        node_bad = _node(tmp_path / "nonexistent.mkv")
        dest = tmp_path / "lib" / "movie.mkv"

        detect_conflicts(
            [(node_bad, dest), (node_good, dest)],
            conflict_resolution="auto",
        )

        assert node_good.staged
        assert node_bad.rejected


class TestEmptyInput:
    """Edge cases with empty input."""

    def test_empty_pairs(self) -> None:
        report = detect_conflicts([], conflict_resolution="auto")
        assert report.valid_pairs == []
        assert report.resolved == []
        assert report.problems == []
        assert report.rejected_count == 0


class TestOverwriteDests:
    """overwrite_dests tracking for process_file integration."""

    def test_overwrite_dests_populated_on_auto_win(self, tmp_path: Path) -> None:
        """When staged beats existing in auto mode, dest is in overwrite_dests."""
        _touch(tmp_path / "a.mkv", b"x" * 200)
        node_a = _node(tmp_path / "a.mkv")
        dest = tmp_path / "lib" / "movie.mkv"
        _touch(dest, b"x" * 100)

        report = detect_conflicts([(node_a, dest)], conflict_resolution="auto")

        assert dest in report.overwrite_dests

    def test_overwrite_dests_empty_when_no_existing(self, tmp_path: Path) -> None:
        """No existing files means no overwrite destinations."""
        _touch(tmp_path / "a.mkv", b"x" * 100)
        _touch(tmp_path / "b.mkv", b"x" * 50)
        node_a = _node(tmp_path / "a.mkv")
        node_b = _node(tmp_path / "b.mkv")
        dest = tmp_path / "lib" / "movie.mkv"

        report = detect_conflicts(
            [(node_a, dest), (node_b, dest)],
            conflict_resolution="auto",
        )

        assert len(report.overwrite_dests) == 0

    def test_overwrite_dests_empty_when_existing_wins(self, tmp_path: Path) -> None:
        """When existing wins, nothing to overwrite."""
        _touch(tmp_path / "a.mkv", b"x" * 100)
        node_a = _node(tmp_path / "a.mkv")
        dest = tmp_path / "lib" / "movie.mkv"
        _touch(dest, b"x" * 200)

        report = detect_conflicts([(node_a, dest)], conflict_resolution="auto")

        assert len(report.overwrite_dests) == 0
