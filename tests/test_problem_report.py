"""Help → Report a Problem (issue #226): Qt-free report building."""

from urllib.parse import parse_qs, urlparse

from djmidi import problem_report
from djmidi.problem_report import (
    MAX_INLINE_URL_LENGTH,
    ReportContext,
    build_report_text,
    collect_context,
    read_log_tail,
    report_issue_url,
    sanitize_text,
)


def _query(url):
    return {key: values[0] for key, values in parse_qs(urlparse(url).query).items()}


def test_sanitize_rewrites_the_home_directory_to_tilde():
    text = "Opened /Users/bob/Music/set.xml and /Users/bob"
    assert sanitize_text(text, home="/Users/bob") == "Opened ~/Music/set.xml and ~"


def test_sanitize_does_not_eat_a_longer_user_name():
    assert sanitize_text("/opt/bobby/x", home="/opt/bob") == "/opt/bobby/x"


def test_sanitize_hides_other_users_and_platform_homes():
    text = "/Users/alice/a.xml /home/carol/b.tsi C:\\Users\\Dave\\c.xml"
    assert sanitize_text(text, home="/nonexistent") == "~/a.xml ~/b.tsi ~\\c.xml"


def test_read_log_tail_keeps_only_the_last_lines(tmp_path):
    log = tmp_path / "djmidi.log"
    log.write_text("".join(f"line {i}\n" for i in range(100)), encoding="utf-8")
    assert read_log_tail(log, 3) == ["line 97", "line 98", "line 99"]


def test_read_log_tail_is_empty_without_a_readable_log(tmp_path):
    assert read_log_tail(None) == []
    assert read_log_tail(tmp_path / "missing.log") == []
    assert read_log_tail(tmp_path / "missing.log", 0) == []


def test_collect_context_sanitizes_log_and_fills_versions(tmp_path):
    home = tmp_path / "home"
    log = tmp_path / "djmidi.log"
    log.write_text(f"INFO loaded {home}/Music/set.xml\n", encoding="utf-8")
    context = collect_context(
        app_version="1.2.3",
        qt_version="6.10",
        controller_plugins=["DDJ-XP2"],
        software_plugins=["Serato DJ Pro"],
        log_path=log,
        home=home,
    )
    assert context.app_version == "1.2.3"
    assert context.qt_version == "6.10"
    assert context.python_version
    assert context.os_name
    assert context.controller_plugins == ("DDJ-XP2",)
    assert context.log_lines == ("INFO loaded ~/Music/set.xml",)


def test_collect_context_marks_unknown_versions():
    context = collect_context(app_version=None)
    assert context.app_version == "unknown"
    assert context.qt_version == "unknown"
    assert context.log_lines == ()


def test_report_text_lists_environment_and_log():
    context = ReportContext(
        app_version="1.2.3",
        os_name="macOS 15 (arm64)",
        python_version="3.14.0",
        qt_version="6.10",
        controller_plugins=("DDJ-XP2", "XDJ-XZ"),
        software_plugins=(),
        log_lines=("a", "b"),
    )
    text = build_report_text(context, "It crashed")
    assert "It crashed" in text
    assert "| App version | 1.2.3 |" in text
    assert "| Controller plugins | DDJ-XP2, XDJ-XZ |" in text
    assert "| Software plugins | _(none)_ |" in text
    assert "```\na\nb\n```" in text


def test_report_text_without_log_says_so():
    assert "_(no log available)_" in build_report_text(ReportContext())


def test_short_report_is_inlined_in_the_issue_url():
    url, inlined = report_issue_url("Crash on save", "body text")
    assert inlined
    assert url.startswith(f"https://github.com/{problem_report.REPORT_REPO}/issues/new?")
    assert _query(url) == {"labels": "bug", "title": "Crash on save", "body": "body text"}


def test_blank_title_falls_back_to_the_default():
    url, _ = report_issue_url("   ", "body")
    assert _query(url)["title"] == problem_report.DEFAULT_TITLE.strip()


def test_long_log_is_replaced_by_a_paste_placeholder():
    context = ReportContext(app_version="1", log_lines=tuple("x" * 200 for _ in range(60)))
    body = build_report_text(context, "Describe")
    url, inlined = report_issue_url("t", body)
    assert not inlined
    assert len(url) <= MAX_INLINE_URL_LENGTH
    query_body = _query(url)["body"]
    assert "Describe" in query_body
    assert "clipboard" in query_body
    assert "x" * 200 not in query_body


def test_overlong_body_without_log_falls_back_to_the_placeholder_only():
    url, inlined = report_issue_url("t", "y" * 10_000)
    assert not inlined
    assert "clipboard" in _query(url)["body"]
