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
# How long to keep waiting for the startup screenshot after the alive window:
# a cold PyInstaller start on a busy Windows/macOS runner can take a while.
_SCREENSHOT_TIMEOUT_SECONDS = 60
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


def _terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def _report_early_exit(process: subprocess.Popen[bytes], output_path: Path) -> int:
    output = output_path.read_text(encoding="utf-8", errors="replace")
    print(output, end="")
    if any(marker in output for marker in _ERROR_MARKERS):
        print("Packaged executable reported a startup error.", file=sys.stderr)
    else:
        print(
            f"Packaged executable exited during startup with status {process.returncode}.",
            file=sys.stderr,
        )
    return 1


def _wait_for_screenshot(
    process: subprocess.Popen[bytes], screenshot: Path, output_path: Path, timeout: float
) -> int:
    """Wait for the app to write ``screenshot``; fail if it exits or times out."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if screenshot.is_file() and screenshot.stat().st_size > 0:
            print(f"Startup screenshot written: {screenshot}")
            return 0
        if process.poll() is not None:
            return _report_early_exit(process, output_path)
        time.sleep(0.2)
    print(f"No startup screenshot after {timeout:.0f}s: {screenshot}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--os", required=True, choices=("linux", "macos", "windows"))
    parser.add_argument(
        "--screenshot",
        type=Path,
        default=None,
        help="ask the app for a startup PNG at this path and fail if none is written",
    )
    parser.add_argument(
        "--screenshot-timeout",
        type=float,
        default=_SCREENSHOT_TIMEOUT_SECONDS,
        help="seconds to wait for the screenshot after the startup window",
    )
    parser.add_argument("--executable", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    executable = args.executable or _executable_path(root, args.os)
    if not executable.is_file():
        print(f"Executable not found: {executable}", file=sys.stderr)
        return 2

    environment = os.environ.copy()
    if args.os == "linux":
        environment.setdefault("QT_QPA_PLATFORM", "offscreen")
    environment.setdefault("DJMIDI_DISABLE_MIDI", "1")
    environment.setdefault("DJMIDI_LOG_DIR", str(root / "build" / "smoke-test-logs"))
    # The child's console output goes to a file rather than an unread pipe: a
    # chatty startup could otherwise fill the pipe buffer and block the app
    # before it ever paints its screenshot.
    output_path = Path(environment["DJMIDI_LOG_DIR"]) / "startup-output.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [str(executable)]
    screenshot = args.screenshot.resolve() if args.screenshot else None
    if screenshot is not None:
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        screenshot.unlink(missing_ok=True)
        command += ["--startup-screenshot", str(screenshot)]

    print(f"Starting packaged executable: {executable}")
    with output_path.open("wb") as output_file:
        process = subprocess.Popen(
            command,
            cwd=root,
            env=environment,
            stdout=output_file,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + _STARTUP_SECONDS
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    return _report_early_exit(process, output_path)
                time.sleep(0.1)
            print(f"Packaged executable stayed alive for {_STARTUP_SECONDS}s.")
            if screenshot is None:
                return 0
            return _wait_for_screenshot(
                process, screenshot, output_path, args.screenshot_timeout
            )
        finally:
            _terminate(process)


if __name__ == "__main__":
    raise SystemExit(main())
