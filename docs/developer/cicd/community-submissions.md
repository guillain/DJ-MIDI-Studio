# 🤝 Community submissions

> How a controller profile sent from Controller Setup becomes a pull request.

📍 [Docs](../../README.md) › [Developer](../README.md) › [CI/CD](README.md) › Community submissions

## Table of Contents

- [The flow](#the-flow)
- [What is checked](#what-is-checked)
- [Reviewing the PR](#reviewing-the-pr)
- [Running it by hand](#running-it-by-hand)
- [Related](#related)

## The flow

1. A DJ builds a profile in Controller Setup and clicks **Submit to
   community catalog…**: the app opens a pre-filled issue with a
   `controller-submission/1` JSON block (`catalog/community.py`).
2. A maintainer reads the issue and adds the **`controller-submission`**
   label. GitHub only keeps the label the app's link pre-fills when the
   author is a collaborator, so a stranger's issue never starts the workflow
   by itself.
3. `.github/workflows/controller-submission.yml` reads the issue body into a
   file and runs `scripts/ingest_controller_submission.py`, which validates
   the JSON (`catalog/community_ingest.py`) and writes
   `controllers/library/community/<slug>.json`.
4. The workflow pushes the branch `community/issue-<N>`, opens (or updates)
   a PR and links it in an issue comment. A bad submission gets a comment
   with the reason instead; after fixing the JSON, remove and re-add the
   label.

## What is checked

The issue body is untrusted text: it is only parsed as JSON from a file,
never put into a shell command. `definition_from_payload` refuses:

- a missing, too long (over 120 characters) or control-character name, or the
  name of a built-in controller (send corrections to those as issues);
- no entries, or more than 2,000;
- an entry whose type isn't `NOTE`/`CC`, whose channels aren't 1–16, or
  whose data1 isn't 0–127;
- two different controls on the same MIDI message
  (`codegen.find_trigger_conflicts`).

Rows that differ only by channel are folded together, as Controller
Setup's own export does. In the library, a `community` profile hides a
rekordbox- or Mixxx-built one with the same name.

## Reviewing the PR

A PR opened with the workflow's token doesn't start the other workflows:
close and reopen it to run the checks. Before merging, check that the
names read like the controller's own labels and that nothing was copied
from documentation that can't be redistributed.

## Running it by hand

`Actions → Controller submission to PR → Run workflow` with the issue number
does the same without touching labels. Locally:

```bash
gh issue view 42 --json body --jq .body > body.md
uv run python scripts/ingest_controller_submission.py --body-file body.md \
  --issue 42 --pr-body pr.md --error-file error.md
```

## Related

- [Controller profiles](../../enduser/controller-profiles.md)
- [Controller Setup](../../enduser/features/controller-setup.md)
- [Build and release](build-and-release.md)
