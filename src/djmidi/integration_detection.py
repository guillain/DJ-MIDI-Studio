"""Explainable, non-destructive controller and software detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from djmidi import catalog, software

IntegrationKind = Literal["controller", "software"]


@dataclass(frozen=True)
class DetectionCandidate:
    kind: IntegrationKind
    plugin_id: str
    name: str
    score: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class DetectionResult:
    candidates: tuple[DetectionCandidate, ...]
    source: str

    @property
    def best(self) -> DetectionCandidate | None:
        return self.candidates[0] if self.candidates else None

    @property
    def needs_confirmation(self) -> bool:
        if len(self.candidates) != 1:
            return bool(self.candidates)
        return self.candidates[0].score < 100

    @property
    def status(self) -> str:
        if not self.candidates:
            return "unknown"
        if self.needs_confirmation:
            return "ambiguous"
        return "match"


def detect_controller_ports(port_names: list[str]) -> DetectionResult:
    """Rank controllers from port names without enabling or changing plugins."""
    by_id: dict[str, DetectionCandidate] = {}
    for port_name in port_names:
        for match in catalog.detect_controller(port_name):
            current = by_id.get(match.controller.plugin_id or match.controller.name)
            candidate = DetectionCandidate(
                kind="controller",
                plugin_id=match.controller.plugin_id or match.controller.name,
                name=match.controller.name,
                score=match.score,
                reasons=(f"port name contains {match.reason.split(' contains ', 1)[-1]}",),
            )
            if current is None or candidate.score > current.score:
                by_id[candidate.plugin_id] = candidate
    return DetectionResult(
        candidates=tuple(sorted(by_id.values(), key=lambda item: (-item.score, item.name))),
        source="MIDI port names",
    )


def detect_software_mapping(text: str, suffix: str = "") -> DetectionResult:
    """Rank mapping plugins from XML signatures and file extension."""
    definitions = software.detect_from_text(text, suffix)
    candidates: list[DetectionCandidate] = []
    for definition in definitions:
        score = 100 if definition.plugin_id in {"serato", "traktor"} else 70
        reason = "mapping file signature" if score == 100 else f"file extension {suffix!r}"
        candidates.append(
            DetectionCandidate(
                kind="software",
                plugin_id=definition.plugin_id,
                name=definition.name,
                score=score,
                reasons=(reason,),
            )
        )
    return DetectionResult(
        candidates=tuple(sorted(candidates, key=lambda item: (-item.score, item.name))),
        source="mapping file signature and extension",
    )


__all__ = [
    "DetectionCandidate",
    "DetectionResult",
    "detect_controller_ports",
    "detect_software_mapping",
]
