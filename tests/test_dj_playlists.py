"""Issue #458: point Serato crates and Traktor playlists at the kept copy --
surgical, backed up, refused while the software runs. Temporary files only."""

from datetime import UTC, datetime
from html import escape
from pathlib import Path

from djmidi.library import dj_playlists as djp
from djmidi.library.serato_library import parse_crate, write_chunk, write_chunks
from djmidi.library.traktor_library import (
    NmlExportTrack,
    build_playlist_nml,
    parse_playlists,
)
from djmidi.library.workspace import traktor_location, volume_root


def _crate(path: Path, tracks: list[str]) -> bytes:
    root = volume_root(path.resolve())
    chunks = [("vrsn", "1.0/Serato ScratchLive Crate".encode("utf-16-be"))]
    chunks.append(("osrt", write_chunk("tvcn", "song".encode("utf-16-be"))))  # kept byte for byte
    for track in tracks:
        chunks.append(("otrk", write_chunk("ptrk", Path(track).relative_to(root).as_posix().encode("utf-16-be"))))
    data = write_chunks(chunks)
    path.write_bytes(data)
    return data


def test_serato_crates_list_the_kept_copy_once_and_keep_other_chunks(tmp_path):
    music = tmp_path.resolve() / "music"
    dropped, kept, other = str(music / "dl" / "a.mp3"), str(music / "a.mp3"), str(music / "c.mp3")
    crates = tmp_path / "Subcrates"
    crates.mkdir()
    friday = crates / "Friday.crate"
    _crate(friday, [dropped, other])
    both = crates / "Both.crate"
    _crate(both, [kept, other, dropped])
    untouched = _crate(crates / "Other.crate", [other])
    plan = djp.plan_serato(crates, [(dropped, kept)])
    assert {change.path.name: (change.replaced, change.removed) for change in plan.changes} == {
        "Both.crate": (0, 1),
        "Friday.crate": (1, 0),
    }
    backup = djp.apply(plan, tmp_path / "backups", now=datetime(2026, 11, 12, 10, 0, tzinfo=UTC))
    root = volume_root(friday.resolve())
    assert [str(root / p) for p in parse_crate(friday)] == [kept, other]
    assert [str(root / p) for p in parse_crate(both)] == [kept, other]
    assert b"o\x00s\x00r\x00t" not in friday.read_bytes() and b"osrt" in friday.read_bytes()
    assert (crates / "Other.crate").read_bytes() == untouched
    assert backup.name == "serato-playlists-20261112-100000"
    assert sorted(p.name for p in backup.iterdir()) == ["Both.crate", "Friday.crate"]
    assert djp.apply(djp.plan_serato(crates, [(dropped, kept)]), tmp_path / "backups") is None


def _nml(path: Path, collection: list[str], playlist: list[str], volumes: Path) -> None:
    def track(p):
        volume, directory, filename = traktor_location(p, volumes)
        return NmlExportTrack(volume, directory, filename, title=Path(p).stem)

    data = build_playlist_nml("Friday & Co", [track(p) for p in playlist])
    # The collection holds every track (build_playlist_nml lists only the playlist's).
    extra = b"".join(
        f'<ENTRY TITLE="x"><LOCATION DIR="{escape(track(p).directory)}" FILE="{track(p).filename}" VOLUME="" '
        f'VOLUMEID=""></LOCATION></ENTRY>'.encode()
        for p in collection
    )
    path.write_bytes(data.replace(b"<SETS", extra + b"<SETS", 1))


def test_traktor_playlists_change_only_their_keys_and_need_the_kept_copy_in_the_collection(tmp_path):
    volumes = tmp_path / "Volumes"
    volumes.mkdir()
    music = tmp_path.resolve() / "music & co"
    dropped, kept, lost = str(music / "dl" / "a.mp3"), str(music / "a.mp3"), str(music / "z.mp3")
    nml = tmp_path / "collection.nml"
    _nml(nml, [kept], [dropped, str(music / "c.mp3"), str(music / "b.mp3")], volumes)
    before = nml.read_bytes()
    plan = djp.plan_traktor(nml, [(dropped, kept), (str(music / "b.mp3"), lost)], volumes)
    assert plan.entries == 1 and set(plan.skipped) == {str(music / "b.mp3")}
    djp.apply(plan, tmp_path / "backups")
    after = nml.read_bytes()
    playlist = parse_playlists(nml)["Friday & Co"]
    kept_key = "".join(traktor_location(kept, volumes))
    assert playlist[0] == kept_key and len(playlist) == 3
    head = before.find(b"<PLAYLISTS")
    assert after[:head] == before[:head]  # the collection is byte-identical


def test_a_running_software_is_detected_from_the_process_list():
    processes = lambda: ["/Applications/Serato DJ Pro.app/Contents/MacOS/Serato DJ Pro", "/usr/bin/zsh"]
    assert djp.is_running(djp.SERATO, processes)
    assert not djp.is_running(djp.TRAKTOR, processes)
    assert djp.is_running(djp.TRAKTOR, lambda: ["Traktor Pro 4"])


def test_the_music_library_refuses_while_running_then_previews_backs_up_and_logs(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from djmidi.gui.music_library_view import MusicLibraryView

    music = tmp_path.resolve() / "music"
    dropped, kept = str(music / "dl" / "a.mp3"), str(music / "a.mp3")
    crates = tmp_path / "Subcrates"
    crates.mkdir()
    _crate(crates / "Friday.crate", [dropped])
    view = MusicLibraryView(db_path=":memory:")
    warnings, questions = [], []
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, text, *a, **k: warnings.append(text))
    monkeypatch.setattr(
        QMessageBox, "question", lambda _p, _t, text, *a, **k: questions.append(text) or QMessageBox.StandardButton.Yes
    )
    running = lambda: ["Serato DJ Pro"]
    assert view.repoint_dj_playlists(kept, [dropped], djp.SERATO, str(crates), processes=running) is None
    assert "Serato DJ Pro is running" in warnings[0] and not questions
    import djmidi.gui.music_library_view as mlv

    lists = []
    monkeypatch.setattr(mlv, "confirm_list", lambda *args, **kwargs: lists.append(args) or True)
    backup = view.repoint_dj_playlists(
        kept, [dropped], djp.SERATO, str(crates), processes=list, backup_root=tmp_path / "b"
    )
    [(cells, _tips)] = lists[0][4]
    assert cells == ("Friday.crate", "1 entry(ies) repointed, 0 duplicate entry(ies) removed")
    assert (backup / "Friday.crate").exists()
    assert parse_crate(crates / "Friday.crate")[0].endswith("music/a.mp3")
    assert view.db.list_changes()[0].kind == "dj-playlists"
    view.close_db()
