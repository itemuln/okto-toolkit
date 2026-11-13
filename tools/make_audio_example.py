"""Generate a synthetic KEY spectrogram fixture, using only the standard library."""

import math
import struct
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
glyphs = [
    ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
]
rows = ["00" + "00".join(glyph[row] for glyph in glyphs) + "00" for row in range(7)]
rate, block = 8000, 1024
samples = bytearray()
for col in range(len(rows[0])):
    frequencies = [600 + (6 - row) * 400 for row in range(7) if rows[row][col] == "1"]
    for sample in range(block):
        t = sample / rate
        # Thick horizontal bands make the synthetic glyphs easier to inspect.
        tones = [f + offset for f in frequencies for offset in (-32, 0, 32)]
        value = sum(math.sin(2 * math.pi * f * t) for f in tones) / 24
        samples.extend(struct.pack("<h", round(value * 32767)))
path = ROOT / "examples" / "hidden-key.wav"
with wave.open(str(path), "wb") as output:
    output.setnchannels(1)
    output.setsampwidth(2)
    output.setframerate(rate)
    output.writeframes(samples)
print(path)
