"""Tests for core data models."""

from pathlib import Path

import pytest

from tapes.models import (
    ARTWORK_EXTENSIONS,
    METADATA_EXTENSIONS,
    SUBTITLE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    FileEntry,
    FileMetadata,
    GroupStatus,
    GroupType,
    ImportGroup,
    file_role,
)


# --- file_role ---


class TestFileRole:
    @pytest.mark.parametrize("ext", [".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".m2ts", ".wmv", ".flv"])
    def test_video_extensions(self, ext):
        assert file_role(Path(f"movie{ext}")) == "video"

    @pytest.mark.parametrize("ext", [".srt", ".sub", ".idx", ".ssa", ".ass", ".vtt"])
    def test_subtitle_extensions(self, ext):
        assert file_role(Path(f"subs{ext}")) == "subtitle"

    @pytest.mark.parametrize("ext", [".nfo", ".xml"])
    def test_metadata_extensions(self, ext):
        assert file_role(Path(f"info{ext}")) == "metadata"

    @pytest.mark.parametrize("ext", [".jpg", ".png", ".webp"])
    def test_artwork_extensions(self, ext):
        assert file_role(Path(f"cover{ext}")) == "artwork"

    def test_unknown_extension(self):
        assert file_role(Path("readme.txt")) == "other"

    def test_no_extension(self):
        assert file_role(Path("LICENSE")) == "other"

    def test_case_insensitive(self):
        assert file_role(Path("movie.MKV")) == "video"
        assert file_role(Path("movie.Mp4")) == "video"
        assert file_role(Path("subs.SRT")) == "subtitle"
        assert file_role(Path("info.NFO")) == "metadata"
        assert file_role(Path("cover.JPG")) == "artwork"


# --- FileMetadata ---


class TestFileMetadata:
    def test_defaults(self):
        meta = FileMetadata()
        assert meta.media_type is None
        assert meta.title is None
        assert meta.year is None
        assert meta.season is None
        assert meta.episode is None
        assert meta.part is None
        assert meta.raw == {}

    def test_with_values(self):
        meta = FileMetadata(
            media_type="movie",
            title="Inception",
            year=2010,
            season=None,
            episode=None,
            part=None,
            raw={"source": "bluray"},
        )
        assert meta.media_type == "movie"
        assert meta.title == "Inception"
        assert meta.year == 2010
        assert meta.raw == {"source": "bluray"}

    def test_episode_metadata(self):
        meta = FileMetadata(
            media_type="episode",
            title="Breaking Bad",
            year=2008,
            season=1,
            episode=3,
        )
        assert meta.season == 1
        assert meta.episode == 3


# --- FileEntry ---


class TestFileEntry:
    def test_creation(self):
        entry = FileEntry(path=Path("/tmp/movie.mkv"))
        assert entry.path == Path("/tmp/movie.mkv")
        assert entry.role == "video"
        assert entry.group is None

    def test_role_auto_detected(self):
        assert FileEntry(path=Path("/tmp/subs.srt")).role == "subtitle"
        assert FileEntry(path=Path("/tmp/cover.jpg")).role == "artwork"
        assert FileEntry(path=Path("/tmp/info.nfo")).role == "metadata"
        assert FileEntry(path=Path("/tmp/readme.txt")).role == "other"

    def test_role_can_be_overridden(self):
        entry = FileEntry(path=Path("/tmp/movie.mkv"), role="other")
        assert entry.role == "other"


# --- GroupType and GroupStatus enums ---


class TestEnums:
    def test_group_types(self):
        assert GroupType.STANDALONE.value == "standalone"
        assert GroupType.MULTI_PART.value == "multi_part"
        assert GroupType.SEASON.value == "season"

    def test_group_statuses(self):
        assert GroupStatus.PENDING.value == "pending"
        assert GroupStatus.ACCEPTED.value == "accepted"
        assert GroupStatus.AUTO_ACCEPTED.value == "auto_accepted"
        assert GroupStatus.SKIPPED.value == "skipped"


# --- ImportGroup ---


class TestImportGroup:
    def test_creation_defaults(self):
        group = ImportGroup(metadata=FileMetadata())
        assert group.group_type == GroupType.STANDALONE
        assert group.status == GroupStatus.PENDING
        assert group.files == []

    def test_add_file(self):
        group = ImportGroup(metadata=FileMetadata())
        entry = FileEntry(path=Path("/tmp/movie.mkv"))
        group.add_file(entry)
        assert entry in group.files
        assert entry.group is group

    def test_add_file_sets_back_reference(self):
        group = ImportGroup(metadata=FileMetadata())
        entry = FileEntry(path=Path("/tmp/movie.mkv"))
        group.add_file(entry)
        assert entry.group is group

    def test_remove_file(self):
        group = ImportGroup(metadata=FileMetadata())
        entry = FileEntry(path=Path("/tmp/movie.mkv"))
        group.add_file(entry)
        group.remove_file(entry)
        assert entry not in group.files
        assert entry.group is None

    def test_add_to_new_group_removes_from_old(self):
        group1 = ImportGroup(metadata=FileMetadata())
        group2 = ImportGroup(metadata=FileMetadata())
        entry = FileEntry(path=Path("/tmp/movie.mkv"))
        group1.add_file(entry)
        assert entry.group is group1
        group2.add_file(entry)
        assert entry.group is group2
        assert entry not in group1.files
        assert entry in group2.files

    def test_no_duplicate_files(self):
        group = ImportGroup(metadata=FileMetadata())
        entry = FileEntry(path=Path("/tmp/movie.mkv"))
        group.add_file(entry)
        group.add_file(entry)
        assert len(group.files) == 1

    def test_files_returns_copy(self):
        group = ImportGroup(metadata=FileMetadata())
        entry = FileEntry(path=Path("/tmp/movie.mkv"))
        group.add_file(entry)
        files = group.files
        files.append(FileEntry(path=Path("/tmp/other.mkv")))
        assert len(group.files) == 1  # internal list unchanged

    def test_video_files(self):
        group = ImportGroup(metadata=FileMetadata())
        video = FileEntry(path=Path("/tmp/movie.mkv"))
        sub = FileEntry(path=Path("/tmp/movie.srt"))
        art = FileEntry(path=Path("/tmp/cover.jpg"))
        group.add_file(video)
        group.add_file(sub)
        group.add_file(art)
        assert group.video_files == [video]

    def test_label_movie_with_year(self):
        meta = FileMetadata(media_type="movie", title="Inception", year=2010)
        group = ImportGroup(metadata=meta)
        assert group.label == "Inception (2010)"

    def test_label_movie_without_year(self):
        meta = FileMetadata(media_type="movie", title="Inception")
        group = ImportGroup(metadata=meta)
        assert group.label == "Inception"

    def test_label_episode_with_season(self):
        meta = FileMetadata(media_type="episode", title="Breaking Bad", season=1)
        group = ImportGroup(metadata=meta)
        assert group.label == "Breaking Bad S01"

    def test_label_episode_without_season(self):
        meta = FileMetadata(media_type="episode", title="Breaking Bad")
        group = ImportGroup(metadata=meta)
        assert group.label == "Breaking Bad"

    def test_label_filename_fallback(self):
        group = ImportGroup(metadata=FileMetadata())
        entry = FileEntry(path=Path("/tmp/some.random.file.mkv"))
        group.add_file(entry)
        assert group.label == "some.random.file.mkv"

    def test_label_no_info_at_all(self):
        group = ImportGroup(metadata=FileMetadata())
        assert group.label == "Unknown"

    def test_remove_nonexistent_file_is_noop(self):
        group = ImportGroup(metadata=FileMetadata())
        entry = FileEntry(path=Path("/tmp/movie.mkv"))
        group.remove_file(entry)  # should not raise


# --- Extension constants ---


class TestConstants:
    def test_video_extensions_count(self):
        assert len(VIDEO_EXTENSIONS) == 9

    def test_subtitle_extensions_count(self):
        assert len(SUBTITLE_EXTENSIONS) == 6

    def test_metadata_extensions_count(self):
        assert len(METADATA_EXTENSIONS) == 2

    def test_artwork_extensions_count(self):
        assert len(ARTWORK_EXTENSIONS) == 3
