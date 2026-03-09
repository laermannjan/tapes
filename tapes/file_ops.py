"""File operations: copy, move, link with dry-run support."""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

_COPY_BUFSIZE = 1024 * 1024  # 1 MB


class OperationCancelledError(Exception):
    """Raised when a file operation is cancelled by the user."""


def _sha256(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _copy_and_hash(
    src: Path,
    dest: Path,
    progress_callback: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> str:
    """Copy *src* to *dest* while computing SHA-256. Returns hex digest.

    If *cancelled* returns ``True`` the partial destination is removed
    and :class:`OperationCancelledError` is raised.
    """
    total = src.stat().st_size
    h = hashlib.sha256()
    copied = 0
    try:
        with src.open("rb") as fsrc, dest.open("wb") as fdst:
            while True:
                if cancelled is not None and cancelled():
                    raise OperationCancelledError  # noqa: TRY301
                buf = fsrc.read(_COPY_BUFSIZE)
                if not buf:
                    break
                fdst.write(buf)
                h.update(buf)
                copied += len(buf)
                if progress_callback is not None:
                    progress_callback(copied, total)
    except OperationCancelledError:
        dest.unlink(missing_ok=True)
        raise
    try:
        shutil.copystat(src, dest)
    except OSError:
        logger.debug("Could not copy file metadata from %s to %s", src, dest)
    return h.hexdigest()


def process_file(
    src: Path,
    dest: Path,
    operation: str,
    dry_run: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> str:
    """Process a single file with the given operation.

    Args:
        src: Source file path.
        dest: Destination file path.
        operation: One of "copy", "move", "link" (symlink), "hardlink".
        dry_run: If True, describe what would happen without doing it.
        cancelled: Callable returning ``True`` to abort mid-copy.

    Returns:
        A message describing what was done (or would be done).

    Raises:
        FileExistsError: If dest already exists.
        ValueError: If operation is not recognized.
        OperationCancelledError: If *cancelled* returns ``True`` during copy.
    """
    if dest.exists():
        raise FileExistsError(f"Destination already exists: {dest}")

    if dry_run:
        return f"[dry-run] Would {operation} {src} -> {dest}"

    dest.parent.mkdir(parents=True, exist_ok=True)

    if operation == "copy":
        _copy_and_hash(src, dest, progress_callback, cancelled=cancelled)
        return f"Copied {src} -> {dest}"
    if operation == "move":
        src_hash = _copy_and_hash(src, dest, progress_callback, cancelled=cancelled)
        if _sha256(dest) == src_hash:
            src.unlink()
        else:
            dest.unlink()
            raise OSError(f"SHA-256 mismatch after copy: {src} -> {dest} (dest removed)")
        return f"Moved {src} -> {dest}"
    if operation == "link":
        dest.symlink_to(src.resolve())
        return f"Linked {dest} -> {src.resolve()}"
    if operation == "hardlink":
        os.link(src, dest)
        return f"Hardlinked {dest} -> {src}"
    raise ValueError(f"Unknown operation: {operation!r}")


def process_staged(
    files: list[tuple[Path, Path]],
    operation: str,
    dry_run: bool = False,
    on_file_start: Callable[[int, int, Path, Path], None] | None = None,
    on_file_progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
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

    Returns:
        List of result messages (one per file).
    """
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
            )
            results.append(msg)
        except OperationCancelledError:
            break
        except Exception:
            logger.exception("Error processing %s", src)
            results.append(f"Error processing {src}")
    return results
