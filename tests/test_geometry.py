from djmidi.gui.geometry import TRANSPORT_GEOMETRY, ControlGeometry


def test_transport_geometry_fractions_are_within_the_unit_square():
    for controller, entries in TRANSPORT_GEOMETRY.items():
        for label, geom in entries.items():
            assert 0.0 <= geom.x <= 1.0, f"{controller} {label} x out of range"
            assert 0.0 <= geom.y <= 1.0, f"{controller} {label} y out of range"
            assert geom.w > 0.0, f"{controller} {label} w must be positive"
            assert geom.h > 0.0, f"{controller} {label} h must be positive"
            assert geom.x + geom.w <= 1.0, f"{controller} {label} extends past the right edge"
            assert geom.y + geom.h <= 1.0, f"{controller} {label} extends past the bottom edge"
            assert geom.shape in ("rect", "circle")


def test_ddj_xp2_has_no_transport_geometry():
    """DDJ-XP2 is a pad/FX companion controller with no deck transport
    section (no PLAY/CUE/SYNC) -- see gui/geometry.py's module docstring."""
    assert "DDJ-XP2" not in TRANSPORT_GEOMETRY


def test_xdj_xz_transport_geometry_covers_the_expected_controls():
    assert set(TRANSPORT_GEOMETRY["XDJ-XZ"]) == {
        "PLAY/PAUSE",
        "CUE",
        "SYNC",
        "Jog wheel",
        "Tempo",
    }


def test_control_geometry_is_frozen():
    geom = ControlGeometry(0.1, 0.2, 0.3, 0.4, "rect", "#ffffff")
    try:
        geom.x = 0.5
        raise AssertionError("expected a FrozenInstanceError")
    except AttributeError:
        pass
