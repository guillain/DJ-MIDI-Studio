"""The controller library: everything known about each control (issue #451).

One place that merges, per Atelier `Feature` (stable id, input, LED), the
layers of knowledge the app has:

1. **documented** -- the catalog profile (official documentation, or an
   installed / Controller Setup profile: the *custom* layer);
2. **captured** -- what the guided check saw the real unit send
   (`atelier.captures`), with the DJ software that was driving it;
3. **LED** -- verified LED data from the LED probe or the light check
   (`atelier.led_data`), else the Atelier's assumption.

Any consumer -- the Atelier, macros, sync sets, Controller Setup -- asks
:func:`knowledge_for` instead of re-deriving it; the audit
(:func:`audit_counts`, :func:`audit_text`) is the same data as a report.
Nothing here changes a profile. Qt-free.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from djmidi import catalog
from djmidi.atelier import captures as captures_mod
from djmidi.atelier.features import Feature, features_for
from djmidi.i18n import QT_TRANSLATE_NOOP, Translate, untranslated

# Capture status of one feature.
VERIFIED = "verified"  # this very message was seen for its control
CONTROL_VERIFIED = "control-verified"  # its control answered, on another deck / pad mode
MISMATCH = "mismatch"  # its control sent something else
SKIPPED = "skipped"  # the user said the unit has no such control
ODD = "odd"  # the user flagged the capture as odd
UNTESTED = "untested"
CAPTURE_STATUSES = (VERIFIED, CONTROL_VERIFIED, MISMATCH, SKIPPED, ODD, UNTESTED)

LED_VERIFIED, LED_ASSUMED, LED_NONE = "verified", "assumed", "none"

STATUS_LABELS = {
    VERIFIED: QT_TRANSLATE_NOOP("ControllerLibrary", "verified"),
    CONTROL_VERIFIED: QT_TRANSLATE_NOOP("ControllerLibrary", "control verified (other deck or mode)"),
    MISMATCH: QT_TRANSLATE_NOOP("ControllerLibrary", "mismatch"),
    SKIPPED: QT_TRANSLATE_NOOP("ControllerLibrary", "not on the unit"),
    ODD: QT_TRANSLATE_NOOP("ControllerLibrary", "flagged as odd"),
    UNTESTED: QT_TRANSLATE_NOOP("ControllerLibrary", "never tested"),
}
LED_LABELS = {
    LED_VERIFIED: QT_TRANSLATE_NOOP("ControllerLibrary", "LED verified"),
    LED_ASSUMED: QT_TRANSLATE_NOOP("ControllerLibrary", "LED assumed"),
    LED_NONE: QT_TRANSLATE_NOOP("ControllerLibrary", "no LED"),
}
_RANK = {MISMATCH: 0, ODD: 1, VERIFIED: 2, CONTROL_VERIFIED: 3, SKIPPED: 4, UNTESTED: 5}


@dataclass(frozen=True)
class ControlKnowledge:
    feature: Feature
    source: str  # "documented" or "custom"
    status: str  # one of CAPTURE_STATUSES
    software: str = ""  # the software of the deciding capture
    got: tuple[str, str, str] | None = None  # what a mismatching capture saw
    day: str = ""
    # (software, status) for every software it was captured under: the
    # same button can answer differently with and without a DJ software.
    per_software: tuple[tuple[str, str], ...] = ()

    @property
    def led(self) -> str:
        if self.feature.led is None:
            return LED_NONE
        return LED_VERIFIED if self.feature.led.verified else LED_ASSUMED


def _source(controller: str) -> str:
    plugin_id = catalog.get_definition(controller).plugin_id or ""
    return "custom" if plugin_id.startswith("user.") else "documented"


def _trigger_of(feature: Feature) -> tuple[str, str, str]:
    return (str(feature.input.channel), feature.input.kind, str(feature.input.number))


def knowledge_for(controller: str, store: captures_mod.CaptureStore | None = None) -> list[ControlKnowledge]:
    """One entry per feature, in catalog order."""
    from djmidi.gui.profile_check import check_items

    store = store if store is not None else captures_mod.load_captures(controller)
    source = _source(controller)
    items = {item.key: item for item in check_items(controller)}
    # trigger -> software -> the (status, record) that decides it there
    seen: dict[tuple[str, str, str], dict[str, tuple[str, captures_mod.CaptureRecord]]] = {}

    def offer(trigger, status, record) -> None:
        by_software = seen.setdefault(trigger, {})
        current = by_software.get(record.software)
        if current is None or _RANK[status] < _RANK[current[0]]:
            by_software[record.software] = (status, record)

    for record in store.records.values():
        item = items.get(record.item)
        if item is None:
            continue  # the profile changed since: the record no longer names a control
        if record.status == captures_mod.OK:
            for trigger in item.triggers:
                offer(trigger, VERIFIED if trigger == record.got else CONTROL_VERIFIED, record)
        else:
            status = {captures_mod.MISMATCH: MISMATCH, captures_mod.SKIPPED: SKIPPED, captures_mod.ODD: ODD}[
                record.status
            ]
            for trigger in item.triggers:
                offer(trigger, status, record)
    knowledge = []
    for feature in features_for(controller):
        by_software = seen.get(_trigger_of(feature), {})
        status, record = _overall(by_software)
        knowledge.append(
            ControlKnowledge(
                feature=feature,
                source=source,
                status=status,
                software=record.software if record else "",
                got=record.got if record and status == MISMATCH else None,
                day=record.day if record else "",
                per_software=tuple((software, verdict[0]) for software, verdict in sorted(by_software.items())),
            )
        )
    return knowledge


def _overall(by_software):
    """A mismatch with no software running is not a profile error when the
    control is verified under a DJ software (the profile describes how the
    controller is used): a software's verdict wins over "none"."""
    if not by_software:
        return UNTESTED, None
    driven = {software: verdict for software, verdict in by_software.items() if software != captures_mod.NO_SOFTWARE}
    pool = driven or by_software
    return min(pool.values(), key=lambda verdict: _RANK[verdict[0]])


@dataclass(frozen=True)
class ControlAudit:
    """One physical control and layer (a check item), as the audit lists it:
    a wrong pad is one wrong control, not one per deck and pad mode."""

    title: str
    section: str
    item: str  # the check item key
    status: str  # VERIFIED, MISMATCH, ODD, SKIPPED or UNTESTED
    per_software: tuple[tuple[str, str], ...] = ()
    got: tuple[str, str, str] | None = None
    messages: int = 0  # how many messages the profile gives it
    leds_verified: int = 0
    leds: int = 0


_ITEM_STATUS = {
    captures_mod.OK: VERIFIED,
    captures_mod.MISMATCH: MISMATCH,
    captures_mod.ODD: ODD,
    captures_mod.SKIPPED: SKIPPED,
}


def audit_controls(controller: str, store: captures_mod.CaptureStore | None = None) -> list[ControlAudit]:
    """The audit, one row per control and layer, in the layout's order."""
    from djmidi.gui.profile_check import check_items

    store = store if store is not None else captures_mod.load_captures(controller)
    by_item: dict[str, dict[str, captures_mod.CaptureRecord]] = {}
    for record in store.records.values():
        by_item.setdefault(record.item, {})[record.software] = record
    leds = {_trigger_of(feature): feature.led for feature in features_for(controller)}
    rows = []
    for item in check_items(controller):
        records = by_item.get(item.key, {})
        verdicts = {software: (_ITEM_STATUS[record.status], record) for software, record in records.items()}
        status, record = _overall(verdicts)
        item_leds = [leds[trigger] for trigger in item.triggers if leds.get(trigger) is not None]
        rows.append(
            ControlAudit(
                title=item.title,
                section=item.section,
                item=item.key,
                status=status,
                per_software=tuple((software, verdict[0]) for software, verdict in sorted(verdicts.items())),
                got=record.got if record is not None and status == MISMATCH else None,
                messages=len(item.triggers),
                leds_verified=sum(led.verified for led in item_leds),
                leds=len(item_leds),
            )
        )
    return rows


def audit_counts(rows) -> dict[str, int]:
    """Per status, plus ``total`` and ``led-verified`` (rows or knowledge)."""
    counts = dict.fromkeys(CAPTURE_STATUSES, 0)
    for entry in rows:
        counts[entry.status] += 1
    if rows and isinstance(rows[0], ControlAudit):
        counts["led-verified"] = sum(row.leds_verified > 0 for row in rows)
    else:
        counts["led-verified"] = sum(entry.led == LED_VERIFIED for entry in rows)
    counts["total"] = len(rows)
    return counts


def _software_label(key: str) -> str:
    return dict(captures_mod.SOFTWARE_CHOICES).get(key, key)


def audit_text(
    controller: str,
    rows: list[ControlAudit] | None = None,
    app_version: str | None = None,
    now: datetime | None = None,
    translate: Translate = untranslated,
) -> str:
    """The audit as Markdown: a summary, then one row per control and layer,
    mismatches first."""
    rows = rows if rows is not None else audit_controls(controller)
    counts = audit_counts(rows)
    stamp = (now or datetime.now(tz=UTC)).strftime("%Y-%m-%d")
    lines = [
        f"## Controller audit: {controller}",
        "",
        f"- Profile: {'custom (installed or Controller Setup)' if _source(controller) == 'custom' else 'built-in (documentation)'}",
        f"- App version: {app_version or 'unknown'}",
        f"- Date: {stamp}",
        (
            f"- Controls: {counts['total']} · verified {counts[VERIFIED]} · mismatch {counts[MISMATCH]}"
            f" · odd {counts[ODD]} · not on the unit {counts[SKIPPED]} · never tested {counts[UNTESTED]}"
            f" · with a verified LED {counts['led-verified']}"
        ),
        "",
        "| Control | Category | Status | Captured with | LEDs verified |",
        "|---|---|---|---|---|",
    ]
    for row in sorted(rows, key=lambda item: _RANK[item.status]):
        status = translate(STATUS_LABELS[row.status])
        if row.got is not None:
            channel, kind, data1 = row.got
            status += f" (got {'Note' if kind == 'NOTE' else 'CC'} {data1} ch {channel})"
        captured = " · ".join(
            f"{translate(_software_label(software))}: {translate(STATUS_LABELS[verdict])}"
            for software, verdict in row.per_software
        )
        led = f"{row.leds_verified}/{row.leds}" if row.leds else "–"
        lines.append(f"| {row.title} | {row.section} | {status} | {captured} | {led} |")
    lines += ["", "---", "", "Made with **DJ MIDI Studio → Verify Profile with the Controller → Audit**."]
    return "\n".join(lines)


__all__ = [
    "CAPTURE_STATUSES",
    "CONTROL_VERIFIED",
    "LED_ASSUMED",
    "LED_LABELS",
    "LED_NONE",
    "LED_VERIFIED",
    "MISMATCH",
    "ODD",
    "SKIPPED",
    "STATUS_LABELS",
    "UNTESTED",
    "VERIFIED",
    "ControlAudit",
    "ControlKnowledge",
    "audit_controls",
    "audit_counts",
    "audit_text",
    "knowledge_for",
]
