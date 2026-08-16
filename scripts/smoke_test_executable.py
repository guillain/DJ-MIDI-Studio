#!/usr/bin/env python3
"""Start a packaged executable long enough to exercise its startup path."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

_STARTUP_SECONDS = 6
_ERROR_MARKERS = (
    "Traceback (most recent call last)",
    "ModuleNotFoundError",
    "ImportError",
    "Failed to execute script",
)


def _executable_path(root: Path, operating_system: str) -> Path:
    folder = root / "dist" / "executables" / operating_system / "DJMidiStudio"
    if operating_system == "windows":
        return folder / "DJMidiStudio.exe"
    return folder / "DJMidiStudio"


def _terminate(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--os", required=True, choices=("linux", "macos", "windows"))
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    executable = _executable_path(root, args.os)
    if not executable.is_file():
        print(f"Executable not found: {executable}", file=sys.stderr)
        return 2

    environment = os.environ.copy()
    if args.os == "linux":
        environment.setdefault("QT_QPA_PLATFORM", "offscreen")
    environment.setdefault("DJMIDI_DISABLE_MIDI", "1")
    environment.setdefault("DJMIDI_LOG_DIR", str(root / "build" / "smoke-test-logs"))

    print(f"Starting packaged executable: {executable}")
    process = subprocess.Popen(
        [str(executable)],
        cwd=root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.monotonic() + _STARTUP_SECONDS
        output = ""
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output += process.stdout.read() if process.stdout else ""
                print(output, end="")
                if any(marker in output for marker in _ERROR_MARKERS):
                    print("Packaged executable reported a startup error.", file=sys.stderr)
                else:
                    print(
                        f"Packaged executable exited before {_STARTUP_SECONDS}s "
                        f"with status {process.returncode}.",
                        file=sys.stderr,
                    )
                return 1
            time.sleep(0.1)
            if process.stdout:
                output += process.stdout.read(0)
        print(f"Packaged executable stayed alive for {_STARTUP_SECONDS}s.")
        return 0
    finally:
        _terminate(process)


if __name__ == "__main__":
    raise SystemExit(main())
