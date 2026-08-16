# Contributing 🤝

> Contributions are welcome: fixes, tests, controller profiles, documentation,
> and carefully scoped experiments.

## Table of Contents

- [What to contribute](#what-to-contribute)
- [Branch and change proposal](#branch-and-change-proposal)
- [Pull request checklist](#pull-request-checklist)
- [Controller and MIDI contributions](#controller-and-midi-contributions)
- [AI-assisted contributions](#ai-assisted-contributions)
- [Review expectations](#review-expectations)

## What to contribute

- 🐛 Reproducible bug fixes with a regression test.
- ✨ Focused features aligned with the current architecture.
- 🎛️ Controller profiles backed by official documentation or clearly labeled
  hardware captures.
- 🧪 Tests, fixtures, accessibility improvements, and CI fixes.
- 📚 English documentation, diagrams, screenshots, and examples.

## Branch and change proposal

```bash
git switch -c fix/short-description
```

Keep commits focused. Explain the problem, proposed behavior, alternatives
considered, and validation in the pull request. For a release preparation
branch, use [`scripts/scm_release.sh`](../../scripts/scm_release.sh) as
described in [Build and Release](../build-and-release.md).

## Pull request checklist

- [ ] The change has a clear user or maintainer benefit.
- [ ] Focused tests were added or updated.
- [ ] `bash scripts/test.sh quick` passes.
- [ ] `bash scripts/test.sh quality` was run when relevant.
- [ ] Documentation and the appropriate index were updated.
- [ ] No private mappings, credentials, generated caches, or unrelated files
      are included.
- [ ] Hardware claims identify their evidence and limitations.

## Controller and MIDI contributions

Use [Controller Setup](../user-guide.md) to learn or import triggers. Preserve
the raw channel/type/data values, cite the official source in
[Controller Documentation](../controllers/README.md), and mark profiles as
provisional when they have not been checked on target hardware. Do not infer a
complete MIDI map from a product image.

## AI-assisted contributions

AI tools may help explore, draft, test, or review code, but the contributor is
accountable for the final patch. Follow [AI-Assisted Development](../agents/ai-assisted-development.md)
and keep reusable prompts/context in [Agent Assets](../agents/assets/README.md).

## Review expectations

Reviewers look for correctness, backwards compatibility, test quality,
maintainability, user-facing documentation, and safe MIDI behavior. A clean
CI result is necessary but does not replace human review of mappings or release
artifacts.
