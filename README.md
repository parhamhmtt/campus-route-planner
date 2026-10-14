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
| - | Chat in plain English (Claude tool use) that calls all of the above | Tools wrap the algorithms; the model never does the maths |
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

## Chatbot

Ask for routes in plain English instead of using the menu:

```
export ANTHROPIC_API_KEY=sk-ant-...     # Windows: set ANTHROPIC_API_KEY=...
python -m campus_route_planner chat
```

```
you> What is the quickest way from Sharif to Beheshti?
  [tool] find_shortest_path({"source": "Sharif", "destination": "Beheshti"})
bot> Sharif -> Tehran -> Elm-o-Sanat -> Beheshti, a total distance of 8.
you> Plan a trip through Sharif, Kharazmi and Beheshti and draw it.
you> Add Allameh in the West region, connected to Tehran with weight 5.
you> Reserve a seat for Sara on Allameh-Tehran, priority 1.
```

How it works: Claude chooses from 13 tools (`tools.py`) and explains the result. Every
route, cost, spanning tree and reservation is computed by the algorithms in this
package, never by the model, and every tool validates its input (unknown names,
non-positive or NaN weights, routes that do not exist) and reports errors back so the
model can recover. The chat and the menu CLI share `data/graph.json`; the chat also
keeps reservations in `data/reservations.json`. Pictures (including the path animation
as a GIF) are saved to `output/`.

Options: `--model` (or the `CAMPUS_CHAT_MODEL` variable), `--data`, `--output`.
Tests use a scripted fake model, so `pytest` needs no API key or network.

## Project layout

```
campus_route_planner/
    cli.py                 menu and user input
    chatbot.py             Claude tool-use loop and terminal chat
    tools.py               tools (and JSON schemas) the chatbot can call
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
