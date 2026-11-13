"""Bounded layered decoding with transparent language heuristics."""

import base64
import binascii
import html
import re
from urllib.parse import unquote

from .common import Candidate, Report

FLAG = re.compile(r"(?i)(?:flag|ctf|okto|password|secret)\{[^{}\r\n]{1,160}\}")
WORDS = set(
    "the a is this secret password flag hello world open unlock key code next path stage competition welcome access granted hidden message congratulations".split()
)


def score(text: str) -> float:
    if not text:
        return 0.0
    printable = sum(c.isprintable() or c in "\r\n\t" for c in text) / len(text)
    letters = sum(c.isalpha() or c.isspace() for c in text) / len(text)
    words = re.findall(r"[a-z]+", text.lower())
    known = sum(word in WORDS for word in words) / max(1, len(words))
    result = 0.42 * printable + 0.22 * letters + 0.26 * known
    if printable < 0.9:
        result *= 0.35
    if FLAG.search(text):
        result = max(result, 0.97)
    return round(min(0.98, result), 4)


def transforms(text: str, xor: bool = False):
    def byte_text(name, raw):
        try:
            return name, raw.decode("utf-8")
        except UnicodeError:
            # Reversible byte representation, so hex/base64-wrapped XOR remains searchable.
            return name + " (Latin-1 byte bridge)", raw.decode("latin1")

    stripped = text.strip()
    compact = re.sub(r"\s+", "", stripped)
    tokens = re.split(r"[\s,;]+", stripped)
    for base, pattern in [(10, r"\d{1,3}"), (2, r"[01]{7,8}"), (16, r"(?:0x)?[0-9a-fA-F]{2}")]:
        if tokens and all(re.fullmatch(pattern, t) for t in tokens):
            try:
                yield byte_text(f"ASCII base {base}", bytes(int(t, base) for t in tokens))
            except (ValueError, UnicodeError):
                pass
    if compact and len(compact) % 8 == 0 and set(compact) <= {"0", "1"}:
        try:
            yield byte_text(
                "binary bytes", bytes(int(compact[i : i + 8], 2) for i in range(0, len(compact), 8))
            )
        except UnicodeError:
            pass
    if compact and len(compact) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]+", compact):
        try:
            yield byte_text("hex", bytes.fromhex(compact))
        except UnicodeError:
            pass
    for name, alphabet, unit, decoder in [
        ("Base64", r"[A-Za-z0-9+/]*={0,2}", 4, lambda x: base64.b64decode(x, validate=True)),
        ("Base64 URL", r"[A-Za-z0-9_-]*={0,2}", 4, base64.urlsafe_b64decode),
        ("Base32", r"[A-Z2-7]*={0,6}", 8, base64.b32decode),
    ]:
        if len(compact) >= 4 and re.fullmatch(alphabet, compact):
            try:
                yield byte_text(name, decoder(compact + "=" * (-len(compact) % unit)))
            except (ValueError, UnicodeError, binascii.Error):
                pass
    if re.search(r"\\x[0-9a-fA-F]{2}", stripped):
        try:
            yield (
                "escaped hex",
                re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m[1], 16)), stripped),
            )
        except ValueError:
            pass
    if "%" in stripped:
        try:
            yield "URL percent decoding", unquote(stripped, errors="strict")
        except UnicodeError:
            pass
    if "&" in stripped:
        yield "HTML entities", html.unescape(stripped)
    yield "reverse", stripped[::-1]
    for shift in range(1, 26):
        table = str.maketrans(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
            "".join(chr((i + shift) % 26 + start) for start in (65, 97) for i in range(26)),
        )
        yield f"Caesar +{shift}" + (" (ROT13)" if shift == 13 else ""), stripped.translate(table)
    if xor and len(text) <= 4096:
        raw = text.encode("latin1") if all(ord(c) < 256 for c in text) else text.encode("utf-8")
        for key in range(1, 256):
            try:
                decoded = bytes(b ^ key for b in raw).decode("utf-8")
            except UnicodeError:
                continue
            if score(decoded) >= 0.60:
                yield f"single-byte XOR 0x{key:02x}", decoded


def solve(text: str, depth: int = 3, limit: int = 20) -> Report:
    if not text.strip():
        raise ValueError("Puzzle input is empty.")
    if len(text) > 32768:
        raise ValueError("Puzzle input is limited to 32,768 characters; isolate the encoded clue.")
    if not 1 <= depth <= 5 or not 1 <= limit <= 100:
        raise ValueError("Use depth 1–5 and limit 1–100.")
    report = Report(
        "encoding",
        next_steps=[
            "Validate the highest-ranked text against the challenge; try a different depth or language if needed."
        ],
    )
    frontier = [(text, [])]
    seen = {text}
    report.candidates.append(Candidate(text, score(text), ["Original input; no transform"], "text"))
    explored = 0
    for level in range(depth):
        following = []
        for value, steps in frontier:
            # XOR is expensive and ambiguous; explore it only on the first two layers.
            for method, decoded in transforms(value, xor=level < 2):
                explored += 1
                if not decoded or decoded in seen or len(decoded) > 32768:
                    continue
                seen.add(decoded)
                chain = steps + [method]
                quality = max(0, score(decoded) - 0.012 * (len(chain) - 1))
                report.candidates.append(
                    Candidate(decoded, round(quality, 4), [" → ".join(chain)], "decoded text")
                )
                following.append((decoded, chain))

        def search_priority(item):
            compact = re.sub(r"\s+", "", item[0])
            # Preserve low-readability intermediate byte encodings for the next layer.
            structural = bool(re.fullmatch(r"[0-9a-fA-F]{8,}", compact) and len(compact) % 2 == 0)
            bridge = "byte bridge" in item[1][-1]
            byte_decoder = item[1][-1].startswith(
                ("ASCII", "binary", "hex", "Base", "escaped", "URL", "HTML")
            )
            return score(item[0]) + 0.6 * (structural or bridge or byte_decoder)

        following.sort(key=search_priority, reverse=True)
        frontier = following[:24]
    report.facts = {
        "transforms_tried": explored,
        "unique_texts": len(seen),
        "depth": depth,
        "beam_width": 24,
    }
    report.warnings = [
        "Bounded search can miss layers. English-biased readability and flag patterns can produce false positives."
    ]
    if len(text) > 4096:
        report.warnings.append("XOR skipped for text over 4,096 characters.")
    return report.rank(limit)
