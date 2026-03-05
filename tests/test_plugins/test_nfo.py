"""Tests for the NFO sidecar plugin."""

from pathlib import Path

from tapes.events.bus import EventBus
from tapes.plugins.builtin.nfo import NfoPlugin


def test_generates_movie_nfo(tmp_path):
    bus = EventBus()
    plugin = NfoPlugin()
    plugin.setup({"enabled": True}, bus)

    video = tmp_path / "Dune (2021)" / "Dune (2021).mkv"
    video.parent.mkdir(parents=True)
    video.touch()

    bus.emit(
        "after_write",
        path=str(video),
        media_type="movie",
        title="Dune",
        year=2021,
        tmdb_id=438631,
    )

    nfo = video.with_suffix(".nfo")
    assert nfo.exists()
    content = nfo.read_text()
    assert "<movie>" in content
    assert "<title>Dune</title>" in content
    assert "<year>2021</year>" in content
    assert "<tmdbid>438631</tmdbid>" in content
    assert "</movie>" in content


def test_generates_tv_nfo(tmp_path):
    bus = EventBus()
    plugin = NfoPlugin()
    plugin.setup({"enabled": True}, bus)

    video = tmp_path / "Breaking Bad" / "Season 01" / "Breaking Bad S01E01.mkv"
    video.parent.mkdir(parents=True)
    video.touch()

    bus.emit(
        "after_write",
        path=str(video),
        media_type="tv",
        title="Pilot",
        year=2008,
        tmdb_id=1399,
        show="Breaking Bad",
        season=1,
        episode=1,
    )

    nfo = video.with_suffix(".nfo")
    assert nfo.exists()
    content = nfo.read_text()
    assert "<episodedetails>" in content
    assert "<title>Pilot</title>" in content
    assert "<showtitle>Breaking Bad</showtitle>" in content
    assert "<season>1</season>" in content
    assert "<episode>1</episode>" in content
    assert "<tmdbid>1399</tmdbid>" in content


def test_no_nfo_when_disabled(tmp_path):
    """Plugin that is set up but not enabled should not write NFO."""
    bus = EventBus()
    plugin = NfoPlugin()
    plugin.setup({"enabled": False}, bus)

    video = tmp_path / "movie.mkv"
    video.touch()

    bus.emit(
        "after_write",
        path=str(video),
        media_type="movie",
        title="Test",
        year=2020,
        tmdb_id=1,
    )

    assert not video.with_suffix(".nfo").exists()


def test_nfo_not_written_when_no_listener(tmp_path):
    """If plugin is not set up, no NFO is written."""
    bus = EventBus()

    video = tmp_path / "movie.mkv"
    video.touch()

    bus.emit(
        "after_write",
        path=str(video),
        media_type="movie",
        title="Test",
        year=2020,
        tmdb_id=1,
    )

    assert not video.with_suffix(".nfo").exists()


def test_nfo_escapes_xml_special_chars(tmp_path):
    """Titles with & or < are properly escaped in NFO XML."""
    bus = EventBus()
    plugin = NfoPlugin()
    plugin.setup({"enabled": True}, bus)

    video = tmp_path / "movie.mkv"
    video.touch()

    bus.emit(
        "after_write",
        path=str(video),
        media_type="movie",
        title="Tom & Jerry <3",
        year=2021,
        tmdb_id=1,
    )

    content = video.with_suffix(".nfo").read_text()
    assert "Tom &amp; Jerry &lt;3" in content
    assert "Tom & Jerry <3" not in content


def test_nfo_overwrites_existing(tmp_path):
    """Re-emitting after_write overwrites existing NFO."""
    bus = EventBus()
    plugin = NfoPlugin()
    plugin.setup({"enabled": True}, bus)

    video = tmp_path / "movie.mkv"
    video.touch()

    bus.emit(
        "after_write",
        path=str(video),
        media_type="movie",
        title="Old",
        year=2019,
        tmdb_id=1,
    )
    bus.emit(
        "after_write",
        path=str(video),
        media_type="movie",
        title="New",
        year=2020,
        tmdb_id=2,
    )

    content = video.with_suffix(".nfo").read_text()
    assert "<title>New</title>" in content
    assert "Old" not in content
