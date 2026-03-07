"""Tree data model for the TUI redesign."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Source:
    """A metadata source (e.g. guessit parse, TMDB result)."""

    name: str
    fields: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0


@dataclass
class FileNode:
    """A file in the tree."""

    path: Path
    staged: bool = False
    ignored: bool = False
    result: dict[str, Any] = field(default_factory=dict)
    sources: list[Source] = field(default_factory=list)


@dataclass
class FolderNode:
    """A directory in the tree."""

    name: str
    children: list[FileNode | FolderNode] = field(default_factory=list)
    collapsed: bool = False


@dataclass
class TreeModel:
    """Tree of folders and files with staging/collapse state."""

    root: FolderNode

    def flatten(self) -> list[FileNode | FolderNode]:
        """Iterate the tree respecting collapsed state.

        The root folder itself is NOT included. Collapsed folders appear
        but their children do not.
        """
        result: list[FileNode | FolderNode] = []
        self._flatten_children(self.root, result)
        return result

    def _flatten_children(
        self,
        folder: FolderNode,
        result: list[FileNode | FolderNode],
    ) -> None:
        for child in folder.children:
            result.append(child)
            if isinstance(child, FolderNode) and not child.collapsed:
                self._flatten_children(child, result)

    def toggle_staged(self, node: FileNode) -> None:
        """Toggle staged flag on a file node."""
        node.staged = not node.staged

    def toggle_ignored(self, node: FileNode) -> None:
        """Toggle ignored flag on a file node."""
        node.ignored = not node.ignored

    def toggle_collapsed(self, node: FolderNode) -> None:
        """Toggle collapsed flag on a folder node."""
        node.collapsed = not node.collapsed

    def collapse_all(self) -> None:
        """Collapse all folders."""
        for folder in self._all_folders(self.root):
            folder.collapsed = True

    def expand_all(self) -> None:
        """Expand all folders."""
        for folder in self._all_folders(self.root):
            folder.collapsed = False

    def _all_folders(self, node: FolderNode) -> list[FolderNode]:
        """Collect all folder nodes (including the given node)."""
        result = [node]
        for child in node.children:
            if isinstance(child, FolderNode):
                result.extend(self._all_folders(child))
        return result

    def toggle_staged_recursive(self, node: FolderNode) -> None:
        """Toggle staged on all file descendants.

        If ALL are staged, unstage all. Otherwise stage all.
        """
        files = collect_files(node)
        if not files:
            return
        all_staged = all(f.staged for f in files)
        for f in files:
            f.staged = not all_staged

    def toggle_ignored_recursive(self, node: FolderNode) -> None:
        """Toggle ignored on all file descendants.

        If ALL are ignored, un-ignore all. Otherwise ignore all.
        """
        files = collect_files(node)
        if not files:
            return
        all_ignored = all(f.ignored for f in files)
        for f in files:
            f.ignored = not all_ignored

    def all_files(self) -> list[FileNode]:
        """Return all FileNodes depth-first."""
        return collect_files(self.root)


def collect_files(node: FolderNode) -> list[FileNode]:
    """Collect all FileNode descendants of a folder, depth-first."""
    result: list[FileNode] = []
    for child in node.children:
        if isinstance(child, FileNode):
            result.append(child)
        elif isinstance(child, FolderNode):
            result.extend(collect_files(child))
    return result


def build_tree(files: list[Path], root_path: Path) -> TreeModel:
    """Build a TreeModel from a flat list of file paths.

    Paths are made relative to root_path. Intermediate directories
    become FolderNodes. Sorting: folders first (alphabetical),
    then files (alphabetical).
    """
    # Build a nested dict structure first
    tree_dict: dict[str, Any] = {}
    for file_path in files:
        rel = file_path.relative_to(root_path)
        parts = rel.parts
        current = tree_dict
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        # Mark leaf files with None
        current[parts[-1]] = None

    root = FolderNode(name=root_path.name)
    _build_folder(root, tree_dict, root_path)
    return TreeModel(root=root)


def _build_folder(
    folder: FolderNode,
    tree_dict: dict[str, Any],
    current_path: Path,
) -> None:
    """Recursively build FolderNode children from the nested dict."""
    folders: list[tuple[str, dict[str, Any]]] = []
    file_names: list[str] = []

    for name, subtree in tree_dict.items():
        if subtree is None:
            file_names.append(name)
        else:
            folders.append((name, subtree))

    # Sort folders alphabetically, then files alphabetically
    folders.sort(key=lambda x: x[0])
    file_names.sort()

    for name, subtree in folders:
        child_folder = FolderNode(name=name)
        _build_folder(child_folder, subtree, current_path / name)
        folder.children.append(child_folder)

    for name in file_names:
        folder.children.append(FileNode(path=current_path / name))


class UndoManager:
    """Single-level undo for metadata changes on FileNodes.

    Call ``snapshot()`` before a mutation to save node state.
    Call ``undo()`` to restore the most recent snapshot.
    """

    def __init__(self) -> None:
        self._snapshot: list[tuple[FileNode, dict[str, Any], list[Source], bool]] | None = None

    def snapshot(self, nodes: list[FileNode]) -> None:
        """Save a deep copy of each node's result, sources, and staged flag."""
        self._snapshot = [
            (node, copy.deepcopy(node.result), copy.deepcopy(node.sources), node.staged)
            for node in nodes
        ]

    def undo(self) -> bool:
        """Restore the most recent snapshot. Returns True if restored."""
        if self._snapshot is None:
            return False
        for node, saved_result, saved_sources, saved_staged in self._snapshot:
            node.result = saved_result
            node.sources = saved_sources
            node.staged = saved_staged
        self._snapshot = None
        return True

    @property
    def has_snapshot(self) -> bool:
        """Whether there is a snapshot to undo."""
        return self._snapshot is not None


def accept_best_source(node: FileNode) -> bool:
    """Apply the highest-confidence source's non-empty fields to result.

    Returns True if a source was applied.
    """
    if not node.sources:
        return False
    best = max(node.sources, key=lambda s: s.confidence)
    if best.confidence == 0:
        return False
    for field, val in best.fields.items():
        if val is not None:
            node.result[field] = val
    return True


def compute_shared_fields(nodes: list[FileNode]) -> dict[str, Any]:
    """Compute shared result fields across multiple file nodes.

    Fields present in all nodes with identical values are kept as-is.
    Fields with differing values become ``"(N values)"`` where N is the
    count of distinct values.
    Fields present in at least one node but not all still appear.
    """
    if not nodes:
        return {}

    # Collect all field names
    all_keys: set[str] = set()
    for node in nodes:
        all_keys.update(node.result.keys())

    result: dict[str, Any] = {}
    for key in sorted(all_keys):
        values: list[Any] = []
        for node in nodes:
            if key in node.result:
                values.append(node.result[key])

        if not values:
            continue

        first = values[0]
        if all(v == first for v in values):
            result[key] = first
        else:
            n_unique = len(set(str(v) for v in values))
            result[key] = f"({n_unique} values)"

    return result
