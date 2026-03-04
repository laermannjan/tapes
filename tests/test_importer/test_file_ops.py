import pytest
from pathlib import Path
from tapes.importer.file_ops import copy_verify, move_file, safe_rename


def test_copy_verify_copies_file(tmp_path):
    src = tmp_path / "src.mkv"
    src.write_bytes(b"video data")
    dst = tmp_path / "dest" / "copy.mkv"

    copy_verify(src, dst)

    assert dst.exists()
    assert dst.read_bytes() == b"video data"
    assert src.exists()  # original still present


def test_copy_verify_raises_on_mismatch(tmp_path, monkeypatch):
    src = tmp_path / "src.mkv"
    src.write_bytes(b"original")
    dst = tmp_path / "dst.mkv"

    # Simulate checksum mismatch by patching _sha256 to return different hashes
    import tapes.importer.file_ops as fo
    call_count = {"n": 0}
    real_sha256 = fo._sha256

    def fake_sha256(path):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return "aaa"
        return "bbb"

    monkeypatch.setattr(fo, "_sha256", fake_sha256)

    with pytest.raises(IOError, match="Checksum mismatch"):
        copy_verify(src, dst)

    assert not dst.exists()  # cleaned up


def test_move_file_with_verify(tmp_path):
    src = tmp_path / "src.mkv"
    src.write_bytes(b"data")
    dst = tmp_path / "sub" / "moved.mkv"

    move_file(src, dst, verify=True)

    assert dst.read_bytes() == b"data"
    assert not src.exists()  # removed


def test_move_file_without_verify(tmp_path):
    src = tmp_path / "src.mkv"
    src.write_bytes(b"data")
    dst = tmp_path / "sub" / "moved.mkv"

    move_file(src, dst, verify=False)

    assert dst.read_bytes() == b"data"
    assert not src.exists()


def test_safe_rename(tmp_path):
    src = tmp_path / "a.mkv"
    src.write_bytes(b"rename me")
    dst = tmp_path / "sub" / "b.mkv"

    safe_rename(src, dst)

    assert dst.read_bytes() == b"rename me"
    assert not src.exists()
