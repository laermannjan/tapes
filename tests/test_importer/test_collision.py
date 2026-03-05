from tapes.importer.collision import detect_collisions, CollisionType


def test_template_collision_detected():
    planned = [
        {"src_path": "Dune.4K.mkv", "dest": "Dune (2021)/Dune (2021).mkv", "resolution": "2160p"},
        {"src_path": "Dune.1080p.mkv", "dest": "Dune (2021)/Dune (2021).mkv", "resolution": "1080p"},
    ]
    collisions = detect_collisions(planned, existing_paths=set())
    assert len(collisions) == 1
    assert collisions[0].type == CollisionType.TEMPLATE_ONLY
    assert len(collisions[0].files) == 2


def test_no_collision_when_unique():
    planned = [
        {"src_path": "Dune.mkv", "dest": "Dune (2021)/Dune (2021).mkv"},
        {"src_path": "Arrival.mkv", "dest": "Arrival (2016)/Arrival (2016).mkv"},
    ]
    assert detect_collisions(planned, existing_paths=set()) == []


def test_likely_duplicate_detected():
    planned = [
        {"src_path": "dune-2021.mkv", "dest": "Dune (2021)/Dune (2021).mkv",
         "resolution": "2160p", "hdr": 1, "size": 22_000_000_000},
        {"src_path": "Dune.2021.mkv", "dest": "Dune (2021)/Dune (2021).mkv",
         "resolution": "2160p", "hdr": 1, "size": 21_900_000_000},
    ]
    collisions = detect_collisions(planned, existing_paths=set())
    assert collisions[0].type == CollisionType.LIKELY_DUPLICATE


def test_existing_path_collision():
    planned = [
        {"src_path": "Dune.mkv", "dest": "Dune (2021)/Dune (2021).mkv"},
    ]
    existing = {"Dune (2021)/Dune (2021).mkv"}
    collisions = detect_collisions(planned, existing_paths=existing)
    assert len(collisions) == 1
    assert collisions[0].type == CollisionType.TEMPLATE_ONLY


def test_empty_planned():
    assert detect_collisions([], existing_paths=set()) == []


def test_diff_fields_reported():
    planned = [
        {"src_path": "a.mkv", "dest": "Movie/Movie.mkv", "resolution": "2160p", "codec": "hevc"},
        {"src_path": "b.mkv", "dest": "Movie/Movie.mkv", "resolution": "1080p", "codec": "hevc"},
    ]
    collisions = detect_collisions(planned, existing_paths=set())
    assert "resolution" in collisions[0].diff_fields
    assert "codec" not in collisions[0].diff_fields


def test_three_way_collision():
    planned = [
        {"src_path": "a.mkv", "dest": "Movie/Movie.mkv", "resolution": "2160p"},
        {"src_path": "b.mkv", "dest": "Movie/Movie.mkv", "resolution": "1080p"},
        {"src_path": "c.mkv", "dest": "Movie/Movie.mkv", "resolution": "720p"},
    ]
    collisions = detect_collisions(planned, existing_paths=set())
    assert len(collisions) == 1
    assert len(collisions[0].files) == 3


def test_multiple_destinations_collide_independently():
    planned = [
        {"src_path": "a.mkv", "dest": "Movie1/Movie1.mkv"},
        {"src_path": "b.mkv", "dest": "Movie1/Movie1.mkv"},
        {"src_path": "c.mkv", "dest": "Movie2/Movie2.mkv"},
        {"src_path": "d.mkv", "dest": "Movie2/Movie2.mkv"},
    ]
    collisions = detect_collisions(planned, existing_paths=set())
    assert len(collisions) == 2
