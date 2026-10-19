import json
from pathlib import Path

import networkx as nx

from .uk_data import ROUTES, UNIVERSITIES

DEFAULT_REGION = "Unassigned"
DEFAULT_SAVE_PATH = Path("data") / "graph.json"


class UniversityGraph:
    
    
    def __init__(self, universities=None, routes=None):
        self.graph = nx.Graph()
        self.regions = {}
        self.positions = {}
        self.sample = (UNIVERSITIES if universities is None else universities,
                       ROUTES if routes is None else routes)
        self.load_sample()

    def load_sample(self):
        universities, routes = self.sample
        self.graph.clear()
        self.regions = {}
        self.positions = {}
        for name, region, *place in universities:
            self.graph.add_node(name)
            self.regions[name] = region
            if place:
                self.positions[name] = (place[0], place[1])
        for u, v, w in routes:
            self.graph.add_edge(u, v, weight=w)

    def get_graph(self):
        return self.graph

    def get_regions(self):
        return self.regions

    def get_positions(self):
        return self.positions

    def add_university(self, name, region=DEFAULT_REGION, position=None):
        if name in self.graph:
            raise ValueError(f"University '{name}' already exists.")
        self.graph.add_node(name)
        self.regions[name] = region or DEFAULT_REGION
        if position:
            self.positions[name] = tuple(position)

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
        self.positions.pop(name, None)

    def save(self, path=DEFAULT_SAVE_PATH):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        nodes = []
        for n in self.graph.nodes:
            node = {"name": n, "region": self.regions.get(n, DEFAULT_REGION)}
            if n in self.positions:
                node["lat"], node["lon"] = self.positions[n]
            nodes.append(node)
        data = {
            "nodes": nodes,
            "edges": [[u, v, d["weight"]] for u, v, d in self.graph.edges(data=True)],
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load(self, path=DEFAULT_SAVE_PATH):
        path = Path(path)
        if not path.exists():
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
        self.graph.clear()
        self.regions = {}
        self.positions = {}
        for node in data["nodes"]:
            self.graph.add_node(node["name"])
            self.regions[node["name"]] = node.get("region", DEFAULT_REGION)
            if "lat" in node and "lon" in node:
                self.positions[node["name"]] = (node["lat"], node["lon"])
        for u, v, w in data["edges"]:
            self.graph.add_edge(u, v, weight=w)
        return True
