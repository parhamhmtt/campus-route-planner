"""Tool layer for the chatbot.

Every tool is a plain method on ``PlannerSession`` that calls the existing
algorithms (Dijkstra, Prim, Held-Karp, ...) and returns a JSON-safe dict. The
language model never computes a route itself: it only picks a tool and explains
the result. ``PlannerSession.call`` is the single entry point used by the chat
loop and never raises, so a bad tool call cannot crash the conversation.
"""

import difflib
import json
import math
import re
from collections.abc import Mapping
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx

from . import visualizer
from .distance_matrix import build_distance_matrix, plot_distance_matrix
from .graph_data import DEFAULT_REGION, DEFAULT_SAVE_PATH, UniversityGraph
from .mst import compute_mst
from .reservation_system import ReservationSystem
from .scalable_graph import ScalableGraph
from .shortest_path import find_shortest_path
from .tsp_solver import MAX_CITIES, expand_route, tsp_dp

DEFAULT_OUTPUT_DIR = Path("output")
MAX_NAME_LENGTH = 60
PLOT_KINDS = (
    "graph",
    "mst",
    "region_mst",
    "shortest_path",
    "path_animation",
    "trip",
    "distance_matrix",
)





def _clean(value):
    """Make a number JSON-safe: inf/nan become None, whole floats become ints."""
    if isinstance(value, float):
        if math.isinf(value) or math.isnan(value):
            return None
        if value.is_integer():
            return int(value)
    return value


def _norm(text):
    """Lower-case and drop punctuation/spaces, so 'elm o sanat' == 'Elm-o-Sanat'."""
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def _slug(text):
    return re.sub(r"[^A-Za-z0-9]+", "-", str(text)).strip("-") or "x"


def _positive_number(value, label):
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            raise ValueError(f"{label} must be a number.") from None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number.")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be a positive, finite number.")
    return value


def _integer(value, label, minimum=None):
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            raise ValueError(f"{label} must be a whole number.") from None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a whole number.")
    if not math.isfinite(value) or int(value) != value:
        raise ValueError(f"{label} must be a whole number.")
    value = int(value)
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be at least {minimum}.")
    return value


def _route_key(a, b):
    return tuple(sorted((a, b)))





class PlannerSession:
    """State shared by all tools: the university graph and the reservations.

    With ``persist=True`` the graph is stored in ``save_path`` (the same file the
    menu CLI uses) and reservations in ``reservations.json`` next to it.
    """

    def __init__(self, save_path=DEFAULT_SAVE_PATH, output_dir=DEFAULT_OUTPUT_DIR,
                 reservations_path=None, persist=True):
        self.persist = persist
        self.save_path = Path(save_path)
        self.reservations_path = (
            Path(reservations_path) if reservations_path
            else self.save_path.parent / "reservations.json"
        )
        self.output_dir = Path(output_dir)
        self.uni = UniversityGraph()
        self.reservations = ReservationSystem()
        if persist:
            self.uni.load(self.save_path)
            self._load_reservations()

    
    def _save_graph(self):
        if self.persist:
            self.uni.save(self.save_path)

    def _save_reservations(self):
        if not self.persist:
            return
        data = [
            {
                "from": a,
                "to": b,
                "capacity": route["capacity"],
                "reservations": [
                    {"priority": p, "student": s} for p, s in sorted(route["queue"])
                ],
            }
            for (a, b), route in self.reservations.routes.items()
        ]
        self.reservations_path.parent.mkdir(parents=True, exist_ok=True)
        self.reservations_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load_reservations(self):
        if not self.reservations_path.exists():
            return
        graph = self.uni.get_graph()
        for item in json.loads(self.reservations_path.read_text(encoding="utf-8")):
            a, b = item["from"], item["to"]
            if not graph.has_edge(a, b):  
                continue
            queue = sorted((e["priority"], e["student"]) for e in item["reservations"])
            
            self.reservations.routes[_route_key(a, b)] = {
                "capacity": item["capacity"],
                "queue": queue,
            }

    
    def resolve(self, name):
        """Map user/model spelling to a real university name, or raise ValueError."""
        graph = self.uni.get_graph()
        if not isinstance(name, str) or not name.strip():
            raise ValueError("A university name is required.")
        name = name.strip()
        if name in graph:
            return name
        wanted = _norm(name)
        matches = [n for n in graph.nodes if wanted and _norm(n) == wanted]
        if len(matches) == 1:
            return matches[0]
        close = difflib.get_close_matches(name, list(graph.nodes), n=3, cutoff=0.6)
        hint = f" Did you mean: {', '.join(close)}?" if close else ""
        known = ", ".join(graph.nodes) or "none"
        raise ValueError(f"University '{name}' not found.{hint} Known universities: {known}.")

    def _require_route(self, a, b):
        a, b = self.resolve(a), self.resolve(b)
        if a == b:
            raise ValueError("Pick two different universities.")
        if not self.uni.get_graph().has_edge(a, b):
            raise ValueError(
                f"There is no direct route between {a} and {b}. "
                "Capacities and reservations work on direct routes only."
            )
        return a, b

    def _match_region(self, region):
        if not isinstance(region, str) or not region.strip():
            return DEFAULT_REGION
        region = region.strip()
        for existing in set(self.uni.get_regions().values()):
            if existing.lower() == region.lower():
                return existing
        return region

    
    
    
    def list_universities(self):
        graph = self.uni.get_graph()
        regions = self.uni.get_regions()
        return {
            "count": graph.number_of_nodes(),
            "universities": [
                {
                    "name": n,
                    "region": regions.get(n, DEFAULT_REGION),
                    "connections": [
                        {"to": v, "weight": _clean(d["weight"])}
                        for v, d in sorted(graph[n].items())
                    ],
                }
                for n in graph.nodes
            ],
        }

    def find_shortest_path(self, source, destination):
        graph = self.uni.get_graph()
        src, dst = self.resolve(source), self.resolve(destination)
        dist, path = find_shortest_path(graph, src, dst)
        if not path:
            return {"reachable": False, "source": src, "destination": dst,
                    "message": f"There is no route from {src} to {dst}."}
        return {"reachable": True, "source": src, "destination": dst,
                "distance": _clean(dist), "path": path}

    def plan_multi_stop_trip(self, stops):
        if not isinstance(stops, (list, tuple)):
            raise ValueError("stops must be a list of university names.")
        resolved = list(dict.fromkeys(self.resolve(s) for s in stops))
        if len(resolved) < 2:
            raise ValueError("Give at least two different universities to visit.")
        if len(resolved) > MAX_CITIES:
            raise ValueError(f"At most {MAX_CITIES} universities are supported.")

        graph = self.uni.get_graph()
        cost, order = tsp_dp(graph, resolved)
        if not order:
            return {"possible": False,
                    "message": "No route connects all of those universities."}
        route = expand_route(graph, order)
        passes_through = list(dict.fromkeys(n for n in route if n not in order))
        return {
            "possible": True,
            "visit_order": order,
            "total_cost": _clean(cost),
            "full_route": route,
            "passes_through_other_universities": passes_through,
            "note": "Cheapest open path: start and end are chosen freely, not a round trip.",
        }

    def get_minimum_spanning_tree(self):
        graph = self.uni.get_graph()
        mst = compute_mst(graph)
        edges = sorted(
            ({"a": u, "b": v, "weight": _clean(d["weight"])}
             for u, v, d in mst.edges(data=True)),
            key=lambda e: (e["weight"], e["a"], e["b"]),
        )
        connected = graph.number_of_nodes() > 0 and nx.is_connected(graph)
        return {
            "edges": edges,
            "total_weight": _clean(sum(d["weight"] for _, _, d in mst.edges(data=True))),
            "network_is_connected": connected,
        }

    def get_region_mst(self):
        graph = self.uni.get_graph()
        regions = self.uni.get_regions()
        final = ScalableGraph(graph, regions).build()
        by_region = {}
        for n in graph.nodes:
            by_region.setdefault(regions.get(n, DEFAULT_REGION), []).append(n)
        return {
            "regions": by_region,
            "edges": sorted(
                ({"a": u, "b": v, "weight": _clean(d["weight"])}
                 for u, v, d in final.edges(data=True)),
                key=lambda e: (e["weight"], e["a"], e["b"]),
            ),
            "total_weight": _clean(sum(d["weight"] for _, _, d in final.edges(data=True))),
        }

    def get_distance_matrix(self):
        graph = self.uni.get_graph()
        names = list(graph.nodes)
        matrix = build_distance_matrix(graph, names)
        return {
            "universities": names,
            "matrix": [[_clean(x) for x in row] for row in matrix],
            "note": "matrix[i][j] is the shortest distance from universities[i] to "
                    "universities[j]; null means unreachable.",
        }

    def add_university(self, name, region=None, connections=None):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("A university name is required.")
        name = name.strip()
        if len(name) > MAX_NAME_LENGTH:
            raise ValueError(f"Name is too long (max {MAX_NAME_LENGTH} characters).")
        if "," in name:
            raise ValueError("Names cannot contain commas.")
        if not _norm(name):
            raise ValueError("Name must contain letters or digits.")
        graph = self.uni.get_graph()
        for existing in graph.nodes:
            if _norm(existing) == _norm(name):
                raise ValueError(f"University '{name}' already exists (as '{existing}').")

        
        links = {}
        for item in connections or []:
            if not isinstance(item, Mapping) or "university" not in item or "weight" not in item:
                raise ValueError("Each connection needs 'university' and 'weight'.")
            other = self.resolve(item["university"])
            links[other] = _positive_number(item["weight"], f"Weight to {other}")

        region = self._match_region(region)
        self.uni.add_university(name, region)
        for other, weight in links.items():
            self.uni.add_connection(name, other, weight)
        self._save_graph()

        result = {
            "added": name,
            "region": region,
            "connections": [{"to": o, "weight": _clean(w)} for o, w in links.items()],
        }
        if not links:
            result["warning"] = (
                f"{name} has no connections yet, so it cannot be reached. "
                "Ask the user which universities to connect it to."
            )
        return result

    def connect_universities(self, university_a, university_b, weight):
        a, b = self.resolve(university_a), self.resolve(university_b)
        weight = _positive_number(weight, "Weight")
        graph = self.uni.get_graph()
        previous = graph[a][b]["weight"] if graph.has_edge(a, b) else None
        self.uni.add_connection(a, b, weight)  
        self._save_graph()
        result = {"connected": [a, b], "weight": _clean(weight)}
        if previous is not None:
            result["replaced_previous_weight"] = _clean(previous)
        return result

    def remove_university(self, name):
        name = self.resolve(name)
        graph = self.uni.get_graph()
        lost = sorted(graph[name])
        self.uni.remove_university(name)
        dropped = [k for k in self.reservations.routes if name in k]
        for key in dropped:
            del self.reservations.routes[key]
        self._save_graph()
        self._save_reservations()
        return {"removed": name, "connections_removed": lost,
                "reservation_routes_cleared": len(dropped)}

    def set_route_capacity(self, university_a, university_b, capacity):
        a, b = self._require_route(university_a, university_b)
        capacity = _integer(capacity, "Capacity", minimum=0)
        self.reservations.set_capacity(a, b, capacity)
        self._save_reservations()
        return {"route": [a, b], "capacity": capacity}

    def reserve_seat(self, university_a, university_b, student_name, priority):
        a, b = self._require_route(university_a, university_b)
        if not isinstance(student_name, str) or not student_name.strip():
            raise ValueError("A student name is required.")
        priority = _integer(priority, "Priority")
        ok, message = self.reservations.reserve(a, b, student_name.strip(), priority)
        if ok:
            self._save_reservations()
        return {"success": ok, "message": message, "route": [a, b]}

    def view_reservations(self, university_a, university_b):
        a, b = self._require_route(university_a, university_b)
        route = self.reservations.routes.get(_route_key(a, b))
        queue = self.reservations.view_reservations(a, b)
        capacity = route["capacity"] if route else None
        return {
            "route": [a, b],
            "capacity": capacity,
            "reservations": [{"student": s, "priority": p} for p, s in queue],
            "seats_left": None if capacity is None else capacity - len(queue),
        }

    def save_plot(self, kind, source=None, destination=None, stops=None):
        if kind not in PLOT_KINDS:
            raise ValueError(f"kind must be one of: {', '.join(PLOT_KINDS)}.")
        graph = self.uni.get_graph()
        if graph.number_of_nodes() == 0:
            raise ValueError("The graph is empty, so there is nothing to draw.")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        name, suffix = kind, ".png"

        if kind == "graph":
            fig = visualizer.draw_graph(graph, "University Graph", show=False)
        elif kind == "mst":
            fig = visualizer.draw_mst(graph, compute_mst(graph),
                                      "Minimum Spanning Tree (red)", show=False)
        elif kind == "region_mst":
            regions = self.uni.get_regions()
            final = ScalableGraph(graph, regions).build()
            fig = visualizer.draw_regions(
                final, lambda n: regions.get(n, DEFAULT_REGION),
                "Scalable Region-Based MST Graph", show=False)
        elif kind == "distance_matrix":
            fig = plot_distance_matrix(graph, list(graph.nodes), show=False)
        elif kind == "trip":
            if not isinstance(stops, (list, tuple)):
                raise ValueError("stops (a list of universities) is required for a trip plot.")
            plan = self.plan_multi_stop_trip(stops)
            if not plan["possible"]:
                raise ValueError(plan["message"])
            order = plan["visit_order"]
            fig = visualizer.draw_route(
                graph, plan["full_route"], order,
                f"TSP route: {' -> '.join(order)} (cost {plan['total_cost']:g})", show=False)
            name = "trip"
        else:  
            if not source or not destination:
                raise ValueError("source and destination are required for a path plot.")
            found = self.find_shortest_path(source, destination)
            if not found["reachable"]:
                raise ValueError(found["message"])
            path, src, dst = found["path"], found["source"], found["destination"]
            title = f"Shortest path from {src} to {dst} (distance {found['distance']:g})"
            name = f"{kind}_{_slug(src)}_to_{_slug(dst)}"
            if kind == "shortest_path":
                fig = visualizer.draw_path(graph, path, title, show=False)
            else:
                if len(path) < 2:
                    raise ValueError("An animation needs two different universities.")
                suffix = ".gif"
                ani = visualizer.animate_path(graph, path, title, show=False)
                fig = plt.gcf()  
                target = self.output_dir / f"{name}{suffix}"
                ani.save(str(target), writer="pillow", fps=20)
                plt.close(fig)
                return {"file": str(target), "kind": kind}

        target = self.output_dir / f"{name}{suffix}"
        fig.savefig(target, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return {"file": str(target), "kind": kind}

    
    
    
    def call(self, name, arguments=None):
        """Run a tool by name. Always returns a dict; failures use an 'error' key."""
        spec = TOOLS.get(name)
        if spec is None:
            return {"error": f"Unknown tool '{name}'."}
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, Mapping):
            return {"error": "Tool arguments must be a JSON object."}
        schema = spec["input_schema"]
        missing = [k for k in schema.get("required", []) if k not in arguments]
        unknown = [k for k in arguments if k not in schema["properties"]]
        if missing:
            return {"error": f"Missing required argument(s): {', '.join(missing)}."}
        if unknown:
            return {"error": f"Unexpected argument(s): {', '.join(unknown)}."}
        try:
            return getattr(self, name)(**arguments)
        except ValueError as err:
            return {"error": str(err)}
        except Exception as err:  
            return {"error": f"Unexpected {type(err).__name__}: {err}"}





def _tool(name, description, properties=None, required=None):
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": properties or {},
            "required": required or [],
        },
    }


_UNI = {"type": "string", "description": "University name"}

TOOL_SCHEMAS = [
    _tool(
        "list_universities",
        "List every university with its region and direct shuttle connections "
        "(neighbour and weight). Use this to see what exists before answering.",
    ),
    _tool(
        "find_shortest_path",
        "Shortest route between two universities (Dijkstra). Returns the distance "
        "and the stops in order.",
        {"source": _UNI, "destination": _UNI},
        ["source", "destination"],
    ),
    _tool(
        "plan_multi_stop_trip",
        "Cheapest order to visit several universities (Held-Karp TSP, 2 to "
        f"{MAX_CITIES} stops). It is an open path: the start and end are chosen "
        "freely, it is not a round trip. Also returns the full route, which may "
        "pass through universities that are not on the stop list.",
        {"stops": {"type": "array", "items": {"type": "string"},
                   "description": "Universities to visit, in any order"}},
        ["stops"],
    ),
    _tool(
        "get_minimum_spanning_tree",
        "Cheapest set of routes that keeps every university connected (Prim). "
        "Returns the edges and the total weight.",
    ),
    _tool(
        "get_region_mst",
        "Region-based MST for large networks: one tree per region, joined by the "
        "cheapest cross-region links. Returns regions, edges and total weight.",
    ),
    _tool(
        "get_distance_matrix",
        "Shortest distance between every pair of universities. null = unreachable.",
    ),
    _tool(
        "add_university",
        "Add a new university and connect it to existing ones. Ask the user for "
        "the connections and weights; do not invent them. The change is saved.",
        {
            "name": {"type": "string", "description": "Unique name, no commas"},
            "region": {"type": "string",
                       "description": "Region name (optional, default 'Unassigned')"},
            "connections": {
                "type": "array",
                "description": "Direct routes to existing universities",
                "items": {
                    "type": "object",
                    "properties": {
                        "university": _UNI,
                        "weight": {"type": "number", "description": "Positive distance/cost"},
                    },
                    "required": ["university", "weight"],
                },
            },
        },
        ["name"],
    ),
    _tool(
        "connect_universities",
        "Create a direct route between two existing universities, or replace the "
        "weight if the route already exists. The change is saved.",
        {"university_a": _UNI, "university_b": _UNI,
         "weight": {"type": "number", "description": "Positive distance/cost"}},
        ["university_a", "university_b", "weight"],
    ),
    _tool(
        "remove_university",
        "Delete a university, all its routes and their reservations. Destructive: "
        "confirm with the user first.",
        {"name": _UNI},
        ["name"],
    ),
    _tool(
        "set_route_capacity",
        "Set how many seats a direct route has. Works on existing direct routes only.",
        {"university_a": _UNI, "university_b": _UNI,
         "capacity": {"type": "integer", "description": "Number of seats, 0 or more"}},
        ["university_a", "university_b", "capacity"],
    ),
    _tool(
        "reserve_seat",
        "Reserve a seat for a student on a direct route. Lower priority number = "
        "higher priority; it only orders the list. Once the route is full, new "
        "requests are rejected. Ask the user for the priority; do not guess.",
        {"university_a": _UNI, "university_b": _UNI,
         "student_name": {"type": "string"},
         "priority": {"type": "integer", "description": "Lower number = higher priority"}},
        ["university_a", "university_b", "student_name", "priority"],
    ),
    _tool(
        "view_reservations",
        "Show the capacity, reservations (in priority order) and free seats of a route.",
        {"university_a": _UNI, "university_b": _UNI},
        ["university_a", "university_b"],
    ),
    _tool(
        "save_plot",
        "Draw a picture and save it to a file (PNG, or GIF for path_animation); "
        "returns the file path. kind: graph, mst, region_mst, distance_matrix, "
        "shortest_path and path_animation (need source and destination), "
        "trip (needs stops).",
        {
            "kind": {"type": "string", "enum": list(PLOT_KINDS)},
            "source": _UNI,
            "destination": _UNI,
            "stops": {"type": "array", "items": {"type": "string"}},
        },
        ["kind"],
    ),
]

TOOLS = {spec["name"]: spec for spec in TOOL_SCHEMAS}
