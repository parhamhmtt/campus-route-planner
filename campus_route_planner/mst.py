import heapq

import networkx as nx


def compute_mst(graph):
    # prim with a heap, restarted per component so a disconnected graph gives a forest
    mst = nx.Graph()
    mst.add_nodes_from(graph.nodes)
    visited = set()

    for root in graph.nodes:
        if root in visited:
            continue
        visited.add(root)
        heap = [(d.get("weight", 1), root, v) for v, d in graph[root].items()]
        heapq.heapify(heap)

        while heap:
            weight, u, v = heapq.heappop(heap)
            if v in visited:
                continue
            visited.add(v)
            mst.add_edge(u, v, weight=weight)
            for nxt, data in graph[v].items():
                if nxt not in visited:
                    heapq.heappush(heap, (data.get("weight", 1), v, nxt))

    return mst
