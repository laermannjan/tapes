"""Conflict detection and auto-resolution for staged file pairs.

Checks for writability, duplicate destinations (same-size files), and
ambiguous destinations (different-size files or existing files on disk).
Each check can be configured independently: ``"auto"`` resolves and
reports, ``"warn"`` reports as a problem and unstages, ``"off"`` skips.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from tapes.templates import full_extension
from tapes.tree_model import FileNode


@dataclass
class ResolvedConflict:
    """A conflict that was automatically resolved."""

    description: str


@dataclass
class Problem:
    """A conflict that could not be auto-resolved."""

    description: str
    skipped_nodes: list[FileNode] = field(default_factory=list)


@dataclass
class ConflictReport:
    """Result of running conflict detection on a set of file pairs."""

    resolved: list[ResolvedConflict] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)
    valid_pairs: list[tuple[FileNode, Path]] = field(default_factory=list)

    @property
    def skipped_count(self) -> int:
        """Total number of skipped nodes across all problems."""
        return sum(len(p.skipped_nodes) for p in self.problems)


def _stem_without_full_ext(path: Path) -> str:
    """Return the filename stem after removing the full extension."""
    ext = full_extension(path)
    name = path.name
    if ext:
        dot_ext = "." + ext
        if name.endswith(dot_ext):
            return name[: -len(dot_ext)]
    return path.stem


def _disambiguated_name(dest: Path, index: int) -> Path:
    """Add a ``-N`` suffix before the full extension.

    E.g. ``movie.en.srt`` with index 2 becomes ``movie-2.en.srt``.
    """
    ext = full_extension(dest)
    stem = _stem_without_full_ext(dest)
    new_name = f"{stem}-{index}.{ext}" if ext else f"{stem}-{index}"
    return dest.parent / new_name


def _writability_check(
    pairs: list[tuple[FileNode, Path]],
    report: ConflictReport,
) -> list[tuple[FileNode, Path]]:
    """Check that destination directories are writable.

    For each unique destination directory, walk up to find the first
    existing ancestor and check ``os.access(ancestor, os.W_OK)``.
    Unwritable destinations become a Problem and nodes are unstaged.
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
            node.staged = False
            report.problems.append(
                Problem(
                    description=f"Destination not writable: {dest_dir}",
                    skipped_nodes=[node],
                )
            )

    return remaining


def _duplicate_detection(
    pairs: list[tuple[FileNode, Path]],
    report: ConflictReport,
    mode: Literal["auto", "warn", "off"],
) -> list[tuple[FileNode, Path]]:
    """Detect same-destination pairs where files have the same size.

    Auto mode keeps the node with the most ``metadata`` fields
    (tie-break: alphabetical by source path) and unstages the rest.
    """
    if mode == "off":
        return pairs

    by_dest: dict[Path, list[tuple[FileNode, Path]]] = defaultdict(list)
    for node, dest in pairs:
        by_dest[dest].append((node, dest))

    remaining: list[tuple[FileNode, Path]] = []

    for dest, group in by_dest.items():
        if len(group) == 1:
            remaining.append(group[0])
            continue

        by_size: dict[int, list[tuple[FileNode, Path]]] = defaultdict(list)
        for node, d in group:
            try:
                size = node.path.stat().st_size
            except OSError:
                size = -1
            by_size[size].append((node, d))

        kept_for_dest: list[tuple[FileNode, Path]] = []

        for size_group in by_size.values():
            if len(size_group) == 1:
                kept_for_dest.append(size_group[0])
                continue

            if mode == "warn":
                skipped = [n for n, _ in size_group]
                for n in skipped:
                    n.staged = False
                report.problems.append(
                    Problem(
                        description=(f"Duplicate files at {dest}: " + ", ".join(str(n.path) for n in skipped)),
                        skipped_nodes=skipped,
                    )
                )
                continue

            sorted_group = sorted(
                size_group,
                key=lambda pair: (-len(pair[0].metadata), str(pair[0].path)),
            )
            keeper = sorted_group[0]
            kept_for_dest.append(keeper)
            for pair in sorted_group[1:]:
                pair[0].staged = False
                report.resolved.append(
                    ResolvedConflict(
                        description=(
                            f"Duplicate: {pair[0].path.name} unstaged (same destination as {keeper[0].path.name})"
                        ),
                    )
                )

        remaining.extend(kept_for_dest)

    return remaining


def _disambiguation(
    pairs: list[tuple[FileNode, Path]],
    report: ConflictReport,
    mode: Literal["auto", "warn", "off"],
) -> list[tuple[FileNode, Path]]:
    """Disambiguate multiple different files targeting the same destination.

    Also handles the case where a destination already exists on disk.
    Auto mode renames subsequent files with ``-2``, ``-3`` suffixes.
    """
    if mode == "off":
        return pairs

    by_dest: dict[Path, list[tuple[FileNode, Path]]] = defaultdict(list)
    for node, dest in pairs:
        by_dest[dest].append((node, dest))

    remaining: list[tuple[FileNode, Path]] = []

    for dest, group in by_dest.items():
        dest_exists = dest.exists()

        if len(group) == 1 and not dest_exists:
            remaining.append(group[0])
            continue

        if mode == "warn":
            skipped = [n for n, _ in group]
            for n in skipped:
                n.staged = False
            if dest_exists:
                desc = f"Destination already exists: {dest}"
            else:
                desc = f"Multiple files target {dest}: " + ", ".join(str(n.path) for n in skipped)
            report.problems.append(
                Problem(description=desc, skipped_nodes=skipped),
            )
            continue

        sorted_group = sorted(group, key=lambda pair: str(pair[0].path))

        if dest_exists:
            suffix_start = 2
            files_to_rename = sorted_group
        else:
            remaining.append(sorted_group[0])
            suffix_start = 2
            files_to_rename = sorted_group[1:]

        for i, (node, _) in enumerate(files_to_rename):
            new_dest = _disambiguated_name(dest, suffix_start + i)
            remaining.append((node, new_dest))
            report.resolved.append(
                ResolvedConflict(
                    description=(f"Renamed: {node.path.name} -> {new_dest.name} (destination conflict at {dest.name})"),
                )
            )

    return remaining


def detect_conflicts(
    pairs: list[tuple[FileNode, Path]],
    *,
    duplicate_resolution: Literal["auto", "warn", "off"] = "auto",
    disambiguation: Literal["auto", "warn", "off"] = "auto",
) -> ConflictReport:
    """Run conflict detection on a list of (FileNode, destination) pairs.

    Checks run in order:
    1. Writability (always on)
    2. Duplicate detection (same dest, same file size)
    3. Disambiguation (same dest, different files; or dest exists on disk)

    Returns a :class:`ConflictReport` with resolved conflicts, problems,
    and the final valid pairs list.
    """
    report = ConflictReport()

    remaining = _writability_check(pairs, report)
    remaining = _duplicate_detection(remaining, report, duplicate_resolution)
    remaining = _disambiguation(remaining, report, disambiguation)

    report.valid_pairs = remaining
    return report
