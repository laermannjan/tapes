import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

from tapes.companions.classifier import classify_companions, rename_companion
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
    manual_prompt,
    read_action,
    search_prompt,
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
            no_db=config.import_.no_db,
        )

    def import_path(self, path: Path) -> dict:
        summary = ImportSummary(dry_run=self._cfg.import_.dry_run)

        video_files = scan_media_files(path)
        if not video_files:
            logger.info("No media files found under %s", path)
            return vars(summary)

        groups = group_media_files(video_files)
        no_db = self._cfg.import_.no_db
        session = ImportSession.create(self._repo, str(path)) if not summary.dry_run and not no_db else None

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

        # Stash identification source for DB record. Must be done before any
        # early return that skips the DB write. The key is namespaced to avoid
        # collision with guessit's "source" (media source like "Blu-ray").
        result.file_info["_identification_source"] = result.source

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
        companions = None  # will be set by _prompt_user if interactive
        if result.requires_interaction:
            # Accept-all mode: auto-accept top candidate if above threshold
            if (self._accept_all and result.candidates
                    and result.candidates[0].confidence >= self._cfg.import_.confidence_threshold):
                candidate = result.candidates[0]
            else:
                candidate, companions = self._prompt_user(video, result, index=index, total=total)
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
        op_id = session.add_operation(str(video), self._cfg.import_.mode) if session else None
        try:
            self._execute_file_op(video, dest)
            self._move_companions(video, dest, companions=companions)
            if not self._cfg.import_.no_db:
                self._write_db_record(video, dest, candidate, result.file_info)
            if session:
                session.update_operation(op_id, state="done", dest_path=str(dest))
            summary.imported += 1
        except Exception as e:
            if session:
                session.update_operation(op_id, state="failed", error=str(e))
            raise

    def _prompt_user(self, video, result, *, index, total):
        """Show interactive prompt and return (candidate, companions) or (None, None)."""
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
                _, idx = action
                return prompt.candidates[idx], companions

            if action == PromptAction.ACCEPT:
                return prompt.candidates[0], companions

            if action == PromptAction.ACCEPT_ALL:
                self._accept_all = True
                return prompt.candidates[0], companions

            if action == PromptAction.SKIP:
                return None, None

            if action == PromptAction.QUIT:
                raise _QuitImport()

            if action == PromptAction.MANUAL:
                default_title = result.file_info.get("title") or result.file_info.get("show") or ""
                default_year = result.file_info.get("year")
                default_media_type = "tv" if "season" in result.file_info else "movie"
                manual_result = manual_prompt(
                    self._console,
                    default_media_type=default_media_type,
                    default_title=default_title,
                    default_year=default_year,
                )
                return manual_result, companions

            if action == PromptAction.SEARCH:
                default_title = result.file_info.get("title") or result.file_info.get("show") or ""
                default_year = result.file_info.get("year")
                default_media_type = "tv" if "season" in result.file_info else "movie"

                mt, title, year = search_prompt(
                    self._console,
                    default_media_type=default_media_type,
                    default_title=default_title,
                    default_year=default_year,
                )
                search_results = self._meta.search(title, year, mt)
                if search_results:
                    prompt = InteractivePrompt(candidates=search_results, is_search_result=True)
                else:
                    prompt = InteractivePrompt(candidates=[], after_failed_search=True)
                continue

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

    def _move_companions(self, src_video: Path, dest_video: Path,
                         companions: list | None = None) -> None:
        """Move companion files alongside the imported video."""
        if companions is None:
            companions = classify_companions(src_video)
        dest_stem = dest_video.stem
        for comp in companions:
            if not comp.move_by_default:
                continue
            new_name = rename_companion(comp.path.name, dest_stem, comp.category)
            new_path = dest_video.parent / comp.relative_to_video.parent / new_name
            try:
                new_path.parent.mkdir(parents=True, exist_ok=True)
                mode = self._cfg.import_.mode
                if mode == "copy":
                    copy_verify(comp.path, new_path)
                elif mode == "move":
                    move_file(comp.path, new_path, verify=True)
                elif mode == "link":
                    new_path.symlink_to(comp.path)
                elif mode == "hardlink":
                    new_path.hardlink_to(comp.path)
            except Exception as e:
                logger.warning("Failed to process companion %s: %s", comp.path, e)

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
            match_source=file_info.get("_identification_source") or "tmdb",
            confidence=candidate.confidence,
            mtime=stat.st_mtime,
            size=stat.st_size,
            imported_at=datetime.now(timezone.utc).isoformat(),
        )
        self._repo.upsert_item(item)
