"""The shared tracklist of Mix Together (remote mix, phase 11)."""

import os
from datetime import UTC, datetime

from test_library_history import _serato_row, _write_session

from djmidi.gui.remote_mix_tracklist import TracklistPanel
from djmidi.library import history
from djmidi.remote_mix import tracklist

START = datetime(2026, 11, 21, 21, 0, tzinfo=UTC)
T0 = int(START.timestamp())


def test_rows_travel_once_in_play_order_and_late_joiners_get_them_again():
    host, guest = tracklist.SharedTracklist(0), tracklist.SharedTracklist(1)
    second = host.add("Strings of Life", "Rhythim Is Rhythim", T0 + 300)
    first = guest.add("Track A", "", T0 + 10)
    assert host.receive(first).dj == 1 and host.receive(first) is None
    assert host.receive(second) is None  # its own row
    assert [row.title for row in host.rows] == ["Track A", "Strings of Life"]
    assert host.add("  ", "nobody", T0) is None
    late = tracklist.SharedTracklist(2)
    for message in host.own_messages():
        late.receive(message)
    assert [row.label() for row in late.rows] == ["Rhythim Is Rhythim – Strings of Life"]
    text = tracklist.text_export(host.rows, lambda dj: ["Host", "Alex"][dj])
    assert "Alex — Track A" in text and "Host — Rhythim Is Rhythim – Strings of Life" in text


def test_the_watcher_reads_only_new_plays_of_the_newest_session(tmp_path):
    sessions = tmp_path / "History" / "Sessions"
    old = _write_session(sessions / "1.session", [_serato_row("/m/old.mp3", T0 - 86400, title="Old")])
    os.utime(old, (T0 - 86400, T0 - 86400))
    rows = [
        _serato_row("/m/before.mp3", T0 - 60, title="Before"),
        _serato_row("/m/a.mp3", T0 + 30, title="A", artist="X"),
        _serato_row("/m/cue.mp3", T0 + 40, title="Only cued", played=False),
    ]
    current = _write_session(sessions / "2.session", rows)
    os.utime(current, (T0 + 100, T0 + 100))
    assert tracklist.watchable_folder(tmp_path / "History") == (history.SOURCE_SERATO, sessions)
    watcher = tracklist.HistoryWatcher({history.SOURCE_SERATO: sessions}, START)
    assert [tracklist.entry_texts(e) for e in watcher.poll()] == [("A", "X")]
    assert watcher.poll() == []  # unchanged file: not read again
    _write_session(current, [*rows, _serato_row("D:\\Music\\b side.mp3", T0 + 400)])
    os.utime(current, (T0 + 500, T0 + 500))
    assert [tracklist.entry_texts(e) for e in watcher.poll()] == [("b side", "")]


def test_the_panel_shares_history_and_typed_tracks_and_saves_them(tmp_path):
    sessions = tmp_path / "History" / "Sessions"
    _write_session(sessions / "2.session", [_serato_row("/m/a.mp3", T0 + 30, title="A", artist="X")])
    sent = []
    panel = TracklistPanel(
        name_of=lambda dj: ["Host", "Alex"][dj],
        history_dirs=lambda: {history.SOURCE_SERATO: tmp_path / "History"},
        exports_dir=tmp_path / "Exports",
        now=lambda: START,
        wall=lambda: T0 + 600,
    )
    try:
        assert not panel.add_button.isEnabled() and not panel.save_button.isEnabled()
        panel.attach(0, sent.append)
        assert "Serato" in panel.source_label.text()
        panel.poll()
        assert sent[-1]["t"] == "A" and sent[-1]["a"] == "X"
        panel.track_edit.setText("Moodymann - Shades of Jae")
        panel.add_typed()
        assert sent[-1]["a"] == "Moodymann" and sent[-1]["t"] == "Shades of Jae"
        panel.receive(tracklist.SharedTracklist(1).add("Their track", "", T0 + 300))
        assert [panel.view.item(i).text().split("  ", 1)[1] for i in range(panel.view.count())] == [
            "Host — X – A", "Alex — Their track", "Host — Moodymann – Shades of Jae",
        ]
        sent.clear()
        panel.resend()
        assert len(sent) == 2
        panel.detach()
        assert panel.save_button.isEnabled() and not panel.add_button.isEnabled()
        path = panel.save()
        assert path.name == "mix-together-tracklist-20261121-210000.txt"
        assert "Alex — Their track" in path.read_text(encoding="utf-8")
    finally:
        panel.close()


def test_a_folder_without_history_is_refused(tmp_path):
    panel = TracklistPanel(history_dirs=dict)
    try:
        assert not panel.use_folder(tmp_path)
        assert "No Serato or Traktor history" in panel.status_label.text()
        panel.attach(0, lambda message: None)
        assert panel.watcher is None and "type your tracks" in panel.source_label.text()
    finally:
        panel.close()


def test_the_dialog_sends_the_tracklist_to_listeners_from_the_control_room(tmp_path):
    from djmidi.gui.remote_mix_dialog import RemoteMixDialog

    sent = []

    class Server:
        def send_message(self, message):
            sent.append(message)

    dialog = RemoteMixDialog(link_factory=lambda: None, addresses=list, controls_path=tmp_path / "c.json",
                             history_dirs=dict, exports_dir=tmp_path)
    try:
        dialog._tracklist_to_listeners()  # nobody listening, no list: nothing
        dialog.tracklist_panel.attach(0, lambda message: None)
        dialog.tracklist_panel.track_edit.setText("Track A")
        dialog.tracklist_panel.add_typed()
        dialog.sound_panel.listen_server = Server()
        dialog._tracklist_to_listeners()
        assert [(m["t"], m["who"]) for m in sent] == [("Track A", "DJ 1")]
    finally:
        dialog.sound_panel.listen_server = None
        dialog.close()


def test_find_this_track_offers_searches_for_the_selected_row(tmp_path, monkeypatch):
    opened = []
    panel = TracklistPanel(history_dirs=dict, exports_dir=tmp_path)
    monkeypatch.setattr(panel, "_open", opened.append)
    try:
        panel.attach(0, lambda message: None)
        assert not panel.find_button.isEnabled()
        panel.track_edit.setText("Moodymann - Shades of Jae")
        panel.add_typed()
        panel.view.setCurrentRow(0)
        assert panel.find_button.isEnabled()
        actions = panel.find_menu.actions()
        assert [a.text() for a in actions] == ["On Beatport", "On Bandcamp", "On Discogs", "On YouTube"]
        actions[0].trigger()
        assert opened == ["https://www.beatport.com/search?q=Moodymann+Shades+of+Jae"]
    finally:
        panel.close()
