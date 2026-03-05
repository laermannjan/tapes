from tapes.companions.classifier import (
    Category,
    CompanionFile,
    classify_companions,
    rename_companion,
)


def test_subtitle_detected(tmp_path):
    (tmp_path / "movie.mkv").touch()
    (tmp_path / "movie.en.srt").touch()
    companions = classify_companions(tmp_path / "movie.mkv")
    subs = [c for c in companions if c.category == Category.SUBTITLE]
    assert len(subs) == 1
    assert subs[0].path.name == "movie.en.srt"


def test_nfo_detected(tmp_path):
    (tmp_path / "movie.mkv").touch()
    (tmp_path / "movie.nfo").touch()
    companions = classify_companions(tmp_path / "movie.mkv")
    nfos = [c for c in companions if c.category == Category.NFO]
    assert len(nfos) == 1
    assert nfos[0].path.name == "movie.nfo"


def test_artwork_detected(tmp_path):
    (tmp_path / "movie.mkv").touch()
    (tmp_path / "poster.jpg").touch()
    (tmp_path / "fanart.jpg").touch()
    companions = classify_companions(tmp_path / "movie.mkv")
    arts = [c for c in companions if c.category == Category.ARTWORK]
    assert len(arts) == 2
    names = {c.path.name for c in arts}
    assert names == {"poster.jpg", "fanart.jpg"}


def test_sample_detected_not_moved_by_default(tmp_path):
    (tmp_path / "movie.mkv").touch()
    (tmp_path / "sample.avi").touch()
    companions = classify_companions(tmp_path / "movie.mkv")
    # sample.avi has a video extension so it is excluded as a video file
    # Use a non-video extension for the sample test
    assert all(c.category != Category.SAMPLE for c in companions)


def test_sample_non_video_detected(tmp_path):
    (tmp_path / "movie.mkv").touch()
    (tmp_path / "sample.txt").touch()
    companions = classify_companions(tmp_path / "movie.mkv")
    samples = [c for c in companions if c.category == Category.SAMPLE]
    assert len(samples) == 1
    assert samples[0].move_by_default is False


def test_unknown_files_not_moved_by_default(tmp_path):
    (tmp_path / "movie.mkv").touch()
    (tmp_path / "readme.txt").touch()
    companions = classify_companions(tmp_path / "movie.mkv")
    unknowns = [c for c in companions if c.category == Category.UNKNOWN]
    assert len(unknowns) == 1
    assert unknowns[0].move_by_default is False


def test_ignore_not_returned(tmp_path):
    (tmp_path / "movie.mkv").touch()
    (tmp_path / "movie.url").touch()
    companions = classify_companions(tmp_path / "movie.mkv")
    assert all(c.category != Category.IGNORE for c in companions)


def test_video_files_excluded(tmp_path):
    (tmp_path / "movie.mkv").touch()
    (tmp_path / "extras.mp4").touch()
    companions = classify_companions(tmp_path / "movie.mkv")
    assert not any(c.path.name == "extras.mp4" for c in companions)


def test_subdirectory_preserved(tmp_path):
    (tmp_path / "movie.mkv").touch()
    subs_dir = tmp_path / "Subs"
    subs_dir.mkdir()
    (subs_dir / "movie.nl.srt").touch()
    companions = classify_companions(tmp_path / "movie.mkv")
    assert any(c.path == subs_dir / "movie.nl.srt" for c in companions)


def test_subtitle_rename():
    new_name = rename_companion("movie.en.srt", "Dune (2021)", Category.SUBTITLE)
    assert new_name == "Dune (2021).en.srt"


def test_nfo_rename():
    new_name = rename_companion("movie.nfo", "Dune (2021)", Category.NFO)
    assert new_name == "Dune (2021).nfo"


def test_artwork_rename_keeps_original():
    new_name = rename_companion("poster.jpg", "Dune (2021)", Category.ARTWORK)
    assert new_name == "poster.jpg"


def test_case_insensitive_subtitle(tmp_path):
    """Uppercase .SRT should still be classified as subtitle."""
    (tmp_path / "movie.mkv").touch()
    (tmp_path / "movie.en.SRT").touch()
    companions = classify_companions(tmp_path / "movie.mkv")
    subs = [c for c in companions if c.category == Category.SUBTITLE]
    assert len(subs) == 1


def test_case_insensitive_artwork(tmp_path):
    """Poster.JPG should still be classified as artwork."""
    (tmp_path / "movie.mkv").touch()
    (tmp_path / "Poster.JPG").touch()
    companions = classify_companions(tmp_path / "movie.mkv")
    arts = [c for c in companions if c.category == Category.ARTWORK]
    assert len(arts) == 1
