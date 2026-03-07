"""File operations: copy, move, link with dry-run support."""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


def _sha256(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def process_file(
    src: Path, dest: Path, operation: str, dry_run: bool = False
) -> str:
    """Process a single file with the given operation.

    Args:
        src: Source file path.
        dest: Destination file path.
        operation: One of "copy", "move", "link" (symlink).
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
        shutil.copy2(src, dest)
        return f"Copied {src} -> {dest}"
    elif operation == "move":
        src_hash = _sha256(src)
        shutil.copy2(src, dest)
        if _sha256(dest) == src_hash:
            src.unlink()
        else:
            dest.unlink()
            raise OSError(
                f"SHA-256 mismatch after copy: {src} -> {dest} (dest removed)"
            )
        return f"Moved {src} -> {dest}"
    elif operation == "link":
        dest.symlink_to(src.resolve())
        return f"Linked {dest} -> {src.resolve()}"
    else:
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
        operation: One of "copy", "move", "link".
        dry_run: If True, describe what would happen without doing it.

    Returns:
        List of result messages (one per file).
    """
    results: list[str] = []
    for src, dest in files:
        try:
            msg = process_file(src, dest, operation, dry_run=dry_run)
            results.append(msg)
        except Exception as exc:
            results.append(f"Error processing {src}: {exc}")
    return results
