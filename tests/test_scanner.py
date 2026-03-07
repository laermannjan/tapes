"""Tests for tapes.scanner -- file discovery."""

from pathlib import Path

import pytest

from tapes.scanner import VIDEO_EXTENSIONS, scan


def _touch(path: Path) -> Path:
    """Create an empty file, ensuring parent dirs exist."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


class TestScanFindsAllFiles:
    """scan() discovers all files, not just video."""

    def test_finds_single_video(self, tmp_path: Path) -> None:
        f = _touch(tmp_path / "movie.mkv")
        assert scan(tmp_path) == [f]

    def test_finds_multiple_videos(self, tmp_path: Path) -> None:
        f1 = _touch(tmp_path / "a.mkv")
        f2 = _touch(tmp_path / "b.mp4")
        result = scan(tmp_path)
        assert f1 in result
        assert f2 in result

    def test_all_nine_video_extensions(self, tmp_path: Path) -> None:
        files = []
        for ext in sorted(VIDEO_EXTENSIONS):
            files.append(_touch(tmp_path / f"video{ext}"))
        result = scan(tmp_path)
        assert len(result) == 9
        for f in files:
            assert f in result

    def test_finds_non_video_files(self, tmp_path: Path) -> None:
        f_txt = _touch(tmp_path / "readme.txt")
        f_srt = _touch(tmp_path / "movie.srt")
        f_jpg = _touch(tmp_path / "cover.jpg")
        result = scan(tmp_path)
        assert f_txt in result
        assert f_srt in result
        assert f_jpg in result

    def test_finds_mixed_files(self, tmp_path: Path) -> None:
        f_txt = _touch(tmp_path / "notes.txt")
        f_mkv = _touch(tmp_path / "movie.mkv")
        f_jpg = _touch(tmp_path / "cover.jpg")
        result = scan(tmp_path)
        assert len(result) == 3
        assert f_txt in result
        assert f_mkv in result
        assert f_jpg in result


class TestScanRecursive:
    """scan() searches subdirectories recursively."""

    def test_finds_nested_video(self, tmp_path: Path) -> None:
        f = _touch(tmp_path / "sub" / "deep" / "movie.mkv")
        assert scan(tmp_path) == [f]

    def test_finds_files_at_multiple_depths(self, tmp_path: Path) -> None:
        f1 = _touch(tmp_path / "a.mp4")
        f2 = _touch(tmp_path / "dir" / "b.mkv")
        f3 = _touch(tmp_path / "dir" / "info.txt")
        result = scan(tmp_path)
        assert len(result) == 3
        assert f1 in result
        assert f2 in result
        assert f3 in result


class TestScanExcludesSamples:
    """scan() excludes sample files only when they are video files."""

    @pytest.mark.parametrize(
        "name",
        [
            "sample.mkv",
            "Sample.mkv",
            "SAMPLE.mkv",
            "sample-file.mkv",
            "sample.file.mkv",
            "sample_file.mkv",
            "movie-sample-clip.mkv",
            "movie.sample.mkv",
            "movie_sample_clip.mkv",
            "movie-sample.mkv",
        ],
    )
    def test_excludes_sample_video_files(self, tmp_path: Path, name: str) -> None:
        _touch(tmp_path / name)
        assert scan(tmp_path) == []

    def test_keeps_non_sample_with_sample_substring(self, tmp_path: Path) -> None:
        """'sampler' or 'example' should not be excluded."""
        f = _touch(tmp_path / "sampler.mkv")
        assert scan(tmp_path) == [f]

    def test_keeps_sample_non_video_file(self, tmp_path: Path) -> None:
        """Sample exclusion only applies to video files."""
        f = _touch(tmp_path / "sample.txt")
        assert scan(tmp_path) == [f]

    def test_keeps_sample_srt(self, tmp_path: Path) -> None:
        f = _touch(tmp_path / "sample.srt")
        assert scan(tmp_path) == [f]

    def test_keeps_sample_jpg(self, tmp_path: Path) -> None:
        f = _touch(tmp_path / "movie-sample.jpg")
        assert scan(tmp_path) == [f]


class TestScanExcludesHiddenDirs:
    """scan() skips files inside hidden (dot-prefixed) directories."""

    def test_excludes_hidden_dir(self, tmp_path: Path) -> None:
        _touch(tmp_path / ".hidden" / "movie.mkv")
        assert scan(tmp_path) == []

    def test_excludes_nested_hidden_dir(self, tmp_path: Path) -> None:
        _touch(tmp_path / "visible" / ".secret" / "movie.mkv")
        assert scan(tmp_path) == []

    def test_keeps_visible_alongside_hidden(self, tmp_path: Path) -> None:
        _touch(tmp_path / ".hidden" / "bad.mkv")
        f = _touch(tmp_path / "good.mkv")
        assert scan(tmp_path) == [f]


class TestScanIgnorePatterns:
    """scan() excludes files matching ignore patterns."""

    def test_ignores_thumbs_db(self, tmp_path: Path) -> None:
        _touch(tmp_path / "Thumbs.db")
        f = _touch(tmp_path / "movie.mkv")
        result = scan(tmp_path, ignore_patterns=["Thumbs.db"])
        assert result == [f]

    def test_ignores_ds_store(self, tmp_path: Path) -> None:
        _touch(tmp_path / ".DS_Store")
        f = _touch(tmp_path / "movie.mkv")
        result = scan(tmp_path, ignore_patterns=[".DS_Store"])
        assert result == [f]

    def test_ignores_glob_pattern(self, tmp_path: Path) -> None:
        _touch(tmp_path / "notes.nfo")
        _touch(tmp_path / "info.nfo")
        f = _touch(tmp_path / "movie.mkv")
        result = scan(tmp_path, ignore_patterns=["*.nfo"])
        assert result == [f]

    def test_multiple_ignore_patterns(self, tmp_path: Path) -> None:
        _touch(tmp_path / "Thumbs.db")
        _touch(tmp_path / ".DS_Store")
        _touch(tmp_path / "desktop.ini")
        f = _touch(tmp_path / "movie.mkv")
        result = scan(tmp_path, ignore_patterns=["Thumbs.db", ".DS_Store", "desktop.ini"])
        assert result == [f]

    def test_no_ignore_patterns_finds_all(self, tmp_path: Path) -> None:
        f1 = _touch(tmp_path / "Thumbs.db")
        f2 = _touch(tmp_path / "movie.mkv")
        result = scan(tmp_path, ignore_patterns=[])
        assert len(result) == 2
        assert f1 in result
        assert f2 in result

    def test_ignore_pattern_applies_to_single_file(self, tmp_path: Path) -> None:
        f = _touch(tmp_path / "Thumbs.db")
        assert scan(f, ignore_patterns=["Thumbs.db"]) == []

    def test_ignore_pattern_in_subdirectory(self, tmp_path: Path) -> None:
        _touch(tmp_path / "sub" / "Thumbs.db")
        f = _touch(tmp_path / "sub" / "movie.mkv")
        result = scan(tmp_path, ignore_patterns=["Thumbs.db"])
        assert result == [f]


class TestScanSingleFile:
    """scan() handles a single file path as root."""

    def test_single_video_file(self, tmp_path: Path) -> None:
        f = _touch(tmp_path / "movie.mkv")
        assert scan(f) == [f]

    def test_single_non_video_file(self, tmp_path: Path) -> None:
        f = _touch(tmp_path / "readme.txt")
        assert scan(f) == [f]

    def test_single_sample_video_excluded(self, tmp_path: Path) -> None:
        f = _touch(tmp_path / "sample.mkv")
        assert scan(f) == []

    def test_single_sample_non_video_included(self, tmp_path: Path) -> None:
        f = _touch(tmp_path / "sample.txt")
        assert scan(f) == [f]


class TestScanSortedOutput:
    """scan() returns paths in sorted order."""

    def test_sorted_output(self, tmp_path: Path) -> None:
        _touch(tmp_path / "c.mkv")
        _touch(tmp_path / "a.txt")
        _touch(tmp_path / "b.mkv")
        result = scan(tmp_path)
        assert result == sorted(result)


class TestScanCaseInsensitiveExtensions:
    """scan() matches video extensions regardless of case for sample check."""

    def test_uppercase_extension(self, tmp_path: Path) -> None:
        f = _touch(tmp_path / "MOVIE.MKV")
        assert scan(tmp_path) == [f]

    def test_mixed_case_extension(self, tmp_path: Path) -> None:
        f = _touch(tmp_path / "movie.Mp4")
        assert scan(tmp_path) == [f]


class TestScanEmptyDirectory:
    """scan() returns empty list for empty directories."""

    def test_empty_dir(self, tmp_path: Path) -> None:
        assert scan(tmp_path) == []


class TestVideoExtensions:
    """VIDEO_EXTENSIONS is available and contains expected values."""

    def test_video_extensions_exists(self) -> None:
        assert isinstance(VIDEO_EXTENSIONS, frozenset)
        assert ".mkv" in VIDEO_EXTENSIONS
        assert ".mp4" in VIDEO_EXTENSIONS
        assert len(VIDEO_EXTENSIONS) == 9
