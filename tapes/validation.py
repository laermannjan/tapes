import os
from tapes.config.schema import TapesConfig


class ConfigError(SystemExit):
    pass


def validate_config(cfg: TapesConfig) -> None:
    """Validate required config at startup. Raises ConfigError with a clear message."""
    if not cfg.metadata.tmdb_api_key:
        cfg.metadata.tmdb_api_key = os.environ.get("TMDB_API_KEY", "")
    if not cfg.metadata.tmdb_api_key:
        raise ConfigError(
            "TMDB API key not configured.\n"
            "  Set TMDB_API_KEY environment variable, or add to tapes.toml:\n"
            "    [metadata]\n"
            '    tmdb_api_key = "your-key-here"'
        )

    if not cfg.library.movies and not cfg.library.tv:
        raise ConfigError(
            "No library paths configured.\n"
            "  Add to tapes.toml:\n"
            "    [library]\n"
            '    movies = "~/Media/Movies"\n'
            '    tv    = "~/Media/TV"'
        )
