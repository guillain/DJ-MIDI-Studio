"""Traktor `.tsi` controller-mapping codec (issue #122).

A `.tsi` is Traktor's settings XML (`<NIXML><TraktorSettings><Entry .../>`);
controller mappings live in one entry, ``DeviceIO.Config.Controller``,
whose ``Value`` is a Base64 blob of nested chunks (see
`software/traktor/README.md` for the full reverse-engineered layout and its
sources). Verified against the maintainer's real exports in
`data/traktor/*.tsi.zip`:

- the chunk tree is exactly ``DIOM > DIOI + DEVS(count) > DEVI(name) > DDAT
  > DDIF/DDIV/DDIC/DDPT/DDDC/DDCB/DVST``, with ``DDCB > CMAS(count) > CMAI``
  and ``DDCB > DCBM(count) > DCBM``; a ``CMAI``'s binding id resolves to a
  ``DCBM`` label, except for a command added but never MIDI-learned, which
  has no binding at all (one such mapping in the real CMD Studio 4a file);
- labels read ``ChNN.Note.<name><octave>`` / ``ChNN.CC.NNN`` /
  ``ChNN.PitchBend``, with note ``C-1`` = MIDI note 0 -- confirmed against
  the official Pioneer XDJ-XZ values in `catalog/xdj_xz.py`: Traktor's
  XDJ-XZ Play (command 100) sits on ``C-1`` = note 0, Cue (206) on ``C#-1``
  = note 1, Sync (125) on ``G1`` = note 31;
- a label can also be *compound* (``Ch01.CC.032+Ch01.CC.000``, two
  messages at once); its first part is reported as the trigger, and it is
  never rewritten, since one trigger can't express both halves;
- re-encoding an unmodified tree (and its Base64) is byte-identical.

Editing is deliberately narrow: only a binding's *label* (its MIDI trigger)
is rewritten; every other byte -- command settings, LED ranges, modifiers,
unknown fields, the rest of the settings XML -- is carried over verbatim.
"""

from __future__ import annotations

import base64
import copy
import re
import struct
from dataclasses import dataclass, field

from djmidi.binary_chunks import (
    BigEndianReader,
    ChunkError,
    ChunkNode,
    decode,
    encode,
    utf16_string_bytes,
    utf16_string_length,
)

CONTROLLER_ENTRY = "DeviceIO.Config.Controller"

_ENTRY_RE = re.compile(r'(<Entry Name="DeviceIO\.Config\.Controller" Type="3" Value=")([^"]*)(")')

TSI_CONTAINERS = {
    (None, "DIOM"): 0,
    ("DIOM", "DEVS"): 4,
    ("DEVS", "DEVI"): utf16_string_length,
    ("DEVI", "DDAT"): 0,
    ("DDAT", "DDDC"): 0,
    ("DDDC", "DDCI"): 4,
    ("DDDC", "DDCO"): 4,
    ("DDAT", "DDCB"): 0,
    ("DDCB", "CMAS"): 4,
    ("DDCB", "DCBM"): 4,
    ("CMAS", "CMAI"): 12,
}

CONTROLLER_TYPES = {0: "Button", 1: "FaderOrKnob", 2: "Encoder", 65535: "LED"}
INTERACTION_MODES = {
    1: "Toggle",
    2: "Hold",
    3: "Direct",
    4: "Relative",
    5: "Increment",
    6: "Decrement",
    7: "Reset",
    8: "Output",
}
# Only IDs cross-checked against a real export (see the module docstring);
# everything else is surfaced as its raw number rather than guessed.
COMMAND_NAMES = {100: "Play/Pause", 125: "Sync On", 206: "Cue"}

_NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_LABEL_RE = re.compile(r"^Ch(\d{2})\.(Note|CC|PitchBend)(?:\.(.+))?$")
_NOTE_RE = re.compile(r"^([A-G]#?)(-?\d+)$")


class TsiError(ValueError):
    """A `.tsi` this codec can't read, or an edit it can't express."""


@dataclass(frozen=True)
class MidiTrigger:
    channel: int  # 1-16
    kind: str  # "Note", "CC" or "PitchBend"
    number: int | None  # None for PitchBend


def is_compound_label(label: str) -> bool:
    """``Ch01.CC.032+Ch01.CC.000``-style labels (seen in the real XDJ-XZ
    export) bind two MIDI messages at once, e.g. a 14-bit CC's MSB + LSB."""
    return "+" in label


def parse_label(label: str) -> MidiTrigger:
    """The trigger a label names -- for a compound label, its first part."""
    label = label.split("+", 1)[0]
    match = _LABEL_RE.match(label)
    if match is None:
        raise TsiError(f"unrecognized Traktor MIDI label {label!r}")
    channel, kind, value = int(match.group(1)), match.group(2), match.group(3)
    if kind == "PitchBend":
        return MidiTrigger(channel, kind, None)
    if value is None:
        raise TsiError(f"Traktor label {label!r} has no note/CC number")
    if kind == "CC":
        return MidiTrigger(channel, kind, int(value))
    note = _NOTE_RE.match(value)
    if note is None:
        raise TsiError(f"unrecognized note name in Traktor label {label!r}")
    number = (int(note.group(2)) + 1) * 12 + _NOTE_NAMES.index(note.group(1))
    return MidiTrigger(channel, kind, number)


def format_label(trigger: MidiTrigger) -> str:
    if not 1 <= trigger.channel <= 16:
        raise TsiError(f"MIDI channel must be 1-16, got {trigger.channel}")
    prefix = f"Ch{trigger.channel:02d}.{trigger.kind}"
    if trigger.kind == "PitchBend":
        return prefix
    if trigger.number is None or not 0 <= trigger.number <= 127:
        raise TsiError(f"MIDI note/CC number must be 0-127, got {trigger.number}")
    if trigger.kind == "CC":
        return f"{prefix}.{trigger.number:03d}"
    octave, pitch = divmod(trigger.number, 12)
    return f"{prefix}.{_NOTE_NAMES[pitch]}{octave - 1}"


@dataclass
class TsiMapping:
    device_index: int
    binding_id: int
    label: str
    direction: str  # "in" (controller -> Traktor) or "out" (LED feedback)
    command_id: int
    controller_type: int
    interaction_mode: int
    target_deck: int  # -1 = the device's target deck, else 0-based slot
    comment: str = ""

    @property
    def trigger(self) -> MidiTrigger | None:
        return parse_label(self.label) if self.label else None

    @property
    def command_name(self) -> str:
        return COMMAND_NAMES.get(self.command_id, f"Command {self.command_id}")


@dataclass
class TsiDevice:
    index: int
    name: str
    version: str = ""
    comment: str = ""
    in_port: str = ""
    out_port: str = ""
    mappings: list[TsiMapping] = field(default_factory=list)


@dataclass
class TsiDocument:
    """A parsed `.tsi`: the original text, its decoded chunk tree, and a
    flat, read-only view of every device's mappings."""

    text: str
    tree: list[ChunkNode]
    devices: list[TsiDevice]

    @property
    def mappings(self) -> list[TsiMapping]:
        return [mapping for device in self.devices for mapping in device.mappings]

    def to_text(self, relabel: dict[tuple[int, int], str] | None = None) -> str:
        """The `.tsi` text with `relabel` ({(device_index, binding_id):
        new label}) applied; byte-identical to the input when empty."""
        if not relabel:
            return self.text
        # Edit a copy: this document stays the pristine source of truth, so
        # an undone edit or a cancelled save never leaves a stale label.
        tree = copy.deepcopy(self.tree)
        for (device_index, binding_id), label in relabel.items():
            parse_label(label)  # validate before touching anything
            _binding_node(tree, device_index, binding_id).payload = struct.pack(
                ">i", binding_id
            ) + utf16_string_bytes(label)
        value = base64.b64encode(encode(tree)).decode("ascii")
        return _ENTRY_RE.sub(lambda match: match.group(1) + value + match.group(3), self.text, count=1)


def describe_changes(old_text: str, new_text: str) -> str:
    """One line per binding whose MIDI trigger differs, for the save
    confirmation -- the raw diff of a .tsi is one multi-megabyte Base64 line."""
    try:
        before, after = parse_tsi(old_text).mappings, parse_tsi(new_text).mappings
    except TsiError:
        return ""
    if len(before) != len(after):
        return f"Traktor bindings: {len(before)} -> {len(after)}"
    lines = [
        f"{new.command_name} (device #{new.device_index + 1}, {new.direction}): {old.label} -> {new.label}"
        for old, new in zip(before, after, strict=True)
        if old.label != new.label
    ]
    if not lines:
        return "No Traktor binding changes."
    return f"{len(lines)} Traktor binding change(s):\n" + "\n".join(lines)


def is_tsi_text(text: str) -> bool:
    return "<NIXML" in text[:512]


def parse_tsi(text: str) -> TsiDocument:
    match = _ENTRY_RE.search(text)
    if match is None:
        # A settings/keyboard-only export: valid, just no controller mappings.
        return TsiDocument(text=text, tree=[], devices=[])
    try:
        blob = base64.b64decode(match.group(2), validate=True)
        tree = decode(blob, TSI_CONTAINERS)
        devices = [_read_device(index, node) for index, node in enumerate(_device_nodes(tree))]
    except (ChunkError, ValueError, UnicodeDecodeError, struct.error) as exc:
        raise TsiError(f"unreadable {CONTROLLER_ENTRY} blob: {exc}") from exc
    return TsiDocument(text=text, tree=tree, devices=devices)


def _device_nodes(tree: list[ChunkNode]) -> list[ChunkNode]:
    root = next((node for node in tree if node.tag == "DIOM"), None)
    devices = root.find("DEVS") if root is not None else None
    return devices.find_all("DEVI") if devices is not None else []


def _string_leaf(parent: ChunkNode, tag: str, count: int = 1) -> list[str]:
    node = parent.find(tag)
    if node is None:
        return [""] * count
    reader = BigEndianReader(node.payload)
    return [reader.utf16_string() for _ in range(count)]


def _read_device(index: int, devi: ChunkNode) -> TsiDevice:
    name = BigEndianReader(devi.prefix).utf16_string()
    data = devi.find("DDAT")
    if data is None:
        return TsiDevice(index=index, name=name)
    (version,) = _string_leaf(data, "DDIV")
    (comment,) = _string_leaf(data, "DDIC")
    in_port, out_port = _string_leaf(data, "DDPT", 2)
    device = TsiDevice(index, name, version, comment, in_port, out_port)
    bindings_container = data.find("DDCB")
    if bindings_container is None:
        return device
    labels = _binding_labels(bindings_container)
    mappings_list = bindings_container.find("CMAS")
    for cmai in mappings_list.find_all("CMAI") if mappings_list is not None else []:
        device.mappings.append(_read_mapping(index, cmai, labels))
    return device


def _binding_labels(ddcb: ChunkNode) -> dict[int, str]:
    labels: dict[int, str] = {}
    bindings = ddcb.find("DCBM")
    for binding in bindings.find_all("DCBM") if bindings is not None else []:
        reader = BigEndianReader(binding.payload)
        binding_id = reader.i32()
        labels[binding_id] = reader.utf16_string()
    return labels


def _read_mapping(device_index: int, cmai: ChunkNode, labels: dict[int, str]) -> TsiMapping:
    header = BigEndianReader(cmai.prefix)
    binding_id, mapping_type, command_id = header.i32(), header.i32(), header.i32()
    settings = cmai.find("CMAD")
    controller_type = interaction_mode = 0
    target_deck = -1
    comment = ""
    if settings is not None:
        reader = BigEndianReader(settings.payload)
        reader.u32()  # unknown
        controller_type, interaction_mode, target_deck = reader.i32(), reader.i32(), reader.i32()
        for _ in range(3):  # AutoRepeat, Invert, SoftTakeover
            reader.i32()
        for _ in range(5):  # RotarySensitivity, RotaryAcceleration, 2x unknown, SetValueTo
            reader.u32()
        comment = reader.utf16_string()
    return TsiMapping(
        device_index=device_index,
        binding_id=binding_id,
        # A command added in Traktor but never MIDI-learned has no binding
        # (seen in the real CMD Studio 4a export) -- valid, just unassigned.
        label=labels.get(binding_id, ""),
        direction="out" if mapping_type == 1 else "in",
        command_id=command_id,
        controller_type=controller_type,
        interaction_mode=interaction_mode,
        target_deck=target_deck,
        comment=comment,
    )


def _binding_node(tree: list[ChunkNode], device_index: int, binding_id: int) -> ChunkNode:
    devices = _device_nodes(tree)
    if not 0 <= device_index < len(devices):
        raise TsiError(f"no device #{device_index} in this .tsi")
    data = devices[device_index].find("DDAT")
    ddcb = data.find("DDCB") if data is not None else None
    bindings = ddcb.find("DCBM") if ddcb is not None else None
    for binding in bindings.find_all("DCBM") if bindings is not None else []:
        if BigEndianReader(binding.payload).i32() == binding_id:
            return binding
    raise TsiError(f"device #{device_index} has no binding {binding_id}")
