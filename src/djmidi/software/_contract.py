"""The contract a DJ software plugin must keep (phase 6 item 7).

A software plugin (a `SoftwareDefinition`: parser + exporter for one DJ
program's mapping format) is what lets this app open, show, validate and
save that program's mappings. :func:`check_software_plugin` runs the checks
every built-in plugin passes against sample files, so a contributor
writing a new one -- VirtualDJ, Engine DJ… -- learns what's wrong before
anyone reviews it:

- **errors** break the app: the parser raises or returns something other
  than controls with a MIDI address the views understand; the exporter's
  output doesn't parse back to the same bindings;
- **warnings** are worth fixing: the plugin wouldn't recognize its own
  sample file, or an edited trigger doesn't survive a save;
- **info** are fine but documented: an unedited save isn't byte-identical,
  or edits are refused (a read-only plugin is allowed, it must just say so
  with a ``ValueError``).

Used by ``scripts/check_software_plugin.py`` and the tests; Qt-free.
"""

from __future__ import annotations

import copy
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from djmidi.model import MidiConfig
from djmidi.software._registry import SoftwareDefinition

ERROR, WARNING, INFO = "error", "warning", "info"
EVENT_TYPES = frozenset({"Note On", "Note Off", "Control Change", "Pitch Bend"})
USERIO_EVENTS = frozenset({"click", "output"})
_PLUGIN_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")


@dataclass(frozen=True)
class ContractIssue:
    severity: str
    message: str
    sample: str = ""

    def __str__(self) -> str:
        where = f" [{self.sample}]" if self.sample else ""
        return f"{self.severity.upper()}{where}: {self.message}"


def _bindings(config: MidiConfig) -> Counter:
    return Counter(
        (control.channel, control.event_type, control.control, userio.event, mapping.tag, mapping.deck_id)
        for control in config.controls
        for userio in control.userios
        for mapping in userio.mappings
    )


def _check_definition(definition: SoftwareDefinition) -> list[ContractIssue]:
    issues = []
    if not _PLUGIN_ID.match(definition.plugin_id or ""):
        issues.append(ContractIssue(ERROR, f"plugin_id {definition.plugin_id!r}: use lowercase letters, digits, ._-"))
    if not (definition.name or "").strip():
        issues.append(ContractIssue(ERROR, "name is empty"))
    if not definition.extensions or any(not ext.startswith(".") or ext != ext.lower() for ext in definition.extensions):
        issues.append(ContractIssue(ERROR, f"extensions {definition.extensions!r}: lowercase, each starting with '.'"))
    for attr in ("parser", "exporter"):
        if not callable(getattr(definition, attr, None)):
            issues.append(ContractIssue(ERROR, f"{attr} is not callable"))
    return issues


def _check_config(config: object, sample: str) -> list[ContractIssue]:
    if not isinstance(config, MidiConfig):
        return [ContractIssue(ERROR, f"parser returned {type(config).__name__}, not a MidiConfig", sample)]
    issues = []
    if not config.controls:
        issues.append(ContractIssue(WARNING, "no control was read from the sample", sample))
    for index, control in enumerate(config.controls):
        where = f"control {index} ({control.channel}/{control.event_type}/{control.control})"
        if not (isinstance(control.channel, str) and control.channel.isdigit() and 1 <= int(control.channel) <= 16):
            issues.append(ContractIssue(ERROR, f"{where}: channel must be the text '1'..'16'", sample))
        if control.event_type not in EVENT_TYPES:
            issues.append(ContractIssue(ERROR, f"{where}: event_type must be one of {sorted(EVENT_TYPES)}", sample))
        if not (isinstance(control.control, str) and control.control.isdigit() and 0 <= int(control.control) <= 127):
            issues.append(ContractIssue(ERROR, f"{where}: control must be the text '0'..'127'", sample))
        for userio in control.userios:
            if userio.event not in USERIO_EVENTS:
                issues.append(ContractIssue(ERROR, f"{where}: userio event {userio.event!r} isn't click/output", sample))
            for mapping in userio.mappings:
                if not (mapping.tag or "").strip():
                    issues.append(ContractIssue(ERROR, f"{where}: a mapping element has no tag (function)", sample))
        if len(issues) > 20:
            issues.append(ContractIssue(ERROR, "… stopping after 20 problems", sample))
            break
    return issues


def _check_detection(definition: SoftwareDefinition, path: Path, text: str) -> list[ContractIssue]:
    suffix = "".join(path.suffixes).lower()
    if definition.signature is not None:
        if not definition.signature(text):
            return [ContractIssue(WARNING, "signature() doesn't recognize this sample", path.name)]
        return []
    if not any(suffix.endswith(ext) for ext in definition.extensions):
        return [ContractIssue(WARNING, f"no signature, and {suffix!r} isn't in extensions", path.name)]
    return []


def _check_edit(definition: SoftwareDefinition, config: MidiConfig, sample: str) -> list[ContractIssue]:
    """Moves one binding to an unused note/CC number and checks a save keeps
    it (or refuses with a ValueError, which a read-only plugin may do)."""
    edited = copy.deepcopy(config)
    used = {(c.channel, c.event_type, c.control) for c in edited.controls}
    control = next((c for c in edited.controls if c.control.isdigit() and any(u.mappings for u in c.userios)), None)
    if control is None:
        return []
    free = next(
        (str(n) for n in range(128) if (control.channel, control.event_type, str(n)) not in used), None
    )
    if free is None:
        return []
    control.control = free
    try:
        text = definition.exporter(edited)
    except ValueError as exc:
        return [ContractIssue(INFO, f"edits are refused on save ({exc}); fine for a read-only plugin", sample)]
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        return [ContractIssue(ERROR, f"exporter crashed on an edited mapping: {exc!r} (raise ValueError)", sample)]
    reparsed = definition.parser(text)
    moved = (control.channel, control.event_type, free)
    if not any((c.channel, c.event_type, c.control) == moved for c in reparsed.controls):
        return [ContractIssue(WARNING, "an edited trigger was lost on save", sample)]
    return []


def check_software_plugin(
    definition: SoftwareDefinition, samples: Iterable[str | Path]
) -> list[ContractIssue]:
    """Every contract problem of `definition` on the sample mapping files."""
    issues = _check_definition(definition)
    if any(issue.severity == ERROR for issue in issues):
        return issues
    paths = [Path(sample) for sample in samples]
    if not paths:
        issues.append(ContractIssue(ERROR, "give at least one real sample mapping file"))
    for path in paths:
        text = path.read_text(encoding="utf-8")
        try:
            config = definition.parser(text)
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            issues.append(ContractIssue(ERROR, f"parser raised {exc!r}", path.name))
            continue
        problems = _check_config(config, path.name)
        issues += problems
        issues += _check_detection(definition, path, text)
        if any(issue.severity == ERROR for issue in problems):
            continue
        try:
            exported = definition.exporter(config)
        except ValueError as exc:
            issues.append(ContractIssue(INFO, f"saving is refused ({exc}); the plugin is read-only", path.name))
            continue
        except Exception as exc:  # noqa: BLE001
            issues.append(ContractIssue(ERROR, f"exporter raised {exc!r} (raise ValueError to refuse)", path.name))
            continue
        if not isinstance(exported, str):
            issues.append(ContractIssue(ERROR, "exporter must return the file's text (str)", path.name))
            continue
        try:
            reparsed = definition.parser(exported)
        except Exception as exc:  # noqa: BLE001
            issues.append(ContractIssue(ERROR, f"the exported text doesn't parse: {exc!r}", path.name))
            continue
        if _bindings(reparsed) != _bindings(config):
            issues.append(ContractIssue(ERROR, "export then parse doesn't give back the same bindings", path.name))
            continue
        if exported != text:
            message = "an unedited save isn't byte-identical to the file (keep comments/layout if you can)"
            issues.append(ContractIssue(INFO, message, path.name))
        issues += _check_edit(definition, config, path.name)
    return issues


__all__ = ["ERROR", "INFO", "WARNING", "ContractIssue", "check_software_plugin"]
