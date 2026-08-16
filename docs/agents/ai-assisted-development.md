# AI-Assisted Development 🤖

> This project uses “vibe coding” as an accelerator: agents explore and draft,
> while humans define intent, verify behavior, and own the merge decision.

## Table of Contents

- [Operating principles](#operating-principles)
- [A practical agent loop](#a-practical-agent-loop)
- [Divide work between agents](#divide-work-between-agents)
- [Evidence and hardware boundaries](#evidence-and-hardware-boundaries)
- [Reusable assets](#reusable-assets)
- [Common failure modes](#common-failure-modes)

## Operating principles

- 🎯 Give the agent one bounded outcome and name the files in scope.
- 🧠 Provide repository context before asking for implementation.
- 🔎 Ask for searches and tests, not confident guesses.
- 🧪 Treat generated code as unreviewed until checks pass.
- 👤 Keep a human maintainer responsible for safety, licensing, and merge.
- 🧾 Record important assumptions and unresolved questions in the PR.

## A practical agent loop

1. **Explore:** inspect the index, architecture, relevant code, tests, and
   current Git status.
2. **Plan:** state the intended behavior, boundaries, and validation commands.
3. **Implement:** make the smallest coherent patch.
4. **Verify:** run focused tests, then the project quality gate as appropriate.
5. **Review:** inspect the diff, docs links, generated files, and user impact.
6. **Hand off:** summarize files changed, evidence, limitations, and follow-up.

## Divide work between agents

Parallel work is useful when boundaries do not overlap:

| Agent role | Good scope | Required hand-off |
| --- | --- | --- |
| Explorer | Find relevant modules, tests, and constraints | Evidence and file paths |
| Implementer | One focused code or docs change | Diff and tests |
| Test reviewer | Regression cases and quality checks | Commands and results |
| Documentation editor | English guides, TOCs, links, screenshots | Updated index and link check |
| Hardware researcher | Official MIDI sources and limitations | URLs, licenses, confidence |

Do not ask multiple agents to rewrite the same file simultaneously. Reconcile
findings before merging overlapping patches.

## Evidence and hardware boundaries

Agents can inspect code, fixtures, PDFs, and virtual MIDI ports. They cannot
claim physical-controller compatibility without a real capture or authoritative
MIDI message list. Label results as **verified**, **simulated**, **provisional**,
or **blocked**. Never include private Serato files or credentials in prompts,
logs, fixtures, or commits.

## Reusable assets

The [Agent Assets Index](assets/README.md) contains portable Markdown assets.
Start with [Project Context](assets/project-context.md), copy the
[Task Template](assets/task-template.md), and finish with the
[Review Checklist](assets/review-checklist.md). Keep provider-specific files
thin; the repository documentation is the source of truth.

## Common failure modes

- Over-broad prompts produce unrelated refactors.
- Generated tests can assert an implementation detail instead of behavior.
- Product images are mistaken for MIDI message maps.
- Repeated Serato controls are “cleaned up” even though they may be required.
- An agent reports success without running the repository’s actual checks.
- A prompt includes private mappings or secrets that later leak into artifacts.
