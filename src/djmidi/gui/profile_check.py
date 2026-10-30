"""Guided controller profile verification (issue #364), Qt-free.

A profile transcribed from documentation (or built from rekordbox's
mappings) is "Not yet" verified until someone presses its controls on a
real unit. :class:`ProfileCheck` walks through the profile one physical
control at a time -- each layout cell (``layout.build_layout``), plain
layer then its SHIFT layer when the profile has one -- and judges each
press the Live Monitor sees:

- **ok**: the message is one of the profile's triggers for that control
  (any deck, any pad mode);
- **mismatch**: it isn't -- the result says whether the profile gives that
  message to another control, or doesn't know it at all;
- **skipped**: the user said the unit has no such control.

:func:`report_text` turns the results into a Markdown report, and
:func:`report_issue_url` into a pre-filled GitHub issue -- the community
route for issue #11 (field-verifying the delivered profiles). The app never
sends anything itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import quote

from djmidi import catalog
from djmidi.catalog.community import COMMUNITY_REPO
from djmidi.gui import layout as layout_mod
from djmidi.i18n import QT_TRANSLATE_NOOP, Translate, untranslated

OK, MISMATCH, SKIPPED = "ok", "mismatch", "skipped"
PLAIN, SHIFT = "plain", "shift"
REPORT_LABEL = "profile-check"
MAX_INLINE_URL_LENGTH = 6000

Trigger = tuple[str, str, str]  # (channel, "NOTE"/"CC", data1)

_PROMPT_PLAIN = QT_TRANSLATE_NOOP("ProfileCheck", "Press {control}")
_PROMPT_SHIFT = QT_TRANSLATE_NOOP("ProfileCheck", "Hold SHIFT and press {control}")
_OTHER_CONTROL = QT_TRANSLATE_NOOP("ProfileCheck", "got {trigger}, which the profile gives to {other}")
_UNKNOWN = QT_TRANSLATE_NOOP("ProfileCheck", "got {trigger}, which isn't in the profile")
_PASTE = "_(The report was copied to your clipboard: paste it here.)_"


def trigger_text(trigger: Trigger) -> str:
    channel, kind, data1 = trigger
    return f"{'Note' if kind == 'NOTE' else 'CC'} {data1} on channel {channel}"


@dataclass(frozen=True)
class CheckItem:
    label: str
    section: str
    layer: str  # PLAIN or SHIFT
    triggers: frozenset[Trigger]

    @property
    def title(self) -> str:
        return self.label if self.layer == PLAIN else f"SHIFT + {self.label}"

    def prompt(self, translate: Translate = untranslated) -> str:
        return translate(_PROMPT_PLAIN if self.layer == PLAIN else _PROMPT_SHIFT).format(control=self.label)


@dataclass(frozen=True)
class CheckResult:
    status: str
    got: Trigger | None = None
    other: str = ""  # the item the profile gives `got` to, when it isn't this one

    def detail(self, translate: Translate = untranslated) -> str:
        if self.status != MISMATCH or self.got is None:
            return ""
        if self.other:
            return translate(_OTHER_CONTROL).format(trigger=trigger_text(self.got), other=self.other)
        return translate(_UNKNOWN).format(trigger=trigger_text(self.got))


def _triggers(entries) -> frozenset[Trigger]:
    return frozenset((channel, entry.note_or_cc, entry.data1) for entry in entries for channel in entry.channels)


def check_items(controller: str) -> list[CheckItem]:
    """One item per physical control and layer, in the layout's order."""
    variants = layout_mod.reverse_lookup(controller)
    items: list[CheckItem] = []
    for cell in layout_mod.build_layout(controller):
        entries = variants.get(cell.key, [])
        plain = [entry for entry in entries if not layout_mod.is_shift_variant(entry)]
        shifted = [entry for entry in entries if layout_mod.is_shift_variant(entry)]
        if plain:
            items.append(CheckItem(cell.label, cell.section, PLAIN, _triggers(plain)))
        if shifted:
            items.append(CheckItem(cell.label, cell.section, SHIFT, _triggers(shifted)))
    return items


@dataclass
class ProfileCheck:
    controller: str
    items: list[CheckItem] = field(default_factory=list)
    results: dict[int, CheckResult] = field(default_factory=dict)
    index: int = 0

    @classmethod
    def start(cls, controller: str) -> ProfileCheck:
        return cls(controller, check_items(controller))

    @property
    def done(self) -> bool:
        return self.index >= len(self.items)

    @property
    def current(self) -> CheckItem | None:
        return None if self.done else self.items[self.index]

    def _owner(self, trigger: Trigger) -> str:
        return next((item.title for item in self.items if trigger in item.triggers), "")

    def press(self, trigger: Trigger) -> CheckResult | None:
        """Judges a press against the current item and moves on; None when
        the check is over."""
        item = self.current
        if item is None:
            return None
        if trigger in item.triggers:
            result = CheckResult(OK, trigger)
        else:
            result = CheckResult(MISMATCH, trigger, self._owner(trigger))
        self.results[self.index] = result
        self.index += 1
        return result

    def skip(self) -> None:
        if self.current is not None:
            self.results[self.index] = CheckResult(SKIPPED)
            self.index += 1

    def back(self) -> None:
        if self.index > 0:
            self.index -= 1
            self.results.pop(self.index, None)

    def counts(self) -> dict[str, int]:
        counts = {OK: 0, MISMATCH: 0, SKIPPED: 0}
        for result in self.results.values():
            counts[result.status] += 1
        return counts


def press_from_event(event) -> Trigger | None:
    """The trigger of a live press: a Note On above 0, or a Control Change
    above 0 (a CC button's release sends 0 and must not count twice)."""
    if event.direction != "in":
        return None
    try:
        value = int(event.data2)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    if event.event_type == "Note On":
        return (event.channel, "NOTE", event.data1)
    if event.event_type == "Control Change":
        return (event.channel, "CC", event.data1)
    return None


def _provenance(controller: str) -> str:
    definition = catalog.get_definition(controller)
    plugin_id = definition.plugin_id or ""
    if plugin_id.startswith("user."):
        return "installed profile (library or Controller Setup)"
    return "built-in profile"


def report_text(check: ProfileCheck, app_version: str | None = None, port: str = "", now: datetime | None = None) -> str:
    """The Markdown report of a check, always in English (it goes to the
    project's issue tracker)."""
    counts = check.counts()
    stamp = (now or datetime.now(tz=UTC)).strftime("%Y-%m-%d")
    lines = [
        f"## Profile check: {check.controller}",
        "",
        f"- Profile: {_provenance(check.controller)}",
        f"- App version: {app_version or 'unknown'}",
        f"- Input port: {port or 'any'}",
        f"- Date: {stamp}",
        (
            f"- Result: {counts[OK]} ok, {counts[MISMATCH]} mismatch, {counts[SKIPPED]} skipped, "
            f"{len(check.items) - len(check.results)} not checked (of {len(check.items)})"
        ),
    ]
    mismatches = [(check.items[i], r) for i, r in sorted(check.results.items()) if r.status == MISMATCH]
    skipped = [check.items[i] for i, r in sorted(check.results.items()) if r.status == SKIPPED]
    lines += ["", "### Mismatches", ""]
    lines += [f"- **{item.title}** ({item.section}): {result.detail()}" for item, result in mismatches] or ["_None._"]
    if skipped:
        lines += ["", "### Skipped (not on this unit)", "", *[f"- {item.title} ({item.section})" for item in skipped]]
    lines += ["", "---", "", "Sent from **DJ MIDI Studio → Verify Profile with the Controller**."]
    return "\n".join(lines)


def report_issue_url(check: ProfileCheck, body: str, *, repo: str = COMMUNITY_REPO) -> tuple[str, bool]:
    """``(url, inlined)``: a pre-filled issue; past the URL limit the body is
    a paste placeholder and ``inlined`` is False (the caller copies it)."""
    counts = check.counts()
    title = f"Profile check: {check.controller} ({counts[OK]} ok, {counts[MISMATCH]} mismatch)"

    def url(text: str) -> str:
        return (
            f"https://github.com/{repo}/issues/new?labels={quote(REPORT_LABEL)}"
            f"&title={quote(title)}&body={quote(text)}"
        )

    full = url(body)
    if len(full) <= MAX_INLINE_URL_LENGTH:
        return full, True
    return url(_PASTE), False


__all__ = [
    "MISMATCH",
    "OK",
    "PLAIN",
    "SHIFT",
    "SKIPPED",
    "CheckItem",
    "CheckResult",
    "ProfileCheck",
    "check_items",
    "press_from_event",
    "report_issue_url",
    "report_text",
    "trigger_text",
]
