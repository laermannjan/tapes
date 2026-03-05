import logging
from dataclasses import dataclass, field
from pathlib import Path

from tapes.config.schema import TapesConfig
from tapes.db.repository import Repository, ItemRecord
from tapes.templates.engine import render_template
from tapes.importer.file_ops import safe_rename

logger = logging.getLogger(__name__)


@dataclass
class MoveResult:
    moved: int = 0
    already_in_place: int = 0
    skipped: int = 0
    failed: int = 0
    planned: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.failed == 0


def plan_moves(repo: Repository, config: TapesConfig) -> list[dict]:
    items = repo.get_all_items()
    moves = []

    for item in items:
        new_path = _render_destination(item, config)
        if new_path is None:
            continue
        new_path_str = str(new_path)
        if item.path == new_path_str:
            continue
        moves.append({
            "item": item,
            "old_path": item.path,
            "new_path": new_path_str,
        })

    return moves


def execute_moves(
    moves: list[dict],
    repo: Repository,
    dry_run: bool = False,
) -> MoveResult:
    result = MoveResult()

    if dry_run:
        result.planned = [{"old_path": m["old_path"], "new_path": m["new_path"]} for m in moves]
        return result

    for move in moves:
        item: ItemRecord = move["item"]
        old = Path(move["old_path"])
        new = Path(move["new_path"])

        if not old.exists():
            logger.warning("Source missing, skipping: %s", old)
            result.skipped += 1
            continue

        try:
            new.parent.mkdir(parents=True, exist_ok=True)
            safe_rename(old, new)
            repo.update_item_path(str(old), str(new))
            result.moved += 1
        except Exception as e:
            logger.error("Failed to move %s -> %s: %s", old, new, e)
            result.failed += 1

    return result


def _render_destination(item: ItemRecord, config: TapesConfig) -> Path | None:
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
        "ext": Path(item.path).suffix.lower(),
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
