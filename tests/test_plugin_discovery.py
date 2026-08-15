from types import SimpleNamespace

from djmidi import catalog


def test_external_controller_plugins_require_trust(monkeypatch):
    loaded: list[str] = []
    entry_point = SimpleNamespace(
        name="untrusted.controller",
        load=lambda: loaded.append("loaded"),
    )
    previous_external_state = catalog._EXTERNAL_DISCOVERED
    previous_diagnostics = list(catalog.DISCOVERY_DIAGNOSTICS)
    try:
        catalog._EXTERNAL_DISCOVERED = False
        catalog.DISCOVERY_DIAGNOSTICS.clear()
        monkeypatch.setattr(catalog.importlib.metadata, "entry_points", lambda group: [entry_point])
        catalog.discover_plugins(trust_external=False)
        assert loaded == []
        assert "trust is disabled" in catalog.DISCOVERY_DIAGNOSTICS[0]
        catalog._EXTERNAL_DISCOVERED = False
        catalog.discover_plugins(trust_external=True)
        assert loaded == ["loaded"]
    finally:
        catalog._EXTERNAL_DISCOVERED = previous_external_state
        catalog.DISCOVERY_DIAGNOSTICS[:] = previous_diagnostics
