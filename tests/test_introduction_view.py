from seratomidiconf.gui.introduction_view import IntroductionView


def test_refresh_controllers_populates_known_names():
    view = IntroductionView()
    view.refresh_controllers()
    assert view._controller_combo.count() >= 2
    assert "DDJ-XP2" in [view._controller_combo.itemText(i) for i in range(view._controller_combo.count())]


def test_drilldown_signal_emits_target_and_selected_controller():
    view = IntroductionView()
    view._controller_combo.setCurrentText("XDJ-XZ")

    captured: list[tuple[str, str]] = []
    view.drillDownRequested.connect(lambda target, controller: captured.append((target, controller)))

    view._emit_drilldown("deck")
    assert captured == [("deck", "XDJ-XZ")]


def test_refresh_controllers_builds_controller_cards():
    view = IntroductionView()
    view.refresh_controllers()
    assert "DDJ-XP2" in view._card_stats
    assert "XDJ-XZ" in view._card_stats


def test_set_loaded_config_info_updates_status_label():
    view = IntroductionView()
    view.set_loaded_config_info("/tmp/example.xml", control_count=640)
    assert "example.xml" in view._loaded_file_label.text()
    assert "640" in view._loaded_file_label.text()


def test_usage_summary_updates_card_stats():
    view = IntroductionView()
    usage = {
        ("DDJ-XP2", "PAD", "Pad 1"): {"1": {"codfather_st", "foo"}},
        ("DDJ-XP2", "PAD", "Pad 2"): {"2": {"bar"}},
        ("XDJ-XZ", "PAD", "Pad 5"): {"1": {"baz"}},
    }
    view.set_usage_summary(usage)
    text = view._card_stats["DDJ-XP2"].text()
    assert "2 cell(s)" in text
    assert "2 deck(s)" in text
    assert "3 function(s)" in text


