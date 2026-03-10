"""Tests for tapes.tree_model."""

from __future__ import annotations

from pathlib import Path

from tapes.tree_model import (
    Candidate,
    FileNode,
    FolderNode,
    TreeModel,
    build_tree,
    compute_shared_fields,
)

# --- Candidate ---


class TestCandidate:
    def test_creation(self) -> None:
        c = Candidate(name="from filename", metadata={"title": "Foo"}, score=0.8)
        assert c.name == "from filename"
        assert c.metadata == {"title": "Foo"}
        assert c.score == 0.8

    def test_defaults(self) -> None:
        c = Candidate(name="x")
        assert c.metadata == {}
        assert c.score == 0.0


# --- FileNode ---


class TestFileNode:
    def test_defaults(self) -> None:
        n = FileNode(path=Path("/a/b.mkv"))
        assert n.staged is False
        assert n.ignored is False
        assert n.metadata == {}
        assert n.candidates == []

    def test_with_values(self) -> None:
        cand = Candidate(name="tmdb", metadata={"title": "X"}, score=0.95)
        n = FileNode(
            path=Path("/a.mkv"),
            staged=True,
            ignored=True,
            metadata={"title": "X"},
            candidates=[cand],
        )
        assert n.staged is True
        assert n.ignored is True
        assert n.metadata["title"] == "X"
        assert len(n.candidates) == 1


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
        names = [c.name if isinstance(c, FolderNode) else c.path.name for c in root.children]
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
        assert f.metadata == {}
        assert f.candidates == []

    def test_empty_file_list(self, tmp_path: Path) -> None:
        model = build_tree([], tmp_path)
        assert model.root.children == []
        assert model.all_files() == []


# --- compute_shared_fields ---


class TestComputeSharedFields:
    def test_all_same(self) -> None:
        nodes = [
            FileNode(path=Path("/a.mkv"), metadata={"title": "Foo", "year": 2020}),
            FileNode(path=Path("/b.mkv"), metadata={"title": "Foo", "year": 2020}),
        ]
        shared = compute_shared_fields(nodes)
        assert shared == {"title": "Foo", "year": 2020}

    def test_differing_values(self) -> None:
        nodes = [
            FileNode(path=Path("/a.mkv"), metadata={"title": "Foo", "year": 2020}),
            FileNode(path=Path("/b.mkv"), metadata={"title": "Bar", "year": 2020}),
        ]
        shared = compute_shared_fields(nodes)
        assert shared["title"] == "(2 values)"
        assert shared["year"] == 2020

    def test_field_in_some_not_all(self) -> None:
        nodes = [
            FileNode(path=Path("/a.mkv"), metadata={"title": "Foo", "season": 1}),
            FileNode(path=Path("/b.mkv"), metadata={"title": "Foo"}),
        ]
        shared = compute_shared_fields(nodes)
        assert shared["title"] == "Foo"
        # season only in one node -- not truly shared
        assert shared["season"] == "(1 values)"

    def test_field_in_some_with_different_values(self) -> None:
        nodes = [
            FileNode(path=Path("/a.mkv"), metadata={"title": "Foo", "season": 1}),
            FileNode(path=Path("/b.mkv"), metadata={"title": "Foo", "season": 2}),
            FileNode(path=Path("/c.mkv"), metadata={"title": "Foo"}),
        ]
        shared = compute_shared_fields(nodes)
        assert shared["title"] == "Foo"
        assert shared["season"] == "(2 values)"

    def test_empty_list(self) -> None:
        assert compute_shared_fields([]) == {}

    def test_single_node(self) -> None:
        nodes = [FileNode(path=Path("/a.mkv"), metadata={"title": "X", "year": 2021})]
        shared = compute_shared_fields(nodes)
        assert shared == {"title": "X", "year": 2021}

    def test_all_empty_results(self) -> None:
        nodes = [
            FileNode(path=Path("/a.mkv")),
            FileNode(path=Path("/b.mkv")),
        ]
        assert compute_shared_fields(nodes) == {}


class TestRemoveNodes:
    def test_removes_file_from_root(self) -> None:
        f1 = FileNode(path=Path("/a.mkv"))
        f2 = FileNode(path=Path("/b.mkv"))
        model = TreeModel(root=FolderNode(name="root", children=[f1, f2]))
        model.remove_nodes([f1])
        assert model.all_files() == [f2]

    def test_removes_from_subfolder(self) -> None:
        f1 = FileNode(path=Path("/sub/a.mkv"))
        sub = FolderNode(name="sub", children=[f1])
        f2 = FileNode(path=Path("/b.mkv"))
        model = TreeModel(root=FolderNode(name="root", children=[sub, f2]))
        model.remove_nodes([f1])
        assert model.all_files() == [f2]

    def test_prunes_empty_folder(self) -> None:
        f1 = FileNode(path=Path("/sub/a.mkv"))
        sub = FolderNode(name="sub", children=[f1])
        model = TreeModel(root=FolderNode(name="root", children=[sub]))
        model.remove_nodes([f1])
        assert model.all_files() == []
        assert model.root.children == []

    def test_invalidates_cache(self) -> None:
        f1 = FileNode(path=Path("/a.mkv"))
        f2 = FileNode(path=Path("/b.mkv"))
        model = TreeModel(root=FolderNode(name="root", children=[f1, f2]))
        _ = model.all_files()  # populate cache
        model.remove_nodes([f1])
        assert model.all_files() == [f2]

    def test_remove_multiple(self) -> None:
        f1 = FileNode(path=Path("/a.mkv"))
        f2 = FileNode(path=Path("/b.mkv"))
        f3 = FileNode(path=Path("/c.mkv"))
        model = TreeModel(root=FolderNode(name="root", children=[f1, f2, f3]))
        model.remove_nodes([f1, f3])
        assert model.all_files() == [f2]


# --- Staging gate ---

MOVIE_TEMPLATE = "{title} ({year})/{title} ({year}).{ext}"
TV_TEMPLATE = "{title} ({year})/Season {season:02d}/{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"


class TestStagingGate:
    def test_toggle_staged_blocked_when_not_ready(self) -> None:
        """toggle_staged does nothing when can_stage returns False."""
        from tapes.fields import MEDIA_TYPE, TITLE
        from tapes.templates import can_fill_template

        node = FileNode(path=Path("movie.mkv"))
        node.metadata = {MEDIA_TYPE: "movie", TITLE: "Inception"}  # no year
        model = TreeModel(root=FolderNode(name="root", children=[node]))

        def can_stage(n: FileNode) -> bool:
            return can_fill_template(n, n.metadata, MOVIE_TEMPLATE, TV_TEMPLATE)

        model.toggle_staged(node, can_stage=can_stage)
        assert node.staged is False

    def test_toggle_staged_allowed_when_ready(self) -> None:
        """toggle_staged works when can_stage returns True."""
        from tapes.fields import MEDIA_TYPE, TITLE, YEAR
        from tapes.templates import can_fill_template

        node = FileNode(path=Path("movie.mkv"))
        node.metadata = {MEDIA_TYPE: "movie", TITLE: "Inception", YEAR: 2010}
        model = TreeModel(root=FolderNode(name="root", children=[node]))

        def can_stage(n: FileNode) -> bool:
            return can_fill_template(n, n.metadata, MOVIE_TEMPLATE, TV_TEMPLATE)

        model.toggle_staged(node, can_stage=can_stage)
        assert node.staged is True

    def test_toggle_staged_unstage_always_allowed(self) -> None:
        """Unstaging is always allowed regardless of can_stage."""
        from tapes.fields import MEDIA_TYPE, TITLE

        node = FileNode(path=Path("movie.mkv"))
        node.metadata = {MEDIA_TYPE: "movie", TITLE: "Inception"}  # incomplete
        node.staged = True  # force staged
        model = TreeModel(root=FolderNode(name="root", children=[node]))

        def can_stage(n: FileNode) -> bool:
            return False  # would block staging

        model.toggle_staged(node, can_stage=can_stage)
        assert node.staged is False  # unstaging still works

    def test_toggle_staged_recursive_skips_incomplete(self) -> None:
        """toggle_staged_recursive only stages files that pass can_stage."""
        from tapes.fields import MEDIA_TYPE, TITLE, YEAR
        from tapes.templates import can_fill_template

        complete = FileNode(path=Path("a.mkv"))
        complete.metadata = {MEDIA_TYPE: "movie", TITLE: "A", YEAR: 2020}
        incomplete = FileNode(path=Path("b.mkv"))
        incomplete.metadata = {MEDIA_TYPE: "movie", TITLE: "B"}  # no year
        folder = FolderNode(name="root", children=[complete, incomplete])
        model = TreeModel(root=folder)

        def can_stage(n: FileNode) -> bool:
            return can_fill_template(n, n.metadata, MOVIE_TEMPLATE, TV_TEMPLATE)

        model.toggle_staged_recursive(folder, can_stage=can_stage)
        assert complete.staged is True
        assert incomplete.staged is False
