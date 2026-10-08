from .distance_matrix import build_distance_matrix
from .shortest_path import find_shortest_path

MAX_CITIES = 15


def tsp_dp(graph, cities):
    """Cheapest order to visit every city once (open path, any start and end).

    Held-Karp dynamic programming over bitmasks. Distances between cities are
    shortest-path distances in the graph, so intermediate stops are allowed.
    O(n^2 * 2^n) time, O(n * 2^n) memory.
    """
    cities = list(dict.fromkeys(cities))
    n = len(cities)

    if n > MAX_CITIES:
        raise ValueError(f"At most {MAX_CITIES} universities are supported.")
    for city in cities:
        if city not in graph:
            raise ValueError(f"University '{city}' not found.")
    if n == 0:
        return 0, []
    if n == 1:
        return 0, cities

    dist = build_distance_matrix(graph, cities)
    inf = float("inf")
    full = (1 << n) - 1

    dp = [[inf] * n for _ in range(1 << n)]
    parent = [[-1] * n for _ in range(1 << n)]
    for i in range(n):
        dp[1 << i][i] = 0

    for mask in range(1, 1 << n):
        for u in range(n):
            if not mask & (1 << u) or dp[mask][u] == inf:
                continue
            for v in range(n):
                if mask & (1 << v) or dist[u][v] == inf:
                    continue
                nxt = mask | (1 << v)
                cost = dp[mask][u] + dist[u][v]
                if cost < dp[nxt][v]:
                    dp[nxt][v] = cost
                    parent[nxt][v] = u

    end = min(range(n), key=lambda i: dp[full][i])
    best = dp[full][end]
    if best == inf:
        return inf, []

    order = []
    mask, cur = full, end
    while cur != -1:
        order.append(cities[cur])
        prev = parent[mask][cur]
        mask ^= 1 << cur
        cur = prev
    order.reverse()
    return best, order


def expand_route(graph, order):
    """Turn a visiting order into the full node-by-node route through the graph."""
    if not order:
        return []
    route = [order[0]]
    for a, b in zip(order, order[1:]):
        _, path = find_shortest_path(graph, a, b)
        route.extend(path[1:])
    return route
