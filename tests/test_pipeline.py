"""Tests for the four-pass import pipeline."""

from __future__ import annotations

from pathlib import Path

from tapes.config import TapesConfig, ScanConfig
from tapes.models import FileEntry, GroupType, ImportGroup
from tapes.pipeline import run_pipeline


def _make_video(tmp_path: Path, name: str) -> Path:
    """Create a zero-byte video file and return its path."""
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.touch()
    return p


def _make_companion(tmp_path: Path, name: str) -> Path:
    """Create a zero-byte companion file and return its path."""
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.touch()
    return p


class TestEmptyDirectory:
    def test_empty_returns_empty_list(self, tmp_path: Path) -> None:
        result = run_pipeline(tmp_path)
        assert result == []

    def test_no_video_files_returns_empty(self, tmp_path: Path) -> None:
        (tmp_path / "readme.txt").touch()
        (tmp_path / "notes.pdf").touch()
        result = run_pipeline(tmp_path)
        assert result == []


class TestSingleMovie:
    def test_single_movie_creates_one_group(self, tmp_path: Path) -> None:
        _make_video(tmp_path, "Inception.2010.mkv")
        result = run_pipeline(tmp_path)
        assert len(result) == 1
        group = result[0]
        assert group.metadata.title == "Inception"
        assert group.metadata.year == 2010
        assert group.group_type == GroupType.STANDALONE

    def test_single_movie_video_file_in_group(self, tmp_path: Path) -> None:
        vid = _make_video(tmp_path, "Inception.2010.mkv")
        result = run_pipeline(tmp_path)
        video_files = result[0].video_files
        assert len(video_files) == 1
        assert video_files[0].path == vid


class TestEpisodeGrouping:
    def test_episodes_same_season_stay_separate(self, tmp_path: Path) -> None:
        _make_video(tmp_path, "Breaking.Bad.S01E01.mkv")
        _make_video(tmp_path, "Breaking.Bad.S01E02.mkv")
        result = run_pipeline(tmp_path)
        # Each episode is its own STANDALONE group
        assert len(result) == 2
        for group in result:
            assert group.group_type == GroupType.STANDALONE
            assert len(group.video_files) == 1

    def test_episodes_different_seasons_separate(self, tmp_path: Path) -> None:
        _make_video(tmp_path, "Breaking.Bad.S01E01.mkv")
        _make_video(tmp_path, "Breaking.Bad.S02E01.mkv")
        result = run_pipeline(tmp_path)
        assert len(result) == 2


class TestMultiPartGrouping:
    def test_multi_part_merged(self, tmp_path: Path) -> None:
        _make_video(tmp_path, "Kill.Bill.cd1.mkv")
        _make_video(tmp_path, "Kill.Bill.cd2.mkv")
        result = run_pipeline(tmp_path)
        multi_groups = [g for g in result if g.group_type == GroupType.MULTI_PART]
        assert len(multi_groups) == 1
        assert len(multi_groups[0].video_files) == 2


class TestCompanionsAttached:
    def test_subtitle_attached_to_video(self, tmp_path: Path) -> None:
        _make_video(tmp_path, "Inception.2010.mkv")
        sub = _make_companion(tmp_path, "Inception.2010.srt")
        result = run_pipeline(tmp_path)
        assert len(result) == 1
        group = result[0]
        companions = [f for f in group.files if f.role != "video"]
        assert len(companions) == 1
        assert companions[0].path == sub

    def test_multiple_companions_attached(self, tmp_path: Path) -> None:
        _make_video(tmp_path, "Inception.2010.mkv")
        _make_companion(tmp_path, "Inception.2010.srt")
        _make_companion(tmp_path, "Inception.2010.nfo")
        result = run_pipeline(tmp_path)
        companions = [f for f in result[0].files if f.role != "video"]
        assert len(companions) == 2


class TestCompanionDedup:
    def test_companion_not_claimed_by_multiple_groups(self, tmp_path: Path) -> None:
        """When two videos could match the same companion, only one gets it."""
        # Two videos with overlapping stem prefixes
        _make_video(tmp_path, "Movie.mkv")
        _make_video(tmp_path, "Movie.Extended.mkv")
        # This companion matches "Movie" exactly
        _make_companion(tmp_path, "Movie.srt")
        result = run_pipeline(tmp_path)
        # Count how many groups contain the companion
        groups_with_companion = [
            g for g in result
            if any(f.path.name == "Movie.srt" for f in g.files)
        ]
        assert len(groups_with_companion) == 1

    def test_companion_dedup_across_groups(self, tmp_path: Path) -> None:
        """A companion file should appear in at most one group across all groups."""
        _make_video(tmp_path, "Show.S01E01.mkv")
        _make_video(tmp_path, "Show.S01E02.mkv")
        # Companion matches both (stem prefix "Show")
        _make_companion(tmp_path, "Show.nfo")
        result = run_pipeline(tmp_path)
        # Flatten all files across all groups
        all_paths = []
        for g in result:
            for f in g.files:
                all_paths.append(f.path)
        # No duplicate paths
        assert len(all_paths) == len(set(all_paths))


class TestMixedContent:
    def test_movies_and_episodes_separate(self, tmp_path: Path) -> None:
        _make_video(tmp_path, "Inception.2010.mkv")
        _make_video(tmp_path, "Breaking.Bad.S01E01.mkv")
        _make_video(tmp_path, "Breaking.Bad.S01E02.mkv")
        result = run_pipeline(tmp_path)
        # One movie group + two episode groups, all STANDALONE
        assert len(result) == 3
        movies = [g for g in result if g.metadata.media_type == "movie"]
        episodes = [g for g in result if g.metadata.media_type == "episode"]
        assert len(movies) == 1
        assert len(episodes) == 2
        for g in result:
            assert g.group_type == GroupType.STANDALONE


class TestAllFilesHaveGroupRef:
    def test_every_file_entry_has_group_backref(self, tmp_path: Path) -> None:
        _make_video(tmp_path, "Inception.2010.mkv")
        _make_companion(tmp_path, "Inception.2010.srt")
        _make_video(tmp_path, "Breaking.Bad.S01E01.mkv")
        _make_video(tmp_path, "Breaking.Bad.S01E02.mkv")
        result = run_pipeline(tmp_path)
        for group in result:
            for f in group.files:
                assert f.group is group, f"File {f.path} missing group backref"


class TestFolderNameFallback:
    def test_folder_name_used_when_parent_is_not_root(self, tmp_path: Path) -> None:
        """When video is in a subdirectory, folder name is passed to extract_metadata.

        extract_metadata uses folder_name as fallback only when filename lacks
        title or year, so we use a generic filename that yields no year.
        """
        subdir = tmp_path / "Inception (2010)"
        subdir.mkdir()
        # Filename has no year; folder provides it
        _make_video(subdir, "inception.mkv")
        result = run_pipeline(tmp_path)
        assert len(result) == 1
        # Year comes from folder name fallback
        assert result[0].metadata.year == 2010

    def test_folder_name_none_when_parent_is_root(self, tmp_path: Path) -> None:
        """When video is directly in root, folder_name should be None."""
        _make_video(tmp_path, "Inception.2010.mkv")
        result = run_pipeline(tmp_path)
        assert len(result) == 1
        # Still works correctly even without folder context
        assert result[0].metadata.title == "Inception"


class TestConfigPassthrough:
    def test_custom_companion_depth(self, tmp_path: Path) -> None:
        """Config companion_depth is respected."""
        _make_video(tmp_path, "Inception.2010.mkv")
        subdir = tmp_path / "subs"
        subdir.mkdir()
        _make_companion(subdir, "Inception.2010.srt")

        # depth=0 should NOT find the subtitle in a subdirectory
        config = TapesConfig(scan=ScanConfig(companion_depth=0))
        result = run_pipeline(tmp_path, config=config)
        companions = [f for f in result[0].files if f.role != "video"]
        assert len(companions) == 0

        # depth=1 should find it
        config = TapesConfig(scan=ScanConfig(companion_depth=1))
        result = run_pipeline(tmp_path, config=config)
        companions = [f for f in result[0].files if f.role != "video"]
        assert len(companions) == 1
