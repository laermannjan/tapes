import os
from tapes.config.schema import TapesConfig


class ConfigError(SystemExit):
    pass


def validate_config(cfg: TapesConfig) -> None:
    """Validate required config at startup. Raises ConfigError with a clear message."""
    if not cfg.metadata.tmdb_token:
        cfg.metadata.tmdb_token = os.environ.get("TMDB_TOKEN", "")
    if not cfg.metadata.tmdb_token:
        raise ConfigError(
            "TMDB read access token not configured.\n"
            "  Set TMDB_TOKEN environment variable, or add to tapes.toml:\n"
            "    [metadata]\n"
            '    tmdb_token = "your-token-here"\n'
            "  Get one at https://www.themoviedb.org/settings/api"
        )

    if not cfg.library.movies and not cfg.library.tv:
        raise ConfigError(
            "No library paths configured.\n"
            "  Add to tapes.toml:\n"
            "    [library]\n"
            '    movies = "~/Media/Movies"\n'
            '    tv    = "~/Media/TV"'
        )
