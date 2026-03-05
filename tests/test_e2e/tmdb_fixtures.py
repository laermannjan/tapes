"""Canned TMDB API responses and mock registration helpers for E2E tests."""

import responses as resp_lib

BASE_URL = "https://api.themoviedb.org/3"

# ---------------------------------------------------------------------------
# Movie fixtures
# ---------------------------------------------------------------------------

DUNE_2021 = {
    "search": {
        "results": [
            {
                "id": 438631,
                "title": "Dune",
                "release_date": "2021-09-15",
                "genre_ids": [878],
            }
        ]
    },
    "detail": {
        "id": 438631,
        "title": "Dune",
        "release_date": "2021-09-15",
        "genres": [{"name": "Science Fiction"}],
        "credits": {
            "crew": [{"job": "Director", "name": "Denis Villeneuve"}]
        },
    },
}

THE_MATRIX_1999 = {
    "search": {
        "results": [
            {
                "id": 603,
                "title": "The Matrix",
                "release_date": "1999-03-30",
                "genre_ids": [28, 878],
            }
        ]
    },
    "detail": {
        "id": 603,
        "title": "The Matrix",
        "release_date": "1999-03-30",
        "genres": [{"name": "Action"}, {"name": "Science Fiction"}],
        "credits": {
            "crew": [{"job": "Director", "name": "Lana Wachowski"}]
        },
    },
}

INCEPTION_2010 = {
    "search": {
        "results": [
            {
                "id": 27205,
                "title": "Inception",
                "release_date": "2010-07-15",
                "genre_ids": [28, 878, 12],
            }
        ]
    },
    "detail": {
        "id": 27205,
        "title": "Inception",
        "release_date": "2010-07-15",
        "genres": [
            {"name": "Action"},
            {"name": "Science Fiction"},
            {"name": "Adventure"},
        ],
        "credits": {
            "crew": [{"job": "Director", "name": "Christopher Nolan"}]
        },
    },
}

THE_GODFATHER_1972 = {
    "search": {
        "results": [
            {
                "id": 238,
                "title": "The Godfather",
                "release_date": "1972-03-14",
                "genre_ids": [18, 80],
            }
        ]
    },
    "detail": {
        "id": 238,
        "title": "The Godfather",
        "release_date": "1972-03-14",
        "genres": [{"name": "Drama"}, {"name": "Crime"}],
        "credits": {
            "crew": [
                {"job": "Director", "name": "Francis Ford Coppola"}
            ]
        },
    },
}

BLADE_RUNNER_1982 = {
    "search": {
        "results": [
            {
                "id": 78,
                "title": "Blade Runner",
                "release_date": "1982-06-25",
                "genre_ids": [878, 18, 53],
            }
        ]
    },
    "detail": {
        "id": 78,
        "title": "Blade Runner",
        "release_date": "1982-06-25",
        "genres": [
            {"name": "Science Fiction"},
            {"name": "Drama"},
            {"name": "Thriller"},
        ],
        "credits": {
            "crew": [{"job": "Director", "name": "Ridley Scott"}]
        },
    },
}

AMELIE_2001 = {
    "search": {
        "results": [
            {
                "id": 194,
                "title": "Amelie",
                "release_date": "2001-04-25",
                "genre_ids": [35, 10749],
            }
        ]
    },
    "detail": {
        "id": 194,
        "title": "Amelie",
        "release_date": "2001-04-25",
        "genres": [{"name": "Comedy"}, {"name": "Romance"}],
        "credits": {
            "crew": [{"job": "Director", "name": "Jean-Pierre Jeunet"}]
        },
    },
}

MOVIE_WITH_SPECIAL_CHARS = {
    "search": {
        "results": [
            {
                "id": 99999,
                "title": 'Movie: The "Sequel"',
                "release_date": "2021-01-01",
                "genre_ids": [18],
            }
        ]
    },
    "detail": {
        "id": 99999,
        "title": 'Movie: The "Sequel"',
        "release_date": "2021-01-01",
        "genres": [{"name": "Drama"}],
        "credits": {"crew": []},
    },
}

# ---------------------------------------------------------------------------
# TV fixtures
# ---------------------------------------------------------------------------

BREAKING_BAD = {
    "search": {
        "results": [
            {
                "id": 1396,
                "name": "Breaking Bad",
                "first_air_date": "2008-01-20",
                "genre_ids": [18],
            }
        ]
    },
    "detail": {
        "id": 1396,
        "name": "Breaking Bad",
        "first_air_date": "2008-01-20",
        "genres": [{"name": "Drama"}],
        "created_by": [{"name": "Vince Gilligan"}],
        "credits": {"crew": []},
        "seasons": [
            {"season_number": 1, "episode_count": 7},
            {"season_number": 2, "episode_count": 13},
            {"season_number": 3, "episode_count": 13},
            {"season_number": 4, "episode_count": 13},
            {"season_number": 5, "episode_count": 16},
        ],
    },
}

THE_WIRE = {
    "search": {
        "results": [
            {
                "id": 1438,
                "name": "The Wire",
                "first_air_date": "2002-06-02",
                "genre_ids": [18],
            }
        ]
    },
    "detail": {
        "id": 1438,
        "name": "The Wire",
        "first_air_date": "2002-06-02",
        "genres": [{"name": "Drama"}],
        "created_by": [{"name": "David Simon"}],
        "credits": {"crew": []},
        "seasons": [
            {"season_number": 1, "episode_count": 13},
            {"season_number": 2, "episode_count": 12},
            {"season_number": 3, "episode_count": 12},
            {"season_number": 4, "episode_count": 13},
            {"season_number": 5, "episode_count": 10},
        ],
    },
}

THE_DAILY_SHOW = {
    "search": {
        "results": [
            {
                "id": 2224,
                "name": "The Daily Show",
                "first_air_date": "1996-07-22",
                "genre_ids": [35, 10763],
            }
        ]
    },
    "detail": {
        "id": 2224,
        "name": "The Daily Show",
        "first_air_date": "1996-07-22",
        "genres": [{"name": "Comedy"}, {"name": "News"}],
        "created_by": [],
        "credits": {"crew": []},
        "seasons": [
            {"season_number": 1, "episode_count": 160},
        ],
    },
}

THE_OFFICE_AMBIGUOUS = {
    "search": {
        "results": [
            {
                "id": 2316,
                "name": "The Office",
                "first_air_date": "2005-03-24",
                "genre_ids": [35],
            },
            {
                "id": 2996,
                "name": "The Office",
                "first_air_date": "2001-07-09",
                "genre_ids": [35],
            },
        ]
    },
    "details": {
        2316: {
            "id": 2316,
            "name": "The Office",
            "first_air_date": "2005-03-24",
            "genres": [{"name": "Comedy"}],
            "created_by": [{"name": "Greg Daniels"}],
            "credits": {"crew": []},
            "seasons": [
                {"season_number": 1, "episode_count": 6},
                {"season_number": 2, "episode_count": 22},
            ],
        },
        2996: {
            "id": 2996,
            "name": "The Office",
            "first_air_date": "2001-07-09",
            "genres": [{"name": "Comedy"}],
            "created_by": [{"name": "Ricky Gervais"}],
            "credits": {"crew": []},
            "seasons": [
                {"season_number": 1, "episode_count": 6},
                {"season_number": 2, "episode_count": 6},
            ],
        },
    },
}

GENERIC_SHOW = {
    "search": {
        "results": [
            {
                "id": 50000,
                "name": "Show Name",
                "first_air_date": "2020-01-01",
                "genre_ids": [18],
            }
        ]
    },
    "detail": {
        "id": 50000,
        "name": "Show Name",
        "first_air_date": "2020-01-01",
        "genres": [{"name": "Drama"}],
        "created_by": [],
        "credits": {"crew": []},
        "seasons": [
            {"season_number": 1, "episode_count": 10},
        ],
    },
}

# ---------------------------------------------------------------------------
# Other
# ---------------------------------------------------------------------------

EMPTY_SEARCH = {"results": []}

# ---------------------------------------------------------------------------
# Mock registration helpers
# ---------------------------------------------------------------------------


def mock_tmdb(fixture, media_type="movie"):
    """Register responses mocks for search + detail.

    Call inside @responses.activate.
    """
    endpoint = "search/tv" if media_type == "tv" else "search/movie"
    resp_lib.add(
        resp_lib.GET, f"{BASE_URL}/{endpoint}", json=fixture["search"]
    )
    detail_type = "tv" if media_type == "tv" else "movie"
    for result in fixture["search"]["results"]:
        tmdb_id = result["id"]
        detail = fixture.get("detail") or fixture["details"][tmdb_id]
        resp_lib.add(
            resp_lib.GET,
            f"{BASE_URL}/{detail_type}/{tmdb_id}",
            json=detail,
        )


def mock_tmdb_ambiguous(fixture, media_type="tv"):
    """Register mocks for fixture with per-ID details dict."""
    endpoint = "search/tv" if media_type == "tv" else "search/movie"
    resp_lib.add(
        resp_lib.GET, f"{BASE_URL}/{endpoint}", json=fixture["search"]
    )
    detail_type = "tv" if media_type == "tv" else "movie"
    for result in fixture["search"]["results"]:
        tmdb_id = result["id"]
        detail = fixture["details"][tmdb_id]
        resp_lib.add(
            resp_lib.GET,
            f"{BASE_URL}/{detail_type}/{tmdb_id}",
            json=detail,
        )


def mock_tmdb_by_id(fixture, media_type="movie"):
    """Register mock for get_by_id only (no search).

    For NFO identification.
    """
    detail_type = "tv" if media_type == "tv" else "movie"
    tmdb_id = fixture["detail"]["id"]
    resp_lib.add(
        resp_lib.GET,
        f"{BASE_URL}/{detail_type}/{tmdb_id}",
        json=fixture["detail"],
    )


def mock_tmdb_empty(media_type="movie"):
    """Register mock returning no search results."""
    endpoint = "search/tv" if media_type == "tv" else "search/movie"
    resp_lib.add(
        resp_lib.GET, f"{BASE_URL}/{endpoint}", json=EMPTY_SEARCH
    )


def mock_tmdb_error(status=401, media_type="movie"):
    """Register mock returning HTTP error."""
    endpoint = "search/tv" if media_type == "tv" else "search/movie"
    resp_lib.add(resp_lib.GET, f"{BASE_URL}/{endpoint}", status=status)
