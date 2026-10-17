import copy
import math
import re

from .distance_matrix import build_distance_matrix, plot_distance_matrix
from .graph_data import DEFAULT_REGION, DEFAULT_SAVE_PATH
from .mst import compute_mst
from .scalable_graph import ScalableGraph
from .shortest_path import find_shortest_path
from .tsp_solver import MAX_CITIES, expand_route, tsp_dp
from .visualizer import (animate_path, draw_graph, draw_mst, draw_path,
                         draw_regions, draw_route)

MAX_NAME_LENGTH = 60
UNDO_LIMIT = 20


def fmt(value):
    return f"{value:g}"


def plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def squash(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def tidy(name):
    name = name.strip()
    return name[:1].upper() + name[1:] if name.islower() else name


def positive(weight):
    if not math.isfinite(weight) or weight <= 0:
        raise ValueError("Weights must be positive numbers.")
    return int(weight) if weight == int(weight) else weight  # 5.0 is shown as 5


class Planner:
    def __init__(self, uni, reservations, figure=None, save_path=DEFAULT_SAVE_PATH,
                 on_draw=None, on_change=None):
        self.uni = uni
        self.reservations = reservations
        self.figure = figure          # where pictures are drawn, None means no pictures
        self.save_path = save_path    # None means do not write the graph to disk
        self.on_draw = on_draw        # called after the figure changed
        self.on_change = on_change    # called after universities or routes changed
        self.animation = None
        self.undo_stack = []

    @property
    def graph(self):
        return self.uni.get_graph()

    def names(self):
        return list(self.graph.nodes)

    def region_names(self):
        return sorted(set(self.uni.get_regions().values()))

    def region_of(self, name):
        return self.uni.get_regions().get(name, DEFAULT_REGION)

    def check(self, *names):
        for name in names:
            if name not in self.graph:
                raise ValueError(f"University '{name}' not found.")

    def need_universities(self):
        if not self.graph:
            raise ValueError("There are no universities yet. Add one first.")

    # undo

    def remember(self, label):
        # call this after the checks pass and right before something is changed
        self.undo_stack.append((self.graph.copy(), dict(self.uni.get_regions()),
                                copy.deepcopy(self.reservations.routes), label))
        del self.undo_stack[:-UNDO_LIMIT]

    def forget(self):
        self.undo_stack.pop()

    def undo(self):
        if not self.undo_stack:
            raise ValueError("There is nothing to undo.")
        graph, regions, routes, label = self.undo_stack.pop()
        self.uni.graph = graph
        self.uni.regions = regions
        self.reservations.routes = routes
        self.changed()
        return f"Undid: {label}."

    # drawing

    def stop_animation(self):
        if self.animation is not None and self.animation.event_source is not None:
            self.animation.event_source.stop()
        self.animation = None

    def drawn(self):
        if self.on_draw:
            self.on_draw()

    def show_network(self):
        self.stop_animation()
        if self.figure is not None:
            if self.graph:
                draw_graph(self.graph, "University graph", show=False, fig=self.figure)
            else:
                self.figure.clear()
            self.drawn()
        count = self.graph.number_of_nodes()
        word = "university" if count == 1 else "universities"
        return f"{count} {word}, {plural(self.graph.number_of_edges(), 'route')}."

    # questions

    def shortest_path(self, source, target, animate=False):
        self.check(source, target)
        if source == target:
            raise ValueError("Pick two different universities.")
        dist, path = find_shortest_path(self.graph, source, target)
        if not path:
            return f"There is no route from {source} to {target}."
        title = f"Shortest path from {source} to {target} (distance {fmt(dist)})"
        self.stop_animation()
        if self.figure is not None:
            if animate:
                self.animation = animate_path(self.graph, path, title, show=False, fig=self.figure)
            else:
                draw_path(self.graph, path, title, show=False, fig=self.figure)
            self.drawn()
        return f"Shortest path: {' -> '.join(path)} (distance {fmt(dist)})"

    def trip(self, stops, start=None, end=None):
        stops = list(dict.fromkeys([n for n in (start, *stops, end) if n]))
        self.check(*stops)
        if len(stops) < 2:
            raise ValueError("Pick at least two universities to visit.")
        if len(stops) > MAX_CITIES:
            raise ValueError(f"At most {MAX_CITIES} universities are supported.")
        cost, order = tsp_dp(self.graph, stops, start=start, end=end)
        if not order:
            return "No route connects all of those universities."
        route = expand_route(self.graph, order)
        lines = [f"Best order: {' -> '.join(order)} (total cost {fmt(cost)})"]
        extra = [n for n in dict.fromkeys(route) if n not in order]
        if extra:
            lines.append(f"The full route also passes through {', '.join(extra)}.")
        self.stop_animation()
        if self.figure is not None:
            title = f"TSP route: {' -> '.join(order)} (cost {fmt(cost)})"
            draw_route(self.graph, route, order, title, show=False, fig=self.figure)
            self.drawn()
        return "\n".join(lines)

    def spanning_tree(self):
        self.need_universities()
        tree = compute_mst(self.graph)
        self.stop_animation()
        if self.figure is not None:
            draw_mst(self.graph, tree, "Minimum spanning tree (red)", show=False, fig=self.figure)
            self.drawn()
        return self.edge_summary(tree, "Keep these routes")

    def region_tree(self):
        self.need_universities()
        final = ScalableGraph(self.graph, self.uni.get_regions()).build()
        self.stop_animation()
        if self.figure is not None:
            draw_regions(final, self.region_of, "Region-based MST", show=False, fig=self.figure)
            self.drawn()
        return self.edge_summary(final, "Region-based MST")

    def edge_summary(self, tree, title):
        edges = sorted(tree.edges(data=True), key=lambda e: (e[2]["weight"], e[0], e[1]))
        total = sum(d["weight"] for _, _, d in edges)
        lines = [f"{title}:"]
        lines += [f"  {u} - {v} ({fmt(d['weight'])})" for u, v, d in edges]
        lines.append(f"Total weight {fmt(total)}.")
        return "\n".join(lines)

    def distance_table(self):
        self.need_universities()
        names = self.names()
        self.stop_animation()
        if self.figure is not None:
            plot_distance_matrix(self.graph, names, show=False, fig=self.figure)
            self.drawn()
        matrix = build_distance_matrix(self.graph, names)
        label = max(len(n) for n in names)
        head = " " * label + "".join(f"{n[:8]:>9}" for n in names)
        rows = [f"{n:<{label}}" + "".join(f"{'-' if x == math.inf else fmt(x):>9}" for x in row)
                for n, row in zip(names, matrix)]
        return "\n".join([head] + rows)

    def direct_weight(self, a, b):
        self.check(a, b)
        if a == b:
            raise ValueError("Pick two different universities.")
        if self.graph.has_edge(a, b):
            return f"The direct route {a} - {b} has weight {fmt(self.graph[a][b]['weight'])}."
        dist, path = find_shortest_path(self.graph, a, b)
        if not path:
            return f"{a} and {b} are not connected at all."
        return (f"{a} and {b} have no direct route. The shortest way is "
                f"{' -> '.join(path)} (distance {fmt(dist)}).")

    def describe(self, name):
        self.check(name)
        links = sorted(self.graph[name].items())
        if not links:
            return f"{name} ({self.region_of(name)}) has no connections yet."
        joined = ", ".join(f"{v} ({fmt(d['weight'])})" for v, d in links)
        return f"{name} ({self.region_of(name)}) connects to {joined}."

    def list_all(self):
        count = self.graph.number_of_nodes()
        if not count:
            return "There are no universities."
        lines = [f"{count} {'university' if count == 1 else 'universities'}:"]
        for name in self.graph.nodes:
            links = ", ".join(f"{v} {fmt(d['weight'])}" for v, d in sorted(self.graph[name].items()))
            lines.append(f"  {name} ({self.region_of(name)}): {links or 'no connections'}")
        return "\n".join(lines)

    # changing the network

    def changed(self):
        if self.save_path:
            self.uni.save(self.save_path)
        self.show_network()
        if self.on_change:
            self.on_change()

    def add_university(self, name, region, links):
        name = tidy(name)
        if not name:
            raise ValueError("Give the university a name.")
        if len(name) > MAX_NAME_LENGTH:
            raise ValueError("That name is too long.")
        for existing in self.graph.nodes:
            if squash(existing) == squash(name):
                raise ValueError(f"{existing} already exists.")

        # check every link before touching the graph
        checked = []
        for other, weight in links:
            self.check(other)
            checked.append((other, positive(weight)))
        links = checked
        if len({other for other, _ in links}) != len(links):
            raise ValueError("Each university can only be linked once.")

        region = (region or "").strip() or DEFAULT_REGION
        for known in self.region_names():
            if known.lower() == region.lower():
                region = known

        self.remember(f"added {name}")
        self.uni.add_university(name, region)
        for other, weight in links:
            self.uni.add_connection(name, other, weight)
        self.changed()
        if not links:
            return f"Added {name} ({region}) with no connections yet."
        joined = ", ".join(f"{o} ({fmt(w)})" for o, w in links)
        return f"Added {name} ({region}), connected to {joined}."

    def connect_cheapest(self, name, candidates):
        # candidates maps a university to the weight it would have, the cheapest one wins
        self.check(name)
        best = None
        for other, weight in candidates.items():
            self.check(other)
            weight = positive(weight)
            if best is None or weight < best[1]:
                best = (other, weight)
        if best is None:
            raise ValueError("Give at least one weight to compare.")
        self.remember(f"connected {name} to {best[0]}")
        self.uni.add_connection(name, *best)
        self.changed()
        return f"Connected {name} to {best[0]} with weight {fmt(best[1])}."

    def connect(self, a, b, weight):
        self.check(a, b)
        weight = positive(weight)
        old = self.graph[a][b]["weight"] if self.graph.has_edge(a, b) else None
        if a != b:
            self.remember(f"route {a} - {b}")
        self.uni.add_connection(a, b, weight)
        self.changed()
        if old is None:
            return f"Connected {a} and {b} with weight {fmt(weight)}."
        return f"Changed {a} - {b} from {fmt(old)} to {fmt(weight)}."

    def remove(self, name):
        self.check(name)
        self.remember(f"removed {name}")
        self.uni.remove_university(name)
        for key in [k for k in self.reservations.routes if name in k]:
            del self.reservations.routes[key]
        self.changed()
        return f"Removed {name} and its connections."

    # seats

    def direct_route(self, a, b):
        self.check(a, b)
        if a == b:
            raise ValueError("Pick two different universities.")
        if not self.graph.has_edge(a, b):
            raise ValueError(f"There is no direct route between {a} and {b}.")

    def set_capacity(self, a, b, capacity):
        self.direct_route(a, b)
        if capacity < 0:
            raise ValueError("Capacity can't be negative.")
        if capacity != int(capacity):
            raise ValueError("Capacity must be a whole number.")
        self.remember(f"capacity of {a} - {b}")
        self.reservations.set_capacity(a, b, int(capacity))
        return f"{a} - {b} now has {plural(int(capacity), 'seat')}."

    def reserve(self, a, b, student, priority):
        self.direct_route(a, b)
        student = student.strip()
        if not student:
            raise ValueError("Give the student's name.")
        self.remember(f"seat for {student} on {a} - {b}")
        ok, message = self.reservations.reserve(a, b, student, int(priority))
        if not ok:
            self.forget()
        return f"{student} now has a seat on {a} - {b}." if ok else message

    def cancel_reservation(self, a, b, student):
        self.direct_route(a, b)
        student = student.strip()
        if not student:
            raise ValueError("Give the student's name.")
        self.remember(f"cancelled {student}'s seat on {a} - {b}")
        ok, message = self.reservations.cancel(a, b, student)
        if not ok:
            self.forget()
        return message

    def seat_report(self, a, b):
        self.direct_route(a, b)
        route = self.reservations.routes.get(tuple(sorted((a, b))))
        if route is None:
            return f"No capacity has been set for {a} - {b} yet."
        queue = self.reservations.view_reservations(a, b)
        lines = [f"{a} - {b}: {len(queue)} of {plural(route['capacity'], 'seat')} taken."]
        lines += [f"  {who} (priority {priority})" for priority, who in queue]
        return "\n".join(lines)
