"""Build an offline pyz, source archive, and checksums. Run after wheel/sdist build."""

import hashlib
import shutil
import tempfile
import zipapp
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
DIST.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as temporary:
    staging = Path(temporary)
    shutil.copytree(
        ROOT / "src" / "okto", staging / "okto", ignore=shutil.ignore_patterns("__pycache__")
    )
    (staging / "__main__.py").write_text(
        "from okto.cli import main\nraise SystemExit(main())\n", encoding="utf-8"
    )
    zipapp.create_archive(staging, DIST / "okto.pyz", compressed=True)

with tempfile.TemporaryDirectory() as temporary:
    staging = Path(temporary) / "okto-toolkit"
    shutil.copytree(
        ROOT,
        staging,
        ignore=shutil.ignore_patterns(
            ".git",
            "dist",
            ".venv",
            ".pytest_cache",
            "__pycache__",
            "*.egg-info",
            "build",
            ".ruff_cache",
        ),
    )
    shutil.make_archive(str(DIST / "okto-toolkit-source"), "zip", staging.parent, staging.name)

files = sorted(p for p in DIST.iterdir() if p.is_file() and p.name != "SHA256SUMS.txt")
(DIST / "SHA256SUMS.txt").write_text(
    "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in files),
    encoding="ascii",
)
print("Built:", ", ".join(p.name for p in files))
