import wave
from datetime import datetime

import numpy as np

from djmidi.remote_mix import recording


def test_the_program_mix_is_written_as_a_wav_block_by_block(tmp_path):
    path = tmp_path / "Exports" / recording.recording_name(datetime(2026, 11, 18, 21, 5, 0))  # noqa: DTZ001
    recorder = recording.ProgramRecorder(path)
    block = np.full((480, 2), 0.5, dtype=np.float32)
    recorder.write(block)
    recorder.write(block * 3)  # clipped, never wrapped
    recorder.close()
    assert path.name == "mix-together-20261118-210500.wav"
    assert recorder.seconds == 960 / 48_000
    with wave.open(str(path)) as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()) == (2, 2, 48_000, 960)
        pcm = np.frombuffer(wav.readframes(960), dtype="<i2")
    assert pcm[0] == 16383 and pcm.max() == 32767


def test_each_dj_gets_a_track_on_the_mix_timeline(tmp_path):
    import wave as wav
    from datetime import datetime

    import numpy as np

    from djmidi.remote_mix import recording

    started = datetime(2026, 11, 21, 21, 0)  # noqa: DTZ001
    stems = recording.StemsRecorder(tmp_path, started)
    block = np.full((480, 2), 0.25, np.float32)
    stems.write({0: block}, {0: "Host"})
    stems.write({0: block, 2: block}, {0: "Host", 2: "Sam B."})  # Sam joins
    stems.write({2: block}, {})  # the host's block is missing: silence
    stems.close()
    assert [p.name for p in stems.paths] == [
        "mix-together-20261121-210000-dj1-Host.wav",
        "mix-together-20261121-210000-dj3-Sam-B.wav",
    ]
    for path in stems.paths:
        with wav.open(str(path)) as f:
            assert f.getnframes() == 3 * 480  # same length: the same timeline
    with wav.open(str(stems.paths[1])) as f:
        frames = np.frombuffer(f.readframes(960), dtype="<i2")
    assert not frames[:960].any() and frames[960:].all()  # silence until Sam joined


def test_a_flac_recording_holds_every_frame(tmp_path):
    from datetime import datetime

    import av
    import numpy as np

    from djmidi.remote_mix import recording

    path = tmp_path / recording.recording_name(datetime(2026, 11, 21, 21, 0), recording.FLAC)  # noqa: DTZ001
    recorder = recording.open_recorder(path)
    assert isinstance(recorder, recording.FlacRecorder)
    for _ in range(5):
        recorder.write(np.full((960, 2), 0.25, np.float32))
    recorder.close()
    assert path.name == "mix-together-20261121-210000.flac" and recorder.seconds == 0.1
    with av.open(str(path)) as container:
        stream = container.streams.audio[0]
        assert stream.rate == 48_000 and sum(frame.samples for frame in container.decode(stream)) == 4800
