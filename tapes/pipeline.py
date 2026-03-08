"""Auto-pipeline: populate sources and auto-accept confident matches."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx

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
    max_workers: int = 4,
) -> None:
    """Query TMDB for all files using a thread pool.

    Args:
        on_progress: Optional callback(done: int, total: int) called after
            each file is processed.
        max_workers: Number of concurrent TMDB queries.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from tapes.config import DEFAULT_AUTO_ACCEPT_THRESHOLD

    if confidence_threshold is None:
        confidence_threshold = DEFAULT_AUTO_ACCEPT_THRESHOLD

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

    with tmdb.create_client(token) as client:

        def query_one(node: FileNode) -> None:
            nonlocal done_count
            _query_tmdb_for_node(
                node,
                token,
                confidence_threshold,
                cache=cache,
                client=client,
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
) -> None:
    """Populate sources and auto-accept confident matches (synchronous).

    For each file node:
    1. Extract metadata from filename via guessit -> result + "from filename" source
    2. Query TMDB (two-stage: show/movie, then episodes) -> add TMDB sources
    3. Auto-accept via should_auto_accept (high similarity OR clear winner)
    """
    from tapes.config import DEFAULT_AUTO_ACCEPT_THRESHOLD

    if confidence_threshold is None:
        confidence_threshold = DEFAULT_AUTO_ACCEPT_THRESHOLD

    run_guessit_pass(model)
    run_tmdb_pass(model, token=token, confidence_threshold=confidence_threshold)


def refresh_tmdb_source(
    node: FileNode,
    token: str = "",
    confidence_threshold: float | None = None,
) -> None:
    """Re-query TMDB for a file and update its sources.

    Uses the node's current result title/year for the query.
    Removes existing TMDB sources, adds new ones if found.
    Auto-accepts if confidence >= threshold.
    """
    from tapes.config import DEFAULT_AUTO_ACCEPT_THRESHOLD

    if confidence_threshold is None:
        confidence_threshold = DEFAULT_AUTO_ACCEPT_THRESHOLD

    # Remove existing TMDB sources
    node.sources = [s for s in node.sources if not s.name.startswith("TMDB")]

    _query_tmdb_for_node(node, token, confidence_threshold)


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
) -> None:
    """Two-stage TMDB query for a single node.

    Stage 1: Find movie/show
    - search_multi with title (+year if available) -> up to 3 Sources
    - Auto-accept via should_auto_accept (high similarity OR clear winner)
    - If accepted media_type == "movie": done

    Stage 2: Find episode (only if stage 1 accepted a TV show)
    - If season in result: fetch that season's episodes
    - Score episodes against result, create Sources with full fields
    - If no auto-accept from that season: try all other seasons
    - If still no auto-accept: keep top 3 episode Sources
    - Auto-accept best episode if confident
    """
    from tapes import tmdb

    if not token:
        return

    title = str(node.result.get(TITLE, ""))
    if not title:
        return

    year = node.result.get(YEAR)

    # Stage 1: search for movie/show
    if cache is not None:
        search_key = ("search", title.lower(), year)
        search_results = cache.get_or_fetch(
            search_key, lambda: tmdb.search_multi(title, token, year=year, client=client)
        )
    else:
        search_results = tmdb.search_multi(title, token, year=year, client=client)

    if not search_results:
        return

    # Create sources for each search result
    tmdb_sources: list[Source] = []
    for i, sr in enumerate(search_results[:3]):
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

    if should_auto_accept(similarities, threshold=threshold):
        # Auto-accept: apply non-empty fields to result
        for field, val in best.fields.items():
            if val is not None:
                node.result[field] = val
        node.staged = True

        # Stage 2: if TV show, fetch episodes
        if best.fields.get(MEDIA_TYPE) == MEDIA_TYPE_EPISODE:
            _query_episodes(node, token, threshold, best.fields, cache=cache, client=client)
            return

    # Add show-level TMDB sources (not episode sources yet)
    node.sources.extend(tmdb_sources)


def _query_episodes(
    node: FileNode,
    token: str,
    threshold: float,
    show_fields: dict,
    cache: _TmdbCache | None = None,
    client: httpx.Client | None = None,
) -> None:
    """Stage 2: fetch episode data for a TV show match."""
    from tapes import tmdb

    show_id = show_fields.get(TMDB_ID)
    show_title = show_fields.get(TITLE, "")
    show_year = show_fields.get(YEAR)

    if show_id is None:
        return

    # Get show info to know available seasons
    if cache is not None:
        show_info = cache.get_or_fetch(("show", show_id), lambda: tmdb.get_show(show_id, token, client=client))
    else:
        show_info = tmdb.get_show(show_id, token, client=client)
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
                    client=client,
                ),
            )
        else:
            episodes = tmdb.get_season_episodes(
                show_id,
                season_num,
                token,
                show_title=show_title,
                show_year=show_year,
                client=client,
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

    # Keep top 3 episode sources by confidence
    all_episode_sources.sort(key=lambda s: s.confidence, reverse=True)
    top_sources = all_episode_sources[:3]

    # Always apply the best episode's fields to the result.
    # We're only here because the show was confidently matched,
    # so the best episode data should be used regardless of its
    # confidence score.
    if top_sources:
        best_ep = top_sources[0]
        for field, val in best_ep.fields.items():
            if val is not None:
                node.result[field] = val

    # Re-number them
    for i, src in enumerate(top_sources):
        src.name = f"TMDB #{i + 1}"

    node.sources.extend(top_sources)
