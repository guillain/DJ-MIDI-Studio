"""Remote mix phase 6: one mixer shared by both DJs."""

from djmidi.remote_mix import controls
from djmidi.remote_mix.table import GUEST, HOST, SharedTable


def test_my_channel_is_their_them_and_the_crossfader_flips():
    host, guest = SharedTable(HOST), SharedTable(GUEST)
    assert guest.receive(host.local_change("me_low", 10)) == [("them_low", 10)]
    assert host.receive(guest.local_change(controls.ME, 80)) == [(controls.THEM, 80)]
    # Crossfader at 20 on the host = mostly the host = 80 on the guest, who has itself on the left.
    assert guest.receive(host.local_change(controls.CROSSFADER, 20)) == [(controls.CROSSFADER, 80)]


def test_the_last_gesture_wins_and_old_packets_never_undo_it():
    host, guest = SharedTable(HOST), SharedTable(GUEST)
    old = host.local_change(controls.CROSSFADER, 10)
    guest.receive(old)
    newer = guest.local_change(controls.CROSSFADER, 70)  # the guest moves after seeing it
    assert host.receive(newer) == [(controls.CROSSFADER, 30)]
    assert guest.receive(old) == []  # a late duplicate changes nothing
    assert guest.values[controls.CROSSFADER] == 70


def test_simultaneous_moves_settle_on_the_same_value_on_both_sides():
    host, guest = SharedTable(HOST), SharedTable(GUEST)
    from_host = host.local_change("me_filter", 20)
    from_guest = guest.local_change("them_filter", 90)  # same control (the host's filter), same stamp
    host.receive(from_guest)
    guest.receive(from_host)
    assert host.values["me_filter"] == guest.values["them_filter"] == 20  # the host wins a tie


def test_a_snapshot_repairs_a_lost_packet_and_bad_messages_are_ignored():
    host, guest = SharedTable(HOST), SharedTable(GUEST)
    host.local_change("me_high", 0)  # lost
    assert guest.receive(host.snapshot()) == [("them_high", 0)]
    assert SharedTable(GUEST).snapshot() is None
    assert guest.receive({"k": "mix", "c": {"host_nope": [1, 99, 1], "guest_low": ["x", 1, 0]}}) == []
    assert guest.receive({"k": "ping"}) == []
