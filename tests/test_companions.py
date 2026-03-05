"""Tests for companion file discovery."""

from pathlib import Path

import pytest

from tapes.companions import COMPANION_EXTENSIONS, COMPANION_SEPARATORS, find_companions


class TestFindCompanions:
    """Tests for find_companions()."""

    def test_subtitle_same_dir(self, tmp_path: Path) -> None:
        video = tmp_path / "Movie.2020.mkv"
        sub = tmp_path / "Movie.2020.srt"
        video.touch()
        sub.touch()

        result = find_companions(video)
        assert len(result) == 1
        assert result[0].path == sub
        assert result[0].role == "subtitle"

    def test_separator_dot(self, tmp_path: Path) -> None:
        video = tmp_path / "Movie.mkv"
        sub = tmp_path / "Movie.en.srt"
        video.touch()
        sub.touch()

        result = find_companions(video)
        assert len(result) == 1
        assert result[0].path == sub

    def test_separator_underscore(self, tmp_path: Path) -> None:
        video = tmp_path / "Movie.mkv"
        companion = tmp_path / "Movie_poster.jpg"
        video.touch()
        companion.touch()

        result = find_companions(video)
        assert len(result) == 1
        assert result[0].path == companion

    def test_separator_dash(self, tmp_path: Path) -> None:
        video = tmp_path / "Movie.mkv"
        companion = tmp_path / "Movie-thumb.jpg"
        video.touch()
        companion.touch()

        result = find_companions(video)
        assert len(result) == 1
        assert result[0].path == companion

    def test_no_separator_no_match(self, tmp_path: Path) -> None:
        """A file whose stem starts with video stem but without a separator should not match."""
        video = tmp_path / "Movie.mkv"
        not_companion = tmp_path / "MovieExtra.srt"
        video.touch()
        not_companion.touch()

        result = find_companions(video)
        assert len(result) == 0

    def test_exact_stem_match(self, tmp_path: Path) -> None:
        """A file with the exact same stem (different extension) is a companion."""
        video = tmp_path / "Movie.mkv"
        nfo = tmp_path / "Movie.nfo"
        video.touch()
        nfo.touch()

        result = find_companions(video)
        assert len(result) == 1
        assert result[0].path == nfo
        assert result[0].role == "metadata"

    def test_child_directory(self, tmp_path: Path) -> None:
        """Companions in a child directory are found with max_depth >= 1."""
        video = tmp_path / "Movie.mkv"
        subs_dir = tmp_path / "Subs"
        subs_dir.mkdir()
        sub = subs_dir / "Movie.en.srt"
        video.touch()
        sub.touch()

        result = find_companions(video, max_depth=1)
        assert len(result) == 1
        assert result[0].path == sub

    def test_depth_limit(self, tmp_path: Path) -> None:
        """Companions deeper than max_depth are not found."""
        video = tmp_path / "Movie.mkv"
        deep_dir = tmp_path / "a" / "b"
        deep_dir.mkdir(parents=True)
        sub = deep_dir / "Movie.srt"
        video.touch()
        sub.touch()

        # depth 0: same dir only
        assert find_companions(video, max_depth=0) == []
        # depth 1: one level deep
        assert find_companions(video, max_depth=1) == []
        # depth 2: found
        result = find_companions(video, max_depth=2)
        assert len(result) == 1
        assert result[0].path == sub

    def test_ignores_video_files(self, tmp_path: Path) -> None:
        """Video files are never companions even if stem matches."""
        video = tmp_path / "Movie.mkv"
        other_video = tmp_path / "Movie.avi"
        video.touch()
        other_video.touch()

        result = find_companions(video)
        assert len(result) == 0

    def test_artwork(self, tmp_path: Path) -> None:
        video = tmp_path / "Movie.mkv"
        art = tmp_path / "Movie.jpg"
        video.touch()
        art.touch()

        result = find_companions(video)
        assert len(result) == 1
        assert result[0].role == "artwork"

    def test_nfo(self, tmp_path: Path) -> None:
        video = tmp_path / "Movie.mkv"
        nfo = tmp_path / "Movie.nfo"
        video.touch()
        nfo.touch()

        result = find_companions(video)
        assert len(result) == 1
        assert result[0].role == "metadata"

    def test_non_whitelisted_extension_ignored(self, tmp_path: Path) -> None:
        video = tmp_path / "Movie.mkv"
        other = tmp_path / "Movie.exe"
        video.touch()
        other.touch()

        result = find_companions(video)
        assert len(result) == 0

    def test_case_insensitive_stem(self, tmp_path: Path) -> None:
        """Stem matching is case-insensitive."""
        video = tmp_path / "Movie.mkv"
        sub = tmp_path / "movie.srt"
        video.touch()
        sub.touch()

        result = find_companions(video)
        assert len(result) == 1
        assert result[0].path == sub

    def test_txt_extension(self, tmp_path: Path) -> None:
        """txt files are valid companions."""
        video = tmp_path / "Movie.mkv"
        txt = tmp_path / "Movie.txt"
        video.touch()
        txt.touch()

        result = find_companions(video)
        assert len(result) == 1
        assert result[0].role == "other"

    def test_multiple_companions(self, tmp_path: Path) -> None:
        video = tmp_path / "Movie.mkv"
        sub = tmp_path / "Movie.srt"
        nfo = tmp_path / "Movie.nfo"
        art = tmp_path / "Movie.jpg"
        video.touch()
        sub.touch()
        nfo.touch()
        art.touch()

        result = find_companions(video)
        assert len(result) == 3
        paths = {r.path for r in result}
        assert paths == {sub, nfo, art}

    def test_permission_error_skipped(self, tmp_path: Path) -> None:
        """PermissionError during directory walk is silently skipped."""
        video = tmp_path / "Movie.mkv"
        video.touch()
        restricted = tmp_path / "restricted"
        restricted.mkdir()
        restricted.chmod(0o000)

        try:
            # Should not raise
            result = find_companions(video, max_depth=1)
            assert isinstance(result, list)
        finally:
            restricted.chmod(0o755)

    def test_video_itself_excluded(self, tmp_path: Path) -> None:
        """The video file itself is never returned as a companion."""
        video = tmp_path / "Movie.mkv"
        video.touch()

        result = find_companions(video)
        assert len(result) == 0


class TestConstants:
    def test_companion_extensions_include_subtitles(self) -> None:
        assert ".srt" in COMPANION_EXTENSIONS
        assert ".sub" in COMPANION_EXTENSIONS

    def test_companion_extensions_include_metadata(self) -> None:
        assert ".nfo" in COMPANION_EXTENSIONS

    def test_companion_extensions_include_artwork(self) -> None:
        assert ".jpg" in COMPANION_EXTENSIONS

    def test_companion_extensions_include_txt(self) -> None:
        assert ".txt" in COMPANION_EXTENSIONS

    def test_companion_separators(self) -> None:
        assert COMPANION_SEPARATORS == (".", "_", "-")
