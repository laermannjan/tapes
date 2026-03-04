from tapes.discovery.scanner import scan_media_files


def test_finds_video_files(tmp_path):
    (tmp_path / "movie.mkv").touch()
    (tmp_path / "readme.txt").touch()
    found = scan_media_files(tmp_path)
    assert any(f.name == "movie.mkv" for f in found)
    assert not any(f.name == "readme.txt" for f in found)


def test_recursive(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "ep.mkv").touch()
    found = scan_media_files(tmp_path)
    assert any(f.name == "ep.mkv" for f in found)


def test_multiple_extensions(tmp_path):
    for name in ["a.mkv", "b.mp4", "c.avi", "d.m4v"]:
        (tmp_path / name).touch()
    found = scan_media_files(tmp_path)
    assert len(found) == 4


def test_excludes_sample_files(tmp_path):
    (tmp_path / "movie.mkv").touch()
    (tmp_path / "sample.mkv").touch()
    found = scan_media_files(tmp_path)
    names = [f.name for f in found]
    assert "movie.mkv" in names
    assert "sample.mkv" not in names
