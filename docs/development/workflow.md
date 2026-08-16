# Development Workflow 🔁

> Small, reviewable changes with evidence attached to every behavior change.

## Table of Contents

- [Start with context](#start-with-context)
- [Plan the change](#plan-the-change)
- [Implement in layers](#implement-in-layers)
- [Validate the result](#validate-the-result)
- [Document the decision](#document-the-decision)
- [Definition of done](#definition-of-done)

## Start with context

Read the relevant user guide and architecture notes before editing code. For
agent-assisted work, also read [Project Context](../agents/assets/project-context.md)
and the maintainer notes in [`CLAUDE.md`](../../CLAUDE.md). Search the codebase
for existing patterns and tests before introducing a new abstraction.

## Plan the change

Describe the user-facing outcome, affected modules, test strategy, and any
hardware or licensing assumptions. Keep unrelated cleanup out of the branch.
For uncertain MIDI behavior, record what is known, what was simulated, and
what still requires physical verification.

## Implement in layers

1. Update the domain/service layer and preserve existing invariants.
2. Add or update focused tests.
3. Wire the GUI or CLI behavior.
4. Update user/developer documentation and screenshots when behavior changes.
5. Review the diff for accidental files, private data, and stale links.

Avoid silently deduplicating Serato controls: repeated triggers can be
load-bearing. Consult `CLAUDE.md` and the parser/exporter tests before changing
mapping semantics.

## Validate the result

```bash
bash scripts/test.sh quick
bash scripts/test.sh quality
git diff --check
```

Use targeted tests during iteration, then run the complete relevant gate before
requesting review. For packaging changes, run `bash scripts/build.sh` and the
executable smoke test when the local platform supports it.

## Document the decision

Explain the user impact, compatibility implications, test evidence, and known
limitations in the pull request. Update the relevant Markdown index so a new
maintainer can find the information without reading commit history.

## Definition of done

- Behavior is covered by tests or an explicit hardware-validation note.
- Public behavior and limitations are documented in English.
- No private mappings, credentials, generated caches, or unrelated edits are
  included.
- CI-relevant commands pass, or the failure is clearly explained.
- A reviewer can understand the change from the PR description and diff.
