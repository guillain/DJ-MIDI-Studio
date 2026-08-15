import pytest

from djmidi.safe_update import prepare_update


def test_safe_update_previews_validates_applies_and_rolls_back(tmp_path):
    path = tmp_path / "mapping.xml"
    path.write_text("<old />\n", encoding="utf-8")
    plan = prepare_update(path, "<new />\n", lambda text: (_ for _ in ()).throw(ValueError()) if "bad" in text else None)
    assert "-<old />" in plan.diff
    plan.apply()
    assert path.read_text(encoding="utf-8") == "<new />\n"
    assert plan.backup_path.read_text(encoding="utf-8") == "<old />\n"
    plan.rollback()
    assert path.read_text(encoding="utf-8") == "<old />\n"


def test_safe_update_validates_before_creating_a_backup(tmp_path):
    path = tmp_path / "mapping.xml"
    path.write_text("<old />\n", encoding="utf-8")
    with pytest.raises(ValueError):
        prepare_update(path, "bad", lambda text: (_ for _ in ()).throw(ValueError("invalid")))
    assert not path.with_name("mapping.xml.bak").exists()
