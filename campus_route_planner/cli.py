import matplotlib.pyplot as plt

from .distance_matrix import plot_distance_matrix
from .graph_data import DEFAULT_REGION, UniversityGraph
from .mst import compute_mst
from .reservation_system import ReservationSystem
from .scalable_graph import ScalableGraph
from .shortest_path import find_shortest_path
from .tsp_solver import MAX_CITIES, expand_route, tsp_dp
from .visualizer import (animate_path, draw_graph, draw_mst, draw_path,
                         draw_regions, draw_route)

MENU = """
Options:
 1. Show original graph
 2. Show MST
 3. Add new university
 4. Find shortest path between universities
 5. Set route capacity
 6. Reserve a seat
 7. View reservations
 8. TSP: best multi-university visit order
 9. Scalable graph (region-based MST)
10. Show distance matrix
11. Delete a university
12. Exit"""


def ask_number(prompt, cast=float):
    while True:
        try:
            return cast(input(prompt).strip())
        except ValueError:
            print("Please enter a valid number.")


def add_university(uni):
    name = input("Name of the new university: ").strip()
    if not name:
        print("Name cannot be empty.")
        return
    region = input(f"Region [{DEFAULT_REGION}]: ").strip() or DEFAULT_REGION
    try:
        uni.add_university(name, region)
    except ValueError as err:
        print(err)
        return

    print("Enter connections as '<University> <weight>', blank line to finish.")
    added = 0
    while True:
        line = input("Connect to: ").strip()
        if not line:
            break
        target, _, raw_weight = line.rpartition(" ")
        try:
            uni.add_connection(name, target.strip(), float(raw_weight))
            added += 1
        except ValueError as err:
            print(err)

    if added == 0:
        suggest_connection(uni, name)


def suggest_connection(uni, name):
    """No links entered: ask for candidate weights and attach to the cheapest."""
    print("No connections entered. Give a weight for each university to compare (blank skips).")
    best = None
    for other in uni.get_graph().nodes:
        if other == name:
            continue
        raw = input(f"Weight {name} - {other}: ").strip()
        if not raw:
            continue
        try:
            weight = float(raw)
        except ValueError:
            continue
        if weight > 0 and (best is None or weight < best[1]):
            best = (other, weight)
    if best:
        uni.add_connection(name, *best)
        print(f"Connected {name} to {best[0]} with weight {best[1]:g}.")
    else:
        print(f"{name} was added without any connection.")


def shortest_path_menu(graph):
    src = input("Source university: ").strip()
    dest = input("Destination university: ").strip()
    try:
        dist, path = find_shortest_path(graph, src, dest)
    except ValueError as err:
        print(err)
        return
    if not path:
        print(f"No route from {src} to {dest}.")
        return
    print(f"Shortest path: {' -> '.join(path)} (distance {dist:g})")
    title = f"Shortest path from {src} to {dest} (distance {dist:g})"
    draw_path(graph, path, title)
    ani = animate_path(graph, path, title, show=False)
    if ani is not None:
        plt.show()


def tsp_menu(graph):
    raw = input(f"Universities to visit (comma-separated, max {MAX_CITIES}): ")
    cities = [c.strip() for c in raw.split(",") if c.strip()]
    if not cities:
        print("No universities entered.")
        return
    try:
        cost, order = tsp_dp(graph, cities)
    except ValueError as err:
        print(err)
        return
    if not order:
        print("No valid path visits all of those universities.")
        return
    print(f"Best visit order: {' -> '.join(order)} (total cost {cost:g})")
    route = expand_route(graph, order)
    draw_route(graph, route, order, f"TSP route: {' -> '.join(order)} (cost {cost:g})")


def region_menu(uni):
    regions = uni.get_regions()
    final = ScalableGraph(uni.get_graph(), regions).build()
    region_of = lambda node: regions.get(node, DEFAULT_REGION)
    draw_regions(final, region_of, "Scalable Region-Based MST Graph")


def reservation_menu(system, choice):
    u1 = input("From university: ").strip()
    u2 = input("To university: ").strip()
    if choice == "5":
        system.set_capacity(u1, u2, ask_number("Capacity: ", int))
        print("Capacity set.")
    elif choice == "6":
        name = input("Student name: ").strip()
        priority = ask_number("Priority (lower is better): ", int)
        print(system.reserve(u1, u2, name, priority)[1])
    else:
        reservations = system.view_reservations(u1, u2)
        if not reservations:
            print("No reservations.")
        for priority, name in reservations:
            print(f"  {name} (priority {priority})")


def main():
    uni = UniversityGraph()
    if uni.load():
        print("Loaded saved graph.")
    reservations = ReservationSystem()

    while True:
        print(MENU)
        choice = input("Enter choice: ").strip()
        graph = uni.get_graph()

        try:
            if choice == "1":
                draw_graph(graph, "University Graph")
            elif choice == "2":
                draw_mst(graph, compute_mst(graph), "Minimum Spanning Tree (red)")
            elif choice == "3":
                add_university(uni)
                uni.save()
            elif choice == "4":
                shortest_path_menu(graph)
            elif choice in ("5", "6", "7"):
                reservation_menu(reservations, choice)
            elif choice == "8":
                tsp_menu(graph)
            elif choice == "9":
                region_menu(uni)
            elif choice == "10":
                plot_distance_matrix(graph, list(graph.nodes))
            elif choice == "11":
                name = input("University to delete (blank to cancel): ").strip()
                if name:
                    uni.remove_university(name)
                    uni.save()
                    print(f"Removed '{name}' and its connections.")
            elif choice == "12":
                break
            else:
                print("Invalid choice. Try again.")
        except (ValueError, EOFError) as err:
            print(err)
            if isinstance(err, EOFError):
                break
