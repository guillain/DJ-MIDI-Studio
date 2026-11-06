import logging

from djmidi import logging_config
from djmidi.logging_config import configure_logging, normalize_level


def test_configure_logging_writes_levels_to_rotating_file(tmp_path):
    path = configure_logging("DEBUG", tmp_path / "execution.log")
    logger = logging.getLogger("djmidi.test")
    logger.debug("debug detail")
    logger.info("startup information")
    for handler in logging.getLogger("djmidi").handlers:
        handler.flush()
    text = path.read_text(encoding="utf-8")
    assert "debug detail" in text
    assert "startup information" in text


def test_normalize_level_rejects_unknown_level():
    assert normalize_level("warning") == logging.WARNING
    try:
        normalize_level("verbose")
    except ValueError as exc:
        assert "Unsupported logging level" in str(exc)
    else:
        raise AssertionError("expected invalid level to fail")


def test_default_logging_falls_back_when_existing_log_cannot_open(monkeypatch, tmp_path):
    blocked_target = tmp_path / "DJ-MIDI-Studio" / "djmidi.log"
    blocked_target.parent.mkdir()
    blocked_target.mkdir()
    fallback_root = tmp_path / "fallback"
    monkeypatch.setattr(logging_config, "default_log_path", lambda: blocked_target)
    monkeypatch.setattr(logging_config.tempfile, "gettempdir", lambda: str(fallback_root))

    path = configure_logging()

    assert path == fallback_root / "djmidi" / "djmidi.log"
    assert path.is_file()


# --- native crash log (faulthandler) ------------------------------------


def _fake_faulthandler(monkeypatch):
    """Record faulthandler.enable calls instead of replacing pytest's own."""
    import faulthandler

    calls = []
    monkeypatch.setattr(faulthandler, "enable", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(logging_config, "_crash_file", None)
    return calls


def test_crash_log_sits_beside_the_log():
    assert logging_config.crash_log_path("/x/data/djmidi.log").as_posix() == "/x/data/djmidi-crash.log"


def test_enable_crash_log_points_faulthandler_at_an_empty_file(monkeypatch, tmp_path):
    calls = _fake_faulthandler(monkeypatch)
    log = configure_logging("INFO", tmp_path / "djmidi.log")
    target = logging_config.enable_crash_log(log)
    assert target == tmp_path / "djmidi-crash.log"
    [call] = calls
    assert call["all_threads"] is True and call["file"].name == str(target)
    assert target.read_text() == ""
    # Same folder again: nothing to do.
    assert logging_config.enable_crash_log(log) == target and len(calls) == 1
    logging_config._crash_file.close()


def test_a_previous_crash_is_copied_into_the_log_and_archived(monkeypatch, tmp_path):
    _fake_faulthandler(monkeypatch)
    log = configure_logging("INFO", tmp_path / "djmidi.log")
    crash = tmp_path / "djmidi-crash.log"
    crash.write_text('Fatal Python error: Segmentation fault\n  File "music_library_view.py", line 42\n')
    logging_config.enable_crash_log(log)
    for handler in logging.getLogger("djmidi").handlers:
        handler.flush()
    text = log.read_text(encoding="utf-8")
    assert "The previous session crashed" in text
    assert 'File "music_library_view.py", line 42' in text
    assert (tmp_path / "djmidi-crash.log.1").read_text().startswith("Fatal Python error")
    assert crash.read_text() == ""  # a fresh, empty file for this session
    logging_config._crash_file.close()


def test_the_crash_log_follows_a_new_log_folder_only_once_enabled(monkeypatch, tmp_path):
    calls = _fake_faulthandler(monkeypatch)
    assert logging_config.enable_crash_log(tmp_path / "a.log", only_if_enabled=True) is None
    assert calls == []
    logging_config.enable_crash_log(tmp_path / "a.log")
    (tmp_path / "other").mkdir()
    moved = logging_config.enable_crash_log(tmp_path / "other" / "b.log", only_if_enabled=True)
    assert moved == tmp_path / "other" / "b-crash.log"
    assert len(calls) == 2 and calls[-1]["file"].name == str(moved)
    logging_config._crash_file.close()
