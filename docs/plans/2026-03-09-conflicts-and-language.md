# Conflict Resolution and TMDB Language Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Detect and auto-resolve file destination conflicts before committing, improve error messages, and add TMDB language support for localized metadata.

**Architecture:** New `tapes/conflicts.py` module handles all conflict detection and resolution logic (pure functions, no UI). CommitView gains a conflict report section. TMDB language threads through config -> pipeline -> tmdb API calls. Similarity scoring compares against both original and localized titles.

**Tech Stack:** Python 3.11+, pytest, textual, httpx, rapidfuzz, pydantic-settings

---

### Task 1: Conflict Detection Module -- Core Types and Duplicate Detection

**Files:**
- Create: `tapes/conflicts.py`
- Create: `tests/test_conflicts.py`

**Step 1: Write failing tests for duplicate detection**

```python
"""Tests for tapes.conflicts."""

from __future__ import annotations

from pathlib import Path

from tapes.conflicts import detect_conflicts, ConflictReport, ResolvedConflict, Problem
from tapes.tree_model import FileNode


class TestDuplicateDetection:
    def test_no_conflicts(self) -> None:
        pairs = [
            (FileNode(path=Path("/a.mkv"), result={"title": "A"}), Path("/lib/A.mkv")),
            (FileNode(path=Path("/b.mkv"), result={"title": "B"}), Path("/lib/B.mkv")),
        ]
        report = detect_conflicts(pairs)
        assert report.resolved == []
        assert report.problems == []
        assert len(report.valid_pairs) == 2

    def test_same_dest_same_size_unstages_lesser(self, tmp_path: Path) -> None:
        """Same destination, same file size -> unstage the one with fewer result fields."""
        src_a = tmp_path / "a.mkv"
        src_b = tmp_path / "b.mkv"
        src_a.write_bytes(b"x" * 100)
        src_b.write_bytes(b"x" * 100)

        node_a = FileNode(path=src_a, result={"title": "X", "year": 2020}, staged=True)
        node_b = FileNode(path=src_b, result={"title": "X"}, staged=True)
        dest = Path("/lib/X.mkv")
        pairs = [(node_a, dest), (node_b, dest)]

        report = detect_conflicts(pairs)
        assert len(report.resolved) == 1
        assert "duplicate" in report.resolved[0].description.lower()
        assert node_b.staged is False  # lesser metadata unstaged
        assert len(report.valid_pairs) == 1
        assert report.valid_pairs[0] == (node_a, dest)

    def test_same_dest_same_size_keeps_more_metadata(self, tmp_path: Path) -> None:
        """When both have same field count, keeps first alphabetically by source."""
        src_a = tmp_path / "a.mkv"
        src_b = tmp_path / "b.mkv"
        src_a.write_bytes(b"x" * 100)
        src_b.write_bytes(b"x" * 100)

        node_a = FileNode(path=src_a, result={"title": "X"}, staged=True)
        node_b = FileNode(path=src_b, result={"title": "X"}, staged=True)
        dest = Path("/lib/X.mkv")
        pairs = [(node_a, dest), (node_b, dest)]

        report = detect_conflicts(pairs)
        assert len(report.resolved) == 1
        assert len(report.valid_pairs) == 1

    def test_same_dest_different_size_disambiguates(self, tmp_path: Path) -> None:
        """Same destination, different size -> disambiguate with suffix."""
        src_a = tmp_path / "a.mkv"
        src_b = tmp_path / "b.mkv"
        src_a.write_bytes(b"x" * 100)
        src_b.write_bytes(b"x" * 200)

        node_a = FileNode(path=src_a, result={"title": "X"}, staged=True)
        node_b = FileNode(path=src_b, result={"title": "X"}, staged=True)
        dest = Path("/lib/X.mkv")
        pairs = [(node_a, dest), (node_b, dest)]

        report = detect_conflicts(pairs)
        assert len(report.resolved) == 1
        assert "disambiguated" in report.resolved[0].description.lower()
        assert len(report.valid_pairs) == 2
        dests = [d for _, d in report.valid_pairs]
        assert Path("/lib/X.mkv") in dests
        assert Path("/lib/X-2.mkv") in dests

    def test_three_way_conflict_mixed(self, tmp_path: Path) -> None:
        """Three files same dest: two same size (dup), one different (disambiguate)."""
        src_a = tmp_path / "a.mkv"
        src_b = tmp_path / "b.mkv"
        src_c = tmp_path / "c.mkv"
        src_a.write_bytes(b"x" * 100)
        src_b.write_bytes(b"x" * 100)
        src_c.write_bytes(b"x" * 200)

        node_a = FileNode(path=src_a, result={"title": "X", "year": 2020}, staged=True)
        node_b = FileNode(path=src_b, result={"title": "X"}, staged=True)
        node_c = FileNode(path=src_c, result={"title": "X"}, staged=True)
        dest = Path("/lib/X.mkv")
        pairs = [(node_a, dest), (node_b, dest), (node_c, dest)]

        report = detect_conflicts(pairs)
        assert len(report.valid_pairs) == 2  # a + c (b unstaged as dup)

    def test_preserves_full_extension(self, tmp_path: Path) -> None:
        """Disambiguating suffix goes before the full extension."""
        src_a = tmp_path / "a.en.srt"
        src_b = tmp_path / "b.en.srt"
        src_a.write_bytes(b"x" * 100)
        src_b.write_bytes(b"x" * 200)

        node_a = FileNode(path=src_a, result={"title": "X"}, staged=True)
        node_b = FileNode(path=src_b, result={"title": "X"}, staged=True)
        dest = Path("/lib/X.en.srt")
        pairs = [(node_a, dest), (node_b, dest)]

        report = detect_conflicts(pairs)
        dests = {d.name for _, d in report.valid_pairs}
        assert "X.en.srt" in dests
        assert "X-2.en.srt" in dests
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_conflicts.py -v`
Expected: FAIL (module not found)

**Step 3: Implement conflict detection**

Create `tapes/conflicts.py`:

```python
"""Conflict detection and auto-resolution for file destinations."""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from tapes.tree_model import FileNode


@dataclass
class ResolvedConflict:
    """A conflict that was auto-resolved."""

    description: str


@dataclass
class Problem:
    """A conflict that cannot be auto-resolved."""

    description: str
    skipped_nodes: list[FileNode] = field(default_factory=list)


@dataclass
class ConflictReport:
    """Result of conflict detection."""

    resolved: list[ResolvedConflict] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)
    valid_pairs: list[tuple[FileNode, Path]] = field(default_factory=list)

    @property
    def skipped_count(self) -> int:
        return sum(len(p.skipped_nodes) for p in self.problems)


def detect_conflicts(
    pairs: list[tuple[FileNode, Path]],
    *,
    duplicate_resolution: str = "auto",
    disambiguation: str = "auto",
) -> ConflictReport:
    """Detect and resolve destination conflicts.

    Args:
        pairs: List of (FileNode, destination_path) tuples.
        duplicate_resolution: "auto", "warn", or "off".
        disambiguation: "auto", "warn", or "off".

    Returns:
        ConflictReport with resolved conflicts, problems, and valid pairs.
    """
    report = ConflictReport()

    # Phase 1: Check writability of destination directories
    _check_writability(pairs, report)

    # Phase 2: Group by destination, detect duplicates and collisions
    remaining = [(n, d) for n, d in pairs if n.staged]
    _resolve_destination_conflicts(remaining, report, duplicate_resolution, disambiguation)

    # Phase 3: Check for pre-existing files at destination
    _check_existing_files(report, disambiguation)

    return report


def _check_writability(
    pairs: list[tuple[FileNode, Path]],
    report: ConflictReport,
) -> None:
    """Check that destination directories are writable."""
    # Collect unique destination dirs and their associated nodes
    dir_nodes: dict[Path, list[FileNode]] = defaultdict(list)
    for node, dest in pairs:
        dir_nodes[dest.parent].append(node)

    checked: dict[Path, bool] = {}
    for dest_dir, nodes in dir_nodes.items():
        writable = _is_writable(dest_dir, checked)
        if not writable:
            report.problems.append(
                Problem(
                    description=f"Cannot write to {dest_dir} -- check permissions",
                    skipped_nodes=list(nodes),
                )
            )
            for n in nodes:
                n.staged = False


def _is_writable(dest_dir: Path, cache: dict[Path, bool]) -> bool:
    """Check if dest_dir (or its nearest existing ancestor) is writable."""
    if dest_dir in cache:
        return cache[dest_dir]

    check = dest_dir
    while not check.exists():
        parent = check.parent
        if parent == check:
            break
        check = parent

    result = os.access(check, os.W_OK)
    cache[dest_dir] = result
    return result


def _resolve_destination_conflicts(
    pairs: list[tuple[FileNode, Path]],
    report: ConflictReport,
    duplicate_resolution: str,
    disambiguation: str,
) -> None:
    """Resolve conflicts where multiple files map to the same destination."""
    # Group by destination
    groups: dict[Path, list[tuple[FileNode, Path]]] = defaultdict(list)
    for node, dest in pairs:
        groups[dest].append((node, dest))

    for dest, group in groups.items():
        if len(group) == 1:
            report.valid_pairs.append(group[0])
            continue

        # Split into size-based buckets
        size_buckets: dict[int, list[tuple[FileNode, Path]]] = defaultdict(list)
        for node, d in group:
            try:
                size = node.path.stat().st_size
            except OSError:
                size = -1  # treat stat failure as unique
            size_buckets[size].append((node, d))

        # Handle same-size groups (duplicates)
        survivors: list[tuple[FileNode, Path]] = []
        for size, bucket in size_buckets.items():
            if len(bucket) == 1:
                survivors.append(bucket[0])
                continue

            if duplicate_resolution == "off":
                survivors.extend(bucket)
                continue

            # Keep the node with most metadata fields; tie-break by path
            bucket.sort(key=lambda x: (-len(x[0].result), str(x[0].path)))
            keeper = bucket[0]
            survivors.append(keeper)

            for node, _ in bucket[1:]:
                if duplicate_resolution == "auto":
                    node.staged = False
                    report.resolved.append(
                        ResolvedConflict(
                            description=f"Unstaged duplicate: {node.path.name} (same as {keeper[0].path.name})",
                        )
                    )
                else:  # warn
                    report.problems.append(
                        Problem(
                            description=f"Duplicate: {node.path.name} and {keeper[0].path.name} map to {dest.name}",
                            skipped_nodes=[node],
                        )
                    )
                    node.staged = False

        # Handle remaining survivors that still share the same dest
        if len(survivors) <= 1:
            report.valid_pairs.extend(survivors)
            continue

        if disambiguation == "off":
            report.valid_pairs.extend(survivors)
            continue

        # Disambiguate: first file keeps original name, rest get -2, -3, etc.
        survivors.sort(key=lambda x: str(x[0].path))

        if disambiguation == "auto":
            report.valid_pairs.append(survivors[0])
            for i, (node, d) in enumerate(survivors[1:], start=2):
                new_dest = _disambiguate_path(d, i)
                report.valid_pairs.append((node, new_dest))
                report.resolved.append(
                    ResolvedConflict(
                        description=f"Disambiguated: {node.path.name} -> {new_dest.name}",
                    )
                )
        else:  # warn
            report.valid_pairs.append(survivors[0])
            for node, d in survivors[1:]:
                report.problems.append(
                    Problem(
                        description=f"Conflict: {node.path.name} maps to same destination as {survivors[0][0].path.name}",
                        skipped_nodes=[node],
                    )
                )
                node.staged = False


def _check_existing_files(
    report: ConflictReport,
    disambiguation: str,
) -> None:
    """Check for pre-existing files at destinations and disambiguate."""
    if disambiguation == "off":
        return

    new_valid: list[tuple[FileNode, Path]] = []
    for node, dest in report.valid_pairs:
        if not dest.exists():
            new_valid.append((node, dest))
            continue

        if disambiguation == "auto":
            # Find a non-conflicting name
            counter = 2
            new_dest = _disambiguate_path(dest, counter)
            while new_dest.exists():
                counter += 1
                new_dest = _disambiguate_path(dest, counter)
            new_valid.append((node, new_dest))
            report.resolved.append(
                ResolvedConflict(
                    description=f"Disambiguated: {dest.name} already exists -> {new_dest.name}",
                )
            )
        else:  # warn
            report.problems.append(
                Problem(
                    description=f"Already exists: {dest}",
                    skipped_nodes=[node],
                )
            )
            node.staged = False

    report.valid_pairs = new_valid


def _disambiguate_path(dest: Path, counter: int) -> Path:
    """Append a disambiguating suffix before the extension.

    Handles multi-part extensions like .en.srt: suffix goes before the
    full extension chain.
    """
    from tapes.ui.tree_render import full_extension

    ext = full_extension(dest)
    if ext:
        dot_ext = "." + ext
        if dest.name.endswith(dot_ext):
            stem = dest.name[: -len(dot_ext)]
            return dest.with_name(f"{stem}-{counter}{dot_ext}")
    # Fallback: use pathlib's stem/suffix
    return dest.with_name(f"{dest.stem}-{counter}{dest.suffix}")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_conflicts.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tapes/conflicts.py tests/test_conflicts.py
git commit -m "feat: add conflict detection and auto-resolution module"
```

---

### Task 2: Writability and Existing-File Checks

**Files:**
- Modify: `tests/test_conflicts.py`

**Step 1: Write failing tests for writability and existing-file checks**

Add to `tests/test_conflicts.py`:

```python
class TestWritabilityCheck:
    def test_writable_destination_passes(self, tmp_path: Path) -> None:
        src = tmp_path / "a.mkv"
        src.write_bytes(b"x" * 100)
        dest = tmp_path / "lib" / "A.mkv"

        node = FileNode(path=src, result={"title": "A"}, staged=True)
        report = detect_conflicts([(node, dest)])
        assert report.problems == []
        assert len(report.valid_pairs) == 1

    def test_unwritable_destination_reported(self, tmp_path: Path) -> None:
        src = tmp_path / "a.mkv"
        src.write_bytes(b"x" * 100)
        unwritable = tmp_path / "readonly"
        unwritable.mkdir()
        unwritable.chmod(0o444)

        dest = unwritable / "A.mkv"
        node = FileNode(path=src, result={"title": "A"}, staged=True)
        report = detect_conflicts([(node, dest)])

        assert len(report.problems) == 1
        assert "cannot write" in report.problems[0].description.lower()
        assert node.staged is False

        # Cleanup
        unwritable.chmod(0o755)

    def test_skipped_count(self, tmp_path: Path) -> None:
        src_a = tmp_path / "a.mkv"
        src_b = tmp_path / "b.mkv"
        src_a.write_bytes(b"x" * 100)
        src_b.write_bytes(b"x" * 100)
        unwritable = tmp_path / "readonly"
        unwritable.mkdir()
        unwritable.chmod(0o444)

        node_a = FileNode(path=src_a, result={"title": "A"}, staged=True)
        node_b = FileNode(path=src_b, result={"title": "B"}, staged=True)
        report = detect_conflicts([
            (node_a, unwritable / "A.mkv"),
            (node_b, unwritable / "B.mkv"),
        ])
        assert report.skipped_count == 2

        unwritable.chmod(0o755)


class TestExistingFileCheck:
    def test_existing_file_disambiguated(self, tmp_path: Path) -> None:
        src = tmp_path / "a.mkv"
        src.write_bytes(b"x" * 100)
        dest = tmp_path / "lib" / "A.mkv"
        dest.parent.mkdir(parents=True)
        dest.write_bytes(b"existing")

        node = FileNode(path=src, result={"title": "A"}, staged=True)
        report = detect_conflicts([(node, dest)])
        assert len(report.resolved) == 1
        assert "already exists" in report.resolved[0].description.lower()
        assert report.valid_pairs[0][1].name == "A-2.mkv"

    def test_existing_file_warn_mode(self, tmp_path: Path) -> None:
        src = tmp_path / "a.mkv"
        src.write_bytes(b"x" * 100)
        dest = tmp_path / "lib" / "A.mkv"
        dest.parent.mkdir(parents=True)
        dest.write_bytes(b"existing")

        node = FileNode(path=src, result={"title": "A"}, staged=True)
        report = detect_conflicts([(node, dest)], disambiguation="warn")
        assert len(report.problems) == 1
        assert node.staged is False


class TestConfigModes:
    def test_duplicate_off_skips_check(self, tmp_path: Path) -> None:
        src_a = tmp_path / "a.mkv"
        src_b = tmp_path / "b.mkv"
        src_a.write_bytes(b"x" * 100)
        src_b.write_bytes(b"x" * 100)

        node_a = FileNode(path=src_a, result={"title": "X"}, staged=True)
        node_b = FileNode(path=src_b, result={"title": "X"}, staged=True)
        dest = Path("/lib/X.mkv")
        pairs = [(node_a, dest), (node_b, dest)]

        report = detect_conflicts(pairs, duplicate_resolution="off")
        assert report.resolved == []
        assert node_a.staged is True
        assert node_b.staged is True

    def test_disambiguation_off_skips_check(self, tmp_path: Path) -> None:
        src_a = tmp_path / "a.mkv"
        src_b = tmp_path / "b.mkv"
        src_a.write_bytes(b"x" * 100)
        src_b.write_bytes(b"x" * 200)

        node_a = FileNode(path=src_a, result={"title": "X"}, staged=True)
        node_b = FileNode(path=src_b, result={"title": "X"}, staged=True)
        dest = Path("/lib/X.mkv")
        pairs = [(node_a, dest), (node_b, dest)]

        report = detect_conflicts(pairs, disambiguation="off")
        # Both go through, no resolution
        assert report.resolved == []
        assert len(report.valid_pairs) == 2
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_conflicts.py -v`
Expected: PASS (implementation from Task 1 covers these)

**Step 3: Commit**

```bash
git add tests/test_conflicts.py
git commit -m "test: add writability, existing-file, and config-mode conflict tests"
```

---

### Task 3: Config Fields for Conflict Resolution

**Files:**
- Modify: `tapes/config.py:25-30` (MetadataConfig)
- Modify: `tapes/cli.py:28-44` (_build_overrides mapping)
- Modify: `tapes/cli.py:87-140` (import_cmd flags)
- Modify: `config.example.yaml`
- Modify: `tests/test_config.py` (if exists)

**Step 1: Write failing test**

Add to tests (create `tests/test_config_conflicts.py` if needed, or add to existing):

```python
"""Tests for conflict resolution config fields."""

from tapes.config import TapesConfig


class TestConflictConfig:
    def test_defaults(self) -> None:
        cfg = TapesConfig()
        assert cfg.metadata.duplicate_resolution == "auto"
        assert cfg.metadata.disambiguation == "auto"

    def test_override(self) -> None:
        cfg = TapesConfig(metadata={"duplicate_resolution": "warn", "disambiguation": "off"})
        assert cfg.metadata.duplicate_resolution == "warn"
        assert cfg.metadata.disambiguation == "off"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config_conflicts.py -v`
Expected: FAIL (fields don't exist)

**Step 3: Add config fields**

In `tapes/config.py`, add to `MetadataConfig` (after line 30):

```python
    duplicate_resolution: Literal["auto", "warn", "off"] = "auto"
    disambiguation: Literal["auto", "warn", "off"] = "auto"
    language: str = ""
```

Update the `Literal` import at line 8:
```python
from typing import Any, Literal
```
(Already imported -- just verify.)

**Step 4: Add CLI flags**

In `tapes/cli.py`, add to the `_build_overrides` mapping (after `"max_results"` line):

```python
        "duplicate_resolution": ("metadata", "duplicate_resolution"),
        "disambiguation": ("metadata", "disambiguation"),
        "language": ("metadata", "language"),
```

Add CLI flags to `import_cmd` in the Metadata section (after `max_results` parameter):

```python
    duplicate_resolution: str | None = typer.Option(
        None, "--duplicate-resolution", help="Duplicate handling: auto, warn, off", rich_help_panel="Metadata"
    ),
    disambiguation: str | None = typer.Option(
        None, "--disambiguation", help="Disambiguation: auto, warn, off", rich_help_panel="Metadata"
    ),
    language: str | None = typer.Option(
        None, "--language", help="TMDB language code (e.g. de, fr, en-US)", rich_help_panel="Metadata"
    ),
```

Add to the `_build_overrides` call in `import_cmd`:

```python
        duplicate_resolution=duplicate_resolution,
        disambiguation=disambiguation,
        language=language,
```

**Step 5: Update config.example.yaml**

Add under the metadata section:

```yaml
  # Conflict handling when multiple files map to the same destination.
  # duplicate_resolution: auto    # auto (unstage lesser), warn, off
  # disambiguation: auto          # auto (add -2 suffix), warn, off

  # TMDB response language (ISO 639-1, e.g. en, de, fr, or en-US, de-DE).
  # Empty = TMDB default. Affects titles and metadata, not search matching.
  # language: ""
```

**Step 6: Run tests**

Run: `uv run pytest tests/test_config_conflicts.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add tapes/config.py tapes/cli.py config.example.yaml tests/test_config_conflicts.py
git commit -m "feat: add conflict resolution and language config fields"
```

---

### Task 4: Wire Conflict Detection into Commit Flow

**Files:**
- Modify: `tapes/ui/tree_app.py:266-278` (_show_commit)
- Modify: `tapes/ui/tree_app.py:386-405` (_compute_file_pairs)
- Modify: `tapes/ui/tree_app.py:491-516` (_do_commit)
- Modify: `tapes/ui/commit_view.py`

**Step 1: Update _compute_file_pairs to return FileNode pairs**

Change `_compute_file_pairs` to return `list[tuple[FileNode, Path]]` instead of `list[tuple[Path, Path]]` so conflict detection can access the nodes.

In `tapes/ui/tree_app.py`, modify `_compute_file_pairs`:

```python
    def _compute_file_pairs(self, staged: list[FileNode]) -> list[tuple[FileNode, Path]]:
        """Compute (node, destination) pairs for staged files."""
        from tapes.ui.tree_render import compute_dest, select_template

        cfg = self.config
        pairs: list[tuple[FileNode, Path]] = []
        for node in staged:
            tmpl = select_template(node, self.movie_template, self.tv_template)
            media_type = node.result.get(MEDIA_TYPE)
            if media_type == MEDIA_TYPE_EPISODE and cfg.library.tv:
                library_root = Path(cfg.library.tv)
            elif cfg.library.movies:
                library_root = Path(cfg.library.movies)
            else:
                library_root = Path()
            dest_rel = compute_dest(node, tmpl)
            if dest_rel is not None:
                pairs.append((node, library_root / dest_rel))
        return pairs
```

**Step 2: Update _show_commit to run conflict detection**

```python
    def _show_commit(self) -> None:
        """Show the commit confirmation view with conflict report."""
        from tapes.conflicts import detect_conflicts

        staged = [f for f in self.model.all_files() if f.staged]
        node_pairs = self._compute_file_pairs(staged)

        report = detect_conflicts(
            node_pairs,
            duplicate_resolution=self.config.metadata.duplicate_resolution,
            disambiguation=self.config.metadata.disambiguation,
        )

        self._mode = AppMode.COMMIT
        bar = self.query_one(BottomBar)
        cv = self.query_one(CommitView)

        # Recollect staged (conflict detection may have unstaged some)
        remaining_staged = [n for n, _ in report.valid_pairs]
        cv._files = remaining_staged
        cv._categories = categorize_staged(remaining_staged)
        cv.operation = bar.operation
        cv.movies_path = self.config.library.movies
        cv.tv_path = self.config.library.tv
        cv.conflict_report = report
        cv.styles.height = cv.computed_height
        cv.styles.display = "block"
        self.query_one(TreeView).add_class("dimmed")
        bar.styles.display = "none"
        cv.focus()
```

**Step 3: Update _do_commit to use valid_pairs from report**

```python
    def _do_commit(self, operation: str) -> None:
        """Execute the commit: process staged files in a worker thread."""
        cv = self.query_one(CommitView)
        report = cv.conflict_report
        if report is None:
            return

        # Convert valid_pairs to (Path, Path) for file_ops
        pairs = [(n.path, d) for n, d in report.valid_pairs]
        staged = [n for n, _ in report.valid_pairs]

        if not pairs:
            self.notify("No files to process")
            return

        # Validate: reject files with no library path (relative destinations).
        bad = [src for src, dest in pairs if not dest.is_absolute()]
        if bad:
            self.notify(
                f"{len(bad)} file(s) have no library path configured",
                severity="error",
            )
            return

        self._commit_cancelled = threading.Event()
        cv.progress_text = f"0/{len(pairs)} files ..."
        cv.styles.height = cv.computed_height
        self.run_worker(
            self._run_commit_worker(pairs, staged, operation),
            thread=True,
        )
```

**Step 4: Update CommitView to accept and display conflict report**

In `tapes/ui/commit_view.py`, add a `conflict_report` attribute and render conflicts:

Add import at top:
```python
from tapes.conflicts import ConflictReport
```

Add to `__init__`:
```python
        self.conflict_report: ConflictReport | None = None
```

Add to `_build_content` after the blank line following separator (before stats), insert conflict rendering:

```python
        # Conflict report (if any)
        if self.conflict_report:
            resolved = self.conflict_report.resolved
            problems = self.conflict_report.problems
            if resolved or problems:
                content.append(Text())
                if resolved:
                    n = len(resolved)
                    content.append(Text(f"  {n} conflict{'s' if n != 1 else ''} resolved:", style=MUTED))
                    for r in resolved:
                        line = Text()
                        line.append("    \u2713 ", style=STAGED_COLOR)
                        line.append(r.description, style=MUTED)
                        content.append(line)
                if problems:
                    if resolved:
                        content.append(Text())
                    n = len(problems)
                    content.append(Text(f"  {n} problem{'s' if n != 1 else ''}:", style=SOFT_RED))
                    for p in problems:
                        line = Text()
                        line.append("    \u2717 ", style=SOFT_RED)
                        line.append(p.description, style=SOFT_RED)
                        content.append(line)
                        if p.skipped_nodes:
                            skip_line = Text()
                            skip_line.append(f"       {len(p.skipped_nodes)} file(s) skipped", style=MUTED)
                            content.append(skip_line)
```

Update `computed_height` to account for conflict report lines.

Update the "enter to confirm" hint to show count when there are skipped files:

```python
        # When files are skipped, show count
        total_valid = len(self._files)
        if self.conflict_report and self.conflict_report.skipped_count > 0:
            bottom.append(f"enter to confirm {total_valid} files \u00b7 esc to cancel", style=f"italic {MUTED}")
        else:
            bottom.append("enter to confirm \u00b7 esc to cancel", style=f"italic {MUTED}")
```

Import colors from tree_render:
```python
from tapes.ui.tree_render import ACCENT, MUTED, STAGED_COLOR, SOFT_RED, render_separator
```

**Step 5: Run full test suite**

Run: `uv run pytest -v`
Expected: PASS

**Step 6: Commit**

```bash
git add tapes/ui/tree_app.py tapes/ui/commit_view.py
git commit -m "feat: wire conflict detection into commit flow with inline report"
```

---

### Task 5: CommitView Conflict Rendering Tests

**Files:**
- Modify: `tests/test_ui/test_commit_view.py`

**Step 1: Write tests for conflict rendering**

```python
from tapes.conflicts import ConflictReport, Problem, ResolvedConflict


class TestCommitViewConflicts:
    def test_no_conflicts_renders_normally(self) -> None:
        files = [FileNode(path=Path("/a.mkv"), result={"media_type": "movie"})]
        view = CommitView(files, "copy")
        view.conflict_report = ConflictReport(valid_pairs=[(files[0], Path("/lib/a.mkv"))])
        plain = render_plain(view)
        assert "conflict" not in plain.lower()

    def test_resolved_conflicts_shown(self) -> None:
        files = [FileNode(path=Path("/a.mkv"), result={"media_type": "movie"})]
        report = ConflictReport(
            resolved=[ResolvedConflict(description="Unstaged duplicate: b.mkv (same as a.mkv)")],
            valid_pairs=[(files[0], Path("/lib/a.mkv"))],
        )
        view = CommitView(files, "copy")
        view.conflict_report = report
        plain = render_plain(view)
        assert "1 conflict resolved" in plain
        assert "Unstaged duplicate" in plain

    def test_problems_shown(self) -> None:
        files = [FileNode(path=Path("/a.mkv"), result={"media_type": "movie"})]
        problem_node = FileNode(path=Path("/b.mkv"), result={})
        report = ConflictReport(
            problems=[Problem(description="Cannot write to /lib", skipped_nodes=[problem_node])],
            valid_pairs=[(files[0], Path("/lib/a.mkv"))],
        )
        view = CommitView(files, "copy")
        view.conflict_report = report
        plain = render_plain(view)
        assert "1 problem" in plain
        assert "Cannot write" in plain
        assert "skipped" in plain

    def test_confirm_shows_count_when_skipped(self) -> None:
        files = [FileNode(path=Path("/a.mkv"), result={"media_type": "movie"})]
        problem_node = FileNode(path=Path("/b.mkv"), result={})
        report = ConflictReport(
            problems=[Problem(description="test", skipped_nodes=[problem_node])],
            valid_pairs=[(files[0], Path("/lib/a.mkv"))],
        )
        view = CommitView(files, "copy")
        view.conflict_report = report
        plain = render_plain(view)
        assert "confirm 1 file" in plain
```

**Step 2: Run tests**

Run: `uv run pytest tests/test_ui/test_commit_view.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_ui/test_commit_view.py
git commit -m "test: add commit view conflict rendering tests"
```

---

### Task 6: Improve FileExistsError Messages

**Files:**
- Modify: `tapes/file_ops.py:158-160`
- Modify: `tests/test_file_ops.py`

**Step 1: Write failing test**

```python
class TestErrorMessages:
    def test_file_exists_error_message(self, tmp_path: Path) -> None:
        src = tmp_path / "a.mkv"
        src.write_text("data")
        dest = tmp_path / "out" / "a.mkv"
        dest.parent.mkdir()
        dest.write_text("existing")

        results = process_staged([(src, dest)], "copy")
        assert len(results) == 1
        assert "already exists" in results[0].lower()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_file_ops.py::TestErrorMessages -v`
Expected: FAIL (current message is "Error processing ...")

**Step 3: Fix error message**

In `tapes/file_ops.py`, change the generic except handler in `process_staged` (around line 158-160):

```python
        except OperationCancelled:
            break
        except FileExistsError:
            logger.warning("Destination already exists for %s", src)
            results.append(f"Error: {dest} already exists")
        except Exception:
            logger.exception("Error processing %s", src)
            results.append(f"Error processing {src}")
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_file_ops.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tapes/file_ops.py tests/test_file_ops.py
git commit -m "fix: show specific error message for FileExistsError"
```

---

### Task 7: TMDB Language Parameter

**Files:**
- Modify: `tapes/tmdb.py:88-151` (search_multi)
- Modify: `tapes/tmdb.py:154-181` (get_show)
- Modify: `tapes/tmdb.py:184-220` (get_season_episodes)
- Modify: `tests/test_tmdb.py`

**Step 1: Write failing tests**

Add to existing test file (or create `tests/test_tmdb_language.py`):

```python
"""Tests for TMDB language parameter support."""

from __future__ import annotations

import httpx
import respx

from tapes.tmdb import get_season_episodes, get_show, search_multi


class TestLanguageParam:
    @respx.mock
    def test_search_multi_passes_language(self) -> None:
        route = respx.get("https://api.themoviedb.org/3/search/multi").respond(
            json={"results": []}
        )
        search_multi("Inception", "tok", language="de")
        assert route.called
        assert route.calls[0].request.url.params["language"] == "de"

    @respx.mock
    def test_search_multi_omits_language_when_empty(self) -> None:
        route = respx.get("https://api.themoviedb.org/3/search/multi").respond(
            json={"results": []}
        )
        search_multi("Inception", "tok", language="")
        assert route.called
        assert "language" not in route.calls[0].request.url.params

    @respx.mock
    def test_search_multi_no_language_param_by_default(self) -> None:
        route = respx.get("https://api.themoviedb.org/3/search/multi").respond(
            json={"results": []}
        )
        search_multi("Inception", "tok")
        assert route.called
        assert "language" not in route.calls[0].request.url.params

    @respx.mock
    def test_get_show_passes_language(self) -> None:
        route = respx.get("https://api.themoviedb.org/3/tv/123").respond(
            json={"id": 123, "name": "Test", "seasons": []}
        )
        get_show(123, "tok", language="fr")
        assert route.called
        assert route.calls[0].request.url.params["language"] == "fr"

    @respx.mock
    def test_get_season_episodes_passes_language(self) -> None:
        route = respx.get("https://api.themoviedb.org/3/tv/123/season/1").respond(
            json={"episodes": []}
        )
        get_season_episodes(123, 1, "tok", language="de-DE")
        assert route.called
        assert route.calls[0].request.url.params["language"] == "de-DE"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tmdb_language.py -v`
Expected: FAIL (language parameter not accepted)

**Step 3: Add language parameter to TMDB functions**

In `tapes/tmdb.py`, update `search_multi` signature and params:

```python
def search_multi(
    query: str,
    token: str,
    year: int | None = None,
    *,
    language: str = "",
    client: httpx.Client | None = None,
    max_results: int = MAX_TMDB_RESULTS,
    max_retries: int = 3,
) -> list[dict]:
```

Add after `params["year"] = year`:
```python
    if language:
        params["language"] = language
```

Also store `original_title`/`original_name` in the returned dicts. In the movie branch:
```python
            results.append(
                {
                    TMDB_ID: item["id"],
                    TITLE: title,
                    "original_title": item.get("original_title", title),
                    YEAR: yr,
                    MEDIA_TYPE: MEDIA_TYPE_MOVIE,
                }
            )
```

In the TV branch:
```python
            results.append(
                {
                    TMDB_ID: item["id"],
                    TITLE: title,
                    "original_title": item.get("original_name", title),
                    YEAR: yr,
                    MEDIA_TYPE: MEDIA_TYPE_EPISODE,
                }
            )
```

Update `get_show`:

```python
def get_show(
    tmdb_id: int,
    token: str,
    *,
    language: str = "",
    client: httpx.Client | None = None,
    max_retries: int = 3,
) -> dict:
```

Add `params` dict:
```python
    params: dict = {}
    if language:
        params["language"] = language

    try:
        resp = _request("GET", f"/tv/{tmdb_id}", token, client=client, max_retries=max_retries, params=params)
```

Update `get_season_episodes`:

```python
def get_season_episodes(
    show_id: int,
    season_number: int,
    token: str,
    show_title: str = "",
    show_year: int | None = None,
    *,
    language: str = "",
    client: httpx.Client | None = None,
    max_retries: int = 3,
) -> list[dict]:
```

Add `params` dict:
```python
    params: dict = {}
    if language:
        params["language"] = language

    try:
        resp = _request("GET", f"/tv/{show_id}/season/{season_number}", token, client=client, max_retries=max_retries, params=params)
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_tmdb_language.py -v`
Expected: PASS

Also run existing TMDB tests:
Run: `uv run pytest tests/test_tmdb.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tapes/tmdb.py tests/test_tmdb_language.py
git commit -m "feat: add language parameter to TMDB API functions"
```

---

### Task 8: Similarity Scoring with Original Title

**Files:**
- Modify: `tapes/similarity.py:62-107` (compute_similarity)
- Modify: `tests/test_similarity.py`

**Step 1: Write failing test**

```python
class TestOriginalTitleScoring:
    def test_scores_against_original_title(self) -> None:
        """When localized title differs, scoring uses original_title."""
        query = {"title": "The Matrix", "year": 1999}
        result = {"title": "Matrix", "original_title": "The Matrix", "year": 1999}
        score = compute_similarity(query, result)
        # Should match well against original_title
        assert score > 0.8

    def test_scores_against_localized_title_when_better(self) -> None:
        """When filename is in the target language, localized title scores better."""
        query = {"title": "Die Matrix", "year": 1999}
        result = {"title": "Die Matrix", "original_title": "The Matrix", "year": 1999}
        score = compute_similarity(query, result)
        assert score > 0.8

    def test_takes_max_of_both(self) -> None:
        """Score is max of original and localized."""
        query = {"title": "The Matrix", "year": 1999}
        result_same = {"title": "The Matrix", "year": 1999}
        result_translated = {"title": "Matrix", "original_title": "The Matrix", "year": 1999}
        score_same = compute_similarity(query, result_same)
        score_translated = compute_similarity(query, result_translated)
        # Both should be high because original_title matches
        assert abs(score_same - score_translated) < 0.1

    def test_no_original_title_uses_title_only(self) -> None:
        """When no original_title, behaves as before."""
        query = {"title": "Inception", "year": 2010}
        result = {"title": "Inception", "year": 2010}
        score = compute_similarity(query, result)
        assert score > 0.9
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_similarity.py::TestOriginalTitleScoring -v`
Expected: FAIL (original_title not considered)

**Step 3: Update compute_similarity**

In `tapes/similarity.py`, modify `compute_similarity` (around line 80-85):

```python
    title_score = _string_similarity(str(q_title), str(r_title))

    # Also score against original_title if present, take the max
    r_original = result.get("original_title")
    if r_original and r_original != r_title:
        original_score = _string_similarity(str(q_title), str(r_original))
        title_score = max(title_score, original_score)
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_similarity.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tapes/similarity.py tests/test_similarity.py
git commit -m "feat: score similarity against both localized and original titles"
```

---

### Task 9: Thread Language Through Pipeline

**Files:**
- Modify: `tapes/pipeline.py` (all functions that call tmdb)
- Modify: `tapes/ui/tree_app.py` (pass language to pipeline)
- Modify: `tests/test_pipeline.py`

**Step 1: Add language parameter to pipeline functions**

Add `language: str = ""` parameter to: `run_tmdb_pass`, `run_auto_pipeline`, `refresh_tmdb_source`, `refresh_tmdb_batch`, `_query_tmdb_for_node`, `_query_episodes`.

Thread it through to all `tmdb.search_multi`, `tmdb.get_show`, and `tmdb.get_season_episodes` calls.

In `run_tmdb_pass` (line 93-105), add `language: str = ""` to signature, pass to `_query_tmdb_for_node`:

```python
def run_tmdb_pass(
    model: TreeModel,
    token: str = "",
    confidence_threshold: float | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
    post_update: Callable[[Callable[[], None]], None] | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    tmdb_timeout: float = 10.0,
    tmdb_retries: int = 3,
    margin_threshold: float | None = None,
    min_margin: float | None = None,
    language: str = "",
) -> None:
```

In `query_one` closure, pass `language=language` to `_query_tmdb_for_node`.

Similarly update `run_auto_pipeline`, `refresh_tmdb_source`, `refresh_tmdb_batch`.

In `_query_tmdb_for_node`, add `language: str = ""` and pass to `tmdb.search_multi(..., language=language)` and to `_query_episodes(..., language=language)`.

In `_query_episodes`, add `language: str = ""` and pass to `tmdb.get_show(..., language=language)` and `tmdb.get_season_episodes(..., language=language)`.

**Step 2: Pass language from TreeApp**

In `tapes/ui/tree_app.py`, wherever pipeline functions are called, pass `language=self.config.metadata.language`:

In `_run_tmdb_worker` (line 192-223):
```python
        language = self.config.metadata.language
        # ... in worker():
            run_tmdb_pass(
                ...,
                language=language,
            )
```

In `_run_refresh_worker` (line 642-673):
```python
        language = self.config.metadata.language
        # ... in worker():
            refresh_tmdb_batch(
                ...,
                language=language,
            )
```

**Step 3: Write test**

```python
"""Tests for language parameter threading through pipeline."""

from unittest.mock import MagicMock, patch

from tapes.pipeline import _query_tmdb_for_node
from tapes.tree_model import FileNode
from pathlib import Path


class TestLanguageThreading:
    @patch("tapes.pipeline.tmdb")
    def test_language_passed_to_search(self, mock_tmdb: MagicMock) -> None:
        mock_tmdb.search_multi.return_value = []
        node = FileNode(path=Path("/a.mkv"), result={"title": "Test"})
        _query_tmdb_for_node(node, "tok", 0.85, language="de")
        mock_tmdb.search_multi.assert_called_once()
        call_kwargs = mock_tmdb.search_multi.call_args
        assert call_kwargs.kwargs.get("language") == "de" or call_kwargs[1].get("language") == "de"
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_pipeline_language.py -v`
Run: `uv run pytest -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tapes/pipeline.py tapes/ui/tree_app.py tests/test_pipeline_language.py
git commit -m "feat: thread TMDB language through pipeline and TUI"
```

---

### Task 10: Final Integration and Config Example

**Files:**
- Modify: `config.example.yaml` (verify language docs)

**Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS

**Step 2: Run ruff and ty**

Run: `uv tool run ruff check tapes/ tests/`
Run: `uv tool run ruff format tapes/ tests/`
Run: `uv tool run ty check`
Expected: Clean

**Step 3: Commit any remaining fixes**

```bash
git add -A
git commit -m "chore: final cleanup for conflict resolution and TMDB language"
```
