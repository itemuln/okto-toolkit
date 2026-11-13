import base64
import json
import math
import random
import sys
import wave
from pathlib import Path

import pytest

from okto import audio, encoding, forensics, graph, web
from okto.cli import main


@pytest.mark.parametrize(
    "encoded,expected",
    [
        ("72 101 108 108 111", "Hello"),
        ("01001000 01101001", "Hi"),
        ("0100100001101001", "Hi"),
        ("666c61677b6865787d", "flag{hex}"),
        ("ZmxhZ3tiYXNlNjR9", "flag{base64}"),
        ("synt{ebg13}", "flag{rot13}"),
        ("%66%6c%61%67%7Burl%7D", "flag{url}"),
        (r"\x66\x6c\x61\x67{escape}", "flag{escape}"),
        ("}esrever{galf", "flag{reverse}"),
        ("&#102;lag{html}", "flag{html}"),
    ],
)
def test_encodings(encoded, expected):
    report = encoding.solve(encoded, limit=100)
    assert expected in [candidate.value for candidate in report.candidates]


def test_layered_encoding():
    text = base64.b64encode(b"flag{layered}".hex().encode()).decode()
    report = encoding.solve(text)
    assert report.candidates[0].value == "flag{layered}"
    assert "Base64" in report.candidates[0].evidence[0]
    assert "hex" in report.candidates[0].evidence[0]


def test_double_base64():
    encoded = base64.b64encode(base64.b64encode(b"flag{offline_ready}")).decode()
    assert encoding.solve(encoded).candidates[0].value == "flag{offline_ready}"


def test_xor():
    encoded = "".join(chr(ord(c) ^ 7) for c in "flag{xor_password}")
    assert "flag{xor_password}" in [c.value for c in encoding.solve(encoded).candidates]


def test_hex_wrapped_high_byte_xor():
    encoded = bytes(b ^ 255 for b in b"flag{byte_xor}").hex()
    report = encoding.solve(encoded)
    assert report.candidates[0].value == "flag{byte_xor}"


def test_ambiguous_encoding():
    report = encoding.solve("zQ1!wP9$")
    assert report.status == "review"
    assert report.warnings
    assert all(c.confidence < 1 for c in report.candidates)


def test_log_paths_and_timestamps():
    report = forensics.scan(
        "2026-11-13T14:00:00Z ERROR GET /hidden/password.txt 403\n"
        "2026-11-13T23:00:00+08:00 backup C:\\vault\\secret.txt\n"
        "2026-11-13 14:03:00 GET /normal 200\n"
        "payload=ZmxhZ3tsb2d9 secret\n"
    )
    assert report.candidates[0].value == "flag{log}"
    assert any(c.value == "C:\\vault\\secret.txt" for c in report.candidates)
    assert [item["line"] for item in report.facts["utc_timeline"]] == [1, 2]
    assert report.facts["naive_timestamps"] == 1


def solve_graph(edges, source="A", target="D", **kwargs):
    return graph.shortest_path(
        dict(edges=edges, source=source, target=target, directed=True, **kwargs)
    )


def test_negative_edges():
    report = solve_graph([["A", "B", 4], ["A", "C", 5], ["B", "C", -7], ["C", "D", 3]])
    assert report.facts["distance"] == 0
    assert report.facts["path"] == ["A", "B", "C", "D"]
    assert report.facts["algorithm"] == "Bellman–Ford"


def test_negative_cycle_target_and_witness():
    edges = [["A", "B", 1], ["B", "C", -2], ["C", "B", 1], ["C", "D", 1]]
    report = solve_graph(edges)
    assert report.facts["outcome"] == "unbounded"
    cycle = report.facts["negative_cycle_witness"]
    weights = {(u, v): w for u, v, w in edges}
    assert cycle[0] == cycle[-1]
    assert sum(weights[u, v] for u, v in zip(cycle, cycle[1:])) < 0


def test_negative_cycle_cannot_reach_target():
    report = solve_graph([["A", "B", 0], ["B", "B", -1], ["A", "D", 7]])
    assert report.facts["outcome"] == "finite"
    assert report.facts["distance"] == 7
    assert report.warnings


def test_unreachable_negative_cycle():
    report = solve_graph([["X", "X", -1], ["A", "D", 3]])
    assert report.facts["distance"] == 3
    assert not report.facts["unbounded_nodes"]


def test_undirected_negative_edge():
    report = graph.shortest_path(
        {"edges": [[0, 1, -1]], "source": 0, "target": 1, "directed": False}
    )
    assert report.facts["outcome"] == "unbounded"


def test_unreachable_and_isolated():
    report = solve_graph([], nodes=["A", "D"])
    assert report.facts["outcome"] == "unreachable"
    report = solve_graph([], source="A", target="A", nodes=["A"])
    assert report.facts["distance"] == 0


@pytest.mark.parametrize(
    "edges,algorithm,cost",
    [
        ([["A", "D", 1]], "BFS", 1),
        ([["A", "B", 2], ["A", "D", 10], ["B", "D", 3]], "Dijkstra", 5),
        ([["A", "B", "0.1"], ["B", "D", "0.2"], ["A", "D", "0.3"]], "Dijkstra", "3/10"),
        ([["A", "D", 10**50]], "Dijkstra", 10**50),
    ],
)
def test_algorithms_and_exactness(edges, algorithm, cost):
    report = solve_graph(edges)
    assert report.facts["algorithm"] == algorithm
    assert report.facts["distance"] == cost


@pytest.mark.parametrize(
    "data",
    [
        {"edges": [["A", "D", "nan"]], "source": "A", "target": "D"},
        {"edges": [["A", "D", True]], "source": "A", "target": "D"},
        {"edges": [[1, "1", 2]], "source": 1, "target": "1"},
        {"edges": [["A", "D"]], "source": "A", "target": "D"},
        {"edges": [], "source": "A", "target": "D"},
        {"edges": [], "nodes": ["A"], "source": "A", "target": "A", "directed": "false"},
    ],
)
def test_invalid_graph(data):
    with pytest.raises(ValueError):
        graph.shortest_path(data)


def test_graph_against_independent_floyd_warshall():
    rng = random.Random(23)
    for _ in range(80):
        n = 5
        edges = [
            [u, v, rng.randint(-4, 9)] for u in range(n) for v in range(n) if rng.random() < 0.22
        ]
        matrix = [[None] * n for _ in range(n)]
        for u in range(n):
            matrix[u][u] = 0
        for u, v, w in edges:
            matrix[u][v] = min(matrix[u][v], w) if matrix[u][v] is not None else w
        for k in range(n):
            for u in range(n):
                for v in range(n):
                    if matrix[u][k] is not None and matrix[k][v] is not None:
                        cost = matrix[u][k] + matrix[k][v]
                        if matrix[u][v] is None or cost < matrix[u][v]:
                            matrix[u][v] = cost
        for target in range(n):
            report = graph.shortest_path(
                dict(edges=edges, nodes=list(range(n)), source=0, target=target)
            )
            unbounded = any(
                matrix[0][k] is not None and matrix[k][k] < 0 and matrix[k][target] is not None
                for k in range(n)
            )
            assert report.facts["outcome"] == (
                "unbounded"
                if unbounded
                else "unreachable"
                if matrix[0][target] is None
                else "finite"
            )
            if not unbounded:
                assert report.facts["distance"] == matrix[0][target]


def write_tone(path, width=2, channels=1):
    rate = 8000
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(width)
        stream.setframerate(rate)
        values = bytearray()
        for index in range(1600):
            sample = int(
                math.sin(2 * math.pi * 1000 * index / rate) * ((1 << (8 * width - 1)) - 1) * 0.8
            )
            for channel in range(channels):
                value = -sample if channel else sample
                values.extend(
                    (value + 128).to_bytes(1, "little")
                    if width == 1
                    else value.to_bytes(width, "little", signed=True)
                )
        stream.writeframes(values)


def test_fft_peak_and_numeric_correctness():
    values = [math.sin(2 * math.pi * 8 * i / 64) for i in range(64)]
    result = audio.fft(values)
    assert max(range(len(result)), key=lambda k: abs(result[k])) == 8
    for k in range(33):
        expected = sum(
            v * complex(math.cos(-2 * math.pi * k * i / 64), math.sin(-2 * math.pi * k * i / 64))
            for i, v in enumerate(values)
        )
        assert abs(result[k] - expected) < 1e-9


@pytest.mark.parametrize("width", [1, 2, 3, 4])
def test_pcm_widths_and_stereo(tmp_path, width):
    path = tmp_path / "tone.wav"
    write_tone(path, width, channels=2)
    report = audio.analyze(path, tmp_path / "images", sizes=(256,))
    assert report.facts["channels"] == 2
    assert len(report.artifacts) == 3
    assert all(abs(view["dominant_frequency_hz"] - 1000) < 1 for view in report.facts["views"])
    assert all(Path(p).read_bytes().startswith(b"\x89PNG") for p in report.artifacts)
    assert not report.candidates  # A tone is not a password.


def test_audio_fallback_without_numpy(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "numpy", None)
    path = tmp_path / "tone.wav"
    write_tone(path)
    report = audio.analyze(path, tmp_path / "images", sizes=(256,))
    assert report.facts["views"][0]["backend"] == "stdlib"
    assert report.facts["views"][0]["dominant_frequency_hz"] == 1000


def test_audio_duration_and_missing_ocr(tmp_path, monkeypatch):
    monkeypatch.setattr(audio.shutil, "which", lambda _: None)
    path = tmp_path / "tone.wav"
    write_tone(path)
    report = audio.analyze(path, tmp_path / "images", seconds=0.1, sizes=(256,), use_ocr=True)
    assert any("first 0.1" in w for w in report.warnings)
    assert any("Tesseract" in w for w in report.warnings)


def test_static_interface(tmp_path):
    path = tmp_path / "index.html"
    path.write_text(
        '<p id="x" hidden>flag{hidden}</p><p id="x"></p><!-- password clue -->'
        '<script>document.querySelector("#missing").addEventListener("click", go)</script>'
        '<script src="missing.js"></script>'
    )
    report = web.inspect(str(path))
    values = "\n".join(c.value for c in report.candidates)
    for expected in (
        "flag{hidden}",
        "Duplicate id",
        "absent id: missing",
        "Missing local resource",
    ):
        assert expected in values


def test_browser_missing_retains_static(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    path = tmp_path / "index.html"
    path.write_text("<p>flag{static}</p>")
    report = web.inspect(str(path), browser=True)
    assert report.candidates[0].value == "flag{static}"
    assert any("unavailable" in w for w in report.warnings)


def test_cli_json_error_and_auto(tmp_path, capsys):
    path = tmp_path / "graph.json"
    path.write_text(json.dumps({"edges": [["A", "D", 2]], "source": "A", "target": "D"}))
    assert main(["solve", str(path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["facts"]["distance"] == 2
    assert main(["solve", str(tmp_path / "missing"), "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "error"


def test_cli_graph_numeric_ids(tmp_path, capsys):
    path = tmp_path / "graph.json"
    path.write_text('{"edges": [[1,2,0.1],[2,3,0.2]], "directed": true}')
    assert main(["graph", str(path), "--source", "1", "--target", "3", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["facts"]["distance"] == "3/10"


def test_no_stacktrace_on_bad_audio(tmp_path, capsys):
    path = tmp_path / "bad.wav"
    path.write_bytes(b"not a wave file")
    assert main(["audio", str(path), "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "error"


def test_ocr_tsv_contract(tmp_path, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(audio.shutil, "which", lambda _: "tesseract")

    def fake_run(args, **kwargs):
        assert args[0] == "tesseract"
        assert args[-1] == "tsv"
        assert kwargs["timeout"] == 20
        return SimpleNamespace(returncode=0, stderr="", stdout="conf\ttext\n92.5\tKEY\n")

    monkeypatch.setattr(audio.subprocess, "run", fake_run)
    result = audio.ocr_image(tmp_path / "test.png")
    assert result[0].value == "KEY"
    assert result[0].confidence < 0.85


def test_no_text_ocr(tmp_path, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(audio.shutil, "which", lambda _: "tesseract")
    monkeypatch.setattr(
        audio.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stderr="", stdout="conf\ttext\n-1\t\n"),
    )
    assert audio.ocr_image(tmp_path / "test.png") == []


@pytest.mark.parametrize("text", ["%ff%ab", "%a", "%%%%", "0xff 0xgg", "999 999 999"])
def test_invalid_decoder_branches_do_not_abort(text):
    assert encoding.solve(text, depth=2).status == "review"


@pytest.mark.parametrize("damage", ["zero-rate", "truncated"])
def test_malformed_wav_headers(tmp_path, damage):
    import struct

    path = tmp_path / "broken.wav"
    write_tone(path)
    raw = bytearray(path.read_bytes())
    if damage == "zero-rate":
        struct.pack_into("<I", raw, 24, 0)
    else:
        raw = raw[:-8]
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        audio.analyze(path, tmp_path / "images", sizes=(256,))
