"""Remote mix phases 6, 7 and 9: one mixer shared by every DJ."""

from djmidi.remote_mix import table
from djmidi.remote_mix.table import CROSSFADER, SharedTable, strip_control


def test_controls_are_named_by_dj_so_every_computer_shows_the_same_mixer():
    host, guest = SharedTable(0), SharedTable(1)
    assert guest.receive(host.local_change(strip_control(0, "low"), 10)) == [("dj0_low", 10)]
    assert host.receive(guest.local_change(CROSSFADER, 20)) == [(CROSSFADER, 20)]
    assert table.default_assign(0) == table.XF_A and table.default_assign(1) == table.XF_B
    assert table.default_assign(2) == table.XF_THRU


def test_the_last_gesture_wins_and_old_packets_never_undo_it():
    host, guest = SharedTable(0), SharedTable(1)
    old = host.local_change(CROSSFADER, 10)
    guest.receive(old)
    newer = guest.local_change(CROSSFADER, 70)  # the guest moves after seeing it
    assert host.receive(newer) == [(CROSSFADER, 70)]
    assert guest.receive(old) == []  # a late duplicate changes nothing
    assert guest.values[CROSSFADER] == 70


def test_simultaneous_moves_settle_on_the_same_value_everywhere():
    host, guest, third = SharedTable(0), SharedTable(1), SharedTable(2)
    from_host = host.local_change("dj0_filter", 20)
    from_guest = guest.local_change("dj0_filter", 90)  # same control, same stamp
    from_third = third.local_change("dj0_filter", 60)
    for receiver, messages in ((host, (from_guest, from_third)), (guest, (from_third, from_host)), (third, (from_host, from_guest))):
        for message in messages:
            receiver.receive(message)
    assert host.values["dj0_filter"] == guest.values["dj0_filter"] == third.values["dj0_filter"] == 20  # host wins a tie


def test_a_snapshot_repairs_a_lost_packet_and_bad_messages_are_ignored():
    host, guest = SharedTable(0), SharedTable(1)
    host.local_change("dj0_high", 0)  # lost
    assert guest.receive(host.snapshot()) == [("dj0_high", 0)]
    assert SharedTable(1).snapshot() is None
    assert guest.receive({"k": "mix", "c": {"host_nope": [1, 99, 1], "dj1_low": ["x", 1, 0], "dj1_nope": [1, 1, 1]}}) == []
    assert guest.receive({"k": "ping"}) == []


def test_the_host_is_the_regie_until_someone_claims_it():
    host, guest, third = SharedTable(0), SharedTable(1), SharedTable(2)
    assert host.regie_is_mine and not guest.regie_is_mine
    claim = third.claim_regie()
    host.receive(claim)
    guest.receive(claim)
    assert third.regie_is_mine and host.regie == guest.regie == 2
    later = SharedTable(0)
    later.receive(third.snapshot())  # a lost claim comes back with the snapshot
    assert not later.regie_is_mine and later.regie == 2
