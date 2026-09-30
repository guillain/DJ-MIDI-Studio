"""Prepare, validate, apply and roll back configuration file updates."""

from __future__ import annotations

import difflib
import logging
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

Validator = Callable[[str], None]
# Describes, in human terms, what changed between two versions of a file --
# for formats whose raw diff is unreadable (e.g. a Traktor .tsi's Base64 blob).
Summarizer = Callable[[str, str], str]

# A diff line longer than this is elided: a single multi-megabyte line (an
# embedded binary blob) would otherwise flood the confirmation dialog.
MAX_DIFF_LINE = 2000
_ELIDED_HEAD = 160


@dataclass
class SafeUpdatePlan:
    path: Path
    original_text: str
    updated_text: str
    diff: str
    backup_path: Path
    target_existed: bool = False
    applied: bool = False

    def apply(self) -> None:
        if self.applied:
            raise RuntimeError("safe update has already been applied")
        _LOGGER.info("Applying safe update to %s (backup=%s)", self.path, self.backup_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            shutil.copy2(self.path, self.backup_path)
            _LOGGER.debug("Backed up %s to %s", self.path, self.backup_path)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(self.updated_text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, self.path)
        except Exception:
            _LOGGER.exception("Failed to apply safe update to %s; rolling back", self.path)
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
            self.rollback()
            raise
        self.applied = True
        _LOGGER.info("Safe update applied to %s", self.path)

    def rollback(self) -> None:
        if not self.applied:
            _LOGGER.debug("Rollback requested for %s but nothing is applied; ignoring", self.path)
            return
        if self.backup_path.exists():
            shutil.copy2(self.backup_path, self.path)
            self.applied = False
            _LOGGER.info("Rolled back %s from backup %s", self.path, self.backup_path)
        elif self.applied and not self.target_existed and self.path.exists():
            # A newly-created target has no backup to restore.  Rollback must
            # return the filesystem to its pre-apply state rather than leave
            # the newly written file behind.
            self.path.unlink()
            self.applied = False
            _LOGGER.info("Rolled back %s by deleting the newly-created file (no prior backup)", self.path)


def _elide_long_lines(diff_lines: list[str]) -> list[str]:
    elided = []
    for line in diff_lines:
        if len(line) > MAX_DIFF_LINE:
            hidden = len(line) - _ELIDED_HEAD
            line = f"{line[:_ELIDED_HEAD]}… [{hidden:,} more characters]\n"
        elided.append(line)
    return elided


def prepare_update(
    path: str | Path,
    updated_text: str,
    validator: Validator | None = None,
    summarize: Summarizer | None = None,
) -> SafeUpdatePlan:
    target = Path(path)
    _LOGGER.debug("Preparing safe update for %s (exists=%s)", target, target.exists())
    original_text = target.read_text(encoding="utf-8") if target.exists() else ""
    if validator is not None:
        try:
            validator(updated_text)
        except Exception:
            _LOGGER.warning("Safe update validation failed for %s", target, exc_info=True)
            raise
    diff = "".join(
        _elide_long_lines(
            list(
                difflib.unified_diff(
                    original_text.splitlines(keepends=True),
                    updated_text.splitlines(keepends=True),
                    fromfile=str(target),
                    tofile=f"{target} (updated)",
                )
            )
        )
    )
    if summarize is not None and original_text:
        summary = summarize(original_text, updated_text)
        if summary:
            diff = f"{summary}\n\n{diff}"
    return SafeUpdatePlan(
        path=target,
        original_text=original_text,
        updated_text=updated_text,
        diff=diff,
        backup_path=target.with_name(f"{target.name}.bak"),
        target_existed=target.exists(),
    )


__all__ = ["SafeUpdatePlan", "prepare_update"]
