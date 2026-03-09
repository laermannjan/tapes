# Multi-File TMDB Refresh Fix

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix multi-file TMDB refresh to correctly preserve per-file metadata, run asynchronously with deduplication, and provide progress feedback.

**Architecture:** Four independent fixes that together resolve a chain of failures: (1) ctrl+a no longer wipes per-file fields, (2) tmdb_id shortcut skips redundant show searches, (3) episode application respects confidence, (4) refresh runs in a worker thread with shared cache. Each fix is independently valuable.

**Tech Stack:** Python 3.11+, Textual (workers, `call_from_thread`), httpx, threading, pytest + respx for tests.

---

## Root Cause Chain

```
ctrl+a on show source -> season/episode popped from all nodes
  -> refresh queries same show for all (no dedup, all blocking main thread)
    -> episode scoring: 0.0 for all (no season/episode to match)
      -> same "best" episode unconditionally applied to all nodes
```

## Relevant Files

**Core:**
- `tapes/pipeline.py` -- refresh_tmdb_source, _query_tmdb_for_node, _query_episodes
- `tapes/ui/detail_view.py` -- apply_source_all_clear
- `tapes/ui/tree_app.py` -- action_refresh_query, worker pattern

**Tests:**
- `tests/test_ui/test_pipeline.py` -- all refresh and pipeline tests
- `tests/test_pipeline.py` -- TmdbCache tests

**Reference for patterns:**
- `tapes/ui/tree_app.py:179-210` -- existing `_run_tmdb_worker` pattern (cache, ThreadPoolExecutor, progress callback, post_update dispatch)
- `tapes/pipeline.py:93-168` -- existing `run_tmdb_pass` pattern

---

### Task 1: Fix `apply_source_all_clear` -- only set, don't pop

**Problem:** `detail_view.py:352-369` iterates all display fields and pops any field not present in the source. When accepting a show-level TMDB source (which has tmdb_id, title, year, media_type but NOT season, episode, episode_title), it wipes per-file metadata from all selected nodes.

**Fix:** Only set fields that are present in the source. Don't touch fields the source doesn't have.

**Files:**
- Modify: `tapes/ui/detail_view.py:352-369`
- Test: `tests/test_ui/test_pipeline.py` (add new test class)

**Step 1: Write failing tests**

Add to `tests/test_ui/test_pipeline.py`:

```python
class TestApplySourceAllClear:
    """Tests for DetailView.apply_source_all_clear preserving per-file fields."""

    def test_preserves_fields_not_in_source(self) -> None:
        """Accepting a show-level source should not wipe season/episode."""
        from tapes.ui.detail_view import DetailView

        node = FileNode(
            path=Path("/media/Breaking.Bad.S01E01.mkv"),
            result={
                "title": "breaking bad",
                "season": 1,
                "episode": 1,
                "media_type": "episode",
            },
            sources=[
                Source(
                    name="TMDB #1",
                    fields={"tmdb_id": 1396, "title": "Breaking Bad", "year": 2008, "media_type": "episode"},
                    confidence=0.7,
                ),
            ],
        )
        dv = DetailView(node, movie_template="{title}.{ext}", tv_template="{title}.{ext}")
        dv._size = (120, 40)  # fake size for field computation
        dv.fields = ["title", "year", "season", "episode", "media_type", "tmdb_id"]
        dv.source_index = 0
        dv.apply_source_all_clear()
        # Show-level fields applied
        assert node.result["tmdb_id"] == 1396
        assert node.result["title"] == "Breaking Bad"
        assert node.result["year"] == 2008
        # Per-file fields preserved (not popped)
        assert node.result["season"] == 1
        assert node.result["episode"] == 1

    def test_preserves_per_file_fields_multi_node(self) -> None:
        """Multi-node: each node keeps its own season/episode."""
        from tapes.ui.detail_view import DetailView

        node1 = FileNode(
            path=Path("/media/show.s01e01.mkv"),
            result={"title": "show", "season": 1, "episode": 1, "media_type": "episode"},
            sources=[
                Source(
                    name="TMDB #1",
                    fields={"tmdb_id": 100, "title": "Show", "year": 2020, "media_type": "episode"},
                    confidence=0.7,
                ),
            ],
        )
        node2 = FileNode(
            path=Path("/media/show.s02e05.mkv"),
            result={"title": "show", "season": 2, "episode": 5, "media_type": "episode"},
            sources=[],
        )
        dv = DetailView(node1, movie_template="{title}.{ext}", tv_template="{title}.{ext}")
        dv._size = (120, 40)
        dv.file_nodes = [node1, node2]
        dv.fields = ["title", "year", "season", "episode", "media_type", "tmdb_id"]
        dv.source_index = 0
        dv.apply_source_all_clear()
        # Show-level fields applied to both
        assert node1.result["tmdb_id"] == 100
        assert node2.result["tmdb_id"] == 100
        # Per-file season/episode preserved
        assert node1.result["season"] == 1
        assert node1.result["episode"] == 1
        assert node2.result["season"] == 2
        assert node2.result["episode"] == 5

    def test_sets_fields_present_in_source(self) -> None:
        """Fields present in the source should be set on all nodes."""
        from tapes.ui.detail_view import DetailView

        node = FileNode(
            path=Path("/media/test.mkv"),
            result={"title": "old title"},
            sources=[
                Source(
                    name="TMDB #1",
                    fields={"title": "New Title", "year": 2020},
                    confidence=0.9,
                ),
            ],
        )
        dv = DetailView(node, movie_template="{title}.{ext}", tv_template="{title}.{ext}")
        dv._size = (120, 40)
        dv.fields = ["title", "year"]
        dv.source_index = 0
        dv.apply_source_all_clear()
        assert node.result["title"] == "New Title"
        assert node.result["year"] == 2020
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ui/test_pipeline.py::TestApplySourceAllClear -v`
Expected: FAIL -- `test_preserves_fields_not_in_source` fails because season/episode are popped.

**Step 3: Implement fix**

In `tapes/ui/detail_view.py`, change `apply_source_all_clear` from:

```python
def apply_source_all_clear(self) -> None:
    """Handle ctrl+a: accept all fields from current source."""
    sources = self.node.sources
    if not sources:
        return
    src_idx = self.source_index
    if src_idx >= len(sources):
        return
    src = sources[src_idx]
    for field_name in self.fields:
        val = src.fields.get(field_name)
        if val is not None:
            for n in self.file_nodes:
                n.result[field_name] = val
        else:
            for n in self.file_nodes:
                n.result.pop(field_name, None)
    self.refresh()
```

To:

```python
def apply_source_all_clear(self) -> None:
    """Handle ctrl+a: accept all fields from current source.

    Only sets fields that are present in the source. Fields not in the
    source are left untouched, preserving per-file metadata like
    season/episode when accepting a show-level match.
    """
    sources = self.node.sources
    if not sources:
        return
    src_idx = self.source_index
    if src_idx >= len(sources):
        return
    src = sources[src_idx]
    for field_name in self.fields:
        val = src.fields.get(field_name)
        if val is not None:
            for n in self.file_nodes:
                n.result[field_name] = val
    self.refresh()
```

The only change: remove the `else` branch that pops fields not in the source.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ui/test_pipeline.py::TestApplySourceAllClear -v`
Expected: PASS

Also run all existing tests to verify no regressions:
Run: `uv run pytest tests/test_ui/test_pipeline.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add tapes/ui/detail_view.py tests/test_ui/test_pipeline.py
git commit -m "fix: preserve per-file fields when accepting source via ctrl+a

apply_source_all_clear no longer pops fields that aren't in the
source. This preserves season/episode/episode_title when accepting
a show-level TMDB match across multiple files."
```

---

### Task 2: Add tmdb_id shortcut to skip show search

**Problem:** `_query_tmdb_for_node` always calls `search_multi(title, year)` even when `node.result` already has a `tmdb_id` identifying the show. This wastes HTTP requests and is semantically wrong -- the show is already identified.

**Fix:** When `node.result` has `tmdb_id` and `media_type == "episode"`, skip `search_multi` and jump directly to `_query_episodes`. When `tmdb_id` is set and `media_type == "movie"`, skip entirely (movie fully identified).

**Files:**
- Modify: `tapes/pipeline.py:295-416` (`_query_tmdb_for_node`)
- Test: `tests/test_ui/test_pipeline.py`

**Step 1: Write failing tests**

Add to `tests/test_ui/test_pipeline.py`:

```python
class TestTmdbIdShortcut:
    """When tmdb_id is already set, skip show search and go to episodes."""

    def test_skips_search_when_tmdb_id_set_for_tv(self, mock_tmdb) -> None:
        """With tmdb_id + media_type=episode, skip search_multi, query episodes directly."""
        node = FileNode(
            path=Path("/media/Breaking.Bad.S01E02.mkv"),
            result={
                "title": "Breaking Bad",
                "year": 2008,
                "tmdb_id": 1396,
                "media_type": "episode",
                "season": 1,
                "episode": 2,
            },
            sources=[],
        )
        with patch("tapes.tmdb.search_multi", side_effect=_mock_search_multi) as mock_search:
            refresh_tmdb_source(node, token=TOKEN)
            mock_search.assert_not_called()
        # Should still have episode sources from direct episode query
        tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
        assert len(tmdb_sources) >= 1
        # Best episode should be S01E02
        assert node.result.get("episode") == 2
        assert node.result.get("episode_title") == "Cat's in the Bag..."

    def test_skips_search_when_tmdb_id_set_for_movie(self, mock_tmdb) -> None:
        """With tmdb_id + media_type=movie, skip entirely (movie fully identified)."""
        node = FileNode(
            path=Path("/media/Dune.mkv"),
            result={
                "title": "Dune",
                "year": 2021,
                "tmdb_id": 438631,
                "media_type": "movie",
            },
            sources=[],
        )
        with patch("tapes.tmdb.search_multi", side_effect=_mock_search_multi) as mock_search:
            refresh_tmdb_source(node, token=TOKEN)
            mock_search.assert_not_called()
        # No sources added (movie already identified)
        assert len(node.sources) == 0

    def test_normal_flow_without_tmdb_id(self, mock_tmdb) -> None:
        """Without tmdb_id, normal search_multi flow is used."""
        node = FileNode(
            path=Path("/media/Dune.mkv"),
            result={"title": "Dune", "year": 2021},
            sources=[],
        )
        with patch("tapes.tmdb.search_multi", side_effect=_mock_search_multi) as mock_search:
            refresh_tmdb_source(node, token=TOKEN)
            mock_search.assert_called_once()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ui/test_pipeline.py::TestTmdbIdShortcut -v`
Expected: FAIL -- `test_skips_search_when_tmdb_id_set_for_tv` fails because search_multi IS called.

**Step 3: Implement fix**

In `tapes/pipeline.py`, add the shortcut at the beginning of `_query_tmdb_for_node`, after the token/title checks:

```python
def _query_tmdb_for_node(
    node: FileNode,
    token: str,
    threshold: float,
    cache: _TmdbCache | None = None,
    client: httpx.Client | None = None,
    post_update: Callable[[Callable[[], None]], None] | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    max_retries: int = 3,
    margin_threshold: float | None = None,
    min_margin: float | None = None,
) -> None:
    # ... existing docstring and imports ...

    _post = post_update if post_update is not None else lambda fn: fn()

    if not token:
        return

    title = str(node.result.get(TITLE, ""))
    if not title:
        return

    year = node.result.get(YEAR)

    # --- tmdb_id shortcut: skip show search when already identified ---
    existing_tmdb_id = node.result.get(TMDB_ID)
    if existing_tmdb_id is not None:
        media_type = node.result.get(MEDIA_TYPE)
        if media_type == MEDIA_TYPE_EPISODE:
            # Show identified -- go directly to episode queries
            show_fields = {
                TMDB_ID: existing_tmdb_id,
                TITLE: title,
                YEAR: year,
                MEDIA_TYPE: MEDIA_TYPE_EPISODE,
            }
            _query_episodes(
                node,
                token,
                threshold,
                show_fields,
                cache=cache,
                client=client,
                post_update=_post,
                max_results=max_results,
                max_retries=max_retries,
            )
            return
        # Movie already identified -- nothing more to fetch
        return

    # ... rest of existing code (search_multi, etc.) ...
```

Insert this block between the `year = node.result.get(YEAR)` line and the `_accept_kwargs` line.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ui/test_pipeline.py::TestTmdbIdShortcut -v`
Expected: PASS

Also run all existing pipeline tests:
Run: `uv run pytest tests/test_ui/test_pipeline.py tests/test_pipeline.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add tapes/pipeline.py tests/test_ui/test_pipeline.py
git commit -m "feat: skip show search when tmdb_id is already set

When node.result has a tmdb_id and media_type is episode, skip
search_multi and go directly to episode queries. When tmdb_id is
set for a movie, skip entirely since the movie is fully identified."
```

---

### Task 3: Confidence gate for episode application

**Problem:** `_query_episodes` (pipeline.py:513-527) unconditionally applies the best episode's fields to the result, regardless of confidence. Comment says "Always apply the best episode's fields". This means a 0.0-confidence episode gets applied, which is wrong when season/episode info is missing or doesn't match.

**Fix:** Only auto-apply the best episode if it passes `should_auto_accept`. Otherwise, add episode sources for user curation without overwriting the result.

**Files:**
- Modify: `tapes/pipeline.py:419-527` (`_query_episodes`)
- Test: `tests/test_ui/test_pipeline.py`

**Step 1: Write failing tests**

Add to `tests/test_ui/test_pipeline.py`:

```python
class TestEpisodeConfidenceGate:
    """Episode application should respect confidence threshold."""

    def test_low_confidence_episode_not_applied(self, mock_tmdb) -> None:
        """When episode confidence is low, don't overwrite result fields."""
        node = FileNode(
            path=Path("/media/Breaking.Bad.S03E05.mkv"),
            result={
                "title": "Breaking Bad",
                "year": 2008,
                "tmdb_id": 1396,
                "media_type": "episode",
                "season": 3,
                "episode": 5,
            },
            sources=[],
        )
        # Mock returns only season 1 episodes. Season 3 won't match,
        # so episode confidence will be low (season mismatch).
        refresh_tmdb_source(node, token=TOKEN)
        # Season/episode should NOT be overwritten to S01E01
        assert node.result["season"] == 3
        assert node.result["episode"] == 5
        # But episode sources should still be added for curation
        tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
        assert len(tmdb_sources) >= 1

    def test_high_confidence_episode_applied(self, mock_tmdb) -> None:
        """When episode confidence is high, apply as before."""
        node = FileNode(
            path=Path("/media/Breaking.Bad.S01E01.mkv"),
            result={
                "title": "Breaking Bad",
                "year": 2008,
                "tmdb_id": 1396,
                "media_type": "episode",
                "season": 1,
                "episode": 1,
            },
            sources=[],
        )
        refresh_tmdb_source(node, token=TOKEN)
        assert node.result.get("episode_title") == "Pilot"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ui/test_pipeline.py::TestEpisodeConfidenceGate -v`
Expected: `test_low_confidence_episode_not_applied` FAIL because season gets overwritten to 1.

**Step 3: Implement fix**

In `tapes/pipeline.py`, change the end of `_query_episodes` (the `_apply_episode` section). Replace lines 513-527:

From:
```python
    # Always apply the best episode's fields to the result.
    # We're only here because the show was confidently matched,
    # so the best episode data should be used regardless of its
    # confidence score.
    _top_copy = list(top_sources)

    def _apply_episode(_n: FileNode = node, _top: list[Source] = _top_copy) -> None:
        if _top:
            best_ep = _top[0]
            for field, val in best_ep.fields.items():
                if val is not None:
                    _n.result[field] = val
        _n.sources.extend(_top)

    _post(_apply_episode)
```

To:
```python
    # Auto-apply episode only if confident; otherwise just add sources for curation
    ep_similarities = [s.confidence for s in top_sources]
    _top_copy = list(top_sources)

    if should_auto_accept(ep_similarities, threshold=threshold):
        _best_fields = dict(top_sources[0].fields)

        def _apply_episode(_n: FileNode = node, _f: dict = _best_fields, _top: list[Source] = _top_copy) -> None:
            for field, val in _f.items():
                if val is not None:
                    _n.result[field] = val
            _n.sources.extend(_top)

        _post(_apply_episode)
    else:
        def _add_episode_sources(_n: FileNode = node, _top: list[Source] = _top_copy) -> None:
            _n.sources.extend(_top)

        _post(_add_episode_sources)
```

Note: `should_auto_accept` is already imported at the top of the file.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ui/test_pipeline.py::TestEpisodeConfidenceGate -v`
Expected: PASS

Run full suite to check for regressions:
Run: `uv run pytest tests/test_ui/test_pipeline.py -v`
Expected: All PASS. Some existing tests may need threshold adjustments if they relied on unconditional episode application. Check `test_tv_show_triggers_episode_stage` and `test_tmdb_episode_data_merged` -- these use `confidence_threshold=0.7` and `0.5` respectively, and S01E01 scores 0.9 (season=0.25 + episode=0.65), so they should still pass.

**Step 5: Commit**

```bash
git add tapes/pipeline.py tests/test_ui/test_pipeline.py
git commit -m "fix: only auto-apply episode when confidence passes threshold

_query_episodes now uses should_auto_accept to gate episode
application. Low-confidence episodes are added as sources for
user curation without overwriting the result's season/episode."
```

---

### Task 4: Batch async refresh with cache, dedup, and progress

**Problem:** `action_refresh_query` runs `refresh_tmdb_source` synchronously in a loop on the main thread, blocking the UI. No shared cache or httpx.Client between calls, so no query deduplication. No progress feedback.

**Fix:** Create `refresh_tmdb_batch` in pipeline.py (mirrors `run_tmdb_pass` pattern) and call it via a Textual worker thread. Reuse existing `_on_tmdb_progress` / `_on_tmdb_done` callbacks.

**Files:**
- Modify: `tapes/pipeline.py` (add `refresh_tmdb_batch`)
- Modify: `tapes/ui/tree_app.py:486-528` (rewrite `action_refresh_query`)
- Test: `tests/test_ui/test_pipeline.py`

**Step 1: Write failing tests for `refresh_tmdb_batch`**

Add to `tests/test_ui/test_pipeline.py`:

```python
class TestRefreshTmdbBatch:
    """Tests for batch refresh with cache and dedup."""

    def test_batch_refreshes_multiple_nodes(self, mock_tmdb) -> None:
        """All nodes in the batch get refreshed."""
        from tapes.pipeline import refresh_tmdb_batch

        node1 = FileNode(
            path=Path("/media/Dune.mkv"),
            result={"title": "Dune", "year": 2021},
            sources=[Source(name="TMDB #1", fields={"title": "Old"}, confidence=0.5)],
        )
        node2 = FileNode(
            path=Path("/media/Arrival.mkv"),
            result={"title": "Arrival", "year": 2016},
            sources=[],
        )
        refresh_tmdb_batch([node1, node2], token=TOKEN)
        for n in [node1, node2]:
            tmdb = [s for s in n.sources if s.name.startswith("TMDB")]
            assert len(tmdb) >= 1

    def test_batch_deduplicates_queries(self, mock_tmdb) -> None:
        """Nodes with same title/year share a single search_multi call."""
        from tapes.pipeline import refresh_tmdb_batch

        node1 = FileNode(
            path=Path("/media/show.s01e01.mkv"),
            result={"title": "Breaking Bad", "season": 1, "episode": 1, "media_type": "episode"},
            sources=[],
        )
        node2 = FileNode(
            path=Path("/media/show.s01e01.nfo"),
            result={"title": "Breaking Bad", "season": 1, "episode": 1, "media_type": "episode"},
            sources=[],
        )
        with patch("tapes.tmdb.search_multi", side_effect=_mock_search_multi) as mock_search:
            refresh_tmdb_batch([node1, node2], token=TOKEN)
            # Cache dedup: search_multi called once, not twice
            assert mock_search.call_count == 1

    def test_batch_clears_existing_tmdb_sources(self, mock_tmdb) -> None:
        """Existing TMDB sources are cleared before refresh."""
        from tapes.pipeline import refresh_tmdb_batch

        node = FileNode(
            path=Path("/media/Dune.mkv"),
            result={"title": "Dune", "year": 2021},
            sources=[Source(name="TMDB #1", fields={"title": "Old"}, confidence=0.1)],
        )
        refresh_tmdb_batch([node], token=TOKEN)
        tmdb_sources = [s for s in node.sources if s.name.startswith("TMDB")]
        assert all(s.fields.get("title") != "Old" for s in tmdb_sources)

    def test_batch_reports_progress(self, mock_tmdb) -> None:
        """on_progress callback is invoked after each node."""
        from tapes.pipeline import refresh_tmdb_batch

        progress_calls: list[tuple[int, int]] = []

        def on_progress(done: int, total: int) -> None:
            progress_calls.append((done, total))

        nodes = [
            FileNode(path=Path(f"/media/file{i}.mkv"), result={"title": "Dune", "year": 2021}, sources=[])
            for i in range(3)
        ]
        refresh_tmdb_batch(nodes, token=TOKEN, on_progress=on_progress)
        assert len(progress_calls) == 3
        assert progress_calls[-1] == (3, 3)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ui/test_pipeline.py::TestRefreshTmdbBatch -v`
Expected: FAIL -- ImportError because `refresh_tmdb_batch` doesn't exist yet.

**Step 3: Implement `refresh_tmdb_batch` in pipeline.py**

Add after `refresh_tmdb_source`:

```python
def refresh_tmdb_batch(
    nodes: list[FileNode],
    token: str = "",
    confidence_threshold: float | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
    post_update: Callable[[Callable[[], None]], None] | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    tmdb_timeout: float = 10.0,
    max_retries: int = 3,
    margin_threshold: float | None = None,
    min_margin: float | None = None,
) -> None:
    """Re-query TMDB for multiple files with shared cache and deduplication.

    Like run_tmdb_pass but operates on a specific list of nodes and clears
    existing TMDB sources before querying. Uses a shared cache and httpx
    client to deduplicate identical queries.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if confidence_threshold is None:
        confidence_threshold = DEFAULT_AUTO_ACCEPT_THRESHOLD

    _post = post_update if post_update is not None else lambda fn: fn()

    if not token or not nodes:
        return

    from tapes import tmdb

    total = len(nodes)
    done_count = 0
    lock = threading.Lock()
    cache = _TmdbCache()

    with tmdb.create_client(token, timeout=tmdb_timeout) as client:

        def _refresh_one(node: FileNode) -> None:
            nonlocal done_count

            # Clear existing TMDB sources
            def _clear_tmdb(n: FileNode = node) -> None:
                n.sources = [s for s in n.sources if not s.name.startswith("TMDB")]

            _post(_clear_tmdb)

            # Query TMDB (cache deduplicates identical queries)
            _query_tmdb_for_node(
                node,
                token,
                confidence_threshold,
                cache=cache,
                client=client,
                post_update=_post,
                max_results=max_results,
                max_retries=max_retries,
                margin_threshold=margin_threshold,
                min_margin=min_margin,
            )

            with lock:
                done_count += 1
                if on_progress is not None:
                    on_progress(done_count, total)

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(_refresh_one, node) for node in nodes]
            for f in as_completed(futures):
                f.result()  # propagate exceptions
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ui/test_pipeline.py::TestRefreshTmdbBatch -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tapes/pipeline.py tests/test_ui/test_pipeline.py
git commit -m "feat: add refresh_tmdb_batch for deduped parallel refresh

Uses shared _TmdbCache and httpx.Client across all nodes in the
batch. Identical queries (same title/year) are deduplicated via
the cache. Runs in a ThreadPoolExecutor with progress reporting."
```

**Step 6: Write failing test for async `action_refresh_query`**

Add to `tests/test_ui/test_pipeline.py`, updating the existing `TestRefreshQueryIntegration` tests:

```python
    @pytest.mark.asyncio()
    async def test_r_in_detail_runs_async_with_progress(self, mock_tmdb) -> None:
        """Pressing 'r' in detail mode runs refresh asynchronously."""
        from tapes.ui.tree_app import TreeApp

        node1 = FileNode(
            path=Path("/media/Dune.mkv"),
            result={"title": "Dune", "year": 2021},
            sources=[],
        )
        node2 = FileNode(
            path=Path("/media/Arrival.mkv"),
            result={"title": "Arrival", "year": 2016},
            sources=[],
        )
        root = FolderNode(name="root", children=[node1, node2])
        model = TreeModel(root=root)
        config_obj = _make_config(TOKEN)
        _tmpl = "{title} ({year}).{ext}"
        app = TreeApp(model=model, movie_template=_tmpl, tv_template=_tmpl, config=config_obj)

        async with app.run_test() as pilot:
            # Enter multi-detail mode
            await pilot.press("v")
            await pilot.press("j")
            await pilot.press("enter")
            assert app.mode == AppMode.DETAIL
            # Press 'r' -- should not block
            await pilot.press("r")
            await app.workers.wait_for_complete()
            for n in [node1, node2]:
                tmdb = [s for s in n.sources if s.name.startswith("TMDB")]
                assert len(tmdb) >= 1
```

**Step 7: Run test to verify it fails**

Run: `uv run pytest tests/test_ui/test_pipeline.py::TestRefreshQueryIntegration::test_r_in_detail_runs_async_with_progress -v`
Expected: FAIL (refresh is currently synchronous, no workers to wait for).

**Step 8: Rewrite `action_refresh_query` in tree_app.py**

Replace `action_refresh_query` and add `_run_refresh_worker`:

```python
    def action_refresh_query(self) -> None:
        if self._mode in _MODAL_MODES:
            return
        if self._tmdb_querying:
            return  # Already querying

        token = self.config.metadata.tmdb_token
        if not token:
            return

        # Collect target nodes
        if self._mode == AppMode.DETAIL:
            nodes = list(self.query_one(DetailView).file_nodes)
        else:
            tv = self.query_one(TreeView)
            if tv.in_range_mode:
                selected = tv.selected_nodes()
                nodes = [n for n in selected if isinstance(n, FileNode)]
                tv.clear_range_select()
            else:
                node = tv.cursor_node()
                nodes = [node] if isinstance(node, FileNode) else []

        if not nodes:
            return

        self._tmdb_querying = True
        self._update_footer()
        self.run_worker(
            self._run_refresh_worker(nodes, token),  # ty: ignore[invalid-argument-type]  # Textual WorkType stubs
            thread=True,
        )

    def _run_refresh_worker(self, nodes: list[FileNode], token: str) -> object:
        """Return a callable that refreshes TMDB data in a background thread."""
        from tapes.pipeline import refresh_tmdb_batch

        threshold = self.config.metadata.auto_accept_threshold
        max_workers = self.config.advanced.max_workers
        max_results = self.config.metadata.max_results
        tmdb_timeout = self.config.advanced.tmdb_timeout
        tmdb_retries = self.config.advanced.tmdb_retries
        margin_threshold = self.config.metadata.margin_accept_threshold
        min_margin = self.config.metadata.min_accept_margin

        def worker() -> None:
            def on_progress(done: int, total: int) -> None:
                self.call_from_thread(self._on_tmdb_progress, done, total)

            refresh_tmdb_batch(
                nodes,
                token=token,
                confidence_threshold=threshold,
                on_progress=on_progress,
                max_workers=max_workers,
                post_update=self.call_from_thread,
                max_results=max_results,
                tmdb_timeout=tmdb_timeout,
                max_retries=tmdb_retries,
                margin_threshold=margin_threshold,
                min_margin=min_margin,
            )
            self.call_from_thread(self._on_tmdb_done)

        return worker
```

Remove the old import `from tapes.pipeline import refresh_tmdb_source` that was inside `action_refresh_query`.

**Step 9: Update existing integration tests**

The existing `TestRefreshQueryIntegration` tests press 'r' and immediately check results. With async refresh, they need `await app.workers.wait_for_complete()` after pressing 'r'. Update each test:

- `test_r_in_tree_refreshes_per_file`: add `await app.workers.wait_for_complete()` after `await pilot.press("r")`
- `test_r_in_detail_refreshes_current_node`: same
- `test_r_in_tree_range_refreshes_all`: same
- `test_r_in_multi_detail_refreshes_all_nodes`: same

**Step 10: Run all tests**

Run: `uv run pytest tests/test_ui/test_pipeline.py -v`
Expected: All PASS

Run: `uv run pytest -v`
Expected: All PASS

**Step 11: Commit**

```bash
git add tapes/pipeline.py tapes/ui/tree_app.py tests/test_ui/test_pipeline.py
git commit -m "feat: run TMDB refresh asynchronously with progress feedback

action_refresh_query now uses refresh_tmdb_batch via a Textual
worker thread. Shared cache deduplicates queries, progress is
shown in the footer via existing _on_tmdb_progress callback.
UI no longer blocks during refresh."
```

---

## Verification

After all 4 tasks, run full test suite:

```bash
uv run pytest -v
```

Expected: All tests pass, no regressions.

### Manual test scenario (matches the original bug report):

1. `uv run tapes import /path/to/show/` with a folder containing 2 seasons, each episode in its own subfolder with .mkv and .nfo files
2. Select all files with range select (v, then navigate down)
3. Press enter to open multi-file detail view
4. Press ctrl+a to accept the show-level TMDB match
5. Verify: season/episode fields are preserved (not "(0 values)")
6. Press r to refresh
7. Verify: UI does not block, "TMDB x/y" progress appears in footer
8. Verify: each file gets its own episode match (different episode_title values)
9. Verify: "(various)" shows for episode fields since each file has different episode data
