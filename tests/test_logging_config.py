import logging

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
