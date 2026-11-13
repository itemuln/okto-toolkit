"""Shared report schema and bounded input handling."""

from dataclasses import asdict, dataclass, field
from pathlib import Path

MAX_BYTES = 64 * 1024 * 1024


@dataclass
class Candidate:
    value: str
    confidence: float
    evidence: list[str]
    kind: str = "clue"


@dataclass
class Report:
    stage: str
    status: str = "review"
    candidates: list[Candidate] = field(default_factory=list)
    facts: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        result = asdict(self)
        result["schema_version"] = 1
        result["confidence_note"] = (
            "Heuristic ranking, not calibrated probability; inspect evidence."
        )
        return result

    def rank(self, limit: int = 20):
        self.candidates.sort(key=lambda item: (-item.confidence, item.value))
        self.candidates = self.candidates[:limit]
        return self


def read_bytes(path: str | Path, limit: int = MAX_BYTES) -> bytes:
    with Path(path).open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"Input exceeds {limit:,} bytes; split it into smaller files.")
    return data


def read_text(path: str | Path) -> str:
    data = read_bytes(path)
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "Expected UTF-8 text. Convert the file or select the audio stage."
        ) from exc
