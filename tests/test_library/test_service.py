import sqlite3
import pytest
from tapes.db.schema import init_db
from tapes.db.repository import Repository
from tapes.library.service import LibraryService


@pytest.fixture
def svc(tmp_path):
    conn = sqlite3.connect(tmp_path / "lib.db")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    _seed(conn)
    return LibraryService(Repository(conn))


def _seed(conn):
    rows = [
        ("/movies/mulholland.mkv", "movie", "Mulholland Drive", 2001, "David Lynch", "Thriller", None, None, None, None, "hevc", "1080p"),
        ("/movies/dune2021.mkv", "movie", "Dune", 2021, "Denis Villeneuve", "Science Fiction", None, None, None, None, "hevc", "2160p"),
        ("/movies/dune1984.mkv", "movie", "Dune", 1984, "David Lynch", "Science Fiction", None, None, None, None, "h264", "720p"),
        ("/tv/wire/s01e01.mkv", "tv", "The Pilot", 2002, None, "Drama", "The Wire", 1, 1, "The Target", "h264", "1080p"),
        ("/tv/wire/s01e02.mkv", "tv", "The Detail", 2002, None, "Drama", "The Wire", 1, 2, "The Detail", "h264", "1080p"),
        ("/movies/matrix.mkv", "movie", "The Matrix", 1999, "Lana Wachowski", "Action", None, None, None, None, "hevc", "2160p"),
    ]
    for path, mt, title, year, director, genre, show, season, ep, ep_title, codec, res in rows:
        conn.execute(
            """INSERT INTO items (path, media_type, title, year, director, genre,
               show, season, episode, episode_title, codec, resolution, mtime, size, imported_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, datetime('now'))""",
            (path, mt, title, year, director, genre, show, season, ep, ep_title, codec, res),
        )
    conn.commit()


# --- Exact field match ---

class TestFieldMatch:
    def test_by_director(self, svc):
        results = svc.query('director:"David Lynch"')
        assert len(results) == 2
        titles = {r.title for r in results}
        assert titles == {"Mulholland Drive", "Dune"}

    def test_by_title(self, svc):
        results = svc.query("title:Dune")
        assert len(results) == 2

    def test_by_genre(self, svc):
        results = svc.query('genre:"Science Fiction"')
        assert len(results) == 2

    def test_by_media_type(self, svc):
        results = svc.query("media_type:tv")
        assert len(results) == 2

    def test_by_show(self, svc):
        results = svc.query('show:"The Wire"')
        assert len(results) == 2

    def test_by_resolution(self, svc):
        results = svc.query("resolution:2160p")
        assert len(results) == 2

    def test_by_codec(self, svc):
        results = svc.query("codec:hevc")
        assert len(results) == 3


# --- Year range queries ---

class TestYearRange:
    def test_year_greater_than(self, svc):
        results = svc.query("year:>2000")
        assert all(r.year > 2000 for r in results)
        assert len(results) == 4

    def test_year_less_than(self, svc):
        results = svc.query("year:<2000")
        assert all(r.year < 2000 for r in results)
        assert len(results) == 2

    def test_year_greater_equal(self, svc):
        results = svc.query("year:>=2001")
        assert all(r.year >= 2001 for r in results)

    def test_year_less_equal(self, svc):
        results = svc.query("year:<=1999")
        assert all(r.year <= 1999 for r in results)

    def test_year_exact(self, svc):
        results = svc.query("year:2002")
        assert len(results) == 2


# --- Combined queries ---

class TestCombined:
    def test_director_and_genre(self, svc):
        results = svc.query('director:"David Lynch" genre:"Science Fiction"')
        assert len(results) == 1
        assert results[0].title == "Dune"
        assert results[0].year == 1984

    def test_year_range_and_media_type(self, svc):
        results = svc.query("year:>2000 media_type:movie")
        assert all(r.year > 2000 and r.media_type == "movie" for r in results)

    def test_show_and_season(self, svc):
        results = svc.query('show:"The Wire" season:1')
        assert len(results) == 2


# --- Free text search ---

class TestFreeText:
    def test_bare_word_matches_title(self, svc):
        results = svc.query("Matrix")
        assert len(results) == 1
        assert results[0].title == "The Matrix"

    def test_bare_word_case_insensitive(self, svc):
        results = svc.query("matrix")
        assert len(results) == 1

    def test_bare_word_partial(self, svc):
        results = svc.query("Dune")
        assert len(results) == 2


# --- Edge cases ---

class TestEdgeCases:
    def test_empty_query_returns_all(self, svc):
        results = svc.query("")
        assert len(results) == 6

    def test_no_results(self, svc):
        results = svc.query("title:Nonexistent")
        assert results == []

    def test_invalid_field_ignored(self, svc):
        results = svc.query("fakefield:value")
        assert results == []
