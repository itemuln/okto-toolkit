"""Extract and correlate log clues without following paths or executing content."""

import re
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import unquote

from .common import Candidate, Report
from .encoding import FLAG
from .encoding import solve as decode

PATH = re.compile(r"""(?:[A-Za-z]:\\|\\\\[\w.-]+\\|/|\.{1,2}/)[^\s<>"'|]*""")
TIME = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?")
SUSPICIOUS = re.compile(
    r"(?i)secret|flag|password|token|hidden|backup|\.bak\b|denied|unauthori[sz]ed|failed|error|\.\./|%2e|%2f"
)


def scan(text: str, limit: int = 20) -> Report:
    if len(text) > 8 * 1024 * 1024:
        raise ValueError(
            "Log analysis is limited to 8 MiB of text; split the log into smaller time ranges."
        )
    report = Report("logs")
    findings: dict[tuple[str, str], Candidate] = {}
    times = []
    naive = 0
    statuses = Counter()
    path_counts = Counter()
    suspicious_lines = 0
    for line_no, line in enumerate(text.splitlines(), 1):
        decoded = unquote(line)
        suspicious = bool(SUSPICIOUS.search(decoded))
        suspicious_lines += suspicious
        timestamp = TIME.search(line)
        stamp = timestamp[0] if timestamp else None
        if stamp:
            try:
                value = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                if value.tzinfo is None:
                    naive += 1
                else:
                    times.append((value.astimezone(timezone.utc), line_no))
            except ValueError:
                report.warnings.append(f"Unparseable timestamp on line {line_no}.")
        statuses.update(re.findall(r"\b[45]\d{2}\b", line))
        evidence = f"Line {line_no}" + (f", {stamp}" if stamp else "") + f": {line[:300]}"
        for match in PATH.finditer(decoded):
            path = match[0].rstrip(".,;:)]}")
            if path in ("/", "//") or path.startswith("//HTTP"):
                continue
            path_counts[path] += 1
            key = ("path", path)
            if key not in findings and len(findings) >= 20000:
                continue
            confidence = 0.45 + 0.20 * suspicious + 0.15 * bool(SUSPICIOUS.search(path))
            candidate = findings.setdefault(key, Candidate(path, round(confidence, 2), [], "path"))
            candidate.confidence = max(candidate.confidence, round(confidence, 2))
            if len(candidate.evidence) < 5:
                candidate.evidence.append(evidence)
        for flag in FLAG.findall(decoded):
            findings[("flag pattern", flag)] = Candidate(flag, 0.97, [evidence], "flag pattern")
        if suspicious:
            # Keep expensive layered decoding to small, explicitly labelled payloads.
            payload = re.search(
                r"(?i)\b(?:payload|encoded|base64)\s*[:=]\s*[\"']?([A-Za-z0-9+/=_-]{8,512})", line
            )
            if payload and len(findings) < 1000:
                for candidate in decode(payload[1], depth=2, limit=3).candidates:
                    if candidate.confidence >= 0.75 and candidate.value != payload[1]:
                        candidate.evidence.insert(0, evidence)
                        candidate.kind = "decoded payload"
                        findings[(candidate.kind, candidate.value)] = candidate
    report.candidates = list(findings.values())
    times.sort()
    report.facts = {
        "lines": len(text.splitlines()),
        "suspicious_lines": suspicious_lines,
        "unique_paths": len(path_counts),
        "path_occurrences": dict(path_counts.most_common(50)),
        "possible_http_error_codes": dict(statuses),
        "utc_timeline": [{"time": t.isoformat(), "line": n} for t, n in times[:100]],
        "naive_timestamps": naive,
    }
    report.warnings += [
        "Path and status extraction is heuristic; a mentioned path is not proof that it exists."
    ]
    if len(findings) >= 20000:
        report.warnings.append(
            "Finding storage reached 20,000 entries; split the log to inspect additional distinct paths."
        )
    if naive:
        report.warnings.append("Timestamps without a timezone are not mixed into the UTC timeline.")
    report.next_steps = [
        "Inspect cited lines and nearby events; confirm promising paths within the supplied challenge files."
    ]
    return report.rank(limit)
