"""Write the controller profile a community submission issue carries.

Run by .github/workflows/controller-submission.yml when a maintainer labels an
issue ``controller-submission``::

    python scripts/ingest_controller_submission.py --body-file body.md --issue 42 \\
        --pr-body pr.md --error-file error.md

On success it writes ``controllers/library/community/<slug>.json`` and the PR
description, and prints ``name=...``/``path=...``/``slug=...`` lines (the
workflow appends them to ``$GITHUB_OUTPUT``). On a bad submission it writes
the reason to ``--error-file`` (posted back on the issue) and exits 1. The
issue body is only parsed as JSON, never executed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from djmidi.catalog.community_ingest import (
    COMMUNITY_DIR,
    SubmissionError,
    extract_payload,
    pull_request_body,
    write_community_profile,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--body-file", type=Path, required=True)
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--out-dir", type=Path, default=COMMUNITY_DIR)
    parser.add_argument("--pr-body", type=Path, required=True)
    parser.add_argument("--error-file", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        payload = extract_payload(args.body_file.read_text(encoding="utf-8"))
        profile = write_community_profile(payload, args.out_dir)
    except SubmissionError as exc:
        args.error_file.write_text(
            f"The `controller-submission` workflow couldn't build a profile from this issue:\n\n> {exc}\n\n"
            "Fix the JSON in the issue (or submit again from Controller Setup), then remove and re-add the label.\n",
            encoding="utf-8",
        )
        print(f"error: {exc}", file=sys.stderr)
        return 1
    args.pr_body.write_text(pull_request_body(profile, args.issue) + "\n", encoding="utf-8")
    print(f"name={profile.definition.name}")
    print(f"path={profile.path.as_posix()}")
    print(f"slug={profile.path.stem}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
