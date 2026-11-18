"""Remote mix phase 2: the other DJ's sound, one bar late, on your grid."""

import time

import numpy as np
import pytest

from djmidi.remote_mix import audio as a

TEMPO = 120.0  # two beats a second: one bar = 2 s = 96000 samples


def _tone(n, start=0):
    t = np.arange(start, start + n) / a.RATE
    mono = 0.5 * np.sin(2 * np.pi * 440 * t)
    return np.stack([mono, -mono], axis=1).astype(np.float32)


def test_packets_round_trip_and_fit_an_internet_packet():
    samples = _tone(a.PACKET_FRAMES)
    packet = a.AudioPacket(position=4800, beat=12.5, tempo=TEMPO, samples=samples)
    data = a.encode_packet(packet)
    assert len(data) <= 1400
    back = a.decode_packet(data)
    assert (back.position, back.beat, back.tempo) == (4800, 12.5, TEMPO)
    assert np.allclose(back.samples, samples, atol=1e-4)
    light = a.decode_packet(a.encode_packet(a.AudioPacket(0, 0.0, TEMPO, samples, codec=a.CODEC_PCM24)))
    assert light.samples.shape == samples.shape
    assert len(a.encode_packet(a.AudioPacket(0, 0.0, TEMPO, samples, codec=a.CODEC_PCM24))) < len(data) * 0.6


def test_decode_refuses_foreign_or_broken_packets():
    good = a.encode_packet(a.AudioPacket(0, 0.0, TEMPO, _tone(a.PACKET_FRAMES)))
    assert a.decode_packet(b"x" * 40) is None
    assert a.decode_packet(good[:-2]) is None
    assert a.decode_packet(good + b"\0\0\0\0") is None
    assert a.decode_packet(b"DJMA" + b"\x09" + good[5:]) is None


def test_packetize_stamps_each_packet_with_its_own_beat():
    packets = a.packetize(_tone(a.PACKET_FRAMES * 3), position=0, beat=8.0, tempo=TEMPO, codec=a.CODEC_PCM48)
    assert [p.position for p in packets] == [0, 240, 480]
    assert packets[2].beat == pytest.approx(8.0 + 480 / a.RATE * 2)


def _feed(player, seconds, beat0=0.0, skip=()):
    samples = _tone(int(seconds * a.RATE))
    for i, packet in enumerate(a.packetize(samples, 0, beat0, TEMPO, a.CODEC_PCM48)):
        if i not in skip:
            player.push(packet)
    return samples


def test_the_sound_comes_back_exactly_one_bar_after_its_beat():
    player = a.BarAlignedPlayer()
    sent = _feed(player, 3.0)
    # Locally at beat 4.5 we must hear what was sent at beat 0.5 = sample 12000.
    out = player.read(480, beat=4.5)
    assert np.allclose(out, sent[12000:12480], atol=1e-4)
    # The cursor runs on by itself.
    assert np.allclose(player.read(480, beat=4.5 + 480 / a.RATE * 2), sent[12480:12960], atol=1e-4)
    assert player.resyncs == 0 and player.gap_ratio() == 0


def test_small_jitter_keeps_the_cursor_and_a_real_jump_resyncs():
    player = a.BarAlignedPlayer()
    _feed(player, 3.0)
    player.read(240, beat=4.5)
    player.read(240, beat=4.5 + 240 / a.RATE * 2 + 0.004)  # 2 ms late: under the 8 ms window
    assert player.resyncs == 0
    player.read(240, beat=5.5)
    assert player.resyncs == 1


def test_lost_packets_play_as_silence_and_count_as_gaps():
    player = a.BarAlignedPlayer()
    _feed(player, 1.0, skip={50})
    out = player.read(240, beat=4.0 + 50 * 240 / a.RATE * 2)
    assert not out.any()
    assert player.gap_ratio() == 1.0
    assert a.BarAlignedPlayer().read(10, beat=0).shape == (10, 2)  # nothing received yet


def test_crossfader_and_program_mix():
    assert a.crossfade_gains(0) == (1.0, 0.0)
    me, them = a.crossfade_gains(0.5)
    assert me == pytest.approx(them) and me**2 + them**2 == pytest.approx(1.0)
    ones = np.ones((4, 2), dtype=np.float32)
    assert np.allclose(a.program_mix(ones, ones * 0.5, 1.0, 1.0, 0.0), ones)
    assert np.allclose(a.program_mix(ones, ones * 0.5, 1.0, 1.0, 1.0), ones * 0.5, atol=1e-6)
    assert a.program_mix(ones, ones, 2.0, 2.0, 0.5).max() == 1.0


def test_two_links_carry_the_sound_over_localhost():
    player_a, player_b = a.BarAlignedPlayer(), a.BarAlignedPlayer()
    link_b = a.AudioLink(port=0, peer=("127.0.0.1", 9), player=player_b, bind_host="127.0.0.1")
    link_a = a.AudioLink(port=0, peer=("127.0.0.1", link_b.port), player=player_a, bind_host="127.0.0.1")
    try:
        link_a.send(a.packetize(_tone(a.PACKET_FRAMES * 10), 0, 0.0, TEMPO, a.CODEC_PCM24))
        deadline = time.monotonic() + 3
        while player_b.received < 10 and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        link_a.close()
        link_b.close()
    assert player_b.received == 10 and link_a.sent == 10


def test_send_buffer_only_sends_whole_packets_and_keeps_the_beat():
    buffer = a.SendBuffer()
    beats_per_frame = TEMPO / 60.0 / a.RATE
    first = buffer.add(_tone(300), position=0, beat=4.0, tempo=TEMPO, codec=a.CODEC_PCM48)
    assert [p.position for p in first] == [0]
    second = buffer.add(_tone(200, 300), position=300, beat=4.0 + 300 * beats_per_frame, tempo=TEMPO, codec=a.CODEC_PCM48)
    assert [p.position for p in second] == [240]
    assert second[0].beat == pytest.approx(4.0 + 240 * beats_per_frame)
    assert np.allclose(second[0].samples, _tone(240, 240))
    assert all(len(p.samples) == a.PACKET_FRAMES for p in first + second)


opus_missing = pytest.mark.skipif(a.opus.unavailable() is not None, reason="PyAV not installed")


@opus_missing
def test_opus_lands_the_sound_on_the_same_sample_and_is_small():
    encoder, decoder = a.opus.OpusEncoder(), a.opus.OpusDecoder()
    n = a.PACKET_FRAMES * 40
    samples = np.zeros((n, 2), dtype=np.float32)
    samples[2400] = 0.8  # a click
    player = a.BarAlignedPlayer()
    sizes = []
    for packet in a.packetize(samples, 0, 0.0, TEMPO, a.CODEC_OPUS):
        for datagram in a.encode_opus(packet, encoder):
            sizes.append(len(datagram))
            decoded = a.decode_packet(datagram, decoder)
            assert decoded is not None and len(decoded.samples) == a.PACKET_FRAMES
            player.push(decoded)
    assert a.decode_packet(datagram) is None  # no decoder, no sound
    # Read the whole thing back one bar later: the click is where it was sent.
    bar = 4 * a.RATE * 60 // int(TEMPO)
    heard = player.read(n, beat=4.0 + 0 * bar)
    assert abs(int(np.argmax(np.abs(heard[:, 0]))) - 2400) <= 2
    # 5 ms of stereo in well under a fifth of the PCM size.
    assert max(sizes[5:]) < a.PACKET_FRAMES * 4 / 3


@opus_missing
def test_two_links_carry_opus_over_localhost():
    player_b = a.BarAlignedPlayer()
    link_b = a.AudioLink(port=0, peer=("127.0.0.1", 9), player=player_b, bind_host="127.0.0.1")
    link_a = a.AudioLink(port=0, peer=("127.0.0.1", link_b.port), player=a.BarAlignedPlayer(), bind_host="127.0.0.1")
    try:
        link_a.send(a.packetize(_tone(a.PACKET_FRAMES * 10), 0, 0.0, TEMPO, a.CODEC_OPUS))
        deadline = time.monotonic() + 3
        while player_b.received < 10 and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        link_a.close()
        link_b.close()
    assert player_b.received == 10 and link_b.rejected == 0
