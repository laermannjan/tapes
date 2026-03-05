from dataclasses import dataclass, field
from pathlib import Path

from tapes.db.repository import Repository
from tapes.discovery.scanner import VIDEO_EXTENSIONS


@dataclass
class CheckResult:
    missing: list[str] = field(default_factory=list)
    orphaned: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing and not self.orphaned


def check_library(repo: Repository, library_roots: list[Path]) -> CheckResult:
    result = CheckResult()
    items = repo.get_all_items()

    # Check for missing files (in DB, not on disk)
    db_paths: set[str] = set()
    for item in items:
        db_paths.add(item.path)
        if not Path(item.path).exists():
            result.missing.append(item.path)

    # Check for orphaned video files (on disk, not in DB)
    for root in library_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            if str(path) not in db_paths:
                result.orphaned.append(str(path))

    return result
