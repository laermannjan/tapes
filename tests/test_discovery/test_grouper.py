from tapes.discovery.grouper import group_media_files
from pathlib import Path


def test_single_movie_is_own_group(tmp_path):
    f = tmp_path / "Dune.2021.mkv"
    f.touch()
    groups = group_media_files([f])
    assert len(groups) == 1
    assert f in groups[0].video_files


def test_tv_season_grouped_together(tmp_path):
    season = tmp_path / "The Wire" / "Season 1"
    season.mkdir(parents=True)
    eps = [season / f"s01e0{i}.mkv" for i in range(1, 4)]
    for ep in eps:
        ep.touch()
    groups = group_media_files(eps)
    assert len(groups) == 1
    assert len(groups[0].video_files) == 3


def test_different_dirs_different_groups(tmp_path):
    d1, d2 = tmp_path / "Movie1", tmp_path / "Movie2"
    d1.mkdir(); d2.mkdir()
    f1 = d1 / "movie1.mkv"; f1.touch()
    f2 = d2 / "movie2.mkv"; f2.touch()
    groups = group_media_files([f1, f2])
    assert len(groups) == 2
