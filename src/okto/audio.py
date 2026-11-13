"""Offline spectrograms: PCM WAV + radix-2 FFT + PNG need no dependencies."""

import cmath
import csv
import io
import math
import shutil
import struct
import subprocess
import wave
import zlib
from pathlib import Path

from .common import Candidate, Report, read_bytes
from .encoding import FLAG


def fft(values):
    """Iterative radix-2 FFT, used when NumPy is unavailable."""
    size = len(values)
    if size < 2 or size & (size - 1):
        raise ValueError("FFT length must be a power of two >= 2.")
    output = [complex(value) for value in values]
    j = 0
    for i in range(1, size):
        bit = size >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            output[i], output[j] = output[j], output[i]
    length = 2
    while length <= size:
        root = cmath.exp(-2j * math.pi / length)
        half = length // 2
        for start in range(0, size, length):
            factor = 1 + 0j
            for k in range(start, start + half):
                even, odd = output[k], factor * output[k + half]
                output[k], output[k + half] = even + odd, even - odd
                factor *= root
        length *= 2
    return output[: size // 2 + 1]


def write_png(path: Path, rows: list[bytes]):
    height, width = len(rows), len(rows[0])

    def chunk(kind, payload):
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload))
        )

    content = b"\x89PNG\r\n\x1a\n"
    content += chunk(b"IHDR", struct.pack(">2I5B", width, height, 8, 0, 0, 0, 0))
    content += chunk(b"IDAT", zlib.compress(b"".join(b"\0" + row for row in rows)))
    content += chunk(b"IEND", b"")
    path.write_bytes(content)


def load_audio(path: str | Path, seconds: float):
    try:
        with wave.open(str(path), "rb") as stream:
            rate, channels, width = (
                stream.getframerate(),
                stream.getnchannels(),
                stream.getsampwidth(),
            )
            total = stream.getnframes()
            if rate <= 0 or channels <= 0:
                raise ValueError("Invalid WAV sample rate or channel count.")
            if channels > 8:
                raise ValueError("Audio supports at most 8 channels; split channels first.")
            if min(total, int(seconds * rate)) * channels > 4_000_000:
                raise ValueError(
                    "Audio sample budget exceeded (4 million samples); lower --seconds or split the file."
                )
            requested = min(total, int(seconds * rate))
            raw = stream.readframes(requested)
        frame_size = width * channels
        if len(raw) != requested * frame_size:
            raise ValueError("Truncated WAV: fewer sample bytes than declared in the header.")
        samples = []
        for offset in range(0, len(raw), width):
            value = int.from_bytes(raw[offset : offset + width], "little", signed=width != 1)
            samples.append((value - 128) / 128 if width == 1 else value / (2 ** (width * 8 - 1)))
        return [samples[c::channels] for c in range(channels)], rate, total / rate, "PCM WAV"
    except (wave.Error, EOFError):
        try:
            import soundfile as sf
        except ImportError:
            raise ValueError(
                "This is not a supported PCM WAV. Convert to PCM WAV or install the audio extra (soundfile)."
            ) from None
        try:
            with sf.SoundFile(path) as stream:
                if stream.channels > 8:
                    raise ValueError("Audio supports at most 8 channels.")
                if min(len(stream), int(seconds * stream.samplerate)) * stream.channels > 4_000_000:
                    raise ValueError(
                        "Audio sample budget exceeded (4 million samples); lower --seconds or split the file."
                    )
                values = stream.read(
                    frames=min(len(stream), int(seconds * stream.samplerate)), always_2d=True
                )
                return (
                    [values[:, c].tolist() for c in range(stream.channels)],
                    stream.samplerate,
                    len(stream) / stream.samplerate,
                    stream.format,
                )
        except RuntimeError as exc:
            raise ValueError(f"Cannot decode audio: {exc}") from exc


def spectrogram(samples, rate: int, size: int, max_columns: int = 640):
    try:
        import numpy as np
    except ImportError:
        np = None
    window = [0.5 - 0.5 * math.cos(2 * math.pi * i / (size - 1)) for i in range(size)]
    # Hop by at most N/4 until the image cap; larger files explicitly report sampled coverage.
    starts = list(range(0, max(1, len(samples) - size + 1), max(1, size // 4)))
    sampled = len(starts) > max_columns
    if sampled:
        starts = sorted(
            {starts[round(i * (len(starts) - 1) / (max_columns - 1))] for i in range(max_columns)}
        )
    columns = []
    peak_bin, peak_energy = 0, 0.0
    height = min(512, size // 2 + 1)
    for start in starts:
        frame = [
            samples[i] * window[i - start] if i < len(samples) else 0
            for i in range(start, start + size)
        ]
        spectrum = np.fft.rfft(frame) if np is not None else fft(frame)
        powers = [abs(value) / size for value in spectrum]
        peak = max(range(len(powers)), key=powers.__getitem__)
        if powers[peak] > peak_energy:
            peak_bin, peak_energy = peak, powers[peak]
        # Bright text on black; absolute dBFS scale, 80 dB range.
        bins = []
        for row in range(height):
            lo = row * len(powers) // height
            hi = max(lo + 1, (row + 1) * len(powers) // height)
            power = max(powers[lo:hi], default=0)
            db = 20 * math.log10(max(power, 1e-12))
            bins.append(round(max(0, min(255, (db + 80) / 80 * 255))))
        columns.append(bins)
    rows = [bytes(column[row] for column in columns) for row in reversed(range(height))]
    return rows, {
        "fft_size": size,
        "frequency_resolution_hz": rate / size,
        "dominant_frequency_hz": peak_bin * rate / size,
        "columns": len(columns),
        "time_sampled": sampled,
        "backend": "numpy" if np is not None else "stdlib",
    }


def ocr_image(path: Path) -> list[Candidate]:
    """Use an already installed Tesseract executable; never download anything."""
    executable = shutil.which("tesseract")
    if not executable:
        return []
    result = subprocess.run(
        [executable, str(path.resolve()), "stdout", "--psm", "6", "tsv"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )
    if result.returncode:
        raise ValueError(f"Tesseract failed: {result.stderr[-300:]}")
    words = []
    confidences = []
    for row in csv.DictReader(io.StringIO(result.stdout), delimiter="\t"):
        if row.get("text", "").strip():
            words.append(row["text"].strip())
            confidences.append(float(row["conf"]))
    if not words:
        return []
    confidence = min(0.85, max(0.05, sum(confidences) / len(confidences) / 100 * 0.85))
    return [
        Candidate(
            " ".join(words),
            round(confidence, 3),
            [f"Tesseract OCR of {path.name}; unverified transcription"],
            "OCR text",
        )
    ]


def analyze(
    path: str | Path,
    output: str | Path,
    seconds: float = 60,
    use_ocr: bool = False,
    sizes=(512, 2048),
) -> Report:
    if not 0 < seconds <= 300:
        raise ValueError("Audio duration limit must be greater than 0 and at most 300 seconds.")
    if not sizes or any(n < 64 or n > 4096 or n & (n - 1) for n in sizes):
        raise ValueError("FFT sizes must be powers of two between 64 and 4096.")
    raw = read_bytes(path)
    channels, rate, duration, audio_format = load_audio(path, seconds)
    if not channels or not channels[0]:
        raise ValueError("Audio contains no samples.")
    if any(not math.isfinite(x) for channel in channels for x in channel):
        raise ValueError("Audio contains non-finite samples.")
    directory = Path(output)
    directory.mkdir(parents=True, exist_ok=True)
    report = Report("audio")
    report.facts = {
        "sample_rate": rate,
        "channels": len(channels),
        "duration_seconds": duration,
        "analyzed_seconds": len(channels[0]) / rate,
        "format": audio_format,
        "views": [],
    }
    for match in FLAG.finditer(raw.decode("latin1")):
        report.candidates.append(
            Candidate(
                match[0],
                0.90,
                [f"Printable flag-shaped bytes at file offset {match.start()}; may be metadata."],
                "embedded text",
            )
        )
    if duration > seconds:
        report.warnings.append(
            f"Only the first {seconds:g} seconds were analyzed. Increase --seconds or split the recording."
        )
    views = [(f"channel-{index + 1}", values) for index, values in enumerate(channels)]
    if len(channels) == 2:
        views.append(("stereo-difference", [(a - b) / 2 for a, b in zip(*channels)]))
    ocr_available = bool(shutil.which("tesseract"))
    for name, samples in views:
        for size in sizes:
            rows, facts = spectrogram(samples, rate, size)
            artifact = directory / f"{name}-fft-{size}.png"
            write_png(artifact, rows)
            report.artifacts.append(str(artifact.resolve()))
            report.facts["views"].append(dict(facts, channel=name, image=artifact.name))
            if use_ocr and ocr_available:
                # Test both polarities; visual inspection is still necessary.
                inverted = directory / f"{name}-fft-{size}-inverted.png"
                write_png(inverted, [bytes(255 - b for b in row) for row in rows])
                report.artifacts.append(str(inverted.resolve()))
                for image in (artifact, inverted):
                    try:
                        report.candidates.extend(ocr_image(image))
                    except (ValueError, subprocess.TimeoutExpired) as exc:
                        report.warnings.append(str(exc))
    if any(v["time_sampled"] for v in report.facts["views"]):
        report.warnings.append(
            "Images are time-sampled to 640 columns; brief signals may be missed. Split the audio into shorter clips."
        )
    if use_ocr and not ocr_available:
        report.warnings.append(
            "Tesseract is not installed/on PATH. Images were generated for manual inspection."
        )
    report.warnings.append(
        "Spectrogram/OCR cannot guarantee a password. No text found does not mean no hidden text exists."
    )
    report.next_steps = [
        "Open PNG views: time runs left to right; frequency runs from 0 at bottom to Nyquist at top.",
        "Inspect each channel and stereo difference; try --fft 4096 for higher frequency resolution.",
    ]
    return report.rank()
