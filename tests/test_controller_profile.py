import json

from djmidi import catalog
from djmidi.catalog.profile import load_controller_profile


def test_load_controller_profile_registers_static_entries(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text(
        json.dumps(
            {
                "manifest": {
                    "plugin_id": "example.profile-controller",
                    "kind": "controller",
                    "name": "Example Profile Controller",
                    "version": "1.0.0",
                    "api_version": "1",
                    "vendor": "Example",
                    "license": "MIT",
                },
                "controller": {
                    "name": "Example Profile Controller",
                    "supported_software": ["serato"],
                    "entries": [
                        {
                            "section": "DECK",
                            "name": "PLAY",
                            "note_or_cc": "NOTE",
                            "channels": ["1"],
                            "data1": "60",
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    definition = load_controller_profile(path)
    try:
        assert definition.plugin_id == "example.profile-controller"
        assert any(hit.name == "PLAY" for hit in catalog.lookup("1", "Note On", "60"))
    finally:
        del catalog._registry._REGISTRY[definition.name]
