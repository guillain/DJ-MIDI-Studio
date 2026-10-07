"""Where mapping dialogs start, the recent-mappings list and the previous
version kept by every save (issue #175)."""

from djmidi import file_locations
from djmidi.safe_update import prepare_update


def test_push_recent_puts_the_path_first_without_duplicates_and_caps_the_list():
    recents = [f"/m/{n}.xml" for n in range(10)]
    updated = file_locations.push_recent(recents, "/m/5.xml", limit=4)
    assert updated == ["/m/5.xml", "/m/0.xml", "/m/1.xml", "/m/2.xml"]


def test_existing_recents_drops_moved_files(tmp_path):
    kept = tmp_path / "a.xml"
    kept.write_text("<midi/>")
    assert file_locations.existing_recents([str(kept), str(tmp_path / "gone.xml")]) == [str(kept)]


def test_backup_path_is_where_a_save_keeps_the_previous_version(tmp_path):
    target = tmp_path / "mapping.xml"
    target.write_text("<midi/>")
    plan = prepare_update(target, "<midi></midi>", lambda text: text)
    assert plan.backup_path == file_locations.backup_path(target) == tmp_path / "mapping.xml.bak"


def test_mapping_start_dir_prefers_last_dir_then_the_software_folder_then_home(tmp_path):
    home = tmp_path / "home"
    serato = home / "Music" / "_Serato_" / "MIDI" / "Xml"
    serato.mkdir(parents=True)
    traktor = home / "Documents" / "Native Instruments" / "Traktor 4.0.0" / "Settings"
    traktor.mkdir(parents=True)
    last = tmp_path / "last"
    last.mkdir()
    assert file_locations.mapping_start_dir("serato", last, home) == last
    assert file_locations.mapping_start_dir("serato", None, home) == serato
    assert file_locations.mapping_start_dir("traktor", tmp_path / "missing", home) == traktor
    assert file_locations.mapping_start_dir(None, None, home) == serato
    assert file_locations.mapping_start_dir(None, None, tmp_path / "empty") == tmp_path / "empty"
