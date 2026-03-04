import hashlib
import shutil
from pathlib import Path


def copy_verify(src: Path, dst: Path) -> None:
    """Copy src to dst, then verify SHA-256 checksum. Raises IOError on mismatch."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    src_hash = _sha256(src)
    shutil.copy2(src, dst)
    dst_hash = _sha256(dst)
    if src_hash != dst_hash:
        dst.unlink(missing_ok=True)
        raise IOError(f"Checksum mismatch after copy: {src} → {dst}")


def safe_rename(src: Path, dst: Path) -> None:
    """
    Rename a file. Uses os.rename (atomic on same filesystem).
    Falls back to copy_verify + delete for cross-filesystem moves.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        src.rename(dst)
    except OSError:
        copy_verify(src, dst)
        src.unlink()


def move_file(src: Path, dst: Path, verify: bool = True) -> None:
    """Move src to dst. verify=True forces copy-verify-delete even on same filesystem."""
    if verify:
        copy_verify(src, dst)
        src.unlink()
    else:
        safe_rename(src, dst)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()
