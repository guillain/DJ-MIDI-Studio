# Agent Task Template 📝

Copy this template and replace the bracketed text before starting work.

## Table of Contents

- [Outcome](#outcome)
- [Scope](#scope)
- [Context](#context)
- [Plan](#plan)
- [Validation](#validation)
- [Hand-off](#hand-off)

## Outcome

Implement or investigate **[one concrete outcome]** for **[user/maintainer]**.

## Scope

- In scope: `[files/modules/docs]`
- Out of scope: `[explicit boundaries]`
- Existing behavior to preserve: `[invariants]`

## Context

- Read: [Project Context](project-context.md), relevant docs, and
  [`CLAUDE.md`](../../../CLAUDE.md).
- Related issue or evidence: `[link, fixture, log, or hardware source]`
- Assumptions: `[write them down]`

## Plan

1. Explore existing code and tests.
2. Make the smallest coherent change.
3. Update English documentation and indexes if behavior changes.
4. Run focused checks, then the relevant quality gate.

## Validation

```bash
[targeted command]
bash scripts/test.sh quick
git diff --check
```

## Hand-off

Report changed files, test results, user impact, limitations, and follow-up
work. Mark hardware evidence as verified, simulated, provisional, or blocked.
