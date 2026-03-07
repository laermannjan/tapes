"""Central definitions for metadata field names.

Import these constants instead of using string literals to avoid
typos and enable IDE navigation / refactoring.
"""

# Core fields (used in templates and throughout)
TITLE = "title"
YEAR = "year"
SEASON = "season"
EPISODE = "episode"
EPISODE_TITLE = "episode_title"
MEDIA_TYPE = "media_type"
TMDB_ID = "tmdb_id"

# media_type values
MEDIA_TYPE_MOVIE = "movie"
MEDIA_TYPE_EPISODE = "episode"

# Integer fields (for type coercion during editing)
INT_FIELDS = frozenset({YEAR, SEASON, EPISODE})
