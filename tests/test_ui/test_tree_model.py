"""Tests for tapes.ui.tree_model."""
from __future__ import annotations

from pathlib import Path

from tapes.ui.tree_model import (
    FileNode,
    FolderNode,
    Source,
    TreeModel,
    build_tree,
    compute_shared_fields,
)


# --- Source ---


class TestSource:
    def test_creation(self) -> None:
        s = Source(name="from filename", fields={"title": "Foo"}, confidence=0.8)
        assert s.name == "from filename"
        assert s.fields == {"title": "Foo"}
        assert s.confidence == 0.8

    def test_defaults(self) -> None:
        s = Source(name="x")
        assert s.fields == {}
        assert s.confidence == 0.0


# --- FileNode ---


class TestFileNode:
    def test_defaults(self) -> None:
        n = FileNode(path=Path("/a/b.mkv"))
        assert n.staged is False
        assert n.ignored is False
        assert n.result == {}
        assert n.sources == []

    def test_with_values(self) -> None:
        src = Source(name="tmdb", fields={"title": "X"}, confidence=0.95)
        n = FileNode(
            path=Path("/a.mkv"),
            staged=True,
            ignored=True,
            result={"title": "X"},
            sources=[src],
        )
        assert n.staged is True
        assert n.ignored is True
        assert n.result["title"] == "X"
        assert len(n.sources) == 1


# --- FolderNode ---


class TestFolderNode:
    def test_defaults(self) -> None:
        f = FolderNode(name="Movies")
        assert f.collapsed is False
        assert f.children == []

    def test_with_children(self) -> None:
        child = FileNode(path=Path("/Movies/a.mkv"))
        f = FolderNode(name="Movies", children=[child], collapsed=False)
        assert len(f.children) == 1
        assert f.collapsed is False


# --- TreeModel.flatten ---


class TestFlatten:
    def test_collapsed_folder_hides_children(self) -> None:
        child = FileNode(path=Path("/root/sub/a.mkv"))
        sub = FolderNode(name="sub", children=[child], collapsed=True)
        root = FolderNode(name="root", children=[sub])
        model = TreeModel(root=root)

        flat = model.flatten()
        assert len(flat) == 1
        assert flat[0] is sub

    def test_expanded_folder_shows_children(self) -> None:
        child = FileNode(path=Path("/root/sub/a.mkv"))
        sub = FolderNode(name="sub", children=[child], collapsed=False)
        root = FolderNode(name="root", children=[sub])
        model = TreeModel(root=root)

        flat = model.flatten()
        assert len(flat) == 2
        assert flat[0] is sub
        assert flat[1] is child

    def test_root_not_in_output(self) -> None:
        child = FileNode(path=Path("/root/a.mkv"))
        root = FolderNode(name="root", children=[child])
        model = TreeModel(root=root)

        flat = model.flatten()
        assert root not in flat
        assert flat == [child]

    def test_nested_expanded(self) -> None:
        f1 = FileNode(path=Path("/r/a/b/c.mkv"))
        inner = FolderNode(name="b", children=[f1], collapsed=False)
        outer = FolderNode(name="a", children=[inner], collapsed=False)
        root = FolderNode(name="r", children=[outer])
        model = TreeModel(root=root)

        flat = model.flatten()
        assert flat == [outer, inner, f1]

    def test_nested_inner_collapsed(self) -> None:
        f1 = FileNode(path=Path("/r/a/b/c.mkv"))
        inner = FolderNode(name="b", children=[f1], collapsed=True)
        outer = FolderNode(name="a", children=[inner], collapsed=False)
        root = FolderNode(name="r", children=[outer])
        model = TreeModel(root=root)

        flat = model.flatten()
        # inner appears but its children don't
        assert flat == [outer, inner]

    def test_empty_root(self) -> None:
        root = FolderNode(name="root")
        model = TreeModel(root=root)
        assert model.flatten() == []


# --- TreeModel toggles ---


class TestToggles:
    def test_toggle_staged(self) -> None:
        n = FileNode(path=Path("/a.mkv"))
        model = TreeModel(root=FolderNode(name="r", children=[n]))
        assert n.staged is False
        model.toggle_staged(n)
        assert n.staged is True
        model.toggle_staged(n)
        assert n.staged is False

    def test_toggle_ignored(self) -> None:
        n = FileNode(path=Path("/a.mkv"))
        model = TreeModel(root=FolderNode(name="r", children=[n]))
        assert n.ignored is False
        model.toggle_ignored(n)
        assert n.ignored is True
        model.toggle_ignored(n)
        assert n.ignored is False

    def test_toggle_collapsed(self) -> None:
        sub = FolderNode(name="sub", collapsed=True)
        model = TreeModel(root=FolderNode(name="r", children=[sub]))
        model.toggle_collapsed(sub)
        assert sub.collapsed is False
        model.toggle_collapsed(sub)
        assert sub.collapsed is True

    def test_toggle_staged_recursive_all_staged_unstages(self) -> None:
        f1 = FileNode(path=Path("/a.mkv"), staged=True)
        f2 = FileNode(path=Path("/b.mkv"), staged=True)
        sub = FolderNode(name="sub", children=[f1, f2])
        model = TreeModel(root=FolderNode(name="r", children=[sub]))

        model.toggle_staged_recursive(sub)
        assert f1.staged is False
        assert f2.staged is False

    def test_toggle_staged_recursive_mixed_stages_all(self) -> None:
        f1 = FileNode(path=Path("/a.mkv"), staged=True)
        f2 = FileNode(path=Path("/b.mkv"), staged=False)
        sub = FolderNode(name="sub", children=[f1, f2])
        model = TreeModel(root=FolderNode(name="r", children=[sub]))

        model.toggle_staged_recursive(sub)
        assert f1.staged is True
        assert f2.staged is True

    def test_toggle_staged_recursive_none_stages_all(self) -> None:
        f1 = FileNode(path=Path("/a.mkv"), staged=False)
        f2 = FileNode(path=Path("/b.mkv"), staged=False)
        sub = FolderNode(name="sub", children=[f1, f2])
        model = TreeModel(root=FolderNode(name="r", children=[sub]))

        model.toggle_staged_recursive(sub)
        assert f1.staged is True
        assert f2.staged is True

    def test_toggle_staged_recursive_nested(self) -> None:
        f1 = FileNode(path=Path("/a.mkv"), staged=False)
        f2 = FileNode(path=Path("/b.mkv"), staged=True)
        inner = FolderNode(name="inner", children=[f2])
        outer = FolderNode(name="outer", children=[f1, inner])
        model = TreeModel(root=FolderNode(name="r", children=[outer]))

        # Mixed -> stage all
        model.toggle_staged_recursive(outer)
        assert f1.staged is True
        assert f2.staged is True

        # All staged -> unstage all
        model.toggle_staged_recursive(outer)
        assert f1.staged is False
        assert f2.staged is False

    def test_toggle_staged_recursive_empty_folder(self) -> None:
        sub = FolderNode(name="empty")
        model = TreeModel(root=FolderNode(name="r", children=[sub]))
        # Should not raise
        model.toggle_staged_recursive(sub)


# --- TreeModel.all_files ---


class TestAllFiles:
    def test_all_files_depth_first(self) -> None:
        f1 = FileNode(path=Path("/r/a.mkv"))
        f2 = FileNode(path=Path("/r/sub/b.mkv"))
        f3 = FileNode(path=Path("/r/c.mkv"))
        sub = FolderNode(name="sub", children=[f2])
        root = FolderNode(name="r", children=[sub, f1, f3])
        model = TreeModel(root=root)

        files = model.all_files()
        assert files == [f2, f1, f3]

    def test_all_files_empty(self) -> None:
        model = TreeModel(root=FolderNode(name="r"))
        assert model.all_files() == []


# --- build_tree ---


class TestBuildTree:
    def test_flat_files(self, tmp_path: Path) -> None:
        files = [tmp_path / "b.mkv", tmp_path / "a.mkv"]
        model = build_tree(files, tmp_path)

        flat = model.all_files()
        assert len(flat) == 2
        # Alphabetically sorted
        assert flat[0].path == tmp_path / "a.mkv"
        assert flat[1].path == tmp_path / "b.mkv"

    def test_nested_directories(self, tmp_path: Path) -> None:
        files = [
            tmp_path / "movies" / "inception.mkv",
            tmp_path / "shows" / "s01" / "e01.mkv",
            tmp_path / "readme.txt",
        ]
        model = build_tree(files, tmp_path)

        # Root should have: movies/, shows/, readme.txt
        root = model.root
        assert len(root.children) == 3

        # Folders first, alphabetical, then files
        assert isinstance(root.children[0], FolderNode)
        assert root.children[0].name == "movies"
        assert isinstance(root.children[1], FolderNode)
        # shows/s01 merged because shows only contained s01
        assert root.children[1].name == "shows/s01"
        assert isinstance(root.children[2], FileNode)
        assert root.children[2].path == tmp_path / "readme.txt"

    def test_sorting_folders_first(self, tmp_path: Path) -> None:
        files = [
            tmp_path / "z_file.mkv",
            tmp_path / "a_dir" / "inner.mkv",
            tmp_path / "b_file.mkv",
            tmp_path / "m_dir" / "inner.mkv",
        ]
        model = build_tree(files, tmp_path)

        root = model.root
        names = [
            c.name if isinstance(c, FolderNode) else c.path.name
            for c in root.children
        ]
        assert names == ["a_dir", "m_dir", "b_file.mkv", "z_file.mkv"]

    def test_root_name(self, tmp_path: Path) -> None:
        files = [tmp_path / "a.mkv"]
        model = build_tree(files, tmp_path)
        assert model.root.name == tmp_path.name

    def test_folders_default_expanded(self, tmp_path: Path) -> None:
        files = [tmp_path / "sub" / "a.mkv"]
        model = build_tree(files, tmp_path)
        sub = model.root.children[0]
        assert isinstance(sub, FolderNode)
        assert sub.collapsed is False

    def test_file_defaults(self, tmp_path: Path) -> None:
        files = [tmp_path / "a.mkv"]
        model = build_tree(files, tmp_path)
        f = model.root.children[0]
        assert isinstance(f, FileNode)
        assert f.staged is False
        assert f.ignored is False
        assert f.result == {}
        assert f.sources == []

    def test_empty_file_list(self, tmp_path: Path) -> None:
        model = build_tree([], tmp_path)
        assert model.root.children == []
        assert model.all_files() == []


# --- compute_shared_fields ---


class TestComputeSharedFields:
    def test_all_same(self) -> None:
        nodes = [
            FileNode(path=Path("/a.mkv"), result={"title": "Foo", "year": 2020}),
            FileNode(path=Path("/b.mkv"), result={"title": "Foo", "year": 2020}),
        ]
        shared = compute_shared_fields(nodes)
        assert shared == {"title": "Foo", "year": 2020}

    def test_differing_values(self) -> None:
        nodes = [
            FileNode(path=Path("/a.mkv"), result={"title": "Foo", "year": 2020}),
            FileNode(path=Path("/b.mkv"), result={"title": "Bar", "year": 2020}),
        ]
        shared = compute_shared_fields(nodes)
        assert shared["title"] == "(2 values)"
        assert shared["year"] == 2020

    def test_field_in_some_not_all(self) -> None:
        nodes = [
            FileNode(path=Path("/a.mkv"), result={"title": "Foo", "season": 1}),
            FileNode(path=Path("/b.mkv"), result={"title": "Foo"}),
        ]
        shared = compute_shared_fields(nodes)
        assert shared["title"] == "Foo"
        # season only in one node, single value, so it's shared
        assert shared["season"] == 1

    def test_field_in_some_with_different_values(self) -> None:
        nodes = [
            FileNode(path=Path("/a.mkv"), result={"title": "Foo", "season": 1}),
            FileNode(path=Path("/b.mkv"), result={"title": "Foo", "season": 2}),
            FileNode(path=Path("/c.mkv"), result={"title": "Foo"}),
        ]
        shared = compute_shared_fields(nodes)
        assert shared["title"] == "Foo"
        assert shared["season"] == "(2 values)"

    def test_empty_list(self) -> None:
        assert compute_shared_fields([]) == {}

    def test_single_node(self) -> None:
        nodes = [FileNode(path=Path("/a.mkv"), result={"title": "X", "year": 2021})]
        shared = compute_shared_fields(nodes)
        assert shared == {"title": "X", "year": 2021}

    def test_all_empty_results(self) -> None:
        nodes = [
            FileNode(path=Path("/a.mkv")),
            FileNode(path=Path("/b.mkv")),
        ]
        assert compute_shared_fields(nodes) == {}
