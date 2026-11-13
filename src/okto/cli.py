"""Human-readable and machine-readable CLI with explicit stage overrides."""

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path

from . import __version__
from .common import read_text


def positive_int(value):
    number = int(value)
    if not 1 <= number <= 100:
        raise argparse.ArgumentTypeError("must be between 1 and 100")
    return number


def parser():
    root = argparse.ArgumentParser(
        prog="okto",
        description="Offline competition analysis with ranked clues and exact graph results.",
    )
    root.add_argument("--version", action="version", version=__version__)
    sub = root.add_subparsers(dest="command", required=True)
    for command in ("solve", "encoding", "logs", "audio", "web", "graph"):
        item = sub.add_parser(command, help=f"Analyze an input ({command})")
        item.add_argument("input", help="Input file; web also accepts an HTTP(S) URL")
        item.add_argument("--json", action="store_true", help="Print structured JSON")
        item.add_argument("--report", metavar="FILE", help="Also save full JSON report")
        item.add_argument(
            "--limit", type=positive_int, default=20, help="Maximum ranked findings (1–100)"
        )
        if command in ("solve", "encoding"):
            item.add_argument("--depth", type=int, choices=range(1, 6), default=3)
        if command == "solve":
            item.add_argument(
                "--stage",
                choices=("encoding", "logs", "audio", "web", "graph"),
                help="Override file-type inference",
            )
        if command in ("solve", "audio"):
            item.add_argument(
                "--output", default="okto-audio", help="Directory for spectrogram PNGs"
            )
            item.add_argument("--seconds", type=float, default=60)
            item.add_argument(
                "--ocr", action="store_true", help="Try an already installed Tesseract"
            )
            item.add_argument(
                "--fft",
                type=int,
                nargs="+",
                default=[512, 2048],
                help="FFT sizes, e.g. 512 2048 4096",
            )
        if command in ("solve", "graph"):
            item.add_argument("--source")
            item.add_argument("--target")
        if command in ("solve", "web"):
            item.add_argument(
                "--browser", action="store_true", help="Run page JavaScript in installed Chromium"
            )
            item.add_argument(
                "--click",
                action="append",
                default=[],
                metavar="SELECTOR",
                help="Explicit browser action; repeatable, in order",
            )
            item.add_argument("--timeout", type=float, default=10)
    doctor = sub.add_parser("doctor", help="Show local optional capabilities; no network access")
    doctor.add_argument("--json", action="store_true")
    return root


def infer(target: str):
    if target.startswith(("http://", "https://")):
        return "web", None
    suffix = Path(target).suffix.lower()
    if suffix in (".wav", ".flac", ".mp3", ".ogg", ".aiff", ".aif"):
        return "audio", None
    if suffix in (".html", ".htm"):
        return "web", None
    if suffix in (".log", ".jsonl"):
        return "logs", None
    if suffix == ".json":
        data = json.loads(read_text(target))
        if isinstance(data, dict) and "edges" in data:
            return "graph", None
    return "encoding", "File type is ambiguous; assumed encoding. Override with --stage if needed."


def doctor():
    return {
        "python": sys.version.split()[0],
        "toolkit": __version__,
        "core": "available (no third-party dependencies)",
        "numpy": importlib.util.find_spec("numpy") is not None,
        "soundfile": importlib.util.find_spec("soundfile") is not None,
        "playwright": importlib.util.find_spec("playwright") is not None,
        "tesseract": shutil.which("tesseract"),
        "note": "Presence is not a runtime check. Browser needs a separate Chromium installation; PCM WAV spectrograms work without extras.",
    }


def main(argv=None) -> int:
    # Windows consoles may use a code page that cannot print arrows or clue text.
    # Keep JSON output valid and retain readable escape sequences instead of crashing.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    arguments = parser().parse_args(argv)
    json_mode = arguments.json
    try:
        if arguments.command == "doctor":
            info = doctor()
            print(
                json.dumps(info, indent=2)
                if json_mode
                else "\n".join(f"{key}: {value}" for key, value in info.items())
            )
            return 0
        warning = None
        if arguments.command == "solve":
            stage, warning = (arguments.stage, None) if arguments.stage else infer(arguments.input)
        else:
            stage = arguments.command
        if stage == "encoding":
            from .encoding import solve

            report = solve(read_text(arguments.input), depth=arguments.depth, limit=arguments.limit)
        elif stage == "logs":
            from .forensics import scan

            report = scan(read_text(arguments.input), limit=arguments.limit)
        elif stage == "graph":
            from .graph import shortest_path

            report = shortest_path(
                json.loads(read_text(arguments.input), parse_float=str),
                arguments.source,
                arguments.target,
            )
        elif stage == "audio":
            from .audio import analyze

            report = analyze(
                arguments.input,
                arguments.output,
                arguments.seconds,
                arguments.ocr,
                tuple(arguments.fft),
            )
        else:
            from .web import inspect

            report = inspect(arguments.input, arguments.browser, arguments.click, arguments.timeout)
        if warning:
            report.warnings.insert(0, warning)
        report.rank(arguments.limit)
        data = report.to_dict()
        encoded = json.dumps(data, ensure_ascii=True, indent=2, allow_nan=False)
        if arguments.report:
            Path(arguments.report).write_text(encoded + "\n", encoding="utf-8")
        if json_mode:
            print(encoded)
        else:
            print(f"OKTO {__version__} | {report.stage} | {report.status}")
            print("Confidence is a heuristic ranking, not a probability.\n")
            for index, candidate in enumerate(report.candidates, 1):
                # repr prevents control characters in hostile inputs from manipulating the terminal.
                preview = repr(candidate.value[:1200])
                print(f"{index:2}. [{candidate.confidence:.2f}] {preview}")
                for evidence in candidate.evidence:
                    print(f"    Evidence: {evidence!r}")
            if not report.candidates:
                print("No ranked clues found. Review facts/artifacts and next steps.")
            print("\nFacts:")
            for name, value in report.facts.items():
                summary = json.dumps(value, ensure_ascii=True)
                if len(summary) > 1200:
                    summary = summary[:1200] + " ... (use --json for full data)"
                print(f"  {name}: {summary}")
            for artifact in report.artifacts:
                print(f"Artifact: {artifact!r}")
            for note in report.warnings:
                print(f"Note: {note!r}")
            for step in report.next_steps:
                print(f"Next: {step}")
        return 0
    except (OSError, ValueError, RuntimeError, OverflowError, UnicodeError) as exc:
        if json_mode:
            print(
                json.dumps(
                    {"schema_version": 1, "status": "error", "error": str(exc)}, ensure_ascii=True
                )
            )
        else:
            print(f"okto: {str(exc)!r}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("okto: cancelled", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
