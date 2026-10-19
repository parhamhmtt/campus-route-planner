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
                         draw_regions, draw_route, project)

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
        self.guessed = set()          # universities whose map position was chosen by us

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
                                dict(self.uni.get_positions()), set(self.guessed),
                                copy.deepcopy(self.reservations.routes), label))
        del self.undo_stack[:-UNDO_LIMIT]

    def forget(self):
        self.undo_stack.pop()

    def undo(self):
        if not self.undo_stack:
            raise ValueError("There is nothing to undo.")
        graph, regions, positions, guessed, routes, label = self.undo_stack.pop()
        self.uni.graph = graph
        self.uni.regions = regions
        self.uni.positions = positions
        self.guessed = guessed
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
                draw_graph(self.graph, "University graph", show=False, fig=self.figure,
                           positions=self.uni.get_positions())
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
            places = self.uni.get_positions()
            if animate:
                # long journeys get fewer frames per leg so they do not drag on
                steps = max(6, min(25, 220 // (len(path) - 1)))
                self.animation = animate_path(self.graph, path, title, steps_per_edge=steps,
                                              show=False, fig=self.figure, positions=places)
            else:
                draw_path(self.graph, path, title, show=False, fig=self.figure, positions=places)
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
            draw_route(self.graph, route, order, title, show=False, fig=self.figure,
                       positions=self.uni.get_positions())
            self.drawn()
        return "\n".join(lines)

    def spanning_tree(self):
        self.need_universities()
        tree = compute_mst(self.graph)
        self.stop_animation()
        if self.figure is not None:
            draw_mst(self.graph, tree, "Minimum spanning tree (red)", show=False, fig=self.figure,
                     positions=self.uni.get_positions())
            self.drawn()
        return self.edge_summary(tree, "Keep these routes")

    def region_tree(self):
        self.need_universities()
        final = ScalableGraph(self.graph, self.uni.get_regions()).build()
        self.stop_animation()
        if self.figure is not None:
            draw_regions(final, self.region_of, "Region-based MST", show=False, fig=self.figure,
                         positions=self.uni.get_positions())
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
        if len(names) > 10:
            return self.distance_summary(names, matrix)
        label = max(len(n) for n in names)
        head = " " * label + "".join(f"{n[:8]:>9}" for n in names)
        rows = [f"{n:<{label}}" + "".join(f"{'-' if x == math.inf else fmt(x):>9}" for x in row)
                for n, row in zip(names, matrix)]
        return "\n".join([head] + rows)

    def distance_summary(self, names, matrix):
        pairs = [(matrix[i][j], names[i], names[j])
                 for i in range(len(names)) for j in range(i + 1, len(names))]
        reachable = [p for p in pairs if p[0] != math.inf]
        lines = [f"{len(names)} universities, the full table is on the map."]
        if reachable:
            far, near = max(reachable), min(reachable)
            lines.append(f"Farthest apart: {far[1]} and {far[2]} ({fmt(far[0])}).")
            lines.append(f"Closest: {near[1]} and {near[2]} ({fmt(near[0])}).")
        cut_off = len(pairs) - len(reachable)
        if cut_off:
            lines.append(f"{plural(cut_off, 'pair')} cannot reach each other.")
        return "\n".join(lines)

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

    def guess_position(self, near):
        # near is a list of universities, the new one goes by them (or mid-map without any)
        places = self.uni.get_positions()
        spots = [places[n] for n in near if n in places] or list(places.values())
        lat = sum(p[0] for p in spots) / len(spots)
        lon = sum(p[1] for p in spots) / len(spots)
        angle = sum(map(ord, "".join(near))) * 2.4
        for step in range(1, 40):
            candidate = (lat + 0.22 * step * math.cos(angle), lon + 0.3 * step * math.sin(angle))
            here = project(*candidate)
            if all(math.dist(here, project(*p)) > 30 for p in places.values()):
                return (round(candidate[0], 4), round(candidate[1], 4))
        return (round(lat, 4), round(lon, 4))

    def has_map(self):
        places = self.uni.get_positions()
        return bool(self.graph) and all(n in places for n in self.graph.nodes)

    def add_university(self, name, region, links, position=None):
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

        if position is not None:
            lat, lon = position
            if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError("Latitude must be between -90 and 90, longitude between -180 and 180.")
        guessing = position is None and self.has_map()
        if guessing:
            position = self.guess_position([other for other, _ in links])

        self.remember(f"added {name}")
        if guessing:
            self.guessed.add(name)  # after the snapshot, so undo takes it back out
        self.uni.add_university(name, region, position)
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
        if name in self.guessed:  # it was dropped mid-map, so move it next to its neighbour
            self.uni.positions[name] = self.guess_position([best[0]])
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
        self.guessed.discard(name)
        self.uni.remove_university(name)
        for key in [k for k in self.reservations.routes if name in k]:
            del self.reservations.routes[key]
        self.changed()
        return f"Removed {name} and its connections."

    def reset_to_sample(self):
        self.remember("reset to the sample network")
        self.uni.load_sample()
        self.reservations.routes = {}
        self.guessed = set()
        self.changed()
        return f"Back to the sample network, {self.show_network()}"

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
