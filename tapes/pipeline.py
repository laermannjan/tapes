"""Auto-pipeline: populate sources and auto-accept confident matches."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx

from tapes.config import DEFAULT_AUTO_ACCEPT_THRESHOLD
from tapes.fields import (
    EPISODE,
    MEDIA_TYPE,
    MEDIA_TYPE_EPISODE,
    SEASON,
    TITLE,
    TMDB_ID,
    YEAR,
)
from tapes.similarity import compute_episode_similarity, compute_similarity, should_auto_accept
from tapes.tree_model import FileNode, Source, TreeModel

DEFAULT_MAX_WORKERS = 4
DEFAULT_MAX_RESULTS = 3

logger = logging.getLogger(__name__)


class _TmdbCache:
    """Thread-safe cache for TMDB API responses.

    If multiple threads request the same key, only one fetches;
    the others block until the result is ready.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[tuple, Any] = {}
        self._pending: dict[tuple, threading.Event] = {}

    def get_or_fetch(self, key: tuple, fetch_fn: Callable[[], Any]) -> Any:
        with self._lock:
            if key in self._data:
                return self._data[key]
            if key in self._pending:
                # Another thread is already fetching this key
                event = self._pending[key]
                is_fetcher = False
            else:
                # We will fetch; create an event others can wait on
                event = threading.Event()
                self._pending[key] = event
                is_fetcher = True

        if not is_fetcher:
            event.wait()
            with self._lock:
                if key in self._data:
                    return self._data[key]
            # Fetch failed for this key
            raise KeyError(f"Fetch failed for {key}")

        # We are the fetcher
        try:
            result = fetch_fn()
            with self._lock:
                self._data[key] = result
        except Exception:
            with self._lock:
                del self._pending[key]  # allow retry
            raise
        else:
            return result
        finally:
            event.set()


def run_guessit_pass(model: TreeModel) -> None:
    """Extract metadata from filenames via guessit for all files.

    This is fast (local-only) and should be called synchronously before
    rendering the UI.
    """
    from tapes.metadata import extract_metadata

    for node in model.all_files():
        _populate_node_guessit(node, extract_metadata)


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
    """Query TMDB for all files using a thread pool.

    Args:
        on_progress: Optional callback(done: int, total: int) called after
            each file is processed.
        max_workers: Number of concurrent TMDB queries.
        post_update: Optional callback to dispatch node mutations to the
            main thread.  Receives a zero-arg callable that performs the
            mutation.  When *None*, mutations execute directly (safe for
            single-threaded / CLI usage).
        max_results: Maximum TMDB results to keep per file.
        tmdb_timeout: Timeout in seconds for TMDB HTTP requests.
        tmdb_retries: Number of retries for failed TMDB requests.
        margin_threshold: Minimum similarity for tier 2 auto-accept.
        min_margin: Minimum gap between best and second for tier 2.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if confidence_threshold is None:
        confidence_threshold = DEFAULT_AUTO_ACCEPT_THRESHOLD

    _post = post_update if post_update is not None else lambda fn: fn()

    if not token:
        return

    from tapes import tmdb

    files = list(model.all_files())
    total = len(files)
    if not total:
        return

    done_count = 0
    lock = threading.Lock()

    cache = _TmdbCache()

    with tmdb.create_client(token, timeout=tmdb_timeout) as client:

        def query_one(node: FileNode) -> None:
            nonlocal done_count
            _query_tmdb_for_node(
                node,
                token,
                confidence_threshold,
                cache=cache,
                client=client,
                post_update=_post,
                max_results=max_results,
                max_retries=tmdb_retries,
                margin_threshold=margin_threshold,
                min_margin=min_margin,
                language=language,
            )
            with lock:
                done_count += 1
                if on_progress is not None:
                    on_progress(done_count, total)

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(query_one, node) for node in files]
            for f in as_completed(futures):
                f.result()  # propagate exceptions


def run_auto_pipeline(
    model: TreeModel,
    token: str = "",
    confidence_threshold: float | None = None,
    post_update: Callable[[Callable[[], None]], None] | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    tmdb_timeout: float = 10.0,
    tmdb_retries: int = 3,
    margin_threshold: float | None = None,
    min_margin: float | None = None,
    language: str = "",
) -> None:
    """Populate sources and auto-accept confident matches (synchronous).

    For each file node:
    1. Extract metadata from filename via guessit -> result + "from filename" source
    2. Query TMDB (two-stage: show/movie, then episodes) -> add TMDB sources
    3. Auto-accept via should_auto_accept (high similarity OR clear winner)
    """

    if confidence_threshold is None:
        confidence_threshold = DEFAULT_AUTO_ACCEPT_THRESHOLD

    run_guessit_pass(model)
    run_tmdb_pass(
        model,
        token=token,
        confidence_threshold=confidence_threshold,
        post_update=post_update,
        max_results=max_results,
        tmdb_timeout=tmdb_timeout,
        tmdb_retries=tmdb_retries,
        margin_threshold=margin_threshold,
        min_margin=min_margin,
        language=language,
    )


def refresh_tmdb_source(
    node: FileNode,
    token: str = "",
    confidence_threshold: float | None = None,
    post_update: Callable[[Callable[[], None]], None] | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    max_retries: int = 3,
    margin_threshold: float | None = None,
    min_margin: float | None = None,
    language: str = "",
) -> None:
    """Re-query TMDB for a file and update its sources.

    Uses the node's current result title/year for the query.
    Removes existing TMDB sources, adds new ones if found.
    Auto-accepts if confidence >= threshold.
    """

    if confidence_threshold is None:
        confidence_threshold = DEFAULT_AUTO_ACCEPT_THRESHOLD

    _post = post_update if post_update is not None else lambda fn: fn()

    # Remove existing TMDB sources
    def _clear_tmdb(node: FileNode = node) -> None:
        node.sources = [s for s in node.sources if not s.name.startswith("TMDB")]

    _post(_clear_tmdb)

    _query_tmdb_for_node(
        node,
        token,
        confidence_threshold,
        post_update=_post,
        max_results=max_results,
        max_retries=max_retries,
        margin_threshold=margin_threshold,
        min_margin=min_margin,
        language=language,
    )


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
    language: str = "",
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
                language=language,
            )

            with lock:
                done_count += 1
                if on_progress is not None:
                    on_progress(done_count, total)

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(_refresh_one, node) for node in nodes]
            for f in as_completed(futures):
                f.result()  # propagate exceptions


def extract_guessit_fields(filename: str) -> dict[str, Any]:
    """Extract metadata fields from a filename via guessit.

    Returns the same field dict that run_guessit_pass would populate.
    """
    from tapes.metadata import extract_metadata

    meta = extract_metadata(filename)
    fields: dict[str, Any] = {}
    if meta.title:
        fields[TITLE] = meta.title
    if meta.year is not None:
        fields[YEAR] = meta.year
    if meta.season is not None:
        fields[SEASON] = meta.season
    if meta.episode is not None:
        fields[EPISODE] = meta.episode
    if meta.media_type:
        fields[MEDIA_TYPE] = meta.media_type
    fields.update({k: v for k, v in meta.raw.items() if v is not None})
    return fields


def _populate_node_guessit(node: FileNode, extract_metadata_fn: Callable[[str], Any]) -> None:
    """Extract metadata from filename via guessit and set as result (base layer).

    The filename extraction is the base layer, not a source. It populates
    ``node.result`` directly. Sources are reserved for TMDB matches only.
    """
    meta = extract_metadata_fn(node.path.name)
    filename_fields: dict = {}
    if meta.title:
        filename_fields[TITLE] = meta.title
    if meta.year is not None:
        filename_fields[YEAR] = meta.year
    if meta.season is not None:
        filename_fields[SEASON] = meta.season
    if meta.episode is not None:
        filename_fields[EPISODE] = meta.episode
    if meta.media_type:
        filename_fields[MEDIA_TYPE] = meta.media_type
    # Add raw fields (codec, media_source, etc.)
    filename_fields.update({k: v for k, v in meta.raw.items() if v is not None})

    node.result = dict(filename_fields)
    node.sources = []


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
    language: str = "",
) -> None:
    """Two-stage TMDB query for a single node.

    Stage 1: Find movie/show
    - search_multi with title (+year if available) -> up to max_results Sources
    - Auto-accept via should_auto_accept (high similarity OR clear winner)
    - If accepted media_type == "movie": done

    Stage 2: Find episode (only if stage 1 accepted a TV show)
    - If season in result: fetch that season's episodes
    - Score episodes against result, create Sources with full fields
    - If no auto-accept from that season: try all other seasons
    - If still no auto-accept: keep top max_results episode Sources
    - Auto-accept best episode if confident
    """
    from tapes import tmdb

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
                language=language,
            )
            return
        # Movie already identified -- nothing more to fetch
        return

    # Build optional kwargs for should_auto_accept margin params
    _accept_kwargs: dict[str, float] = {}
    if margin_threshold is not None:
        _accept_kwargs["margin_threshold"] = margin_threshold
    if min_margin is not None:
        _accept_kwargs["min_margin"] = min_margin

    # Stage 1: search for movie/show
    if cache is not None:
        search_key = ("search", title.lower(), year)
        search_results = cache.get_or_fetch(
            search_key,
            lambda: tmdb.search_multi(
                title,
                token,
                year=year,
                language=language,
                client=client,
                max_results=max_results,
                max_retries=max_retries,
            ),
        )
    else:
        search_results = tmdb.search_multi(
            title,
            token,
            year=year,
            language=language,
            client=client,
            max_results=max_results,
            max_retries=max_retries,
        )

    if not search_results:
        return

    # Create sources for each search result
    tmdb_sources: list[Source] = []
    for i, sr in enumerate(search_results[:max_results]):
        confidence = compute_similarity(node.result, sr)
        source = Source(
            name=f"TMDB #{i + 1}",
            fields=dict(sr),
            confidence=confidence,
        )
        tmdb_sources.append(source)

    # Sort by similarity for should_auto_accept (expects descending order)
    tmdb_sources.sort(key=lambda s: s.confidence, reverse=True)
    for i, src in enumerate(tmdb_sources):
        src.name = f"TMDB #{i + 1}"
    similarities = [s.confidence for s in tmdb_sources]
    best = tmdb_sources[0]

    logger.debug(
        "%s: candidates=%s",
        node.path.name,
        [(s.name, s.fields.get(TITLE), f"{s.confidence:.2f}") for s in tmdb_sources],
    )

    if should_auto_accept(similarities, threshold=threshold, **_accept_kwargs):
        # Auto-accept: apply non-empty fields to result
        # Snapshot fields before dispatching -- the dict may be mutated later
        _best_fields = dict(best.fields)

        def _apply_best(_n: FileNode = node, _f: dict = _best_fields) -> None:
            for field, val in _f.items():
                if val is not None:
                    _n.result[field] = val
            _n.staged = True

        _post(_apply_best)

        # Stage 2: if TV show, fetch episodes
        if best.fields.get(MEDIA_TYPE) == MEDIA_TYPE_EPISODE:
            _query_episodes(
                node,
                token,
                threshold,
                best.fields,
                cache=cache,
                client=client,
                post_update=_post,
                max_results=max_results,
                max_retries=max_retries,
                language=language,
            )
            return

    # Add show-level TMDB sources (not episode sources yet)
    _sources_copy = list(tmdb_sources)

    def _extend_sources(_n: FileNode = node, _s: list[Source] = _sources_copy) -> None:
        _n.sources.extend(_s)

    _post(_extend_sources)


def _query_episodes(
    node: FileNode,
    token: str,
    threshold: float,
    show_fields: dict,
    cache: _TmdbCache | None = None,
    client: httpx.Client | None = None,
    post_update: Callable[[Callable[[], None]], None] | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    max_retries: int = 3,
    language: str = "",
) -> None:
    """Stage 2: fetch episode data for a TV show match."""
    from tapes import tmdb

    _post = post_update if post_update is not None else lambda fn: fn()

    show_id = show_fields.get(TMDB_ID)
    show_title = show_fields.get(TITLE, "")
    show_year = show_fields.get(YEAR)

    if show_id is None:
        return

    # Get show info to know available seasons
    if cache is not None:
        show_info = cache.get_or_fetch(
            ("show", show_id),
            lambda: tmdb.get_show(show_id, token, language=language, client=client, max_retries=max_retries),
        )
    else:
        show_info = tmdb.get_show(show_id, token, language=language, client=client, max_retries=max_retries)
    if not show_info:
        return

    available_seasons = show_info.get("seasons", [])
    query_season = node.result.get(SEASON)

    # Try the query season first, then others
    seasons_to_try: list[int] = []
    if query_season is not None and query_season in available_seasons:
        seasons_to_try.append(query_season)
    # Add remaining seasons
    for s in available_seasons:
        if s not in seasons_to_try:
            seasons_to_try.append(s)

    all_episode_sources: list[Source] = []

    for season_num in seasons_to_try:
        if cache is not None:
            episodes = cache.get_or_fetch(
                ("episodes", show_id, season_num),
                lambda sn=season_num: tmdb.get_season_episodes(
                    show_id,
                    sn,
                    token,
                    show_title=show_title,
                    show_year=show_year,
                    language=language,
                    client=client,
                    max_retries=max_retries,
                ),
            )
        else:
            episodes = tmdb.get_season_episodes(
                show_id,
                season_num,
                token,
                show_title=show_title,
                show_year=show_year,
                language=language,
                client=client,
                max_retries=max_retries,
            )

        for ep in episodes:
            confidence = compute_episode_similarity(node.result, ep)
            source = Source(
                name=f"TMDB #{len(all_episode_sources) + 1}",
                fields=dict(ep),
                confidence=confidence,
            )
            all_episode_sources.append(source)

        # If we found a match in this season, stop searching more
        if any(s.confidence >= threshold for s in all_episode_sources):
            break

    # Keep top max_results episode sources by confidence
    all_episode_sources.sort(key=lambda s: s.confidence, reverse=True)
    top_sources = all_episode_sources[:max_results]

    # Re-number them
    for i, src in enumerate(top_sources):
        src.name = f"TMDB #{i + 1}"

    # Auto-apply episode only if confident; otherwise just add sources for curation
    ep_similarities = [s.confidence for s in top_sources]
    _top_copy = list(top_sources)

    if should_auto_accept(ep_similarities, threshold=threshold):
        _best_fields = dict(top_sources[0].fields)

        def _apply_episode(_n: FileNode = node, _f: dict = _best_fields, _top: list[Source] = _top_copy) -> None:
            for field, val in _f.items():
                if val is not None:
                    _n.result[field] = val
            _n.staged = True
            _n.sources.extend(_top)

        _post(_apply_episode)
    else:

        def _add_episode_sources(_n: FileNode = node, _top: list[Source] = _top_copy) -> None:
            _n.sources.extend(_top)

        _post(_add_episode_sources)
