"""Interpret captured relations without upgrading declarations into observed calls."""
from collections import deque


def is_startup(edge):
    return edge.get("type") == "startup" or edge.get("evidence_kind") in {
        "compose_startup_order", "compose_link", "aspire_wait_for"}


def is_call(edge):
    return (not is_startup(edge) and edge.get("type", "http") in {"http", "https", "grpc"}
            and edge.get("evidence_kind", "legacy") in {"legacy", "source_inferred", "runtime_observed"})


def dependency_depth(service, edges, limit=8):
    """Largest shortest-path distance, bounded to eight hops; cycles cannot inflate it."""
    adjacency = {}
    for edge in edges:
        if not is_startup(edge):
            adjacency.setdefault(edge["from"], set()).add(edge["to"])
    distances, queue = {service: 0}, deque([service])
    while queue:
        current = queue.popleft()
        if distances[current] == limit:
            continue
        for target in adjacency.get(current, ()):
            if target not in distances:
                distances[target] = distances[current] + 1
                queue.append(target)
    return max(distances.values())
