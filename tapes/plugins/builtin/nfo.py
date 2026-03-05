"""NFO sidecar plugin -- writes Kodi-compatible NFO files after import."""

import logging
from pathlib import Path
from xml.sax.saxutils import escape

logger = logging.getLogger(__name__)


class NfoPlugin:
    """Writes NFO sidecar files alongside imported video files.

    Listens to the ``after_write`` event and generates a minimal XML NFO
    file compatible with Kodi/Jellyfin/Emby scrapers.
    """

    name = "nfo"

    def setup(self, config: dict, event_bus) -> None:
        self._enabled = config.get("enabled", False)
        if self._enabled:
            event_bus.on("after_write", self._on_after_write)

    def _on_after_write(
        self,
        path: str,
        media_type: str,
        title: str,
        year: int,
        tmdb_id: int,
        **kwargs,
    ) -> None:
        video = Path(path)
        nfo_path = video.with_suffix(".nfo")

        if media_type == "tv":
            content = self._render_tv(title, year, tmdb_id, **kwargs)
        else:
            content = self._render_movie(title, year, tmdb_id)

        nfo_path.write_text(content, encoding="utf-8")
        logger.info("Wrote NFO: %s", nfo_path)

    def _render_movie(self, title: str, year: int, tmdb_id: int) -> str:
        return (
            f"<movie>\n"
            f"  <title>{escape(str(title))}</title>\n"
            f"  <year>{year}</year>\n"
            f"  <tmdbid>{tmdb_id}</tmdbid>\n"
            f"</movie>\n"
        )

    def _render_tv(self, title: str, year: int, tmdb_id: int, **kwargs) -> str:
        show = escape(str(kwargs.get("show", "")))
        season = kwargs.get("season", "")
        episode = kwargs.get("episode", "")
        return (
            f"<episodedetails>\n"
            f"  <title>{escape(str(title))}</title>\n"
            f"  <showtitle>{show}</showtitle>\n"
            f"  <season>{season}</season>\n"
            f"  <episode>{episode}</episode>\n"
            f"  <tmdbid>{tmdb_id}</tmdbid>\n"
            f"</episodedetails>\n"
        )
