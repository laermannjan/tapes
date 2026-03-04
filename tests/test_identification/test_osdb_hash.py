from tapes.identification.osdb_hash import compute_hash


def test_hash_small_file(tmp_path):
    f = tmp_path / "test.mkv"
    f.write_bytes(b"\x00" * 1024)
    h = compute_hash(f)
    assert isinstance(h, str)
    assert len(h) == 16  # 64-bit hash as hex string


def test_hash_deterministic(tmp_path):
    f = tmp_path / "test.mkv"
    f.write_bytes(b"\xAB" * 65536 * 2)
    assert compute_hash(f) == compute_hash(f)


def test_hash_differs_by_content(tmp_path):
    f1 = tmp_path / "a.mkv"
    f2 = tmp_path / "b.mkv"
    f1.write_bytes(b"\x00" * 1024)
    f2.write_bytes(b"\xFF" * 1024)
    assert compute_hash(f1) != compute_hash(f2)
