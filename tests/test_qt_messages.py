from PySide6.QtCore import qInstallMessageHandler, qWarning

from djmidi.gui import qt_messages


def test_only_the_audio_channel_chatter_is_dropped(monkeypatch):
    seen = []
    previous = qInstallMessageHandler(lambda kind, context, message: seen.append(message))
    monkeypatch.setattr(qt_messages, "_installed", False)
    try:
        qt_messages.install()
        before = qt_messages.dropped
        qWarning("audio device has unrecognized channel, index: 2 label: 400")
        qWarning("Using Qt multimedia with FFmpeg version 7.1.5 LGPL version 2.1 or later")
        qWarning("QPainter::begin: Paint device returned engine == 0")
        assert qt_messages.dropped == before + 2
        assert seen == ["QPainter::begin: Paint device returned engine == 0"]
    finally:
        qInstallMessageHandler(previous)
