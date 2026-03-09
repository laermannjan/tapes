"""Tests for tapes.conflicts -- conflict detection and auto-resolution."""

from __future__ import annotations

from pathlib import Path

from tapes.conflicts import ConflictReport, Problem, detect_conflicts
from tapes.tree_model import FileNode


def _touch(path: Path, content: bytes = b"") -> Path:
    """Create a file with given content, ensuring parent dirs exist."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _node(path: Path, staged: bool = True, **result_fields: object) -> FileNode:
    """Create a FileNode with the given path, staged flag, and result fields."""
    return FileNode(path=path, staged=staged, metadata=dict(result_fields))


class TestDuplicateDetection:
    """Duplicate detection: same destination, same file size."""

    def test_no_conflicts(self, tmp_path: Path) -> None:
        """Distinct destinations produce no conflicts."""
        src_a = _touch(tmp_path / "a.mkv", b"aaaa")
        src_b = _touch(tmp_path / "b.mkv", b"bbbb")
        node_a = _node(src_a, title="A")
        node_b = _node(src_b, title="B")
        dest_a = tmp_path / "lib" / "A.mkv"
        dest_b = tmp_path / "lib" / "B.mkv"

        report = detect_conflicts([(node_a, dest_a), (node_b, dest_b)])

        assert len(report.resolved) == 0
        assert len(report.problems) == 0
        assert len(report.valid_pairs) == 2

    def test_same_dest_same_size_unstages_lesser(self, tmp_path: Path) -> None:
        """Same dest + same size: node with fewer result fields is unstaged."""
        src_a = _touch(tmp_path / "a.mkv", b"xxxx")
        src_b = _touch(tmp_path / "b.mkv", b"yyyy")
        # b has more metadata fields than a.
        node_a = _node(src_a, title="Movie")
        node_b = _node(src_b, title="Movie", year=2024, tmdb_id=123)
        dest = tmp_path / "lib" / "Movie.mkv"

        report = detect_conflicts([(node_a, dest), (node_b, dest)])

        assert len(report.resolved) == 1
        assert "unstaged" in report.resolved[0].description
        assert node_a.staged is False
        assert node_b.staged is True
        assert len(report.valid_pairs) == 1
        assert report.valid_pairs[0][0] is node_b

    def test_same_dest_same_size_keeps_more_metadata(self, tmp_path: Path) -> None:
        """The node with more result fields is kept."""
        src_a = _touch(tmp_path / "a.mkv", b"data")
        src_b = _touch(tmp_path / "b.mkv", b"data")
        # a has 3 fields, b has 1.
        node_a = _node(src_a, title="Movie", year=2024, tmdb_id=42)
        node_b = _node(src_b, title="Movie")
        dest = tmp_path / "lib" / "Movie.mkv"

        report = detect_conflicts([(node_a, dest), (node_b, dest)])

        assert len(report.valid_pairs) == 1
        assert report.valid_pairs[0][0] is node_a
        assert node_a.staged is True
        assert node_b.staged is False

    def test_same_dest_different_size_disambiguates(self, tmp_path: Path) -> None:
        """Same dest + different size goes to disambiguation, not duplicate."""
        src_a = _touch(tmp_path / "a.mkv", b"short")
        src_b = _touch(tmp_path / "b.mkv", b"much longer content")
        node_a = _node(src_a, title="Movie")
        node_b = _node(src_b, title="Movie")
        dest = tmp_path / "lib" / "Movie.mkv"

        report = detect_conflicts([(node_a, dest), (node_b, dest)])

        # Both should remain (one renamed), no duplicates resolved.
        assert len(report.valid_pairs) == 2
        assert node_a.staged is True
        assert node_b.staged is True
        # One should have been renamed.
        dests = [d for _, d in report.valid_pairs]
        assert dest in dests
        renamed = [d for d in dests if d != dest]
        assert len(renamed) == 1
        assert "-2" in renamed[0].name

    def test_three_way_mixed_conflict(self, tmp_path: Path) -> None:
        """Three files at same dest: two same-size (duplicate) + one different (disambiguate)."""
        src_a = _touch(tmp_path / "a.mkv", b"same")
        src_b = _touch(tmp_path / "b.mkv", b"same")
        src_c = _touch(tmp_path / "c.mkv", b"different content")
        node_a = _node(src_a, title="Movie", year=2024)
        node_b = _node(src_b, title="Movie")
        node_c = _node(src_c, title="Movie")
        dest = tmp_path / "lib" / "Movie.mkv"

        report = detect_conflicts([(node_a, dest), (node_b, dest), (node_c, dest)])

        # node_b should be unstaged as duplicate (fewer fields than node_a).
        assert node_b.staged is False
        # node_a and node_c should survive (one original, one renamed).
        assert node_a.staged is True
        assert node_c.staged is True
        assert len(report.valid_pairs) == 2
        # At least one resolved conflict (the duplicate).
        assert any("unstaged" in r.description for r in report.resolved)

    def test_preserves_full_extension(self, tmp_path: Path) -> None:
        """Disambiguation preserves multi-tag extensions like .en.srt."""
        src_a = _touch(tmp_path / "a.en.srt", b"sub A")
        src_b = _touch(tmp_path / "b.en.srt", b"sub B different")
        node_a = _node(src_a, title="Movie")
        node_b = _node(src_b, title="Movie")
        dest = tmp_path / "lib" / "Movie.en.srt"

        report = detect_conflicts([(node_a, dest), (node_b, dest)])

        assert len(report.valid_pairs) == 2
        dests = {d.name for _, d in report.valid_pairs}
        assert "Movie.en.srt" in dests
        assert "Movie-2.en.srt" in dests

    def test_tie_break_alphabetical(self, tmp_path: Path) -> None:
        """When result field counts are equal, alphabetically first path wins."""
        src_a = _touch(tmp_path / "alpha.mkv", b"data")
        src_b = _touch(tmp_path / "beta.mkv", b"data")
        node_a = _node(src_a, title="Movie")
        node_b = _node(src_b, title="Movie")
        dest = tmp_path / "lib" / "Movie.mkv"

        report = detect_conflicts([(node_a, dest), (node_b, dest)])

        # Same field count, so alphabetically first (alpha) wins.
        assert len(report.valid_pairs) == 1
        assert report.valid_pairs[0][0] is node_a
        assert node_b.staged is False


class TestWritabilityCheck:
    """Writability: destination directory must be writable."""

    def test_writable_passes(self, tmp_path: Path) -> None:
        """Writable destination directories pass through."""
        src = _touch(tmp_path / "movie.mkv", b"data")
        node = _node(src, title="Movie")
        dest = tmp_path / "lib" / "Movie.mkv"

        report = detect_conflicts([(node, dest)])

        assert len(report.problems) == 0
        assert len(report.valid_pairs) == 1
        assert node.staged is True

    def test_unwritable_reported_as_problem(self, tmp_path: Path) -> None:
        """Unwritable destination is reported as problem, node unstaged."""
        src = _touch(tmp_path / "movie.mkv", b"data")
        node = _node(src, title="Movie")
        # Create a read-only directory.
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o555)
        dest = readonly_dir / "sub" / "Movie.mkv"

        try:
            report = detect_conflicts([(node, dest)])

            assert len(report.problems) == 1
            assert "not writable" in report.problems[0].description.lower()
            assert node in report.problems[0].skipped_nodes
            assert node.staged is False
            assert len(report.valid_pairs) == 0
        finally:
            # Restore permissions for cleanup.
            readonly_dir.chmod(0o755)

    def test_skipped_count_property(self, tmp_path: Path) -> None:
        """skipped_count sums all skipped nodes across problems."""
        report = ConflictReport(
            problems=[
                Problem(description="p1", skipped_nodes=[_node(tmp_path / "a.mkv")]),
                Problem(
                    description="p2",
                    skipped_nodes=[
                        _node(tmp_path / "b.mkv"),
                        _node(tmp_path / "c.mkv"),
                    ],
                ),
            ],
        )
        assert report.skipped_count == 3

    def test_skipped_count_empty(self) -> None:
        """skipped_count is 0 when no problems."""
        report = ConflictReport()
        assert report.skipped_count == 0


class TestExistingFileCheck:
    """Disambiguation when destination already exists on disk."""

    def test_existing_file_gets_disambiguated(self, tmp_path: Path) -> None:
        """A file targeting an existing destination gets a -2 suffix."""
        src = _touch(tmp_path / "new_movie.mkv", b"new data")
        # Pre-create the destination.
        dest = tmp_path / "lib" / "Movie.mkv"
        _touch(dest, b"existing data")
        node = _node(src, title="Movie")

        report = detect_conflicts([(node, dest)])

        assert len(report.valid_pairs) == 1
        new_dest = report.valid_pairs[0][1]
        assert new_dest.name == "Movie-2.mkv"
        assert new_dest.parent == dest.parent
        assert len(report.resolved) == 1
        assert "Renamed" in report.resolved[0].description

    def test_warn_mode_reports_problem(self, tmp_path: Path) -> None:
        """In warn mode, existing destination is reported as problem."""
        src = _touch(tmp_path / "movie.mkv", b"data")
        dest = tmp_path / "lib" / "Movie.mkv"
        _touch(dest, b"existing")
        node = _node(src, title="Movie")

        report = detect_conflicts([(node, dest)], disambiguation="warn")

        assert len(report.problems) == 1
        assert "already exists" in report.problems[0].description.lower()
        assert node.staged is False
        assert len(report.valid_pairs) == 0

    def test_existing_file_with_full_extension(self, tmp_path: Path) -> None:
        """Existing file disambiguation preserves full extension."""
        src = _touch(tmp_path / "sub.forced.en.srt", b"sub data")
        dest = tmp_path / "lib" / "Movie.forced.en.srt"
        _touch(dest, b"existing")
        node = _node(src, title="Movie")

        report = detect_conflicts([(node, dest)])

        assert len(report.valid_pairs) == 1
        new_dest = report.valid_pairs[0][1]
        assert new_dest.name == "Movie-2.forced.en.srt"


class TestConfigModes:
    """Config mode toggling for duplicate_resolution and disambiguation."""

    def test_duplicate_resolution_off_skips(self, tmp_path: Path) -> None:
        """duplicate_resolution=off skips duplicate detection entirely."""
        src_a = _touch(tmp_path / "a.mkv", b"same")
        src_b = _touch(tmp_path / "b.mkv", b"same")
        node_a = _node(src_a, title="Movie")
        node_b = _node(src_b, title="Movie")
        dest = tmp_path / "lib" / "Movie.mkv"

        report = detect_conflicts(
            [(node_a, dest), (node_b, dest)],
            duplicate_resolution="off",
        )

        # Both nodes pass through duplicate check, but disambiguation
        # still triggers since they share a destination.
        assert node_a.staged is True
        assert node_b.staged is True
        # Disambiguation should rename one.
        assert len(report.valid_pairs) == 2

    def test_disambiguation_off_skips(self, tmp_path: Path) -> None:
        """disambiguation=off skips disambiguation entirely."""
        src_a = _touch(tmp_path / "a.mkv", b"short")
        src_b = _touch(tmp_path / "b.mkv", b"much longer")
        node_a = _node(src_a, title="Movie")
        node_b = _node(src_b, title="Movie")
        dest = tmp_path / "lib" / "Movie.mkv"

        report = detect_conflicts(
            [(node_a, dest), (node_b, dest)],
            disambiguation="off",
        )

        # Both pass through without renaming.
        assert len(report.valid_pairs) == 2
        dests = [d for _, d in report.valid_pairs]
        # Both still point at the same destination (no renaming).
        assert all(d == dest for d in dests)
        assert len(report.resolved) == 0

    def test_duplicate_resolution_warn(self, tmp_path: Path) -> None:
        """duplicate_resolution=warn reports duplicates as problems."""
        src_a = _touch(tmp_path / "a.mkv", b"same")
        src_b = _touch(tmp_path / "b.mkv", b"same")
        node_a = _node(src_a, title="Movie", year=2024)
        node_b = _node(src_b, title="Movie")
        dest = tmp_path / "lib" / "Movie.mkv"

        report = detect_conflicts(
            [(node_a, dest), (node_b, dest)],
            duplicate_resolution="warn",
        )

        assert len(report.problems) == 1
        assert "Duplicate" in report.problems[0].description
        assert node_a.staged is False
        assert node_b.staged is False
        assert len(report.valid_pairs) == 0

    def test_disambiguation_warn(self, tmp_path: Path) -> None:
        """disambiguation=warn reports ambiguous destinations as problems."""
        src_a = _touch(tmp_path / "a.mkv", b"short")
        src_b = _touch(tmp_path / "b.mkv", b"much longer")
        node_a = _node(src_a, title="Movie")
        node_b = _node(src_b, title="Movie")
        dest = tmp_path / "lib" / "Movie.mkv"

        report = detect_conflicts(
            [(node_a, dest), (node_b, dest)],
            disambiguation="warn",
        )

        assert len(report.problems) == 1
        assert "Multiple files" in report.problems[0].description
        assert node_a.staged is False
        assert node_b.staged is False
        assert len(report.valid_pairs) == 0

    def test_both_off_passes_everything(self, tmp_path: Path) -> None:
        """Both checks off: all pairs pass through unchanged."""
        src_a = _touch(tmp_path / "a.mkv", b"same")
        src_b = _touch(tmp_path / "b.mkv", b"same")
        node_a = _node(src_a, title="Movie")
        node_b = _node(src_b, title="Movie")
        dest = tmp_path / "lib" / "Movie.mkv"

        report = detect_conflicts(
            [(node_a, dest), (node_b, dest)],
            duplicate_resolution="off",
            disambiguation="off",
        )

        assert len(report.valid_pairs) == 2
        assert len(report.resolved) == 0
        assert len(report.problems) == 0

    def test_empty_pairs(self) -> None:
        """Empty input produces empty report."""
        report = detect_conflicts([])
        assert report.valid_pairs == []
        assert report.resolved == []
        assert report.problems == []
        assert report.skipped_count == 0
