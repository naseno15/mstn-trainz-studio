"""Write mono PCM16 WAV."""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np


def write_mono_pcm16(path: Path, mono: np.ndarray, sample_rate: int) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(np.rint(mono.astype(np.float64)), -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sample_rate))
        w.writeframes(pcm.tobytes())
