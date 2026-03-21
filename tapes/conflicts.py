"""Unified conflict detection and resolution for staged files.

Groups all staged file pairs by destination, injects virtual nodes for
files already on disk, and applies one of three resolution policies:

- ``auto``: largest file wins (existing wins ties); losers are rejected.
- ``skip``: existing file always wins; staged-vs-staged falls back to auto.
- ``keep_all``: all files are kept; duplicates get numeric suffixes.

Writability is always checked first - unwritable destinations are rejected
regardless of policy.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import structlog

from tapes.templates import full_extension
from tapes.tree_model import FileNode, FileStatus

logger = structlog.get_logger()


@dataclass
class ExistingFile:
    """Virtual node representing a file already at the destination."""

    path: Path
    size: int
    is_existing: bool = True


@dataclass
class ResolvedConflict:
    """A conflict that was automatically resolved."""

    description: str


@dataclass
class Problem:
    """A conflict that could not be auto-resolved."""

    description: str
    rejected_nodes: list[FileNode] = field(default_factory=list)


@dataclass
class ConflictReport:
    """Result of running conflict detection."""

    resolved: list[ResolvedConflict] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)
    valid_pairs: list[tuple[FileNode, Path]] = field(default_factory=list)
    overwrite_dests: set[Path] = field(default_factory=set)

    @property
    def rejected_count(self) -> int:
        """Total number of rejected nodes across all problems."""
        return sum(len(p.rejected_nodes) for p in self.problems)


# Type alias for entries in conflict groups:
# (node, dest, size, index) where index provides deterministic tie-breaking
Entry = tuple[FileNode | ExistingFile, Path, int, int]


def _file_size(node: FileNode) -> int:
    """Get file size, returning -1 on error."""
    try:
        return node.path.stat().st_size
    except OSError:
        return -1


def _stem_without_full_ext(path: Path) -> str:
    """Return the filename stem after removing the full extension."""
    ext = full_extension(path)
    name = path.name
    if ext:
        dot_ext = "." + ext
        if name.endswith(dot_ext):
            return name[: -len(dot_ext)]
    return path.stem


def _suffixed_name(dest: Path, index: int) -> Path:
    """Add a ``' N'`` suffix before the full extension.

    E.g. ``Dune (2021).mkv`` with index 2 becomes ``Dune (2021) 2.mkv``.
    Compound extensions are preserved:
    ``movie.en.srt`` with index 2 becomes ``movie 2.en.srt``.
    """
    ext = full_extension(dest)
    stem = _stem_without_full_ext(dest)
    new_name = f"{stem} {index}.{ext}" if ext else f"{stem} {index}"
    return dest.parent / new_name


def _writability_check(
    pairs: list[tuple[FileNode, Path]],
    report: ConflictReport,
) -> list[tuple[FileNode, Path]]:
    """Check that destination directories are writable.

    For each unique destination directory, walk up to find the first
    existing ancestor and check ``os.access(ancestor, os.W_OK)``.
    Unwritable destinations set the node to REJECTED.
    """
    remaining: list[tuple[FileNode, Path]] = []
    dir_writable: dict[Path, bool] = {}

    for node, dest in pairs:
        dest_dir = dest.parent
        if dest_dir not in dir_writable:
            ancestor = dest_dir
            while not ancestor.exists():
                parent = ancestor.parent
                if parent == ancestor:
                    break
                ancestor = parent
            dir_writable[dest_dir] = os.access(ancestor, os.W_OK)

        if dir_writable[dest_dir]:
            remaining.append((node, dest))
        else:
            node.status = FileStatus.REJECTED
            log = logger.bind(file=node.path.name)
            log.info("rejected", reason="not_writable", dest_dir=str(dest_dir))
            report.problems.append(
                Problem(
                    description=f"Destination not writable: {dest_dir}",
                    rejected_nodes=[node],
                )
            )

    return remaining


def _resolve_group_auto(
    entries: list[Entry],
    report: ConflictReport,
) -> list[tuple[FileNode, Path]]:
    """Auto: largest file wins. Existing wins ties.

    Sort key: ``(-size, not is_existing, index)`` ensures deterministic
    tie-breaking. Existing files sort before staged at the same size,
    and among staged files of equal size, first-in-scan-order wins.
    """
    sorted_entries = sorted(
        entries,
        key=lambda e: (-e[2], not isinstance(e[0], ExistingFile), e[3]),
    )
    winner = sorted_entries[0]
    result: list[tuple[FileNode, Path]] = []

    dest_path = str(sorted_entries[0][1])

    if isinstance(winner[0], ExistingFile):
        # Existing file wins - reject all staged files
        logger.debug("conflict_resolved", winner="existing", winner_size=winner[2], dest=dest_path)
        for node, dest, size, _ in sorted_entries:
            if isinstance(node, FileNode):
                node.status = FileStatus.REJECTED
                log = logger.bind(file=node.path.name)
                log.info("rejected", reason="conflict", detail="existing file wins", size=size, dest=dest_path)
                report.resolved.append(
                    ResolvedConflict(f"Rejected: {node.path.name} (existing file at {dest.name} is larger or equal)")
                )
    else:
        # Staged file wins
        logger.debug("conflict_resolved", winner=winner[0].path.name, winner_size=winner[2], dest=dest_path)
        result.append((winner[0], winner[1]))
        for node, dest, size, _ in sorted_entries[1:]:
            if isinstance(node, ExistingFile):
                logger.info("conflict_overwrite", dest=str(dest), winner=winner[0].path.name, existing_size=size)
                report.resolved.append(
                    ResolvedConflict(f"Overwrite: existing {dest.name} will be replaced by {winner[0].path.name}")
                )
                report.overwrite_dests.add(dest)
            elif isinstance(node, FileNode):
                node.status = FileStatus.REJECTED
                log = logger.bind(file=node.path.name)
                log.info("rejected", reason="conflict", detail="smaller file", size=size, winner=winner[0].path.name)
                report.resolved.append(
                    ResolvedConflict(f"Rejected: {node.path.name} (smaller than {winner[0].path.name})")
                )

    return result


def _resolve_group_skip(
    entries: list[Entry],
    report: ConflictReport,
) -> list[tuple[FileNode, Path]]:
    """Skip: existing file always wins if present, otherwise fall back to auto."""
    has_existing = any(isinstance(e[0], ExistingFile) for e in entries)

    if has_existing:
        # Reject all staged files
        for node, dest, _, _ in entries:
            if isinstance(node, FileNode):
                node.status = FileStatus.REJECTED
                report.resolved.append(
                    ResolvedConflict(f"Skipped: {node.path.name} (file already exists at {dest.name})")
                )
        return []

    return _resolve_group_auto(entries, report)


def _resolve_group_keep_all(
    entries: list[Entry],
    report: ConflictReport,
    dest: Path,
) -> list[tuple[FileNode, Path]]:
    """Keep all: first staged file keeps clean name, rest get numeric suffixes.

    If an existing file is present, it keeps the clean name and all
    staged files get suffixes.
    """
    result: list[tuple[FileNode, Path]] = []
    suffix_index = 2

    has_existing = any(isinstance(e[0], ExistingFile) for e in entries)
    staged_entries = [(n, d, s, i) for n, d, s, i in entries if isinstance(n, FileNode)]

    if has_existing:
        # All staged files get suffixes (existing keeps clean name)
        for node, _, _, _ in staged_entries:
            new_dest = _suffixed_name(dest, suffix_index)
            result.append((node, new_dest))
            report.resolved.append(ResolvedConflict(f"Renamed: {node.path.name} -> {new_dest.name}"))
            suffix_index += 1
    # First staged file keeps clean name
    elif staged_entries:
        first_node = staged_entries[0][0]
        result.append((first_node, dest))
        for node, _, _, _ in staged_entries[1:]:
            new_dest = _suffixed_name(dest, suffix_index)
            result.append((node, new_dest))
            report.resolved.append(ResolvedConflict(f"Renamed: {node.path.name} -> {new_dest.name}"))
            suffix_index += 1

    return result


def _resolve_conflicts(
    pairs: list[tuple[FileNode, Path]],
    report: ConflictReport,
    conflict_resolution: Literal["auto", "skip", "keep_all"],
) -> list[tuple[FileNode, Path]]:
    """Group by destination, inject virtual nodes for existing files, resolve."""
    by_dest: dict[Path, list[tuple[FileNode, Path]]] = defaultdict(list)
    for node, dest in pairs:
        by_dest[dest].append((node, dest))

    remaining: list[tuple[FileNode, Path]] = []

    for dest, group in by_dest.items():
        # Build entries with sizes and index for deterministic tie-breaking
        entries: list[Entry] = []
        for idx, (node, d) in enumerate(group):
            entries.append((node, d, _file_size(node), idx))

        # Inject virtual node if destination exists on disk
        if dest.exists():
            try:
                existing_size = dest.stat().st_size
                # Use a high index so existing file doesn't interfere with
                # staged-file index ordering (it wins ties via is_existing flag)
                entries.append((ExistingFile(path=dest, size=existing_size), dest, existing_size, len(group)))
            except OSError:
                pass

        if len(entries) <= 1:
            # No conflict (single staged file, no existing)
            remaining.extend(group)
            continue

        staged_names = [n.path.name for n, _, _, _ in entries if isinstance(n, FileNode)]
        has_existing = any(isinstance(e[0], ExistingFile) for e in entries)
        logger.info(
            "conflict_group",
            dest=dest.name,
            count=len(staged_names),
            has_existing=has_existing,
            policy=conflict_resolution,
            files=staged_names,
        )

        if conflict_resolution == "auto":
            remaining.extend(_resolve_group_auto(entries, report))
        elif conflict_resolution == "skip":
            remaining.extend(_resolve_group_skip(entries, report))
        elif conflict_resolution == "keep_all":
            remaining.extend(_resolve_group_keep_all(entries, report, dest))

    return remaining


def detect_conflicts(
    pairs: list[tuple[FileNode, Path]],
    *,
    conflict_resolution: Literal["auto", "skip", "keep_all"] = "auto",
) -> ConflictReport:
    """Run conflict detection on a list of (FileNode, destination) pairs.

    Checks run in order:

    1. **Writability** (always on) - unwritable destinations are rejected.
    2. **Conflict resolution** - staged-vs-staged and staged-vs-existing
       conflicts are resolved according to *conflict_resolution* policy.

    Returns a :class:`ConflictReport` with resolved conflicts, problems,
    and the final valid pairs list.
    """
    report = ConflictReport()
    remaining = _writability_check(pairs, report)
    remaining = _resolve_conflicts(remaining, report, conflict_resolution)
    report.valid_pairs = remaining
    return report
