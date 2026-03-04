import struct
from pathlib import Path

CHUNK = 65536  # 64 KB


def compute_hash(path: Path) -> str:
    """
    Compute the OpenSubtitles movie hash.
    Hash = file_size + 64-bit checksum of first 64KB + last 64KB.
    Returns a 16-character hex string.
    Note: API lookup is deferred to post-v0.1 (see ADR-004).
    """
    size = path.stat().st_size
    hash_value = size

    with open(path, "rb") as f:
        first_chunk = f.read(CHUNK).ljust(CHUNK, b"\x00")
        last_chunk = _read_last_chunk(f, size).ljust(CHUNK, b"\x00")

    for chunk in (first_chunk, last_chunk):
        for (word,) in struct.iter_unpack("<Q", chunk):
            hash_value = (hash_value + word) & 0xFFFFFFFFFFFFFFFF

    return format(hash_value, "016x")


def _read_last_chunk(f, size: int) -> bytes:
    f.seek(max(0, size - CHUNK))
    return f.read(CHUNK)
