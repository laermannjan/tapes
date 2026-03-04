from tapes.identification.filename import parse_filename


def test_movie():
    r = parse_filename("Dune.2021.2160p.BluRay.x265.mkv")
    assert r["title"] == "Dune"
    assert r["year"] == 2021
    assert r["screen_size"] == "2160p"   # guessit field name; pipeline normalises later


def test_tv_episode():
    r = parse_filename("The.Wire.S01E03.720p.mkv")
    assert r["show"] == "The Wire"
    assert r["season"] == 1
    assert r["episode"] == 3


def test_multi_episode_returns_list():
    r = parse_filename("The.Wire.S01E01E02.mkv")
    assert isinstance(r["episode"], list)
    assert r["episode"] == [1, 2]


def test_edition():
    r = parse_filename("Blade.Runner.1982.Directors.Cut.mkv")
    assert r.get("edition") is not None


def test_folder_name_as_hint(tmp_path):
    r = parse_filename("s01e01.mkv", folder_name="The Wire (2002)")
    assert r["show"] == "The Wire"
    assert r["year"] == 2002
