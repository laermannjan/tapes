"""Auto-pipeline: populate candidates and auto-accept confident matches."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx

from tapes.config import DEFAULT_MIN_SCORE
from tapes.fields import (
    EPISODE,
    MEDIA_TYPE,
    MEDIA_TYPE_EPISODE,
    SEASON,
    TITLE,
    TMDB_ID,
    YEAR,
)
from tapes.similarity import DEFAULT_MIN_PROMINENCE, compute_episode_similarity, compute_similarity, should_auto_accept
from tapes.tree_model import Candidate, FileNode, TreeModel

DEFAULT_MAX_WORKERS = 4
DEFAULT_MAX_RESULTS = 3

logger = logging.getLogger(__name__)


def _make_metadata_updater(
    node: FileNode,
    fields: dict[str, Any],
    stage: bool,
) -> Callable[[], None]:
    """Create a closure that updates node metadata on the main thread.

    Uses explicit parameters instead of closing over loop variables to avoid
    late-binding bugs -- each closure captures the values at creation time,
    not at call time.
    """

    def _apply() -> None:
        for field_name, val in fields.items():
            if val is not None:
                node.metadata[field_name] = val
        if stage:
            node.staged = True

    return _apply


def _make_candidates_updater(
    node: FileNode,
    candidates: list[Candidate],
) -> Callable[[], None]:
    """Create a closure that extends node candidates."""

    def _extend() -> None:
        node.candidates.extend(candidates)

    return _extend


@dataclass
class PipelineParams:
    """Bundled parameters for pipeline functions."""

    token: str = ""
    min_score: float = DEFAULT_MIN_SCORE
    min_prominence: float = DEFAULT_MIN_PROMINENCE
    max_results: int = DEFAULT_MAX_RESULTS
    max_workers: int = DEFAULT_MAX_WORKERS
    tmdb_timeout: float = 10.0
    tmdb_retries: int = 3
    language: str = ""

    @classmethod
    def from_config(cls, config: TapesConfig) -> PipelineParams:
        """Create PipelineParams from a TapesConfig instance."""
        return cls(
            token=config.metadata.tmdb_token,
            min_score=config.metadata.min_score,
            min_prominence=config.metadata.min_prominence,
            max_results=config.metadata.max_results,
            max_workers=config.advanced.max_workers,
            tmdb_timeout=config.advanced.tmdb_timeout,
            tmdb_retries=config.advanced.tmdb_retries,
            language=config.metadata.language,
        )


if TYPE_CHECKING:
    from tapes.config import TapesConfig


def _resolve_params(
    params: PipelineParams | None,
    *,
    token: str = "",
    min_score: float | None = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
    max_results: int = DEFAULT_MAX_RESULTS,
    tmdb_timeout: float = 10.0,
    tmdb_retries: int = 3,
    min_prominence: float | None = None,
    language: str = "",
) -> PipelineParams:
    """Return *params* if given, otherwise build one from keyword arguments.

    This lets every public function accept either a ``PipelineParams`` object
    **or** the legacy individual keyword arguments during the transition period.
    """
    if params is not None:
        return params
    return PipelineParams(
        token=token,
        min_score=min_score if min_score is not None else DEFAULT_MIN_SCORE,
        min_prominence=min_prominence if min_prominence is not None else DEFAULT_MIN_PROMINENCE,
        max_results=max_results,
        max_workers=max_workers,
        tmdb_timeout=tmdb_timeout,
        tmdb_retries=tmdb_retries,
        language=language,
    )


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
    from tapes.extract import extract_metadata

    for node in model.all_files():
        _populate_node_guessit(node, extract_metadata)


def run_tmdb_pass(
    model: TreeModel,
    params: PipelineParams | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    post_update: Callable[[Callable[[], None]], None] | None = None,
    can_stage: Callable[[FileNode, dict], bool] | None = None,
    *,
    token: str = "",
    min_score: float | None = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
    max_results: int = DEFAULT_MAX_RESULTS,
    tmdb_timeout: float = 10.0,
    tmdb_retries: int = 3,
    min_prominence: float | None = None,
    language: str = "",
) -> None:
    """Query TMDB for all files using a thread pool.

    Args:
        params: Bundled pipeline parameters. When provided, individual kwargs
            (token, min_score, etc.) are ignored.
        on_progress: Optional callback(done: int, total: int) called after
            each file is processed.
        post_update: Optional callback to dispatch node mutations to the
            main thread.  Receives a zero-arg callable that performs the
            mutation.  When *None*, mutations execute directly (safe for
            single-threaded / CLI usage).
        can_stage: Optional callback to check if a node can be staged.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    p = _resolve_params(
        params,
        token=token,
        min_score=min_score,
        max_workers=max_workers,
        max_results=max_results,
        tmdb_timeout=tmdb_timeout,
        tmdb_retries=tmdb_retries,
        min_prominence=min_prominence,
        language=language,
    )

    _post = post_update if post_update is not None else lambda fn: fn()

    if not p.token:
        return

    from tapes import tmdb

    files = list(model.all_files())
    total = len(files)
    if not total:
        return

    done_count = 0
    lock = threading.Lock()

    cache = _TmdbCache()

    with tmdb.create_client(p.token, timeout=p.tmdb_timeout) as client:

        def query_one(node: FileNode) -> None:
            nonlocal done_count
            _query_tmdb_for_node(
                node,
                p,
                cache=cache,
                client=client,
                post_update=_post,
                can_stage=can_stage,
            )
            with lock:
                done_count += 1
                if on_progress is not None:
                    on_progress(done_count, total)

        with ThreadPoolExecutor(max_workers=p.max_workers) as pool:
            futures = [pool.submit(query_one, node) for node in files]
            for f in as_completed(futures):
                f.result()  # propagate exceptions


def run_auto_pipeline(
    model: TreeModel,
    params: PipelineParams | None = None,
    post_update: Callable[[Callable[[], None]], None] | None = None,
    can_stage: Callable[[FileNode, dict], bool] | None = None,
    *,
    token: str = "",
    min_score: float | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    tmdb_timeout: float = 10.0,
    tmdb_retries: int = 3,
    min_prominence: float | None = None,
    language: str = "",
) -> None:
    """Populate candidates and auto-accept confident matches (synchronous).

    For each file node:
    1. Extract metadata from filename via guessit -> metadata + "from filename" candidate
    2. Query TMDB (two-stage: show/movie, then episodes) -> add TMDB candidates
    3. Auto-accept via should_auto_accept (score >= min_score AND prominent)
    """
    p = _resolve_params(
        params,
        token=token,
        min_score=min_score,
        max_results=max_results,
        tmdb_timeout=tmdb_timeout,
        tmdb_retries=tmdb_retries,
        min_prominence=min_prominence,
        language=language,
    )

    run_guessit_pass(model)
    run_tmdb_pass(
        model,
        p,
        post_update=post_update,
        can_stage=can_stage,
    )


def refresh_tmdb_source(
    node: FileNode,
    params: PipelineParams | None = None,
    post_update: Callable[[Callable[[], None]], None] | None = None,
    can_stage: Callable[[FileNode, dict], bool] | None = None,
    *,
    token: str = "",
    min_score: float | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    max_retries: int = 3,
    min_prominence: float | None = None,
    language: str = "",
) -> None:
    """Re-query TMDB for a file and update its candidates.

    Uses the node's current metadata title/year for the query.
    Removes existing TMDB candidates, adds new ones if found.
    Auto-accepts if score >= min_score and prominent.
    """
    p = _resolve_params(
        params,
        token=token,
        min_score=min_score,
        max_results=max_results,
        tmdb_retries=max_retries,
        min_prominence=min_prominence,
        language=language,
    )

    _post = post_update if post_update is not None else lambda fn: fn()

    # Remove existing TMDB candidates
    def _clear_tmdb(node: FileNode = node) -> None:
        node.candidates = [c for c in node.candidates if not c.name.startswith("TMDB")]

    _post(_clear_tmdb)

    _query_tmdb_for_node(
        node,
        p,
        post_update=_post,
        can_stage=can_stage,
    )


def refresh_tmdb_batch(
    nodes: list[FileNode],
    params: PipelineParams | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    post_update: Callable[[Callable[[], None]], None] | None = None,
    can_stage: Callable[[FileNode, dict], bool] | None = None,
    *,
    token: str = "",
    min_score: float | None = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
    max_results: int = DEFAULT_MAX_RESULTS,
    tmdb_timeout: float = 10.0,
    max_retries: int = 3,
    min_prominence: float | None = None,
    language: str = "",
) -> None:
    """Re-query TMDB for multiple files with shared cache and deduplication.

    Like run_tmdb_pass but operates on a specific list of nodes and clears
    existing TMDB candidates before querying. Uses a shared cache and httpx
    client to deduplicate identical queries.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    p = _resolve_params(
        params,
        token=token,
        min_score=min_score,
        max_workers=max_workers,
        max_results=max_results,
        tmdb_timeout=tmdb_timeout,
        tmdb_retries=max_retries,
        min_prominence=min_prominence,
        language=language,
    )

    _post = post_update if post_update is not None else lambda fn: fn()

    if not p.token or not nodes:
        return

    from tapes import tmdb

    total = len(nodes)
    done_count = 0
    lock = threading.Lock()
    cache = _TmdbCache()

    with tmdb.create_client(p.token, timeout=p.tmdb_timeout) as client:

        def _refresh_one(node: FileNode) -> None:
            nonlocal done_count

            # Clear existing TMDB candidates
            def _clear_tmdb(n: FileNode = node) -> None:
                n.candidates = [c for c in n.candidates if not c.name.startswith("TMDB")]

            _post(_clear_tmdb)

            # Query TMDB (cache deduplicates identical queries)
            _query_tmdb_for_node(
                node,
                p,
                cache=cache,
                client=client,
                post_update=_post,
                can_stage=can_stage,
            )

            with lock:
                done_count += 1
                if on_progress is not None:
                    on_progress(done_count, total)

        with ThreadPoolExecutor(max_workers=p.max_workers) as pool:
            futures = [pool.submit(_refresh_one, node) for node in nodes]
            for f in as_completed(futures):
                f.result()  # propagate exceptions


def extract_guessit_fields(filename: str) -> dict[str, Any]:
    """Extract metadata fields from a filename via guessit.

    Returns the same field dict that run_guessit_pass would populate.
    """
    from tapes.extract import extract_metadata

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
    """Extract metadata from filename via guessit and set as metadata (base layer).

    The filename extraction is the base layer, not a candidate. It populates
    ``node.metadata`` directly. Candidates are reserved for TMDB matches only.
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

    node.metadata = dict(filename_fields)
    node.candidates = []


def _query_tmdb_for_node(
    node: FileNode,
    params: PipelineParams,
    cache: _TmdbCache | None = None,
    client: httpx.Client | None = None,
    post_update: Callable[[Callable[[], None]], None] | None = None,
    can_stage: Callable[[FileNode, dict], bool] | None = None,
) -> None:
    """Two-stage TMDB query for a single node.

    Stage 1: Find movie/show
    - search_multi with title (+year if available) -> up to max_results Candidates
    - Auto-accept via should_auto_accept (score >= min_score AND prominent)
    - If accepted media_type == "movie": done

    Stage 2: Find episode (only if stage 1 accepted a TV show)
    - If season in metadata: fetch that season's episodes
    - Score episodes against metadata, create Candidates with full fields
    - If no auto-accept from that season: try all other seasons
    - If still no auto-accept: keep top max_results episode Candidates
    - Auto-accept best episode if confident
    """
    from tapes import tmdb

    _post = post_update if post_update is not None else lambda fn: fn()

    if not params.token:
        return

    title = str(node.metadata.get(TITLE, ""))
    if not title:
        return

    year = node.metadata.get(YEAR)

    # --- tmdb_id shortcut: skip show search when already identified ---
    existing_tmdb_id = node.metadata.get(TMDB_ID)
    if existing_tmdb_id is not None:
        media_type = node.metadata.get(MEDIA_TYPE)
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
                params,
                show_fields,
                cache=cache,
                client=client,
                post_update=_post,
                can_stage=can_stage,
            )
            return
        # Movie already identified -- nothing more to fetch
        return

    # Stage 1: search for movie/show
    if cache is not None:
        search_key = ("search", title.lower(), year)
        search_results = cache.get_or_fetch(
            search_key,
            lambda: tmdb.search_multi(
                title,
                params.token,
                year=year,
                language=params.language,
                client=client,
                max_results=params.max_results,
                max_retries=params.tmdb_retries,
            ),
        )
    else:
        search_results = tmdb.search_multi(
            title,
            params.token,
            year=year,
            language=params.language,
            client=client,
            max_results=params.max_results,
            max_retries=params.tmdb_retries,
        )

    if not search_results:
        return

    # Create candidates for each search result
    tmdb_candidates: list[Candidate] = []
    for i, sr in enumerate(search_results[: params.max_results]):
        sim = compute_similarity(node.metadata, sr)
        cand = Candidate(
            name=f"TMDB #{i + 1}",
            metadata=dict(sr),
            score=sim,
        )
        tmdb_candidates.append(cand)

    # Sort by similarity for should_auto_accept (expects descending order)
    tmdb_candidates.sort(key=lambda c: c.score, reverse=True)
    for i, cand in enumerate(tmdb_candidates):
        cand.name = f"TMDB #{i + 1}"
    similarities = [c.score for c in tmdb_candidates]
    best = tmdb_candidates[0]

    logger.debug(
        "%s: candidates=%s",
        node.path.name,
        [(c.name, c.metadata.get(TITLE), f"{c.score:.2f}") for c in tmdb_candidates],
    )

    if should_auto_accept(similarities, min_score=params.min_score, min_prominence=params.min_prominence):
        # Auto-accept: apply non-empty fields to metadata
        # Snapshot metadata before dispatching -- the dict may be mutated later
        _best_metadata = dict(best.metadata)

        # Check if merged metadata would fill the template
        _stageable = True
        if can_stage is not None:
            merged = {**node.metadata, **{k: v for k, v in _best_metadata.items() if v is not None}}
            if not can_stage(node, merged):
                logger.debug("%s: auto-accept skipped, template fields incomplete", node.path.name)
                _stageable = False

        # Apply best metadata (always), stage only if template is complete
        _post(_make_metadata_updater(node, _best_metadata, stage=_stageable))

        # Always add show/movie-level candidates (invariant #1)
        _post(_make_candidates_updater(node, list(tmdb_candidates)))

        # Stage 2: if TV show, fetch episodes (which add their own candidates)
        if best.metadata.get(MEDIA_TYPE) == MEDIA_TYPE_EPISODE:
            _query_episodes(
                node,
                params,
                best.metadata,
                cache=cache,
                client=client,
                post_update=_post,
                can_stage=can_stage,
            )

        return

    # Add show-level TMDB candidates (not episode candidates yet)
    _post(_make_candidates_updater(node, list(tmdb_candidates)))


def _query_episodes(
    node: FileNode,
    params: PipelineParams,
    show_fields: dict,
    cache: _TmdbCache | None = None,
    client: httpx.Client | None = None,
    post_update: Callable[[Callable[[], None]], None] | None = None,
    can_stage: Callable[[FileNode, dict], bool] | None = None,
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
            lambda: tmdb.get_show(
                show_id,
                params.token,
                language=params.language,
                client=client,
                max_retries=params.tmdb_retries,
            ),
        )
    else:
        show_info = tmdb.get_show(
            show_id,
            params.token,
            language=params.language,
            client=client,
            max_retries=params.tmdb_retries,
        )
    if not show_info:
        return

    available_seasons = show_info.get("seasons", [])
    query_season = node.metadata.get(SEASON)

    # Try the query season first, then others
    seasons_to_try: list[int] = []
    if query_season is not None and query_season in available_seasons:
        seasons_to_try.append(query_season)
    # Add remaining seasons
    for s in available_seasons:
        if s not in seasons_to_try:
            seasons_to_try.append(s)

    all_episode_candidates: list[Candidate] = []

    for season_num in seasons_to_try:
        if cache is not None:
            episodes = cache.get_or_fetch(
                ("episodes", show_id, season_num),
                lambda sn=season_num: tmdb.get_season_episodes(
                    show_id,
                    sn,
                    params.token,
                    show_title=show_title,
                    show_year=show_year,
                    language=params.language,
                    client=client,
                    max_retries=params.tmdb_retries,
                ),
            )
        else:
            episodes = tmdb.get_season_episodes(
                show_id,
                season_num,
                params.token,
                show_title=show_title,
                show_year=show_year,
                language=params.language,
                client=client,
                max_retries=params.tmdb_retries,
            )

        for ep in episodes:
            sim = compute_episode_similarity(node.metadata, ep)
            cand = Candidate(
                name=f"TMDB #{len(all_episode_candidates) + 1}",
                metadata=dict(ep),
                score=sim,
            )
            all_episode_candidates.append(cand)

    # Keep top max_results episode candidates by score
    all_episode_candidates.sort(key=lambda c: c.score, reverse=True)
    top_candidates = all_episode_candidates[: params.max_results]

    # Re-number them
    for i, cand in enumerate(top_candidates):
        cand.name = f"TMDB #{i + 1}"

    # Auto-apply episode only if confident; otherwise just add candidates for curation
    ep_similarities = [c.score for c in top_candidates]
    _top_copy = list(top_candidates)

    if should_auto_accept(ep_similarities, min_score=params.min_score):
        _best_metadata = dict(top_candidates[0].metadata)

        # Check if merged metadata would fill the template
        stage = True
        if can_stage is not None:
            merged = {**node.metadata, **{k: v for k, v in _best_metadata.items() if v is not None}}
            if not can_stage(node, merged):
                logger.debug("%s: episode auto-accept skipped, template fields incomplete", node.path.name)
                stage = False

        _post(_make_metadata_updater(node, _best_metadata, stage=stage))
        _post(_make_candidates_updater(node, _top_copy))
    else:
        _post(_make_candidates_updater(node, _top_copy))
