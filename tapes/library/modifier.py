import logging
from dataclasses import dataclass, field
from pathlib import Path

from tapes.companions.classifier import classify_companions, rename_companion
from tapes.config.schema import TapesConfig
from tapes.db.repository import Repository, ItemRecord
from tapes.metadata.base import MetadataSource
from tapes.templates.engine import render_template
from tapes.importer.file_ops import safe_rename

logger = logging.getLogger(__name__)


@dataclass
class ModifyResult:
    ok: bool = True
    error: str = ""
    moved: bool = False
    old_path: str = ""
    new_path: str = ""
    items_modified: int = 0
    errors: list[str] = field(default_factory=list)


def _parse_tmdb_id(tmdb_id: str) -> tuple[int | None, str]:
    """Parse 'tmdb:12345' format. Returns (id, error)."""
    if not tmdb_id.startswith("tmdb:"):
        return None, "Invalid ID format. Use tmdb:<id> (e.g. tmdb:438631)"
    try:
        return int(tmdb_id[5:]), ""
    except ValueError:
        return None, "Invalid ID format. Use tmdb:<id> (e.g. tmdb:438631)"


def _find_items(repo: Repository, path: Path) -> list[ItemRecord]:
    """Look up items by exact path or directory prefix."""
    path_str = str(path)
    if path.is_dir():
        return repo.query_items("path LIKE ?", [path_str.rstrip("/") + "/%"])
    return repo.query_items("path = ?", [path_str])


def modify_items(
    repo: Repository,
    config: TapesConfig,
    metadata_source: MetadataSource,
    path: Path,
    tmdb_id: str | None = None,
    no_move: bool = False,
    event_bus=None,
) -> ModifyResult:
    """Modify one or more items under path."""
    path = path.resolve() if path.exists() else path

    items = _find_items(repo, path)
    if not items:
        return ModifyResult(ok=False, error=f"Item not found in library: {path}")

    if tmdb_id is None:
        return ModifyResult(ok=False, error="No --id provided. Interactive mode not yet supported.")

    parsed_id, err = _parse_tmdb_id(tmdb_id)
    if err:
        return ModifyResult(ok=False, error=err)

    overall = ModifyResult()
    for item in items:
        result = _modify_single(repo, config, metadata_source, item, parsed_id, no_move, event_bus)
        if result.ok:
            overall.items_modified += 1
            if result.moved:
                overall.moved = True
            overall.old_path = result.old_path
            overall.new_path = result.new_path
        else:
            overall.errors.append(result.error)

    if overall.errors:
        overall.ok = overall.items_modified > 0
        overall.error = "; ".join(overall.errors)

    return overall


# Keep the old name as an alias for backwards compatibility with tests
def modify_item(
    repo: Repository,
    config: TapesConfig,
    metadata_source: MetadataSource,
    path: Path,
    tmdb_id: str | None = None,
    no_move: bool = False,
    event_bus=None,
) -> ModifyResult:
    return modify_items(repo, config, metadata_source, path, tmdb_id, no_move, event_bus)


def _modify_single(
    repo: Repository,
    config: TapesConfig,
    metadata_source: MetadataSource,
    item: ItemRecord,
    parsed_id: int,
    no_move: bool,
    event_bus,
) -> ModifyResult:
    result = metadata_source.get_by_id(parsed_id, item.media_type)
    if result is None:
        return ModifyResult(ok=False, error=f"TMDB ID {parsed_id} not found for {item.media_type}")

    # Update item metadata
    item.tmdb_id = result.tmdb_id
    item.title = result.title
    item.year = result.year
    item.director = result.director
    item.genre = result.genre
    item.confidence = result.confidence
    item.match_source = "tmdb"
    if result.media_type == "tv":
        item.show = result.show
        item.season = result.season
        item.episode = result.episode
        item.episode_title = result.episode_title

    # Compute new path from template
    old_video = Path(item.path)
    new_path = _render_destination(item, config, old_video.suffix)
    moved = False
    old_path_str = item.path

    if not no_move and new_path and str(new_path) != item.path:
        if old_video.exists():
            new_path.parent.mkdir(parents=True, exist_ok=True)

            # Move companion files alongside the video
            _move_companions(old_video, new_path)

            safe_rename(old_video, new_path)
            repo.update_item_path(item.path, str(new_path))
            item.path = str(new_path)
            moved = True

    # Write updated metadata to DB
    repo.upsert_item(item)

    # Emit after_write so plugins (e.g. NFO) can regenerate
    if event_bus is not None:
        event_bus.emit(
            "after_write",
            path=item.path,
            media_type=item.media_type,
            title=item.title,
            year=item.year,
            tmdb_id=item.tmdb_id,
            show=item.show,
            season=item.season,
            episode=item.episode,
        )

    return ModifyResult(ok=True, moved=moved, old_path=old_path_str, new_path=item.path)


def _move_companions(old_video: Path, new_video: Path) -> None:
    """Move companion files from old location to new location."""
    companions = classify_companions(old_video)
    new_stem = new_video.stem
    for comp in companions:
        if not comp.move_by_default:
            continue
        new_name = rename_companion(comp.path.name, new_stem, comp.category)
        new_comp_path = new_video.parent / comp.relative_to_video.parent / new_name
        try:
            new_comp_path.parent.mkdir(parents=True, exist_ok=True)
            safe_rename(comp.path, new_comp_path)
        except Exception as e:
            logger.warning("Failed to move companion %s: %s", comp.path, e)


def _render_destination(item: ItemRecord, config: TapesConfig, ext: str) -> Path | None:
    fields = {
        "title": item.title,
        "year": item.year,
        "show": item.show,
        "season": item.season,
        "episode": item.episode,
        "episode_title": item.episode_title,
        "director": item.director,
        "genre": item.genre,
        "edition": item.edition,
        "ext": ext.lower(),
    }

    if item.media_type == "tv":
        if not config.library.tv:
            return None
        template = config.templates.tv
        library_root = Path(config.library.tv).expanduser()
    else:
        if not config.library.movies:
            return None
        template = config.templates.movie
        library_root = Path(config.library.movies).expanduser()

    rendered = render_template(template, fields, replace=config.replace)
    return library_root / rendered
