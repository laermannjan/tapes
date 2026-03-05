import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

from tapes.companions.classifier import classify_companions
from tapes.config.schema import TapesConfig
from tapes.db.repository import Repository, ItemRecord
from tapes.discovery.scanner import scan_media_files
from tapes.discovery.grouper import group_media_files
from tapes.identification.pipeline import IdentificationPipeline
from tapes.importer.interactive import (
    InteractivePrompt,
    PromptAction,
    display_prompt,
    edit_companions,
    read_action,
)
from tapes.metadata.base import MetadataSource, SearchResult
from tapes.templates.engine import render_template
from tapes.importer.session import ImportSession
from tapes.importer.file_ops import copy_verify, move_file, safe_rename

logger = logging.getLogger(__name__)


class _QuitImport(Exception):
    """Internal sentinel raised when the user chooses to quit."""
    pass


@dataclass
class ImportSummary:
    dry_run: bool = False
    imported: int = 0
    skipped: int = 0
    errors: int = 0
    unmatched: list[str] = field(default_factory=list)
    planned: list[dict] = field(default_factory=list)  # for dry-run preview


class ImportService:
    def __init__(
        self,
        repo: Repository,
        metadata_source: MetadataSource,
        config: TapesConfig,
        event_bus=None,
        console=None,
    ):
        self._repo = repo
        self._meta = metadata_source
        self._cfg = config
        self._bus = event_bus
        self._console = console or Console()
        self._accept_all = False
        self._pipeline = IdentificationPipeline(
            repo=repo,
            metadata_source=metadata_source,
            confidence_threshold=config.import_.confidence_threshold,
        )

    def import_path(self, path: Path) -> dict:
        summary = ImportSummary(dry_run=self._cfg.import_.dry_run)

        video_files = scan_media_files(path)
        if not video_files:
            logger.info("No media files found under %s", path)
            return vars(summary)

        groups = group_media_files(video_files)
        session = ImportSession.create(self._repo, str(path)) if not summary.dry_run else None

        total_videos = sum(len(g.video_files) for g in groups)
        video_index = 0

        try:
            for group in groups:
                for video in group.video_files:
                    video_index += 1
                    try:
                        self._process_file(video, summary, session,
                                           index=video_index, total=total_videos)
                    except _QuitImport:
                        raise
                    except Exception as e:
                        logger.error("Error processing %s: %s", video, e)
                        summary.errors += 1
        except _QuitImport:
            pass  # graceful exit

        if session:
            session.complete()

        return vars(summary)

    def _process_file(
        self,
        video: Path,
        summary: ImportSummary,
        session: ImportSession | None,
        *,
        index: int = 0,
        total: int = 0,
    ) -> None:
        result = self._pipeline.identify(video)

        # Already in DB — skip
        if result.item is not None:
            summary.skipped += 1
            return

        # --interactive: force every file through the prompt
        if self._cfg.import_.interactive:
            result.requires_interaction = True

        # No candidates at all — mark unmatched
        if not result.candidates and not result.requires_interaction:
            summary.unmatched.append(str(video))
            summary.skipped += 1
            return

        # Needs interaction
        if result.requires_interaction:
            if not result.candidates:
                summary.unmatched.append(str(video))
                summary.skipped += 1
                return

            # Accept-all mode: auto-accept top candidate
            if self._accept_all:
                candidate = result.candidates[0]
            else:
                candidate = self._prompt_user(video, result, index=index, total=total)
                if candidate is None:
                    summary.skipped += 1
                    return
        else:
            # Auto-accepted — pick best candidate
            if not result.candidates:
                summary.unmatched.append(str(video))
                summary.skipped += 1
                return
            candidate = result.candidates[0]

        dest = self._render_destination(video, candidate)

        if summary.dry_run:
            summary.planned.append({
                "source": str(video),
                "dest": str(dest),
                "title": candidate.title,
                "year": candidate.year,
                "confidence": candidate.confidence,
            })
            summary.imported += 1
            return

        # Execute file operation
        op_id = session.add_operation(str(video), self._cfg.import_.mode)
        try:
            self._execute_file_op(video, dest)
            self._write_db_record(video, dest, candidate, result.file_info)
            session.update_operation(op_id, state="done", dest_path=str(dest))
            summary.imported += 1
        except Exception as e:
            session.update_operation(op_id, state="failed", error=str(e))
            raise

    def _prompt_user(self, video, result, *, index, total):
        """Show interactive prompt and return selected candidate or None."""
        companions = classify_companions(video)
        prompt = InteractivePrompt(candidates=result.candidates)

        while True:
            display_prompt(
                self._console,
                prompt,
                index=index,
                total=total,
                filename=video.name,
                source=result.source,
                companions=companions or None,
            )
            action = read_action(prompt, has_companions=bool(companions))

            if action == "edit":
                companions = edit_companions(self._console, companions)
                continue

            if isinstance(action, tuple):
                # Numbered candidate selection
                _, idx = action
                return result.candidates[idx]

            if action == PromptAction.ACCEPT:
                return result.candidates[0]

            if action == PromptAction.ACCEPT_ALL:
                self._accept_all = True
                return result.candidates[0]

            if action == PromptAction.SKIP:
                return None

            if action == PromptAction.QUIT:
                raise _QuitImport()

            # SEARCH, MANUAL: skip for now (full search flow is separate work)
            return None

    def _render_destination(self, video: Path, candidate: SearchResult) -> Path:
        cfg = self._cfg
        fields = {
            "title": candidate.title,
            "year": candidate.year,
            "show": candidate.show,
            "season": candidate.season,
            "episode": candidate.episode,
            "episode_title": candidate.episode_title,
            "director": candidate.director,
            "genre": candidate.genre,
            "edition": None,
            "ext": video.suffix.lower(),
        }

        if candidate.media_type == "tv":
            template = cfg.templates.tv
            library_root = Path(cfg.library.tv).expanduser()
        else:
            template = cfg.templates.movie
            library_root = Path(cfg.library.movies).expanduser()

        rendered = render_template(template, fields, replace=cfg.replace)
        return library_root / rendered

    def _execute_file_op(self, src: Path, dst: Path) -> None:
        mode = self._cfg.import_.mode
        dst.parent.mkdir(parents=True, exist_ok=True)
        if mode == "copy":
            copy_verify(src, dst)
        elif mode == "move":
            move_file(src, dst, verify=True)
        elif mode == "link":
            dst.symlink_to(src)
        elif mode == "hardlink":
            dst.hardlink_to(src)

    def _write_db_record(
        self,
        src: Path,
        dst: Path,
        candidate: SearchResult,
        file_info: dict,
    ) -> None:
        # Use dst for stat since src may be deleted in move mode
        stat = dst.stat()
        item = ItemRecord(
            id=None,
            path=str(dst),
            media_type=candidate.media_type,
            tmdb_id=candidate.tmdb_id,
            title=candidate.title,
            year=candidate.year,
            show=candidate.show,
            season=candidate.season,
            episode=candidate.episode,
            episode_title=candidate.episode_title,
            director=candidate.director,
            genre=candidate.genre,
            edition=None,
            codec=file_info.get("codec"),
            resolution=file_info.get("resolution") or file_info.get("screen_size"),
            audio=file_info.get("audio"),
            hdr=file_info.get("hdr", 0),
            match_source=file_info.get("source", "tmdb"),
            confidence=candidate.confidence,
            mtime=stat.st_mtime,
            size=stat.st_size,
            imported_at=datetime.now(timezone.utc).isoformat(),
        )
        self._repo.upsert_item(item)
