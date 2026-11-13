"""Verify wheel installation offline, isolated CLI, and dependency-free pyz."""

import json
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command, directory, expected=0):
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        command, cwd=directory, env=environment, capture_output=True, text=True, timeout=90
    )
    assert result.returncode == expected, (command, result.returncode, result.stdout, result.stderr)
    return result.stdout


with tempfile.TemporaryDirectory() as temporary:
    directory = Path(temporary)
    venv.create(directory / "venv", with_pip=True)
    python = directory / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    executable = directory / "venv" / ("Scripts/okto.exe" if os.name == "nt" else "bin/okto")
    wheel = next((ROOT / "dist").glob("*.whl"))
    run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)], directory)
    for prefix in (
        [str(python), "-m", "okto"],
        [sys.executable, "-S", str(ROOT / "dist/okto.pyz")],
    ):
        info = json.loads(run(prefix + ["doctor", "--json"], directory))
        assert not info["numpy"] and not info["playwright"] and not info["soundfile"]
        report = json.loads(
            run(prefix + ["solve", str(ROOT / "examples/graph.json"), "--json"], directory)
        )
        assert report["facts"]["distance"] == 0
        report = json.loads(
            run(prefix + ["solve", str(ROOT / "examples/puzzle.txt"), "--json"], directory)
        )
        assert any("flag{" in c["value"] for c in report["candidates"])
        report = json.loads(
            run(prefix + ["logs", str(ROOT / "examples/server.log"), "--json"], directory)
        )
        assert any(c["value"] == "flag{log_clue}" for c in report["candidates"])
        report = json.loads(
            run(prefix + ["web", str(ROOT / "examples/interface.html"), "--json"], directory)
        )
        assert any("absent id" in c["value"] for c in report["candidates"])
        report = json.loads(
            run(
                prefix
                + [
                    "audio",
                    str(ROOT / "examples/hidden-key.wav"),
                    "--fft",
                    "512",
                    "--output",
                    str(directory / "views"),
                    "--json",
                ],
                directory,
            )
        )
        assert report["facts"]["views"][0]["backend"] == "stdlib"
        assert Path(report["artifacts"][0]).is_file()
        error = json.loads(run(prefix + ["solve", "missing.txt", "--json"], directory, expected=2))
        assert error["status"] == "error"
    assert run([str(executable), "--version"], directory).strip() == "1.0.0"
print(
    "PASS: clean offline wheel install, console entry point, and -S pyz; all five stages and error exit codes."
)
