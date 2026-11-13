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
        process.wait(timeout=15)  # a loaded machine can take a while to reap it


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
    parser.add_argument(
        "--require-analysis",
        action="store_true",
        help="also run the app's BPM/key analysis self-check and fail if the build lacks it",
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

    if args.require_analysis:
        status = _analysis_self_check(executable, root, environment)
        if status != 0:
            return status

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


# librosa's first beat-tracking call compiles with numba: slow on CI runners.
_ANALYSIS_TIMEOUT_SECONDS = 300


def _analysis_self_check(executable: Path, root: Path, environment: dict[str, str]) -> int:
    """Run ``--self-check-analysis`` (write, read and analyse a WAV inside the
    packaged app): 0 when BPM/key analysis works in this build."""
    print("Running the packaged app's analysis self-check…")
    try:
        result = subprocess.run(
            [str(executable), "--self-check-analysis"],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=_ANALYSIS_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print(f"Analysis self-check did not finish in {_ANALYSIS_TIMEOUT_SECONDS}s.", file=sys.stderr)
        return 1
    if result.returncode != 0:
        print(f"Analysis self-check failed (status {result.returncode}).", file=sys.stderr)
        print(result.stdout[-4000:], result.stderr[-4000:], sep="\n", file=sys.stderr)
        log_dir = Path(environment["DJMIDI_LOG_DIR"])
        for log in sorted(log_dir.glob("*.log")):
            print(f"--- {log.name} (end)", file=sys.stderr)
            print(log.read_text(errors="replace")[-4000:], file=sys.stderr)
        return 1
    print("Analysis self-check passed: BPM/key analysis is in this build.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
