"""Tests for tapes.scanner -- video file discovery."""

from pathlib import Path

import pytest

from tapes.scanner import VIDEO_EXTENSIONS, scan


def _touch(path: Path) -> Path:
    """Create an empty file, ensuring parent dirs exist."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


class TestScanFindsVideoFiles:
    """scan() discovers files with video extensions."""

    def test_finds_single_video(self, tmp_path: Path) -> None:
        f = _touch(tmp_path / "movie.mkv")
        assert scan(tmp_path) == [f]

    def test_finds_multiple_videos(self, tmp_path: Path) -> None:
        f1 = _touch(tmp_path / "a.mkv")
        f2 = _touch(tmp_path / "b.mp4")
        result = scan(tmp_path)
        assert f1 in result
        assert f2 in result
        assert len(result) == 2

    def test_all_nine_video_extensions(self, tmp_path: Path) -> None:
        files = []
        for ext in sorted(VIDEO_EXTENSIONS):
            files.append(_touch(tmp_path / f"video{ext}"))
        result = scan(tmp_path)
        assert len(result) == 9
        for f in files:
            assert f in result


class TestScanIgnoresNonVideo:
    """scan() skips files that are not video."""

    def test_ignores_text_file(self, tmp_path: Path) -> None:
        _touch(tmp_path / "readme.txt")
        assert scan(tmp_path) == []

    def test_ignores_subtitle(self, tmp_path: Path) -> None:
        _touch(tmp_path / "movie.srt")
        assert scan(tmp_path) == []

    def test_mixed_files(self, tmp_path: Path) -> None:
        _touch(tmp_path / "notes.txt")
        f = _touch(tmp_path / "movie.mkv")
        _touch(tmp_path / "cover.jpg")
        assert scan(tmp_path) == [f]


class TestScanRecursive:
    """scan() searches subdirectories recursively."""

    def test_finds_nested_video(self, tmp_path: Path) -> None:
        f = _touch(tmp_path / "sub" / "deep" / "movie.mkv")
        assert scan(tmp_path) == [f]

    def test_finds_videos_at_multiple_depths(self, tmp_path: Path) -> None:
        f1 = _touch(tmp_path / "a.mp4")
        f2 = _touch(tmp_path / "dir" / "b.mkv")
        result = scan(tmp_path)
        assert len(result) == 2
        assert f1 in result
        assert f2 in result


class TestScanExcludesSamples:
    """scan() excludes files matching the sample pattern."""

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
    def test_excludes_sample_files(self, tmp_path: Path, name: str) -> None:
        _touch(tmp_path / name)
        assert scan(tmp_path) == []

    def test_keeps_non_sample_with_sample_substring(self, tmp_path: Path) -> None:
        """'sampler' or 'example' should not be excluded."""
        f = _touch(tmp_path / "sampler.mkv")
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


class TestScanSingleFile:
    """scan() handles a single file path as root."""

    def test_single_video_file(self, tmp_path: Path) -> None:
        f = _touch(tmp_path / "movie.mkv")
        assert scan(f) == [f]

    def test_single_non_video_file(self, tmp_path: Path) -> None:
        f = _touch(tmp_path / "readme.txt")
        assert scan(f) == []


class TestScanSortedOutput:
    """scan() returns paths in sorted order."""

    def test_sorted_output(self, tmp_path: Path) -> None:
        _touch(tmp_path / "c.mkv")
        _touch(tmp_path / "a.mkv")
        _touch(tmp_path / "b.mkv")
        result = scan(tmp_path)
        assert result == sorted(result)


class TestScanCaseInsensitiveExtensions:
    """scan() matches extensions regardless of case."""

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

    def test_dir_with_only_non_video(self, tmp_path: Path) -> None:
        _touch(tmp_path / "file.txt")
        assert scan(tmp_path) == []
