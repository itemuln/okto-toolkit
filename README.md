# OKTO competition toolkit

Five local analysis tools, one CLI, no required third-party packages. Supported targets: **Windows and macOS**, with **Python 3.11 or later**. The offline `.pyz` file includes the toolkit, **not the Python interpreter**.

## Public download

- [Download the latest release](https://github.com/itemuln/okto-toolkit/releases/latest)
- [Download the single-file offline launcher](https://github.com/itemuln/okto-toolkit/releases/latest/download/okto.pyz)
- [Source code and automated checks](https://github.com/itemuln/okto-toolkit)

Download `okto.pyz`, open a terminal in its folder, and run:

**Windows (PowerShell):**

```powershell
py -3 okto.pyz --help
py -3 okto.pyz solve "C:\path\to\input.txt"
```

**macOS (Terminal):**

```sh
python3 okto.pyz --help
python3 okto.pyz solve "/path/to/input.txt"
```

Use `audio file.wav`, `logs file.log`, `web index.html`, or `graph graph.json` to select a stage explicitly. Download once; the core tools run offline. Optional browser/OCR features need their additional components prepared separately.

For an installed package, create a virtual environment with your Python interpreter and install the public wheel:

```sh
python -m pip install https://github.com/itemuln/okto-toolkit/releases/download/v1.0.0/okto_toolkit-1.0.0-py3-none-any.whl
python -m okto --help
```

The event host confirmed in this task that prewritten tools are permitted. The accessible competition chat described five stages but supplied no original competition image or challenge files. These implementations follow those stage descriptions; the examples are synthetic practice fixtures, not answers to the actual competition.

## Install from PyPI

Use a virtual environment so installation also works with managed Python installations.

**Windows (PowerShell):**

```powershell
py -3 -m venv okto-env
.\okto-env\Scripts\python -m pip install okto-toolkit
.\okto-env\Scripts\python -m okto --help
.\okto-env\Scripts\python -m okto solve input.txt
```

**macOS (Terminal):**

```sh
python3 -m venv okto-env
./okto-env/bin/python -m pip install okto-toolkit
./okto-env/bin/python -m okto --help
./okto-env/bin/python -m okto solve input.txt
```

The [PyPI project page](https://pypi.org/project/okto-toolkit/) shows available versions. The core package has no required third-party dependencies. For extras, install `"okto-toolkit[audio,web]"` in the same environment and follow the preparation section below.

## Windows: start here

Extract the source ZIP. Open PowerShell in the extracted `okto-toolkit` folder.

```powershell
py -3 --version
py -3 dist\okto.pyz doctor
py -3 dist\okto.pyz solve examples\puzzle.txt
py -3 dist\okto.pyz solve examples\server.log
py -3 dist\okto.pyz solve examples\graph.json --json
py -3 dist\okto.pyz web examples\interface.html
py -3 dist\okto.pyz audio recording.wav --output spectrograms
py -3 dist\okto.pyz audio examples\hidden-key.wav --fft 512 --output practice-views
```

Alternatively, install the included universal wheel **offline**:

```powershell
py -3 -m pip install --no-index --no-deps --find-links=dist okto-toolkit
py -3 -m okto --help
```

`install-windows.cmd` runs the same offline install. `okto.cmd` runs the `.pyz` directly. Installed users can use `okto` if their Python Scripts directory is on PATH; `py -3 -m okto` avoids that requirement. On machines with several Python versions, use `py -3.13` or another installed version >=3.11 consistently. No administrator rights should be needed in a writable virtual environment.

The direct GitHub wheel and offline launcher are alternatives to installing from PyPI, and can be transferred to a computer without internet access.

Practice fixture answers: the puzzle is double Base64 encoding of `flag{offline_ready}`; the log includes `flag{log_clue}` and a suspicious backup path; the audio draws `KEY`; the HTML has a mismatched button selector and a hidden source flag; the graph's A → B → C → D path costs 0.

## Commands and reports

```powershell
okto solve input.txt                         # infer a stage
okto solve clues.txt --stage logs            # override ambiguous inference
okto encoding puzzle.txt --depth 4 --limit 10
okto logs server.log --report findings.json
okto audio secret.wav --fft 512 2048 4096 --seconds 30 --output views
okto audio secret.wav --ocr --output views
okto web index.html
okto web http://localhost:3000 --browser
okto web http://localhost:3000 --browser --click "#start" --click "#unlock"
okto graph graph.json --source A --target D --json
okto doctor --json
```

Use the `.pyz` prefix in place of `okto` when running without installation. Every analysis command accepts `--json`, `--report FILE`, and `--limit N`. Reports use schema version 1 and include `stage`, `status`, `candidates`, `facts`, `warnings`, `next_steps`, and `artifacts`. Each candidate has a value, score, kind, and evidence.

**Confidence scores are heuristic rankings, not probabilities.** Text, log, audio, and interface reports remain `review`; a plausible password is not a verified password. Graph results are `solved` only for the supplied graph assumptions. Exit codes: 0 = analysis completed (including ambiguous, unreachable, or unbounded results), 2 = invalid input/dependency or I/O failure, 130 = cancelled. Inspect `facts.outcome` for graph outcomes. Optional browser/OCR failure retains available evidence and adds a warning.

Inference uses URLs and file extensions: audio formats → audio, HTML → web, `.log`/`.jsonl` → logs, JSON with `edges` → graph. Other files default to encoding **with an ambiguity warning**. Graph edge-list text, screenshots, and archive contents are not automatically parsed. Provide graph JSON explicitly; extract archives manually.

## What each stage does

| Stage | Automatic analysis | Evidence and limitations |
|---|---|---|
| ASCII / encoding | Decimal ASCII, binary, hex, Base64/Base64 URL, Base32, escaped hex, URL/HTML entities, all Caesar shifts including ROT13, reversal, single-byte XOR, layered beam search | Transformation chains and readability scores; English-biased, bounded depth/beam; does not solve arbitrary cryptography or infer unknown XOR keys of multiple bytes |
| Logs / paths | Unix/Windows/UNC paths, percent-decoded paths, suspicious-line correlation, flag patterns, labelled encoded payloads, timezone-aware UTC ordering, possible error codes | Line numbers, timestamps, snippets, occurrence counts; log formats vary, numeric codes may not be HTTP statuses, mentioned paths may not exist |
| Audio / spectrogram | PCM WAV decoding, multiple FFT resolutions, per-channel and stereo-difference images, embedded flag-shaped bytes, optional Tesseract OCR in both polarities | PNGs and technical metadata; no guaranteed text/password, no speech recognition, no invented transcription when OCR is absent |
| Interface debugging | Duplicate IDs, absent static selectors, hidden elements, source comments/flags, missing relative local assets; optional real-browser errors, failed requests, HTTP >=400 responses, computed hidden elements | Observations plus likely causes; does not automatically patch a site or understand arbitrary application logic |
| Weighted graph | BFS for unit weights, Dijkstra for nonnegative weights, Bellman–Ford for negative edges, reachable negative-cycle witness and affected destinations | Exact integer/rational arithmetic; one shortest path, exact distance, all-node distances; no finite minimum when a relevant negative cycle exists |

The browser executes the page's JavaScript when `--browser` is specified. It loads a page without automatically clicking or submitting forms. Only explicit `--click` selectors trigger interactions; these can change application state. Runtime collection covers navigation, requested clicks, and a 750 ms settling period, so delayed or untriggered failures can be missed. Static mode fetches one HTML document and does not fetch remote assets. No custom scripts from inputs are executed by the encoding, log, graph, or audio analyzers.

### Graph JSON

```json
{
  "directed": true,
  "source": "A",
  "target": "D",
  "nodes": ["A", "B", "C", "D", "isolated"],
  "edges": [["A", "B", 4], ["A", "C", 5], ["B", "C", -7], ["C", "D", 3]]
}
```

`nodes` is optional except for isolated vertices. Source/target must be supplied in the file or CLI; no guessing. Node IDs are strings or integers, normalized to strings; mixing `1` and `"1"` as distinct nodes is rejected. CLI `--source 1` can select integer node 1. Edges are triples; parallel edges and self-loops are supported. Directed defaults to true with a warning if omitted. Undirected negative edges allow traversal both ways and therefore form negative cycles.

Weights can be integers, decimals, or quoted rational strings such as `"1/3"`. JSON decimals are read without float rounding. The Python API converts float weights via their decimal string; pass strings/Fraction-compatible values for intended exact rationals. Costs are integers when integral, otherwise strings such as `"3/10"`. Unreachable distances are JSON `null`; negatively unbounded distances are `"-infinity"`. A negative cycle that cannot reach the requested target does not invalidate that target's finite result. Disconnected negative cycles are irrelevant to the source and are not reported as source-reachable.

### Audio interpretation

Images have time left to right and frequency bottom to top (0 to sample rate / 2). PNGs use an 80 dB range, bright energy on black, and no axes so hidden letters remain unobstructed. Dimensions and frequency resolution appear under `facts.views`. Silence produces images without claiming a password.

Default analysis covers only the first 60 seconds. Change `--seconds` (up to 300), or split the recording. Each view samples at most 640 time columns and pools at most 512 frequency rows; warnings identify time sampling. Narrow/brief lettering can disappear: inspect shorter segments and alternate FFT sizes. Audio is limited to 8 channels and 4 million decoded sample values per run. Long/high-rate stereo recordings may require a lower `--seconds` value. PCM WAV widths 8/16/24/32-bit work in the standard-library fallback. WAV float/compressed formats and other containers require optional SoundFile support; supported codecs depend on that installation. MP3 support is not guaranteed; convert to PCM WAV if decoding fails.

For OCR, install Tesseract separately and ensure `tesseract` is on PATH. `--ocr` calls that local executable with a timeout, does not download a model, and retains images if it is absent or fails. Tesseract recognition on spectrograms is often unreliable. Inspect all views manually. OCR confidence is capped at 0.85 and remains an unverified transcription.

## Optional extras and offline preparation

On a connected preparation machine:

```powershell
py -3 -m pip install ".[audio,web]"
py -3 -m playwright install chromium
```

NumPy accelerates FFTs; SoundFile adds audio formats. Playwright needs a separate browser download. Neither the wheel nor `.pyz` bundles extras, Chromium, Tesseract, or Python. `doctor` reports package/executable presence, not a full runtime guarantee.

To prepare optional packages for an offline **Windows PC**, download wheels on a connected Windows machine with the **same Python version and architecture**:

```powershell
py -3 -m pip download --only-binary=:all: --dest wheelhouse ".[audio,web]"
py -3 -m pip install --no-index --find-links=wheelhouse "okto-toolkit[audio,web]"
```

Copy `wheelhouse` to the offline PC and run the second command there. Browser binaries require separate preparation: install Chromium on the connected Windows preparation machine with `PLAYWRIGHT_BROWSERS_PATH` pointing to a transferable folder; copy that folder and set the same variable to its new location on the event PC. Test it before the event. Do not copy macOS native wheels or browsers to Windows. Python itself must already be installed or transferred using its official Windows installer subject to the host's setup policy.

## Python API

```python
from okto.encoding import solve
from okto.forensics import scan
from okto.graph import shortest_path
from okto.audio import analyze
from okto.web import inspect

print(solve("72 101 108 108 111").to_dict())
print(scan("ERROR GET /hidden/password.txt 403").to_dict())
print(
    shortest_path(
        {"edges": [["A", "B", -2]], "source": "A", "target": "B", "directed": True}
    ).to_dict()
)
# analyze("secret.wav", "spectrograms")
# inspect("http://localhost:3000", browser=True, click=["#start"])
```

Inputs are size-bounded, never passed to `eval`, and errors are actionable. Files default to a 64 MiB byte limit (HTML 2 MiB); encoding is limited to 32,768 characters, logs to 8 MiB of text, graph to 20,000 nodes/200,000 directed edges and 20 million Bellman–Ford edge relaxations. These are analysis budgets, not claims to handle unlimited hostile inputs. The toolkit has no telemetry or hosted AI dependency; networking occurs for explicit web URLs/browser content and package installation only. Reports can contain challenge secrets, full URLs and log excerpts: store/share them accordingly.

## Development and release

```powershell
py -3 -m pip install ".[dev]"
py -3 -m pytest -q
py -3 -m build
py -3 tools\build_release.py
py -3 tools\smoke_release.py
py -3 -S dist\okto.pyz solve examples\graph.json --json
```

Builds produce a universal wheel, source tarball, single-file offline `.pyz`, source ZIP, and SHA-256 manifest under `dist/`. Build from a clean tree. The outer handoff ZIP includes `dist/` and source; `okto-toolkit-source.zip` inside `dist/` intentionally excludes distribution artifacts and must be built before using its launcher scripts.

The GitHub Actions workflow tests Windows/macOS on Python 3.11/3.13, builds the package, exercises all five stages through the fallback with site packages disabled, installs the wheel without network access, and tests real Chromium diagnostics on both systems. See the [live checks](https://github.com/itemuln/okto-toolkit/actions) for current results and `VALIDATION.md` for the original local handoff record.

API references used: [Python zipapp](https://docs.python.org/3/library/zipapp.html), [Playwright Page API](https://playwright.dev/python/docs/api/class-page), [NumPy real FFT](https://numpy.org/doc/stable/reference/generated/numpy.fft.rfft.html).
