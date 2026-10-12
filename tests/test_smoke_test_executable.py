"""scripts/smoke_test_executable.py (issue #231), driven with tiny fake
executables instead of a real PyInstaller build."""

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "smoke_test_executable.py"

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="fake executables rely on a shebang line"
)


def _load_script(monkeypatch):
    spec = importlib.util.spec_from_file_location("smoke_test_executable", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_STARTUP_SECONDS", 0.5)
    return module


def _fake_executable(tmp_path, body):
    path = tmp_path / "fake-app"
    path.write_text(f"#!{sys.executable}\n" + textwrap.dedent(body))
    path.chmod(0o755)
    return path


def _run(module, tmp_path, monkeypatch, executable, *extra):
    monkeypatch.setenv("DJMIDI_LOG_DIR", str(tmp_path / "logs"))
    return module.main(["--os", "linux", "--executable", str(executable), *extra])


# Writes the PNG named after --startup-screenshot, then idles like the app.
_SCREENSHOT_APP = """
import sys, time
path = sys.argv[sys.argv.index("--startup-screenshot") + 1]
time.sleep(0.7)
open(path, "wb").write(b"PNG")
time.sleep(30)
"""


def test_passes_when_the_app_stays_alive_and_writes_the_screenshot(tmp_path, monkeypatch):
    module = _load_script(monkeypatch)
    executable = _fake_executable(tmp_path, _SCREENSHOT_APP)
    screenshot = tmp_path / "shots" / "startup.png"
    assert _run(module, tmp_path, monkeypatch, executable, "--screenshot", str(screenshot)) == 0
    assert screenshot.read_bytes() == b"PNG"


def test_without_screenshot_flag_only_checks_the_app_stays_alive(tmp_path, monkeypatch):
    module = _load_script(monkeypatch)
    executable = _fake_executable(tmp_path, "import time, sys\nassert len(sys.argv) == 1\ntime.sleep(30)\n")
    assert _run(module, tmp_path, monkeypatch, executable) == 0


def test_fails_on_a_startup_crash_and_prints_its_output(tmp_path, monkeypatch, capsys):
    module = _load_script(monkeypatch)
    executable = _fake_executable(tmp_path, "raise ImportError('missing frozen module')\n")
    assert _run(module, tmp_path, monkeypatch, executable, "--screenshot", str(tmp_path / "s.png")) == 1
    captured = capsys.readouterr()
    assert "missing frozen module" in captured.out
    assert "startup error" in captured.err


def test_fails_when_the_app_dies_before_writing_the_screenshot(tmp_path, monkeypatch, capsys):
    module = _load_script(monkeypatch)
    executable = _fake_executable(tmp_path, "import time\ntime.sleep(1)\nraise SystemExit(3)\n")
    assert _run(module, tmp_path, monkeypatch, executable, "--screenshot", str(tmp_path / "s.png")) == 1
    assert "status 3" in capsys.readouterr().err


def test_fails_when_no_screenshot_appears_in_time(tmp_path, monkeypatch, capsys):
    module = _load_script(monkeypatch)
    executable = _fake_executable(tmp_path, "import time\ntime.sleep(30)\n")
    result = _run(
        module, tmp_path, monkeypatch, executable,
        "--screenshot", str(tmp_path / "s.png"), "--screenshot-timeout", "0.5",
    )
    assert result == 1
    assert "No startup screenshot" in capsys.readouterr().err


def test_a_stale_screenshot_from_a_previous_run_does_not_count(tmp_path, monkeypatch):
    module = _load_script(monkeypatch)
    screenshot = tmp_path / "s.png"
    screenshot.write_bytes(b"old")
    executable = _fake_executable(tmp_path, "import time\ntime.sleep(30)\n")
    result = _run(
        module, tmp_path, monkeypatch, executable,
        "--screenshot", str(screenshot), "--screenshot-timeout", "0.3",
    )
    assert result == 1


def test_missing_executable_returns_2(tmp_path, monkeypatch):
    module = _load_script(monkeypatch)
    assert _run(module, tmp_path, monkeypatch, tmp_path / "absent") == 2
