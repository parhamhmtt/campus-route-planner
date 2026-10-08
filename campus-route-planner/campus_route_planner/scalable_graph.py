from collections import defaultdict

import networkx as nx

DEFAULT_REGION = "Unassigned"


class ScalableGraph:
    """Region-based MST: one MST per region, then the pieces joined by cheap cross-region links.

    Overall cost is dominated by sorting edges, O(E log E).
    """

    def __init__(self, full_graph, region_map):
        self.full_graph = full_graph
        self.region_map = region_map
        self.region_graphs = defaultdict(nx.Graph)
        self.merged_graph = nx.Graph()

    def region_of(self, node):
        return self.region_map.get(node, DEFAULT_REGION)

    def build_region_graphs(self):
        for node in self.full_graph.nodes:
            self.region_graphs[self.region_of(node)].add_node(node)
        for u, v, data in self.full_graph.edges(data=True):
            if self.region_of(u) == self.region_of(v):
                self.region_graphs[self.region_of(u)].add_edge(u, v, **data)

    def get_mst_per_region(self):
        return {
            region: nx.minimum_spanning_tree(g, weight="weight")
            for region, g in self.region_graphs.items()
        }

    def merge_msts(self, mst_dict):
        for mst in mst_dict.values():
            self.merged_graph.add_nodes_from(mst.nodes)
            self.merged_graph.add_edges_from(mst.edges(data=True))

    def connect_regions(self):
        """Link the regional trees using the cheapest cross-region edges (Kruskal).

        A region can be split into several pieces inside itself, so the union-find
        works on the connected components of the merged graph, not on whole regions.
        """
        links = sorted(
            (data.get("weight", 1), u, v)
            for u, v, data in self.full_graph.edges(data=True)
            if self.region_of(u) != self.region_of(v)
        )

        parent = {}
        for component in nx.connected_components(self.merged_graph):
            root = next(iter(component))
            for node in component:
                parent[node] = root

        def find(node):
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node

        for weight, u, v in links:
            root_u, root_v = find(u), find(v)
            if root_u != root_v:
                parent[root_u] = root_v
                self.merged_graph.add_edge(u, v, weight=weight)

    def get_final_graph(self):
        return self.merged_graph

    def build(self):
        self.build_region_graphs()
        self.merge_msts(self.get_mst_per_region())
        self.connect_regions()
        return self.get_final_graph()
