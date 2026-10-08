import heapq


def find_shortest_path(graph, source, target):
    """Return (distance, path) between two nodes, or (inf, []) if unreachable.

    Dijkstra with a binary heap: O((V + E) log V) time, O(V) memory.
    """
    for node in (source, target):
        if node not in graph:
            raise ValueError(f"University '{node}' not found.")

    distances = {node: float("inf") for node in graph.nodes}
    parent = {}
    distances[source] = 0
    heap = [(0, source)]

    while heap:
        dist, node = heapq.heappop(heap)
        if dist > distances[node]:
            continue
        if node == target:
            break
        for neighbor, data in graph[node].items():
            new_dist = dist + data.get("weight", 1)
            if new_dist < distances[neighbor]:
                distances[neighbor] = new_dist
                parent[neighbor] = node
                heapq.heappush(heap, (new_dist, neighbor))

    if distances[target] == float("inf"):
        return float("inf"), []

    path = [target]
    while path[-1] != source:
        path.append(parent[path[-1]])
    path.reverse()
    return distances[target], path
