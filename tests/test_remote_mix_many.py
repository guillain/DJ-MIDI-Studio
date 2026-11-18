"""Remote mix phase 9: several DJs in a star around the host."""

import time

from djmidi.remote_mix import probe


def _wait(condition, seconds=3.0):
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.01)
    return condition()


def test_the_host_admits_guests_gives_them_ids_and_relays_the_mixer():
    host = probe.ProbeSession(port=0, bind_host="127.0.0.1", interval=0.02, max_peers=2, name="Host")
    host.start()
    guests = []
    try:
        for name in ("Alex", "Sam", "Late"):
            guest = probe.ProbeSession(port=0, peer=("127.0.0.1", host.port), bind_host="127.0.0.1", interval=0.02, name=name)
            guest.start()
            guests.append(guest)
        alex, sam, late = guests
        assert _wait(lambda: alex.my_id is not None and sam.my_id is not None and len(alex.roster) == 3)
        assert {alex.my_id, sam.my_id} == {1, 2}
        assert alex.roster[0] == "Host" and set(alex.roster.values()) == {"Host", "Alex", "Sam"}
        assert late.my_id is None  # the room is full
        assert set(host.peer_ids()) == {"127.0.0.1"} and sorted(host._guests.values()) == [1, 2]
        alex.send({"k": "mix", "c": {"crossfader": [30, 1, 0]}})
        assert _wait(lambda: not sam.inbox.empty())  # through the hub
        assert not host.inbox.empty()
        assert alex.inbox.empty()  # never echoed back to the sender
    finally:
        for session in (*guests, host):
            session.stop()


import sys

import numpy as np
import pytest

from djmidi.remote_mix import audio


@pytest.mark.skipif(sys.platform == "darwin", reason="needs 127.0.0.2/3 (all of 127/8 answers on Linux and Windows)")
def test_the_hub_relays_each_guests_sound_to_the_others_stamped_with_its_dj_id():
    ips = {"127.0.0.2": 1, "127.0.0.3": 2}
    port = 47911
    banks = [audio.PlayerBank() for _ in range(3)]
    hub = audio.AudioLink(port=port, peer=("127.0.0.1", port), bind_host="127.0.0.1", players=banks[0],
                          peer_ids=lambda: ips, hub=True, me=lambda: 0)
    guests = [
        audio.AudioLink(port=port, peer=("127.0.0.1", port), bind_host=ip, players=bank, me=lambda dj=dj: dj)
        for (ip, dj), bank in zip(ips.items(), banks[1:], strict=True)
    ]
    tone = np.full((audio.PACKET_FRAMES * 4, 2), 0.25, dtype=np.float32)
    try:
        guests[0].send(audio.packetize(tone, 0, 0.0, 120.0, audio.CODEC_PCM48))  # DJ 1 plays
        hub.send(audio.packetize(tone, 0, 0.0, 120.0, audio.CODEC_PCM48))  # the host plays
        deadline = time.monotonic() + 3
        while (banks[2].get(1).received < 4 or banks[2].get(0).received < 4) and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        for link in (hub, *guests):
            link.close()
    assert banks[0].get(1).received == 4  # the host hears DJ 1
    assert banks[2].get(1).received == 4  # DJ 2 hears DJ 1, through the host
    assert banks[2].get(0).received == 4 and banks[1].get(0).received == 4  # both hear the host
    assert banks[1].get(1).received == 0  # never your own sound back
