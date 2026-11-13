# Validation record — 13 November 2026

## Public macOS and Windows checks

All six jobs in [GitHub Actions run 43451304367](https://github.com/itemuln/okto-toolkit/actions/runs/43451304367) passed for runtime source commit `eeeb47b088bb380944dd2557aaf2311636330e1b`:

- macOS and Windows on Python 3.11 and 3.13: tests, lint, wheel/sdist builds, clean offline installation, and all five stages through both installed package and dependency-free launcher.
- Real Chromium diagnostics on both macOS and Windows.

This supersedes the original local-only platform limitations below. Actual event hardware and real OCR accuracy remain unverified.

## Checks performed

- Source tests on macOS ARM64 / Python 3.13.9: **57 passed**, including three real Chromium integration tests. The full suite ran in an isolated environment without NumPy/SoundFile, exercising the standard-library audio path.
- Separate source run with NumPy available: **54 passed, 3 browser tests skipped**. Browser tests run separately in the full suite above.
- Ruff static checks: passed.
- Graph results checked against an independent Floyd–Warshall implementation across 80 seeded random graphs and five destinations each, including reachable/disconnected negative cycles. Tests also cover exact decimal/rational costs, very large integers, isolated nodes and directed/undirected behavior.
- Encoding tests cover numeric ASCII, binary, hex, Base64, double/layered encodings, URL/HTML/escaped bytes, ROT13, reversal, XOR including high-byte wrapped ciphertext, ambiguous input, and malformed decoder branches.
- Audio tests cover 8/16/24/32-bit PCM WAV, stereo and stereo difference, FFT against a direct mathematical DFT, optional NumPy absence, duration limits, malformed/truncated WAV, and no invented password for a tone. OCR TSV parsing/no-text behavior is tested with controlled responses; this is not a test of actual OCR recognition.
- Real Chromium tests serve a local fixture and verify requested clicks, JavaScript exceptions, console errors, HTTP 500 responses, failed requests, computed hidden elements, HTTP 404 body retention, and incomplete-action warnings.
- Synthetic audio example: inspected the generated FFT-512 PNG visually; it displays **KEY**. The analyzer returns images and no password candidate when no OCR engine is available.

## Distribution checks

The delivered wheel, source distribution, and offline launcher are built from this source. `tools/smoke_release.py` checks a clean virtual environment with an offline/no-dependencies wheel install, the installed console entry point, and the `.pyz` with Python site packages disabled. It exercises all five stages and asserts nonzero error exits. The handoff's `RELEASE-CHECKS.txt` records the actual smoke-check outcome; rerun the script after modifying/rebuilding the package.

`dist/SHA256SUMS.txt` records artifact hashes. The outer handoff ZIP has its own SHA-256 file. Neither the presence of hashes nor this record is a code-signing certificate.

## Original local handoff limitations (before public checks)

- **No Windows machine was available for execution here.** The wheel is universal pure Python and uses portable file handling. Windows batch files and Windows/Linux CI are provided, but that workflow has not been run on a hosted repository. Validate Python installation, command launcher, console behavior, optional native wheels, and Chromium on the actual event PC.
- Python 3.11 is the declared minimum and has a configured CI lane, but local execution here used Python 3.13; the offline smoke launcher is additionally checked with the available Python 3.14 interpreter.
- Tesseract was not installed; actual password OCR recognition was not validated. Optional SoundFile codec coverage was not exhaustively tested. Use PCM WAV and visual inspection as the offline fallback.
- No original competition image or challenge attachments were available in the retrieved conversation. Examples are synthetic, and performance on the event's actual files is unverified. No heuristic module promises perfect automatic solutions.
- No PyPI publication, upload, remote repository creation, or deployment was performed. The event host confirmed that prewritten tools are allowed.
