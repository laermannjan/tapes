"""Tests for interactive prompt logic and default-action determination."""

from unittest.mock import MagicMock

from tapes.importer.interactive import InteractivePrompt, PromptAction


def _candidate(confidence):
    c = MagicMock()
    c.confidence = confidence
    return c


# --- Default action tests based on design doc table ---


def test_accept_on_enter_high_confidence():
    prompt = InteractivePrompt(candidates=[_candidate(0.86)])
    assert prompt.default_action == PromptAction.ACCEPT


def test_accept_when_gap_large():
    """Single strong match with big gap to #2."""
    prompt = InteractivePrompt(candidates=[_candidate(0.70), _candidate(0.45)])
    assert prompt.default_action == PromptAction.ACCEPT


def test_search_on_enter_low_confidence():
    """Single match below 0.75 with no big gap."""
    prompt = InteractivePrompt(candidates=[_candidate(0.55)])
    assert prompt.default_action == PromptAction.SEARCH


def test_search_on_enter_ambiguous():
    """Multiple candidates close together."""
    prompt = InteractivePrompt(candidates=[_candidate(0.65), _candidate(0.60)])
    assert prompt.default_action == PromptAction.SEARCH


def test_search_on_enter_no_match():
    prompt = InteractivePrompt(candidates=[])
    assert prompt.default_action == PromptAction.SEARCH


def test_skip_on_enter_after_failed_search():
    prompt = InteractivePrompt(candidates=[], after_failed_search=True)
    assert prompt.default_action == PromptAction.SKIP


def test_search_results_dominant():
    """After search, one result dominates."""
    prompt = InteractivePrompt(
        candidates=[_candidate(0.90), _candidate(0.65)],
        is_search_result=True,
    )
    assert prompt.default_action == PromptAction.ACCEPT


def test_search_results_close():
    """After search, results too close - no default."""
    prompt = InteractivePrompt(
        candidates=[_candidate(0.70), _candidate(0.60)],
        is_search_result=True,
    )
    assert prompt.default_action is None


# --- Edge cases ---


def test_accept_at_exact_threshold():
    """Confidence exactly at STRONG_CONFIDENCE threshold."""
    prompt = InteractivePrompt(candidates=[_candidate(0.75)])
    assert prompt.default_action == PromptAction.ACCEPT


def test_accept_gap_exactly_at_threshold():
    """Gap exactly at GAP_THRESHOLD."""
    prompt = InteractivePrompt(candidates=[_candidate(0.60), _candidate(0.40)])
    assert prompt.default_action == PromptAction.ACCEPT


def test_search_gap_just_below_threshold():
    """Gap just below GAP_THRESHOLD, confidence below strong."""
    prompt = InteractivePrompt(candidates=[_candidate(0.60), _candidate(0.41)])
    assert prompt.default_action == PromptAction.SEARCH


def test_search_results_single_candidate():
    """Search results with only one candidate - gap to 0 is the confidence itself."""
    prompt = InteractivePrompt(
        candidates=[_candidate(0.50)],
        is_search_result=True,
    )
    assert prompt.default_action == PromptAction.ACCEPT


def test_prompt_action_values():
    """PromptAction enum has expected string values."""
    assert PromptAction.ACCEPT == "accept"
    assert PromptAction.SEARCH == "search"
    assert PromptAction.SKIP == "skip"
    assert PromptAction.MANUAL == "manual"
    assert PromptAction.QUIT == "quit"


# --- display_prompt tests ---

import re
from io import StringIO
from rich.console import Console
from tapes.importer.interactive import display_prompt
from tapes.metadata.base import SearchResult

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _search_result(title="Dune", year=2021, tmdb_id=438631, confidence=0.94,
                   media_type="movie", **kwargs):
    return SearchResult(
        tmdb_id=tmdb_id, title=title, year=year,
        media_type=media_type, confidence=confidence, **kwargs,
    )


def test_display_single_match_shows_title_and_confidence():
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    prompt = InteractivePrompt(candidates=[_search_result()])
    display_prompt(con, prompt, index=1, total=5, filename="Dune.2021.2160p.BluRay.mkv",
                   source="filename")
    output = _strip_ansi(buf.getvalue())
    assert "Dune (2021)" in output
    assert "tmdb:438631" in output
    assert "94%" in output
    assert "[1/5]" in output
    assert "filename" in output


def test_display_accept_is_default_for_strong_match():
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    prompt = InteractivePrompt(candidates=[_search_result(confidence=0.86)])
    display_prompt(con, prompt, index=2, total=8, filename="Dune.2021.mkv",
                   source="filename")
    output = _strip_ansi(buf.getvalue())
    assert "accept" in output.lower()


def test_display_no_match():
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    prompt = InteractivePrompt(candidates=[])
    display_prompt(con, prompt, index=3, total=10, filename="unknown_file.mkv")
    output = _strip_ansi(buf.getvalue())
    assert "no match found" in output.lower()


def test_display_multiple_candidates_numbered():
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    candidates = [
        _search_result(title="Blade Runner", year=1982, tmdb_id=78, confidence=0.62),
        _search_result(title="Blade Runner 2049", year=2017, tmdb_id=335984, confidence=0.55),
    ]
    prompt = InteractivePrompt(candidates=candidates)
    display_prompt(con, prompt, index=1, total=3, filename="Blade.Runner.mkv",
                   source="filename")
    output = _strip_ansi(buf.getvalue())
    assert "1." in output
    assert "2." in output
    assert "Blade Runner (1982)" in output
    assert "Blade Runner 2049 (2017)" in output


def test_display_no_source_omits_bracket():
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    prompt = InteractivePrompt(candidates=[_search_result()])
    display_prompt(con, prompt, index=1, total=1, filename="Dune.mkv")
    output = _strip_ansi(buf.getvalue())
    # source brackets should not appear when source is None
    assert "[filename]" not in output


def test_display_action_keys_shown():
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    prompt = InteractivePrompt(candidates=[_search_result()])
    display_prompt(con, prompt, index=1, total=1, filename="Dune.mkv")
    output = _strip_ansi(buf.getvalue())
    assert "[s]earch" in output.lower()
    assert "[x]skip" in output.lower()
    assert "[q]uit" in output.lower()


def test_display_skip_is_default_after_failed_search():
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    prompt = InteractivePrompt(candidates=[], after_failed_search=True)
    display_prompt(con, prompt, index=1, total=1, filename="mystery.mkv")
    output = _strip_ansi(buf.getvalue())
    assert "skip" in output.lower()


def test_display_year_none():
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    prompt = InteractivePrompt(candidates=[_search_result(year=None)])
    display_prompt(con, prompt, index=1, total=1, filename="Dune.mkv")
    output = _strip_ansi(buf.getvalue())
    assert "Dune" in output
    # Should not show "(None)"
    assert "(None)" not in output


# --- Companion file display tests (Task 3) ---

from pathlib import Path
from tapes.companions.classifier import CompanionFile, Category


def test_display_shows_companion_files():
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    prompt = InteractivePrompt(candidates=[_search_result()])
    companions = [
        CompanionFile(Path("/src/Dune.2021.en.srt"), Category.SUBTITLE, True, Path("Dune.2021.en.srt")),
        CompanionFile(Path("/src/poster.jpg"), Category.ARTWORK, True, Path("poster.jpg")),
        CompanionFile(Path("/src/sample.mkv"), Category.SAMPLE, False, Path("sample.mkv")),
    ]
    display_prompt(con, prompt, index=1, total=1, filename="Dune.2021.mkv",
                   source="filename", companions=companions)
    output = _strip_ansi(buf.getvalue())
    assert "subtitle" in output
    assert "Dune.2021.en.srt" in output
    assert "artwork" in output
    assert "poster.jpg" in output
    assert "sample" in output


def test_display_edit_key_only_when_companions():
    # With companions
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    companions = [CompanionFile(Path("/src/sub.srt"), Category.SUBTITLE, True, Path("sub.srt"))]
    prompt = InteractivePrompt(candidates=[_search_result()])
    display_prompt(con, prompt, index=1, total=1, filename="movie.mkv",
                   source="filename", companions=companions)
    assert "[e]dit" in _strip_ansi(buf.getvalue()).lower()

    # Without companions
    buf2 = StringIO()
    con2 = Console(file=buf2, force_terminal=True, no_color=True, width=100)
    display_prompt(con2, prompt, index=1, total=1, filename="movie.mkv", source="filename")
    assert "[e]dit" not in _strip_ansi(buf2.getvalue()).lower()


def test_display_companion_markers():
    """move_by_default=True shows +, False shows ?."""
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    prompt = InteractivePrompt(candidates=[_search_result()])
    companions = [
        CompanionFile(Path("/src/sub.srt"), Category.SUBTITLE, True, Path("sub.srt")),
        CompanionFile(Path("/src/sample.mkv"), Category.SAMPLE, False, Path("sample.mkv")),
    ]
    display_prompt(con, prompt, index=1, total=1, filename="movie.mkv",
                   source="filename", companions=companions)
    output = _strip_ansi(buf.getvalue())
    # + for move_by_default=True, ? for False
    assert "+" in output
    assert "?" in output


# --- Companion file checklist editor tests (Task 4) ---

from tapes.importer.interactive import edit_companions


def test_edit_companions_returns_selected():
    from unittest.mock import patch
    video = CompanionFile(Path("/src/movie.mkv"), Category.VIDEO, True, Path("movie.mkv"))
    sub = CompanionFile(Path("/src/movie.en.srt"), Category.SUBTITLE, True, Path("movie.en.srt"))
    sample = CompanionFile(Path("/src/sample.mkv"), Category.SAMPLE, False, Path("sample.mkv"))

    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    # Toggle sample on (index 2), then confirm
    with patch("tapes.importer.interactive._read_key", side_effect=["2", "\r"]):
        result = edit_companions(con, [video, sub, sample])

    assert video in result
    assert sub in result
    assert sample in result


def test_edit_companions_video_locked():
    from unittest.mock import patch
    video = CompanionFile(Path("/src/movie.mkv"), Category.VIDEO, True, Path("movie.mkv"))
    sub = CompanionFile(Path("/src/sub.srt"), Category.SUBTITLE, True, Path("sub.srt"))

    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    # Try to toggle video (index 0), then confirm
    with patch("tapes.importer.interactive._read_key", side_effect=["0", "\r"]):
        result = edit_companions(con, [video, sub])

    assert video in result  # still selected


def test_edit_companions_toggle_off():
    from unittest.mock import patch
    video = CompanionFile(Path("/src/movie.mkv"), Category.VIDEO, True, Path("movie.mkv"))
    sub = CompanionFile(Path("/src/sub.srt"), Category.SUBTITLE, True, Path("sub.srt"))

    buf = StringIO()
    con = Console(file=buf, force_terminal=True, no_color=True, width=100)
    # Toggle subtitle off (index 1), then confirm
    with patch("tapes.importer.interactive._read_key", side_effect=["1", "\r"]):
        result = edit_companions(con, [video, sub])

    assert video in result
    assert sub not in result


# --- read_action tests (Task 5) ---

from unittest.mock import patch
from tapes.importer.interactive import read_action


def test_read_action_enter_returns_default():
    prompt = InteractivePrompt(candidates=[_search_result(confidence=0.86)])
    with patch("tapes.importer.interactive._read_key", return_value="\r"):
        action = read_action(prompt)
    assert action == PromptAction.ACCEPT


def test_read_action_s_returns_search():
    prompt = InteractivePrompt(candidates=[_search_result()])
    with patch("tapes.importer.interactive._read_key", return_value="s"):
        action = read_action(prompt)
    assert action == PromptAction.SEARCH


def test_read_action_x_returns_skip():
    prompt = InteractivePrompt(candidates=[_search_result()])
    with patch("tapes.importer.interactive._read_key", return_value="x"):
        action = read_action(prompt)
    assert action == PromptAction.SKIP


def test_read_action_q_returns_quit():
    prompt = InteractivePrompt(candidates=[_search_result()])
    with patch("tapes.importer.interactive._read_key", return_value="q"):
        action = read_action(prompt)
    assert action == PromptAction.QUIT


def test_read_action_m_returns_manual():
    prompt = InteractivePrompt(candidates=[_search_result()])
    with patch("tapes.importer.interactive._read_key", return_value="m"):
        action = read_action(prompt)
    assert action == PromptAction.MANUAL


def test_read_action_number_selects_candidate():
    candidates = [
        _search_result("Blade Runner", 1982, tmdb_id=78, confidence=0.62),
        _search_result("Blade Runner 2049", 2017, tmdb_id=335984, confidence=0.51),
    ]
    prompt = InteractivePrompt(candidates=candidates)
    with patch("tapes.importer.interactive._read_key", return_value="2"):
        action = read_action(prompt)
    assert action == (PromptAction.ACCEPT, 1)  # 0-based index


def test_read_action_invalid_key_retries():
    prompt = InteractivePrompt(candidates=[_search_result()])
    with patch("tapes.importer.interactive._read_key", side_effect=["z", "s"]):
        action = read_action(prompt)
    assert action == PromptAction.SEARCH


def test_read_action_enter_no_default_retries():
    # Search results too close - no default
    candidates = [_search_result(confidence=0.70), _search_result(confidence=0.60)]
    prompt = InteractivePrompt(candidates=candidates, is_search_result=True)
    with patch("tapes.importer.interactive._read_key", side_effect=["\r", "1"]):
        action = read_action(prompt)
    assert action == (PromptAction.ACCEPT, 0)


def test_read_action_e_returns_edit():
    prompt = InteractivePrompt(candidates=[_search_result()])
    with patch("tapes.importer.interactive._read_key", return_value="e"):
        action = read_action(prompt, has_companions=True)
    assert action == "edit"


def test_read_action_e_ignored_without_companions():
    prompt = InteractivePrompt(candidates=[_search_result()])
    with patch("tapes.importer.interactive._read_key", side_effect=["e", "s"]):
        action = read_action(prompt, has_companions=False)
    assert action == PromptAction.SEARCH
