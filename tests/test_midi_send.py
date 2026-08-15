from __future__ import annotations

from unittest.mock import patch

from djmidi import midi_send


def test_cli_list_ports_returns_zero(capsys):
    with patch("sys.argv", ["djmidi-send-midi", "--list-ports"]), patch(
        "djmidi.midi_send.list_output_ports", return_value=["Port A", "Port B"]
    ):
        rc = midi_send.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "Port A" in out
    assert "Port B" in out


def test_cli_sends_message_when_all_args_present():
    with patch(
        "sys.argv",
        [
            "djmidi-send-midi",
            "--port",
            "Port A",
            "--type",
            "note_on",
            "--channel",
            "8",
            "--data1",
            "64",
            "--data2",
            "127",
        ],
    ), patch("djmidi.midi_send.send_midi_message") as mock_send:
        rc = midi_send.main()
    assert rc == 0
    mock_send.assert_called_once()


def test_cli_returns_error_code_on_send_failure(capsys):
    with patch(
        "sys.argv",
        [
            "djmidi-send-midi",
            "--port",
            "Port A",
            "--type",
            "note_on",
            "--channel",
            "8",
            "--data1",
            "64",
            "--data2",
            "127",
        ],
    ), patch("djmidi.midi_send.send_midi_message", side_effect=ValueError("boom")):
        rc = midi_send.main()
    err = capsys.readouterr().err
    assert rc == 2
    assert "boom" in err


def test_cli_missing_required_args_exits_with_parser_error():
    with patch("sys.argv", ["djmidi-send-midi", "--port", "Port A"]):
        try:
            midi_send.main()
            assert False, "Expected parser to exit"
        except SystemExit as exc:
            assert exc.code == 2


def test_cli_double_click_sends_note_on_and_note_off_twice():
    with patch(
        "sys.argv",
        [
            "djmidi-send-midi",
            "--port",
            "Port A",
            "--type",
            "note_on",
            "--channel",
            "1",
            "--data1",
            "27",
            "--data2",
            "127",
            "--double-click",
            "--double-click-delay-ms",
            "0",
        ],
    ), patch("djmidi.midi_send.send_midi_message") as mock_send:
        rc = midi_send.main()
    assert rc == 0
    assert mock_send.call_count == 4


def test_cli_double_click_rejects_non_note_on_type(capsys):
    with patch(
        "sys.argv",
        [
            "djmidi-send-midi",
            "--port",
            "Port A",
            "--type",
            "cc",
            "--channel",
            "1",
            "--data1",
            "27",
            "--data2",
            "127",
            "--double-click",
        ],
    ):
        rc = midi_send.main()
    err = capsys.readouterr().err
    assert rc == 2
    assert "double-click" in err


