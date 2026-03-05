import logging
from dataclasses import dataclass, field
from pathlib import Path

from tapes.db.repository import Repository, ItemRecord
from tapes.metadata.base import MetadataSource, SearchResult
from tapes.identification.filename import parse_filename
from tapes.identification.osdb_hash import compute_hash
from tapes.identification.mediainfo import parse_mediainfo
from tapes.identification.nfo_scanner import scan_for_nfo_id

logger = logging.getLogger(__name__)

NFO_ID_CONFIDENCE = 0.95


@dataclass
class IdentificationResult:
    item: ItemRecord | None = None
    candidates: list[SearchResult] = field(default_factory=list)
    file_info: dict = field(default_factory=dict)
    source: str | None = None
    requires_interaction: bool = False
    multi_episode: bool = False


class IdentificationPipeline:
    def __init__(
        self,
        repo: Repository,
        metadata_source: MetadataSource,
        confidence_threshold: float = 0.9,
        no_db: bool = False,
    ):
        self._repo = repo
        self._meta = metadata_source
        self._threshold = confidence_threshold
        self._no_db = no_db

    def identify(self, path: Path) -> IdentificationResult:
        stat = path.stat()

        # Step 1: DB cache lookup
        if not self._no_db:
            cached = self._repo.find_by_path_stat(str(path), stat.st_mtime, stat.st_size)
            if cached:
                return IdentificationResult(item=cached, source="db_cache")

        file_info: dict = {"path": str(path), "mtime": stat.st_mtime, "size": stat.st_size}

        # Step 2: NFO scan (walks up 2 directory levels)
        nfo_id = scan_for_nfo_id(path)
        if nfo_id:
            id_type, id_val = nfo_id
            # Detect media type from NFO filename convention
            media_type = _guess_media_type_from_nfo(path)
            result = self._meta.get_by_id(id_val, media_type)
            if result:
                result.confidence = NFO_ID_CONFIDENCE
                return IdentificationResult(
                    candidates=[result],
                    file_info=file_info,
                    source="nfo",
                )

        # Step 3: guessit filename parsing
        parsed = parse_filename(path.name, folder_name=path.parent.name)
        file_info.update(parsed)

        # Guard: multi-episode files must go interactive
        if isinstance(file_info.get("episode"), list):
            return IdentificationResult(
                file_info=file_info,
                requires_interaction=True,
                multi_episode=True,
            )

        # Step 4: OSDB hash (computed; API lookup deferred — ADR-004)
        file_info["osdb_hash"] = compute_hash(path)

        # Step 5: MediaInfo (overrides guessit for technical fields)
        file_info.update(parse_mediainfo(path))

        # Step 6: TMDB query
        candidates: list[SearchResult] = []
        if self._meta.is_available():
            title = file_info.get("title") or file_info.get("show") or ""
            year = file_info.get("year")
            media_type = "tv" if "season" in file_info else "movie"
            candidates = self._meta.search(title, year, media_type)
        else:
            logger.warning("Metadata source unavailable; skipping TMDB lookup for %s", path.name)

        # Step 7: auto-accept if top candidate clears threshold
        if candidates and candidates[0].confidence >= self._threshold:
            return IdentificationResult(
                candidates=candidates,
                file_info=file_info,
                source="filename",
            )

        return IdentificationResult(
            candidates=candidates,
            file_info=file_info,
            requires_interaction=True,
        )


def _guess_media_type_from_nfo(video_path: Path) -> str:
    """Heuristic: if a tvshow.nfo is nearby, it's a TV file."""
    for directory in (video_path.parent, video_path.parent.parent):
        if (directory / "tvshow.nfo").exists():
            return "tv"
    return "movie"
