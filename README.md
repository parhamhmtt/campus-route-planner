# Campus Route Planner


<p align="center">
</p>

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

## Gallery


<p align="center">
  <img src="docs/images/path_animation.gif" alt="Animated Dijkstra shortest path from Sharif to Beheshti" width="480"><br>
  <em>Dijkstra shortest path, animated</em>
</p>

| | |
|---|---|
| <img src="docs/images/mst.png" alt="Minimum spanning tree"><br><sub>Minimum spanning tree (Prim)</sub> | <img src="docs/images/trip.png" alt="TSP multi-stop route"><br><sub>Best multi-stop order (Held-Karp TSP)</sub> |
| <img src="docs/images/region_mst.png" alt="Region-based MST"><br><sub>Region-based MST for large graphs</sub> | <img src="docs/images/distance_matrix.png" alt="Distance matrix heatmap"><br><sub>All-pairs distance heatmap</sub> |

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










```
```



## Project layout

```
campus_route_planner/
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
