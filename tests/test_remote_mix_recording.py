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
