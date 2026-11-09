"""Remapping one control onto another, by features (Atelier, issue #413,
step 6).

The MIDI router already remaps per control (`midi_router.RemapRule`, issue
#368) but asks for kinds, channels and numbers. Here a rule comes from two
`atelier.Feature`s -- the control pressed and the control it should act as
-- or from one feature and "block". Rules are added to a route's
`MidiValueTransform`, replacing any rule for the same source control.
Qt-free.
"""

from __future__ import annotations

from dataclasses import replace

from djmidi.atelier.describe import feature_name
from djmidi.atelier.features import NOTE, Feature, feature_for_message
from djmidi.i18n import QT_TRANSLATE_NOOP, Translate, untranslated
from djmidi.midi_router import BLOCK, CC, MidiValueTransform, RemapRule
from djmidi.midi_router import NOTE as ROUTER_NOTE

_KIND = {NOTE: ROUTER_NOTE, "CC": CC}
_EVENT = {ROUTER_NOTE: "Note On", CC: "Control Change"}
_ARROW = QT_TRANSLATE_NOOP("FeatureActions", "{source} → {target}")
_BLOCKED = QT_TRANSLATE_NOOP("FeatureActions", "{source} → blocked")


def remap_rule(source: Feature, target: Feature | None) -> RemapRule:
    """`source`'s messages leave as `target`'s, or are dropped (None)."""
    kind = _KIND[source.input.kind]
    if target is None:
        return RemapRule(kind, source.input.channel, source.input.number, BLOCK)
    return RemapRule(
        kind,
        source.input.channel,
        source.input.number,
        _KIND[target.input.kind],
        target.input.channel,
        target.input.number,
    )


def _same_source(a: RemapRule, b: RemapRule) -> bool:
    return (a.source_kind, a.source_channel, a.source_data1) == (b.source_kind, b.source_channel, b.source_data1)


def with_remap(transform: MidiValueTransform | None, rule: RemapRule) -> MidiValueTransform:
    """`transform` (or a neutral one) with `rule` replacing any rule for the
    same source control, else appended."""
    base = transform or MidiValueTransform()
    kept = [existing for existing in base.remaps if not _same_source(existing, rule)]
    position = next((i for i, existing in enumerate(base.remaps) if _same_source(existing, rule)), len(kept))
    kept.insert(position, rule)
    return replace(base, remaps=tuple(kept))


def without_remap(transform: MidiValueTransform | None, rule: RemapRule) -> MidiValueTransform | None:
    if transform is None:
        return None
    return replace(transform, remaps=tuple(existing for existing in transform.remaps if existing != rule))


def _feature_for(controller: str, kind: str, channel: int, number: int) -> Feature | None:
    return feature_for_message(controller, _EVENT[kind], channel, number)


def describe_remap(controller: str, rule: RemapRule, translate: Translate = untranslated) -> str:
    """``BEAT SYNC (deck 1) → PLAY/PAUSE (deck 1)``, or the raw address when
    `controller` has no such control."""
    source = _feature_for(controller, rule.source_kind, rule.source_channel, rule.source_data1)
    source_text = (
        feature_name(source, translate)
        if source is not None
        else f"{rule.source_kind.upper()} ch {rule.source_channel} · {rule.source_data1}"
    )
    if rule.target_kind == BLOCK:
        return translate(_BLOCKED).format(source=source_text)
    target = _feature_for(controller, rule.target_kind, rule.target_channel, rule.target_data1)
    target_text = (
        feature_name(target, translate)
        if target is not None
        else f"{rule.target_kind.upper()} ch {rule.target_channel} · {rule.target_data1}"
    )
    return translate(_ARROW).format(source=source_text, target=target_text)


__all__ = ["describe_remap", "remap_rule", "with_remap", "without_remap"]
