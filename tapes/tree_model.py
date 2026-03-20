"""Tree data model for the TUI redesign."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class FileStatus(Enum):
    PENDING = "pending"
    STAGED = "staged"
    REJECTED = "rejected"


@dataclass
class Candidate:
    """A metadata candidate (e.g. TMDB search result)."""

    name: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0


@dataclass
class FileNode:
    """A file in the tree."""

    path: Path
    status: FileStatus = FileStatus.PENDING
    metadata: dict[str, Any] = field(default_factory=dict)
    candidates: list[Candidate] = field(default_factory=list)

    @property
    def staged(self) -> bool:
        return self.status == FileStatus.STAGED

    @property
    def rejected(self) -> bool:
        return self.status == FileStatus.REJECTED

    @property
    def pending(self) -> bool:
        return self.status == FileStatus.PENDING


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

    def __post_init__(self) -> None:
        self._cached_files: list[FileNode] | None = None

    def all_files(self) -> list[FileNode]:
        """Return all FileNodes depth-first (cached, returns a copy).

        The cache assumes the tree structure is immutable after construction.
        """
        if self._cached_files is None:
            self._cached_files = collect_files(self.root)
        return list(self._cached_files)

    def toggle_staged(
        self,
        node: FileNode,
        can_stage: Callable[[FileNode], bool] | None = None,
    ) -> None:
        """Toggle staged status on a file node.

        If *can_stage* is provided and the node is not currently staged,
        staging is only allowed when ``can_stage(node)`` returns True.
        Unstaging is always allowed.
        """
        if node.staged:
            node.status = FileStatus.PENDING
        elif can_stage is None or can_stage(node):
            node.status = FileStatus.STAGED

    def toggle_rejected(self, node: FileNode) -> None:
        """Toggle rejected status on a file node.

        PENDING <-> REJECTED (toggle), STAGED -> REJECTED (one-way).
        """
        if node.rejected:
            node.status = FileStatus.PENDING
        else:
            node.status = FileStatus.REJECTED

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

    def toggle_staged_recursive(
        self,
        node: FolderNode,
        can_stage: Callable[[FileNode], bool] | None = None,
    ) -> None:
        """Toggle staged on all file descendants.

        If ALL are staged, unstage all. Otherwise stage only those
        that pass *can_stage* (if provided).
        """
        files = collect_files(node)
        if not files:
            return
        all_staged = all(f.staged for f in files)
        if all_staged:
            for f in files:
                f.status = FileStatus.PENDING
        else:
            for f in files:
                if not f.staged and (can_stage is None or can_stage(f)):
                    f.status = FileStatus.STAGED

    def toggle_rejected_recursive(self, node: FolderNode) -> None:
        """Toggle rejected on all file descendants.

        If ALL are rejected, un-reject all. Otherwise reject all.
        """
        files = collect_files(node)
        if not files:
            return
        all_rejected = all(f.rejected for f in files)
        for f in files:
            if all_rejected:
                f.status = FileStatus.PENDING
            else:
                f.status = FileStatus.REJECTED

    def remove_nodes(self, nodes: list[FileNode]) -> None:
        """Remove file nodes from the tree and prune empty folders."""
        to_remove = {id(n) for n in nodes}
        _prune(self.root, to_remove)
        self._cached_files = None


def collect_files(node: FolderNode) -> list[FileNode]:
    """Collect all FileNode descendants of a folder, depth-first."""
    result: list[FileNode] = []
    for child in node.children:
        if isinstance(child, FileNode):
            result.append(child)
        elif isinstance(child, FolderNode):
            result.extend(collect_files(child))
    return result


def _prune(folder: FolderNode, to_remove: set[int]) -> None:
    """Remove matching file nodes and empty folders recursively."""
    folder.children = [c for c in folder.children if id(c) not in to_remove]
    for c in folder.children:
        if isinstance(c, FolderNode):
            _prune(c, to_remove)
    folder.children = [c for c in folder.children if not isinstance(c, FolderNode) or c.children]


def build_tree(files: list[Path], root_path: Path) -> TreeModel:
    """Build a TreeModel from a flat list of file paths.

    Paths are made relative to root_path. Intermediate directories
    become FolderNodes. Sorting: folders first (alphabetical),
    then files (alphabetical).
    """
    tree_dict: dict[str, Any] = {}
    for file_path in files:
        rel = file_path.relative_to(root_path)
        parts = rel.parts
        current = tree_dict
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = None

    root = FolderNode(name=root_path.name)
    _build_folder(root, tree_dict, root_path)
    _compress_single_child_dirs(root)
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

    folders.sort(key=lambda x: x[0])
    file_names.sort()

    for name, subtree in folders:
        child_folder = FolderNode(name=name)
        _build_folder(child_folder, subtree, current_path / name)
        folder.children.append(child_folder)

    for name in file_names:
        folder.children.append(FileNode(path=current_path / name))


def _compress_single_child_dirs(folder: FolderNode) -> None:
    """Merge chains of single-child directories.

    If a folder's only child is another folder (no sibling files),
    merge them: ``foo/ -> bar/`` becomes ``foo/bar/``.
    Applied recursively bottom-up.
    """
    for child in folder.children:
        if isinstance(child, FolderNode):
            _compress_single_child_dirs(child)

    i = 0
    while i < len(folder.children):
        child = folder.children[i]
        if isinstance(child, FolderNode):
            # Merge while this child has exactly one child and it's a folder
            while len(child.children) == 1 and isinstance(child.children[0], FolderNode):
                grandchild = child.children[0]
                child.name = f"{child.name}/{grandchild.name}"
                child.children = grandchild.children
        i += 1


def compute_shared_fields(nodes: list[FileNode]) -> dict[str, Any]:
    """Compute shared metadata fields across multiple file nodes.

    Fields present in all nodes with identical values are kept as-is.
    Fields with differing values become ``"(N values)"`` where N is the
    count of distinct values.
    Fields present in at least one node but not all still appear.
    """
    if not nodes:
        return {}

    all_keys: set[str] = set()
    for node in nodes:
        all_keys.update(node.metadata.keys())

    shared: dict[str, Any] = {}
    for key in sorted(all_keys):
        values: list[Any] = [node.metadata[key] for node in nodes if key in node.metadata]

        if not values:
            continue

        first = values[0]
        if len(values) == len(nodes) and all(v == first for v in values):
            shared[key] = first
        else:
            n_unique = len({str(v) for v in values})
            shared[key] = f"({n_unique} values)"

    return shared
