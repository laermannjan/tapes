import responses as resp_lib
from tapes.metadata.tmdb import TMDBSource

BASE = "https://api.themoviedb.org/3"

MOVIE_SEARCH = {
    "results": [
        {"id": 438631, "title": "Dune", "release_date": "2021-09-15", "genre_ids": [878]}
    ]
}
MOVIE_DETAIL = {
    "id": 438631,
    "title": "Dune",
    "release_date": "2021-09-15",
    "genres": [{"name": "Science Fiction"}],
    "credits": {"crew": [{"job": "Director", "name": "Denis Villeneuve"}]},
}
TV_SEARCH = {
    "results": [
        {"id": 1438, "name": "The Wire", "first_air_date": "2002-06-02", "genre_ids": [18]}
    ]
}
TV_DETAIL = {
    "id": 1438,
    "name": "The Wire",
    "first_air_date": "2002-06-02",
    "genres": [{"name": "Drama"}],
    "created_by": [{"name": "David Simon"}],
    "seasons": [{"season_number": 1, "episode_count": 13}],
}


@resp_lib.activate
def test_search_movie():
    resp_lib.add(resp_lib.GET, f"{BASE}/search/movie", json=MOVIE_SEARCH)
    resp_lib.add(resp_lib.GET, f"{BASE}/movie/438631", json=MOVIE_DETAIL)
    source = TMDBSource(api_key="testkey")
    results = source.search("Dune", 2021, "movie")
    assert len(results) >= 1
    assert results[0].tmdb_id == 438631
    assert results[0].title == "Dune"
    assert results[0].director == "Denis Villeneuve"
    assert results[0].genre == "Science Fiction"


@resp_lib.activate
def test_search_movie_exact_year_confidence():
    resp_lib.add(resp_lib.GET, f"{BASE}/search/movie", json=MOVIE_SEARCH)
    resp_lib.add(resp_lib.GET, f"{BASE}/movie/438631", json=MOVIE_DETAIL)
    source = TMDBSource(api_key="testkey")
    results = source.search("Dune", 2021, "movie")
    assert results[0].confidence >= 0.90


@resp_lib.activate
def test_search_tv():
    resp_lib.add(resp_lib.GET, f"{BASE}/search/tv", json=TV_SEARCH)
    resp_lib.add(resp_lib.GET, f"{BASE}/tv/1438", json=TV_DETAIL)
    source = TMDBSource(api_key="testkey")
    results = source.search("The Wire", 2002, "tv")
    assert results[0].tmdb_id == 1438
    assert results[0].show == "The Wire"


@resp_lib.activate
def test_get_by_id_movie():
    resp_lib.add(resp_lib.GET, f"{BASE}/movie/438631", json=MOVIE_DETAIL)
    source = TMDBSource(api_key="testkey")
    result = source.get_by_id(438631, "movie")
    assert result is not None
    assert result.title == "Dune"


@resp_lib.activate
def test_is_available_true():
    resp_lib.add(resp_lib.GET, f"{BASE}/configuration", json={"images": {}})
    source = TMDBSource(api_key="testkey")
    assert source.is_available() is True


@resp_lib.activate
def test_is_available_false_on_401():
    resp_lib.add(resp_lib.GET, f"{BASE}/configuration", status=401)
    source = TMDBSource(api_key="bad_key")
    assert source.is_available() is False


@resp_lib.activate
def test_search_no_results():
    resp_lib.add(resp_lib.GET, f"{BASE}/search/movie", json={"results": []})
    source = TMDBSource(api_key="testkey")
    results = source.search("xyzzy unknown film", None, "movie")
    assert results == []
