"""Dependency-network helpers built on NetworkX. Pure logic: no database, no UI.

Nodes are activity ids (ints); an edge A -> B means "B cannot start until A finishes".
"""
from __future__ import annotations

from collections.abc import Iterable

import networkx as nx


def build_graph(activity_ids: Iterable[int], links: Iterable[tuple[int, int]]) -> nx.DiGraph:
    """Build a directed graph. `links` are (predecessor_id, successor_id) pairs.

    Raises ValueError if a link refers to an activity that is not in `activity_ids`
    (that would be a data-integrity bug, not a user mistake).
    """
    graph = nx.DiGraph()
    graph.add_nodes_from(activity_ids)
    for predecessor, successor in links:
        if predecessor not in graph or successor not in graph:
            raise ValueError(f"Link {predecessor} -> {successor} refers to an unknown activity.")
        graph.add_edge(predecessor, successor)
    return graph


def find_cycle(graph: nx.DiGraph) -> list[int] | None:
    """Return the node ids of one cycle in order (e.g. [1, 2, 3] means 1->2->3->1), or None."""
    try:
        edges = nx.find_cycle(graph)
    except nx.NetworkXNoCycle:
        return None
    return [source for source, _target in edges]


def find_cycle_through_new_link(
    graph: nx.DiGraph, predecessor: int, successor: int
) -> list[int] | None:
    """Would adding predecessor -> successor create a cycle? If so, return that cycle.

    A new edge P -> S closes a loop exactly when S can already reach P. The returned
    list starts at P: [P, S, ..., X] means P -> S -> ... -> X -> P.
    """
    if predecessor not in graph or successor not in graph:
        raise ValueError("Both activities must already be in the graph.")
    if predecessor == successor:
        return [predecessor]
    try:
        path = nx.shortest_path(graph, source=successor, target=predecessor)
    except nx.NetworkXNoPath:
        return None
    return [predecessor, *path[:-1]]
