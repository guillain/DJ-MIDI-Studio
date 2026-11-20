from djmidi.dj_software import find_dj_software


def test_found_by_application_or_data_folder_running_first(tmp_path):
    apps = tmp_path / "Applications"
    (apps / "Native Instruments" / "Traktor Pro 4.app").mkdir(parents=True)
    (apps / "Mixxx.app").mkdir()
    home = tmp_path / "home"
    (home / "Music" / "_Serato_").mkdir(parents=True)
    found = find_dj_software(home=home, app_dirs=[apps], running=lambda: {"Mixxx"})
    assert [(s.id, s.running) for s in found] == [("mixxx", True), ("serato", False), ("traktor", False)]


def test_nothing_found(tmp_path):
    assert find_dj_software(home=tmp_path, app_dirs=[tmp_path / "none"], running=set) == []


def test_a_running_program_counts_even_if_installed_elsewhere(tmp_path):
    found = find_dj_software(home=tmp_path, app_dirs=[], running=lambda: {"rekordbox"})
    assert [(s.name, s.running) for s in found] == [("rekordbox", True)]
