import json
from pathlib import Path

import networkx as nx

DEFAULT_REGION = "Unassigned"

DEFAULT_REGIONS = {
    "Sharif": "Central",
    "Tehran": "Central",
    "Amirkabir": "Central",
    "Elm-o-Sanat": "East",
    "Kharazmi": "East",
    "Beheshti": "North",
}

DEFAULT_EDGES = [
    ("Sharif", "Tehran", 3),
    ("Sharif", "Amirkabir", 2),
    ("Tehran", "Elm-o-Sanat", 4),
    ("Amirkabir", "Kharazmi", 6),
    ("Kharazmi", "Beheshti", 5),
    ("Elm-o-Sanat", "Beheshti", 1),
]

DEFAULT_SAVE_PATH = Path("data") / "graph.json"


class UniversityGraph:
    """Weighted undirected graph of universities plus a region for each one."""

    def __init__(self):
        self.graph = nx.Graph()
        self.regions = {}
        self._load_defaults()

    def _load_defaults(self):
        self.graph.clear()
        self.regions = dict(DEFAULT_REGIONS)
        self.graph.add_nodes_from(DEFAULT_REGIONS)
        for u, v, w in DEFAULT_EDGES:
            self.graph.add_edge(u, v, weight=w)

    def get_graph(self):
        return self.graph

    def get_regions(self):
        return self.regions

    def add_university(self, name, region=DEFAULT_REGION):
        if name in self.graph:
            raise ValueError(f"University '{name}' already exists.")
        self.graph.add_node(name)
        self.regions[name] = region or DEFAULT_REGION

    def add_connection(self, u, v, weight):
        if u == v:
            raise ValueError("A university cannot be connected to itself.")
        for name in (u, v):
            if name not in self.graph:
                raise ValueError(f"University '{name}' not found.")
        if weight <= 0:
            raise ValueError("Weight must be positive.")
        self.graph.add_edge(u, v, weight=weight)

    def remove_university(self, name):
        if name not in self.graph:
            raise ValueError(f"University '{name}' not found.")
        self.graph.remove_node(name)
        self.regions.pop(name, None)

    def save(self, path=DEFAULT_SAVE_PATH):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "nodes": [
                {"name": n, "region": self.regions.get(n, DEFAULT_REGION)}
                for n in self.graph.nodes
            ],
            "edges": [[u, v, d["weight"]] for u, v, d in self.graph.edges(data=True)],
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load(self, path=DEFAULT_SAVE_PATH):
        """Load a saved graph. Returns False (and keeps defaults) if there is none."""
        path = Path(path)
        if not path.exists():
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
        self.graph.clear()
        self.regions = {}
        for node in data["nodes"]:
            self.graph.add_node(node["name"])
            self.regions[node["name"]] = node.get("region", DEFAULT_REGION)
        for u, v, w in data["edges"]:
            self.graph.add_edge(u, v, weight=w)
        return True
