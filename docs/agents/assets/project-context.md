# DJ MIDI Studio — Agent Project Context 🧠

Use this short context before exploring a task. Read the full maintainer notes
in [`CLAUDE.md`](../../../CLAUDE.md) when implementation details matter.

## Table of Contents

- [Product](#product)
- [Main boundaries](#main-boundaries)
- [Non-negotiable constraints](#non-negotiable-constraints)
- [Validation](#validation)

## Product

DJ MIDI Studio is a PySide6 desktop application for visualizing and editing DJ
software MIDI mappings. It parses a typed model from Serato-compatible XML,
validates edits, and exports XML while preserving mapping semantics.

## Main boundaries

- `src/djmidi/model.py`: domain dataclasses.
- `src/djmidi/parser.py` and `exporter.py`: XML round-trip.
- `src/djmidi/validator.py`: structural and conflict checks.
- `src/djmidi/catalog/`: controller registry and physical-control lookup.
- `src/djmidi/gui/`: PySide6 views, layout, MIDI monitor, and setup tools.
- `tests/`: parser/exporter, catalog, GUI, MIDI, and integration coverage.
- `docs/`: English user, developer, hardware, agent, and release documentation.

## Non-negotiable constraints

- Preserve existing XML round-trip behavior.
- Do not deduplicate repeated Serato controls without new evidence; repetition
  can be load-bearing.
- Keep hardware claims tied to official MIDI documentation or real captures.
- Keep external plugins explicitly trusted; Python plugins are not sandboxed.
- Keep private mappings, logs containing private data, secrets, and generated
  build output out of commits.

## Validation

Use `bash scripts/test.sh quick` for fast feedback and
`bash scripts/test.sh quality` for the full quality gate. Run targeted tests
first while iterating, then inspect `git diff --check` and the final diff.
