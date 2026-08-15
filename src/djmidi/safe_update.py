"""Prepare, validate, apply and roll back configuration file updates."""

from __future__ import annotations

import difflib
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

Validator = Callable[[str], None]


@dataclass
class SafeUpdatePlan:
    path: Path
    original_text: str
    updated_text: str
    diff: str
    backup_path: Path
    applied: bool = False

    def apply(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            shutil.copy2(self.path, self.backup_path)
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
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
            self.rollback()
            raise
        self.applied = True

    def rollback(self) -> None:
        if self.backup_path.exists():
            shutil.copy2(self.backup_path, self.path)
            self.applied = False


def prepare_update(path: str | Path, updated_text: str, validator: Validator | None = None) -> SafeUpdatePlan:
    target = Path(path)
    original_text = target.read_text(encoding="utf-8") if target.exists() else ""
    if validator is not None:
        validator(updated_text)
    diff = "".join(
        difflib.unified_diff(
            original_text.splitlines(keepends=True),
            updated_text.splitlines(keepends=True),
            fromfile=str(target),
            tofile=f"{target} (updated)",
        )
    )
    return SafeUpdatePlan(
        path=target,
        original_text=original_text,
        updated_text=updated_text,
        diff=diff,
        backup_path=target.with_name(f"{target.name}.bak"),
    )


__all__ = ["SafeUpdatePlan", "prepare_update"]
