"""What's new dialog (issue #409): shows a release's own notes."""

from __future__ import annotations

from djmidi.gui import whats_new_dialog as whats_new_dialog_module
from djmidi.gui.whats_new_dialog import WhatsNewDialog
from djmidi.update_check import ReleaseInfo

_RELEASE = ReleaseInfo(
    tag="v9.1.0-future",
    version=(9, 1, 0),
    url="https://github.com/guillain/DJ-MIDI-Studio/releases/tag/v9.1.0-future",
    name="DJ MIDI Studio v9.1.0",
    body="## Added\n\n- A great new thing",
)


def test_dialog_renders_the_release_notes_as_markdown():
    dialog = WhatsNewDialog(_RELEASE)
    assert "v9.1.0" in dialog.windowTitle()
    assert dialog.notes.toPlainText().strip() == "Added\nA great new thing"  # markdown stripped of syntax
    dialog.close()


def test_dialog_falls_back_to_a_placeholder_without_notes():
    release = ReleaseInfo(tag="v9.1.0-future", version=(9, 1, 0), url=_RELEASE.url)
    dialog = WhatsNewDialog(release)
    assert "No release notes" in dialog.notes.toPlainText()
    dialog.close()


def test_open_release_page_button_opens_the_url(monkeypatch):
    opened = []
    monkeypatch.setattr(whats_new_dialog_module.QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    dialog = WhatsNewDialog(_RELEASE)
    dialog.open_button.click()
    assert opened == [_RELEASE.url]
    dialog.close()


def test_close_button_rejects_the_dialog():
    dialog = WhatsNewDialog(_RELEASE)
    results = []
    dialog.rejected.connect(lambda: results.append("rejected"))
    dialog.buttons.button(dialog.buttons.StandardButton.Close).click()
    assert results == ["rejected"]
