# Agent Review Checklist 🔍

## Table of Contents

- [Scope and correctness](#scope-and-correctness)
- [Tests and evidence](#tests-and-evidence)
- [Documentation and assets](#documentation-and-assets)
- [Privacy and repository hygiene](#privacy-and-repository-hygiene)

## Scope and correctness

- [ ] The patch solves the stated outcome and avoids unrelated refactoring.
- [ ] Existing parser/exporter, catalog, GUI, and MIDI invariants are intact.
- [ ] Error paths and user-facing messages are safe and understandable.

## Tests and evidence

- [ ] Focused regression tests cover the changed behavior.
- [ ] `bash scripts/test.sh quick` passes, or the failure is explained.
- [ ] The relevant quality gate was run for core, dependency, CI, or security
      changes.
- [ ] Hardware claims identify their source and confidence level.

## Documentation and assets

- [ ] User-visible behavior is documented in English.
- [ ] The relevant TOC/index links were updated.
- [ ] Screenshots, PDFs, and other assets have provenance and appropriate
      licensing notes.
- [ ] Markdown links work from their source file.

## Privacy and repository hygiene

- [ ] No secrets, tokens, private mappings, personal logs, or machine paths.
- [ ] No generated caches, `.DS_Store` files, or unrelated modifications.
- [ ] `git diff --check` passes.
