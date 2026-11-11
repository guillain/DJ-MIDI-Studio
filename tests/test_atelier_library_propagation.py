"""Issue #451 / epic #413: what the guided check learns about a controller
reaches every view of its features -- the feature card (Atelier and
Controller Emulator) says what the unit was seen sending, and a capture or a
verified LED recorded anywhere refreshes the others."""

from djmidi.atelier import captures as cap
from djmidi.atelier import library as lib
from djmidi.atelier.features import feature_by_id
from djmidi.atelier.led_data import LedRecord, save_led_record
from djmidi.catalog._registry import ControlInfo, ControllerDefinition, register
from djmidi.midi_io import MidiEvent

NAME = "Propagation Test"
SYNC = "deck.sync@1"


def _register():
    entries = [
        ControlInfo(NAME, "Deck", "Sync", "NOTE", ("1", "2"), "88"),
        ControlInfo(NAME, "Deck", "Cue", "NOTE", ("1", "2"), "12"),
    ]
    register(ControllerDefinition(name=NAME, static_entries=entries, section_order=("Deck",)), replace=True)


def test_the_knowledge_of_a_feature_follows_the_captures():
    _register()
    feature = feature_by_id(NAME, SYNC)
    assert lib.describe_knowledge(lib.knowledge_of(feature)) == "never tested on the unit"
    cap.record_capture(NAME, cap.CaptureRecord("Deck/Sync/plain", cap.OK, ("1", "NOTE", "88"), software="serato"))
    cap.record_capture(
        NAME, cap.CaptureRecord("Deck/Sync/plain", cap.MISMATCH, ("1", "NOTE", "16"), day="2026-11-10")
    )
    text = lib.describe_knowledge(lib.knowledge_of(feature))
    # Serato's verdict wins over "no software"; both are listed.
    assert text.startswith("verified — ")
    assert "Serato DJ Pro: verified" in text and "No DJ software running: mismatch" in text
    cap.forget_captures(NAME)
    cap.record_capture(NAME, cap.CaptureRecord("Deck/Sync/plain", cap.MISMATCH, ("1", "NOTE", "16")))
    assert "(the unit sent Note 16 ch 1)" in lib.describe_knowledge(lib.knowledge_of(feature))


def test_a_check_in_the_dialog_refreshes_the_atelier_and_the_emulator_cards():
    from djmidi.gui.atelier_view import AtelierView
    from djmidi.gui.feature_card import FeatureCard
    from djmidi.gui.profile_check_dialog import ProfileCheckDialog

    _register()
    atelier = AtelierView()
    atelier.controller_combo.setCurrentText(NAME)
    atelier.select_feature(SYNC)
    assert "never tested" in atelier.feature_card.checked_label.text()
    atelier.set_led_choice(2)  # an unsaved scene edit survives the refresh
    emulator_card = FeatureCard()  # the Controller Emulator's inspector
    emulator_card.set_feature(feature_by_id(NAME, SYNC))

    def refresh(controller):
        atelier.refresh_library(controller)
        emulator_card.refresh()

    dialog = ProfileCheckDialog([NAME], ["TEST"], ensure_listening=lambda: True, initial=NAME)
    dialog.libraryChanged.connect(refresh)
    dialog.software_combo.setCurrentIndex(dialog.software_combo.findData("serato"))
    assert dialog.start() and dialog.check.current.title == "Sync"
    dialog.feed_event(MidiEvent("in", "1", "Note On", "88", "127", 0.0, "TEST"))
    for card in (atelier.feature_card, emulator_card):
        assert card.checked_label.text().startswith("verified — Serato DJ Pro: verified")
    assert atelier.is_dirty and atelier.feature.id == SYNC

    save_led_record(NAME, LedRecord(SYNC, 1, 88, source="light check"))
    dialog.libraryChanged.emit(NAME)
    assert atelier.feature.led.verified and "verified (light check)" in atelier.feature_card.led_label.text()
    assert emulator_card.feature.led.verified
    dialog.close()


def test_the_main_window_propagates_library_changes():
    from djmidi.gui.main_window import MainWindow

    _register()
    window = MainWindow()
    window.atelier_view.controller_combo.setCurrentText(NAME)
    window.atelier_view.select_feature(SYNC)
    dialog = window.open_profile_check(NAME)
    save_led_record(NAME, LedRecord(SYNC, 1, 88, source="light check"))
    dialog.libraryChanged.emit(NAME)
    assert window.atelier_view.feature.led.verified
    dialog.close()
    window.close()
