"""Exact rational-weight shortest paths and destination-specific cycle handling."""

import heapq
from collections import deque
from fractions import Fraction
from itertools import count

from .common import Candidate, Report


def shortest_path(data: dict, source=None, target=None) -> Report:
    if not isinstance(data, dict):
        raise ValueError("Graph input must be a JSON object.")
    source = source if source is not None else data.get("source")
    target = target if target is not None else data.get("target")
    if source is None or target is None:
        raise ValueError("Provide source and target in JSON or with --source/--target.")
    directed = data.get("directed", True)
    if not isinstance(directed, bool):
        raise ValueError("directed must be true or false.")

    def node(value):
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise ValueError("Node IDs must be strings or integers (not booleans).")
        return str(value)

    nodes = set()
    raw_ids = {}

    def register(value):
        name = node(value)
        if name in raw_ids and type(raw_ids[name]) is not type(value):
            raise ValueError(f"Ambiguous node IDs: {name!r} occurs as both string and integer.")
        raw_ids[name] = value
        nodes.add(name)
        return name

    raw_nodes = data.get("nodes", [])
    if not isinstance(raw_nodes, list) or not isinstance(data.get("edges"), list):
        raise ValueError("nodes and edges must be lists; edges are [from, to, weight].")
    for value in raw_nodes:
        register(value)
    edges = []
    for index, edge in enumerate(data["edges"]):
        if not isinstance(edge, (list, tuple)) or len(edge) != 3:
            raise ValueError(f"Edge {index} must be [from, to, weight].")
        u, v = register(edge[0]), register(edge[1])
        try:
            if isinstance(edge[2], bool):
                raise ValueError()
            w = Fraction(str(edge[2]))
        except (ValueError, ZeroDivisionError):
            raise ValueError(f"Edge {index} has an invalid finite numeric weight.") from None
        edges.append((u, v, w))
        if not directed:
            edges.append((v, u, w))
    source, target = node(source), node(target)
    if source not in nodes or target not in nodes:
        raise ValueError(
            "Source and target must occur in nodes or edges; declare isolated nodes explicitly."
        )
    if len(nodes) > 20000 or len(edges) > 200000:
        raise ValueError("Graph limit: 20,000 nodes and 200,000 directed edges.")
    adjacency = {n: [] for n in nodes}
    for u, v, w in edges:
        adjacency[u].append((v, w))
    dist = {source: Fraction(0)}
    previous = {}
    affected = set()
    witness = []
    if all(w == 1 for _, _, w in edges):
        algorithm = "BFS"
        queue = deque([source])
        while queue:
            u = queue.popleft()
            for v, w in adjacency[u]:
                if v not in dist:
                    dist[v], previous[v] = dist[u] + w, u
                    queue.append(v)
    elif all(w >= 0 for _, _, w in edges):
        algorithm = "Dijkstra"
        sequence = count()
        heap = [(Fraction(0), next(sequence), source)]
        while heap:
            cost, _, u = heapq.heappop(heap)
            if cost != dist[u]:
                continue
            for v, w in adjacency[u]:
                candidate = cost + w
                if v not in dist or candidate < dist[v]:
                    dist[v], previous[v] = candidate, u
                    heapq.heappush(heap, (candidate, next(sequence), v))
    else:
        algorithm = "Bellman–Ford"
        if len(nodes) * len(edges) > 20_000_000:
            raise ValueError(
                "Negative-edge graph exceeds the 20 million relaxation budget; isolate the relevant subgraph."
            )
        for _ in range(len(nodes) - 1):
            changed = False
            for u, v, w in edges:
                if u in dist and (v not in dist or dist[u] + w < dist[v]):
                    dist[v], previous[v] = dist[u] + w, u
                    changed = True
            if not changed:
                break
        # One extra pass collects seeds and predecessors for an actual cycle witness.
        for u, v, w in edges:
            if u in dist and (v not in dist or dist[u] + w < dist[v]):
                dist[v], previous[v] = dist[u] + w, u
                affected.add(v)
        if affected:
            cursor = sorted(affected)[0]
            for _ in nodes:
                cursor = previous[cursor]
            cycle = [cursor]
            following = previous[cursor]
            while following != cursor and len(cycle) <= len(nodes):
                cycle.append(following)
                following = previous[following]
            witness = list(reversed(cycle + [cursor]))
            queue = deque(affected)
            while queue:
                for v, _ in adjacency[queue.popleft()]:
                    if v not in affected:
                        affected.add(v)
                        queue.append(v)

    def exact(value):
        return value.numerator if value.denominator == 1 else str(value)

    report = Report("graph", status="solved")
    report.facts = {
        "algorithm": algorithm,
        "source": source,
        "target": target,
        "directed": directed,
        "nodes": len(nodes),
        "edges": len(edges),
        "negative_cycle_witness": witness,
        "unbounded_nodes": sorted(affected),
        "distances": {
            n: "-infinity" if n in affected else exact(dist[n]) if n in dist else None
            for n in sorted(nodes)
        },
    }
    if target in affected:
        report.facts.update(outcome="unbounded", distance="-infinity", path=[])
        report.candidates = [
            Candidate(
                "No finite shortest path",
                1.0,
                ["A source-reachable negative cycle can reach the target."],
                "exact result",
            )
        ]
    elif target not in dist:
        report.facts.update(outcome="unreachable", distance=None, path=[])
        report.candidates = [
            Candidate(
                "Target is unreachable",
                1.0,
                [f"{algorithm} exhausted source-reachable vertices."],
                "exact result",
            )
        ]
    else:
        path = [target]
        while path[-1] != source:
            path.append(previous[path[-1]])
        path.reverse()
        report.facts.update(outcome="finite", distance=exact(dist[target]), path=path)
        report.candidates = [
            Candidate(
                " → ".join(path),
                1.0,
                [f"Exact cost: {exact(dist[target])}; algorithm: {algorithm}"],
                "exact result",
            )
        ]
    if affected and target not in affected:
        report.warnings.append(
            "A source-reachable negative cycle exists but cannot affect this target."
        )
    if "directed" not in data:
        report.warnings.append(
            "directed was omitted; assumed true. Set false for an undirected graph."
        )
    return report
