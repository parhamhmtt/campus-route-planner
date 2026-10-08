# Campus Route Planner

A command-line tool for planning transport between universities. Universities are
nodes in a weighted graph and bus routes are edges. It was built for an algorithm
design course project and covers all four phases of the brief.

## Features

| Phase | Feature | Algorithm |
|-------|---------|-----------|
| 1 | Minimum spanning tree of the route network | Prim with a priority queue |
| 1 | Add a university and connect it without rebuilding the graph | Incremental edge insertion |
| 2 | Shortest path between two universities, with animation | Dijkstra |
| 2 | Route capacities and seat reservations | Priority queue (lower number = higher priority) |
| 3 | Best order to visit several universities | Held-Karp TSP (DP + bitmask) |
| 4 | Region-based MST for large graphs | Per-region MST, then Kruskal across regions |
| - | All-pairs distance matrix heatmap | Dijkstra from every node |

### Complexity

| Algorithm | Time | Memory |
|-----------|------|--------|
| Prim MST | O(E log V) | O(V + E) |
| Dijkstra | O((V + E) log V) | O(V) |
| TSP (n stops) | O(n² · 2ⁿ) | O(n · 2ⁿ) |
| Distance matrix | O(V · (V + E) log V) | O(V²) |
| Region-based MST | O(E log E) | O(V + E) |

TSP accepts up to 15 stops. Distances between stops are shortest-path distances,
so the route may pass through universities that are not on the stop list.

## Getting started

Requires Python 3.9 or newer.

```bash
git clone https://github.com/parhamhmtt/campus-route-planner.git
cd campus-route-planner
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m campus_route_planner
```

Plots open in a window, so a desktop environment is needed. On some Linux systems
you may also need `sudo apt install python3-tk`.

## Usage

The program starts with six sample universities and shows a menu:

```
 1. Show original graph            7. View reservations
 2. Show MST                       8. TSP: best multi-university visit order
 3. Add new university             9. Scalable graph (region-based MST)
 4. Find shortest path            10. Show distance matrix
 5. Set route capacity            11. Delete a university
 6. Reserve a seat                12. Exit
```

Example: option 8 with `Sharif, Beheshti, Kharazmi` prints the cheapest visiting
order and draws the full route on the graph.

The graph and each university's region are saved to `data/graph.json` whenever
you add or delete a university, and loaded again on the next start. Delete that
file to go back to the sample data. Reservations are kept in memory only.

## Project layout

```
campus_route_planner/
    cli.py                 menu and user input
    graph_data.py          graph, regions and JSON save/load
    mst.py                 Prim's algorithm
    shortest_path.py       Dijkstra
    tsp_solver.py          bitmask TSP and route expansion
    reservation_system.py  capacities and priority-queue reservations
    scalable_graph.py      region-based MST
    distance_matrix.py     distance matrix and heatmap
    visualizer.py          graph drawing and path animation
tests/                     pytest suite
```

## Tests

```bash
python -m pytest
```
