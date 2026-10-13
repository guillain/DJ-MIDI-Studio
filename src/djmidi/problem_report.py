"""Build a "Report a problem" text and a pre-filled GitHub issue link (issue #226).

Same no-backend approach as ``catalog/community.py``: nothing is uploaded by
the app. It gathers a few environment facts (app/OS/Python/Qt versions, the
enabled plugins) and the last lines of the execution log, the user reviews
and edits that text in a preview, then the GUI copies it to the clipboard and
opens a GitHub "new issue" page with it pre-filled.

Privacy rules, applied here so they're testable without a QApplication:

- every path under a home directory is rewritten to its home-relative form
  (``/Users/<name>/Music/x.mp3`` -> ``~/Music/x.mp3``), including other
  users' homes and Windows profiles, so the account name never leaks;
- no mapping or library content is collected — only plugin names and the
  log tail, which the user sees and can trim before anything leaves the app.

Qt-free on purpose: the Qt version is passed in by the caller.
"""

from __future__ import annotations

import platform
import re
import sys
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

from djmidi.catalog.community import COMMUNITY_REPO

REPORT_REPO = COMMUNITY_REPO
REPORT_LABEL = "bug"
DEFAULT_LOG_LINES = 40
DEFAULT_TITLE = "[problem report] "
# Same browser/proxy-safe limit community.py uses; past it the log tail is
# dropped from the URL (the full text stays on the clipboard).
MAX_INLINE_URL_LENGTH = 6000

_LOG_PLACEHOLDER = (
    "<!-- The full report, including the log lines, was copied to your "
    "clipboard by the app — paste it here. -->"
)
# A home directory on macOS, Linux or Windows, followed by the user name.
_HOME_PATTERNS = (
    re.compile(r"/Users/[^/\s\"':]+"),
    re.compile(r"/home/[^/\s\"':]+"),
    re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"':]+", re.IGNORECASE),
)


@dataclass(frozen=True)
class ReportContext:
    """Everything the report says about the user's setup."""

    app_version: str = ""
    os_name: str = ""
    python_version: str = ""
    qt_version: str = ""
    controller_plugins: tuple[str, ...] = ()
    software_plugins: tuple[str, ...] = ()
    log_lines: tuple[str, ...] = field(default_factory=tuple)


def sanitize_text(text: str, home: str | Path | None = None) -> str:
    """Rewrite every home-directory path to its ``~``-relative form."""
    home_text = str(home if home is not None else Path.home()).rstrip("/\\")
    if len(home_text) > 1:
        # Only a whole path component: /Users/bob must not eat /Users/bobby.
        text = re.sub(re.escape(home_text) + r"(?![^\\/\s\"':])", "~", text)
    for pattern in _HOME_PATTERNS:
        text = pattern.sub("~", text)
    return text


def read_log_tail(path: str | Path | None, max_lines: int = DEFAULT_LOG_LINES) -> list[str]:
    """The last ``max_lines`` lines of the log, or ``[]`` if it can't be read."""
    if path is None or max_lines <= 0:
        return []
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return [line.rstrip("\r\n") for line in deque(handle, maxlen=max_lines)]
    except OSError:
        return []


def os_description() -> str:
    system = platform.system() or sys.platform
    if system == "Darwin":
        release = platform.mac_ver()[0]
        return f"macOS {release}".strip() + f" ({platform.machine()})"
    return f"{system} {platform.release()} ({platform.machine()})"


def collect_context(
    *,
    app_version: str | None,
    qt_version: str = "",
    controller_plugins: Iterable[str] = (),
    software_plugins: Iterable[str] = (),
    log_path: str | Path | None = None,
    max_log_lines: int = DEFAULT_LOG_LINES,
    home: str | Path | None = None,
) -> ReportContext:
    """Gather the report's facts; every free-text value is sanitized."""
    log_lines = tuple(sanitize_text(line, home) for line in read_log_tail(log_path, max_log_lines))
    return ReportContext(
        app_version=app_version or "unknown",
        os_name=os_description(),
        python_version=platform.python_version(),
        qt_version=qt_version or "unknown",
        controller_plugins=tuple(sanitize_text(name, home) for name in controller_plugins),
        software_plugins=tuple(sanitize_text(name, home) for name in software_plugins),
        log_lines=log_lines,
    )


def build_report_text(context: ReportContext, description: str = "") -> str:
    """Markdown body of the issue, shown to the user for review/editing."""
    rows = [
        ("App version", context.app_version or "unknown"),
        ("OS", context.os_name or "unknown"),
        ("Python", context.python_version or "unknown"),
        ("Qt", context.qt_version or "unknown"),
        ("Controller plugins", ", ".join(context.controller_plugins) or "_(none)_"),
        ("Software plugins", ", ".join(context.software_plugins) or "_(none)_"),
    ]
    lines = [
        "### What happened",
        "",
        description.strip() or "<!-- Describe the problem and the steps to reproduce it. -->",
        "",
        "### Environment",
        "",
        "| Field | Value |",
        "| --- | --- |",
    ]
    lines += [f"| {label} | {value} |" for label, value in rows]
    lines += ["", f"### Last log lines ({len(context.log_lines)})", ""]
    if context.log_lines:
        lines += ["```", *context.log_lines, "```"]
    else:
        lines.append("_(no log available)_")
    lines += ["", "---", "", "Sent from **DJ MIDI Studio → Help → Report a Problem**."]
    return "\n".join(lines)


def _issue_url(title: str, body: str, repo: str) -> str:
    return (
        f"https://github.com/{repo}/issues/new?labels={quote(REPORT_LABEL)}"
        f"&title={quote(title)}&body={quote(body)}"
    )


def report_issue_url(title: str, body: str, *, repo: str = REPORT_REPO) -> tuple[str, bool]:
    """Return ``(url, body_was_inlined)`` for the pre-filled issue.

    ``body`` is the (possibly user-edited) report text. When the URL would be
    too long, the fenced log block is replaced by a paste placeholder; if it's
    still too long, the whole body is. ``False`` tells the caller the user has
    to paste the clipboard text.
    """
    title = title.strip() or DEFAULT_TITLE.strip()
    url = _issue_url(title, body, repo)
    if len(url) <= MAX_INLINE_URL_LENGTH:
        return url, True
    trimmed = re.sub(r"```.*?```", _LOG_PLACEHOLDER, body, flags=re.DOTALL)
    url = _issue_url(title, trimmed, repo)
    if trimmed != body and len(url) <= MAX_INLINE_URL_LENGTH:
        return url, False
    return _issue_url(title, _LOG_PLACEHOLDER, repo), False


__all__ = [
    "DEFAULT_LOG_LINES",
    "DEFAULT_TITLE",
    "MAX_INLINE_URL_LENGTH",
    "REPORT_LABEL",
    "REPORT_REPO",
    "ReportContext",
    "build_report_text",
    "collect_context",
    "os_description",
    "read_log_tail",
    "report_issue_url",
    "sanitize_text",
]
