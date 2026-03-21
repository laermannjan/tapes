"""File operations: copy, move, link with dry-run support."""

from __future__ import annotations

import os
import shutil
import threading
from collections.abc import Callable
from pathlib import Path

import structlog

logger = structlog.get_logger()

_POLL_INTERVAL = 0.5  # seconds between dest-size polls


class OperationCancelledError(Exception):
    """Raised when a file operation is cancelled by the user."""


def _copy(
    src: Path,
    dest: Path,
    progress_callback: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> None:
    """Copy *src* to *dest* using shutil.copy2 (kernel-optimised).

    Runs the copy in a thread and polls the destination file size to
    report approximate progress.  Cancellation is checked between polls;
    mid-file cancellation waits for the current copy to finish, then
    removes the destination.
    """
    total = src.stat().st_size
    error: BaseException | None = None

    def _do_copy() -> None:
        nonlocal error
        try:
            shutil.copy2(src, dest)
        except BaseException as exc:  # noqa: BLE001
            error = exc

    copy_thread = threading.Thread(target=_do_copy, daemon=True)
    copy_thread.start()

    while True:
        copy_thread.join(timeout=_POLL_INTERVAL)
        alive = copy_thread.is_alive()
        # Report progress (even after thread finishes, for final update)
        if progress_callback is not None:
            try:
                current = dest.stat().st_size if dest.exists() else 0
            except OSError:
                current = 0
            progress_callback(min(current, total), total)
        if not alive:
            break
        if cancelled is not None and cancelled():
            # Cannot interrupt shutil.copy2 -- wait for it to finish,
            # then clean up the destination.
            copy_thread.join()
            try:
                dest.unlink(missing_ok=True)
            except OSError:
                logger.debug("cleanup_failed", dest=str(dest), reason="cancelled")
            raise OperationCancelledError

    if error is not None:
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            logger.debug("cleanup_failed", dest=str(dest), reason="partial")
        raise error


def process_file(
    src: Path,
    dest: Path,
    operation: str,
    dry_run: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    overwrite: bool = False,
) -> str:
    """Process a single file with the given operation.

    Uses ``shutil.copy2`` which can leverage kernel-level optimisations
    (``copy_file_range``, ``sendfile``).  Progress is approximate
    (polled from destination file size).  Cancellation takes effect
    after the current file finishes.

    Args:
        src: Source file path.
        dest: Destination file path.
        operation: One of "copy", "move", "link" (symlink), "hardlink".
        dry_run: If True, describe what would happen without doing it.
        cancelled: Callable returning ``True`` to abort mid-copy.
        overwrite: If True, skip the ``dest.exists()`` guard. Used when
            conflict resolution has determined this file should replace
            an existing destination.

    Returns:
        A message describing what was done (or would be done).

    Raises:
        FileExistsError: If dest already exists and *overwrite* is False.
        ValueError: If operation is not recognized.
        OperationCancelledError: If *cancelled* returns ``True`` during copy.
    """
    if not overwrite and dest.exists():
        raise FileExistsError(f"Destination already exists: {dest}")

    if dry_run:
        return f"[dry-run] Would {operation} {src} -> {dest}"

    dest.parent.mkdir(parents=True, exist_ok=True)

    if operation == "copy":
        _copy(src, dest, progress_callback, cancelled=cancelled)
        return f"Copied {src} -> {dest}"
    if operation == "move":
        try:
            src.rename(dest)
        except OSError:
            pass  # cross-device -- fall back to copy + delete
        else:
            return f"Moved {src} -> {dest}"
        _copy(src, dest, progress_callback, cancelled=cancelled)
        src.unlink()
        return f"Moved {src} -> {dest}"
    if operation == "link":
        dest.symlink_to(src.resolve())
        return f"Linked {dest} -> {src.resolve()}"
    if operation == "hardlink":
        os.link(src, dest)
        return f"Hardlinked {dest} -> {src}"
    raise ValueError(f"Unknown operation: {operation!r}")


def delete_files(paths: list[Path], *, dry_run: bool = False) -> list[str]:
    """Delete a list of files. Returns a status message per file."""
    results: list[str] = []
    for path in paths:
        if dry_run:
            logger.info("deleted", file=path.name, dry_run=True)
            results.append(f"[dry-run] Would delete {path}")
            continue
        try:
            path.unlink()
            logger.info("deleted", file=path.name, dry_run=False)
            results.append(f"Deleted {path}")
        except FileNotFoundError:
            results.append(f"Not found: {path}")
        except OSError as e:
            results.append(f"Error deleting {path}: {e}")
    return results


def process_staged(
    files: list[tuple[Path, Path]],
    operation: str,
    dry_run: bool = False,
    on_file_start: Callable[[int, int, Path, Path], None] | None = None,
    on_file_progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    overwrite_dests: set[Path] | None = None,
) -> list[str]:
    """Process a list of (source, destination) file pairs.

    Continues on error for individual files, including the error
    message in the results list.

    Args:
        files: List of (source, destination) path pairs.
        operation: One of "copy", "move", "link", "hardlink".
        dry_run: If True, describe what would happen without doing it.
        on_file_start: Callback ``(index, total, src, dest)`` called before
            each file is processed.
        on_file_progress: Callback ``(copied_bytes, total_bytes)`` forwarded
            to :func:`process_file` for byte-level progress during copies.
        cancelled: Callable returning ``True`` to stop processing.  Checked
            between files and passed through to copy operations.
        overwrite_dests: Set of destination paths that should overwrite
            existing files (from conflict resolution).

    Returns:
        List of result messages (one per file).
    """
    _overwrite = overwrite_dests or set()
    total = len(files)
    results: list[str] = []
    for i, (src, dest) in enumerate(files):
        if cancelled is not None and cancelled():
            break
        if on_file_start is not None:
            on_file_start(i, total, src, dest)
        try:
            msg = process_file(
                src,
                dest,
                operation,
                dry_run=dry_run,
                progress_callback=on_file_progress,
                cancelled=cancelled,
                overwrite=dest in _overwrite,
            )
            logger.info("processed", file=src.name, dest=str(dest), operation=operation)
            results.append(msg)
        except OperationCancelledError:
            break
        except FileExistsError:
            logger.warning("file_exists", file=str(src), dest=str(dest))
            results.append(f"Error: {dest} already exists")
        except Exception:
            logger.error("processing_error", file=str(src), exc_info=True)  # noqa: G201
            results.append(f"Error processing {src}")
    return results
