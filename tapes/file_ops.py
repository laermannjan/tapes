"""File operations: copy, move, link with dry-run support."""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Callable
from pathlib import Path

_COPY_BUFSIZE = 1024 * 1024  # 1 MB


def _sha256(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _copy_and_hash(
    src: Path,
    dest: Path,
    progress_callback: Callable[[int, int], None] | None = None,
) -> str:
    """Copy *src* to *dest* while computing SHA-256. Returns hex digest."""
    total = src.stat().st_size
    h = hashlib.sha256()
    copied = 0
    with src.open("rb") as fsrc, dest.open("wb") as fdst:
        while True:
            buf = fsrc.read(_COPY_BUFSIZE)
            if not buf:
                break
            fdst.write(buf)
            h.update(buf)
            copied += len(buf)
            if progress_callback is not None:
                progress_callback(copied, total)
    shutil.copystat(src, dest)
    return h.hexdigest()


def process_file(
    src: Path,
    dest: Path,
    operation: str,
    dry_run: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
) -> str:
    """Process a single file with the given operation.

    Args:
        src: Source file path.
        dest: Destination file path.
        operation: One of "copy", "move", "link" (symlink), "hardlink".
        dry_run: If True, describe what would happen without doing it.

    Returns:
        A message describing what was done (or would be done).

    Raises:
        FileExistsError: If dest already exists.
        ValueError: If operation is not recognized.
    """
    if dest.exists():
        raise FileExistsError(f"Destination already exists: {dest}")

    if dry_run:
        return f"[dry-run] Would {operation} {src} -> {dest}"

    dest.parent.mkdir(parents=True, exist_ok=True)

    if operation == "copy":
        _copy_and_hash(src, dest, progress_callback)
        return f"Copied {src} -> {dest}"
    if operation == "move":
        src_hash = _copy_and_hash(src, dest, progress_callback)
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
        import os

        os.link(src, dest)
        return f"Hardlinked {dest} -> {src}"
    raise ValueError(f"Unknown operation: {operation!r}")


def process_staged(
    files: list[tuple[Path, Path]],
    operation: str,
    dry_run: bool = False,
) -> list[str]:
    """Process a list of (source, destination) file pairs.

    Continues on error for individual files, including the error
    message in the results list.

    Args:
        files: List of (source, destination) path pairs.
        operation: One of "copy", "move", "link", "hardlink".
        dry_run: If True, describe what would happen without doing it.

    Returns:
        List of result messages (one per file).
    """
    results: list[str] = []
    for src, dest in files:
        try:
            msg = process_file(src, dest, operation, dry_run=dry_run)
            results.append(msg)
        except Exception as exc:  # noqa: BLE001
            results.append(f"Error processing {src}: {exc}")
    return results
