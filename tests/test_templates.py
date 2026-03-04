from tapes.templates.engine import render_template, sanitize_path


def test_basic_movie():
    result = render_template(
        "{title} ({year})/{title} ({year}){ext}",
        {"title": "Dune", "year": 2021, "ext": ".mkv"},
    )
    assert result == "Dune (2021)/Dune (2021).mkv"


def test_tv_episode():
    result = render_template(
        "{show}/Season {season:02d}/{show} - S{season:02d}E{episode:02d} - {episode_title}{ext}",
        {"show": "The Wire", "season": 1, "episode": 3, "episode_title": "The Buys", "ext": ".mkv"},
    )
    assert result == "The Wire/Season 01/The Wire - S01E03 - The Buys.mkv"


def test_conditional_edition_present():
    result = render_template(
        "{title} ({year}){edition: - $}{ext}",
        {"title": "Dune", "year": 2021, "edition": "Director's Cut", "ext": ".mkv"},
    )
    assert result == "Dune (2021) - Director's Cut.mkv"


def test_conditional_edition_absent():
    result = render_template(
        "{title} ({year}){edition: - $}{ext}",
        {"title": "Dune", "year": 2021, "ext": ".mkv"},
    )
    assert result == "Dune (2021).mkv"


def test_conditional_none_value():
    result = render_template(
        "{title}{edition: - $}{ext}",
        {"title": "Dune", "edition": None, "ext": ".mkv"},
    )
    assert result == "Dune.mkv"


def test_missing_field_renders_empty():
    result = render_template("{title} ({year}){ext}", {"title": "Dune", "ext": ".mkv"})
    assert result == "Dune ().mkv"


def test_sanitize_colon():
    assert sanitize_path("Mission: Impossible.mkv", {": ": " - "}) == "Mission - Impossible.mkv"


def test_slash_in_title_replaced_via_render():
    # The replace table is applied to field VALUES during render, not to
    # path separators. A title like "AC/DC" gets its "/" replaced before
    # it's embedded into the path, so path separators are never affected.
    result = render_template(
        "Movies/{title}{ext}",
        {"title": "AC/DC Live", "ext": ".mkv"},
        replace={"/": "-"},
    )
    assert result == "Movies/AC-DC Live.mkv"


def test_sanitize_windows_illegal_chars():
    result = sanitize_path('file<with>illegal:chars?.mkv', {})
    for ch in '<>:"|?*':
        assert ch not in result


def test_sanitize_windows_reserved_name():
    result = sanitize_path("CON.mkv", {})
    assert result != "CON.mkv"


def test_render_uses_replace_table():
    result = render_template(
        "{title}{ext}",
        {"title": "Mission: Impossible", "ext": ".mkv"},
        replace={": ": " - "},
    )
    assert result == "Mission - Impossible.mkv"
