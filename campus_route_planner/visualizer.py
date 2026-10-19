import json
import math
import textwrap
from pathlib import Path

import matplotlib.animation as animation
import matplotlib.patheffects as effects
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon

LAYOUT_SEED = 42
BASE_COLOR = "skyblue"
REGION_PALETTE = ["#4c9be8", "#f2a541", "#6bbf59", "#c77dd6", "#e8645a", "#8d8d8d",
                  "#2a9d8f", "#e9c46a", "#9b5de5", "#00a6a6"]

# the map: kilometres east and north of a point in the middle of the UK
LAT0, LON0 = 54.5, -3.0
VIEW = (-8.4, 1.9, 49.8, 58.8)  # west, east, south, north (degrees)
SEA, LAND, ABROAD, COAST = "#e6eef4", "#fbfaf6", "#eceee9", "#a9b6b2"
MAP_NODE, LABEL_COLOR = "#3a86c8", "#1d2830"
MANY_EDGES = 30  # above this only the highlighted routes get a weight
CHAR_KM, LABEL_KM, GAP_KM = 12.5, 22.0, 13.0  # rough label size on the map

_outline = None


def project(lat, lon):
    return ((lon - LON0) * math.cos(math.radians(LAT0)) * 111.32, (lat - LAT0) * 110.57)


def outline():
    global _outline
    if _outline is None:
        raw = json.loads(Path(__file__).with_name("uk_outline.json").read_text())
        _outline = {nation: [[project(lat, lon) for lon, lat in ring] for ring in rings]
                    for nation, rings in raw.items()}
    return _outline


def _layout(graph):
    return nx.spring_layout(graph, seed=LAYOUT_SEED)


def _map_positions(graph, positions):
    # real coordinates are used only when every university has them
    if not positions or any(n not in positions for n in graph.nodes):
        return None
    return {n: project(*positions[n]) for n in graph.nodes}


def _axes(fig):
    # draw into the figure we are given (the gui window), or open a new one
    if fig is None:
        return plt.subplots()
    fig.clear()
    return fig, fig.add_subplot()


def _finish(fig, title, show):
    # a long title (a trip with many stops) goes on two lines instead of running off the edge
    fig.suptitle(textwrap.fill(title, 70), fontsize=10, fontweight="bold")
    if show:
        plt.show()
    return fig


def _overlap(a, b):
    width = min(a[2], b[2]) - max(a[0], b[0])
    height = min(a[3], b[3]) - max(a[1], b[1])
    return width * height if width > 0 and height > 0 else 0


def _label_spots(pos):
    # for every name pick the spot around its dot that collides least with the others
    crowd = {n: sum(1 for m in pos if m != n and math.dist(pos[n], pos[m]) < 100) for n in pos}
    dots = [(x - GAP_KM, y - GAP_KM, x + GAP_KM, y + GAP_KM) for x, y in pos.values()]
    placed, spots = [], {}
    r = GAP_KM
    for name in sorted(pos, key=lambda n: -crowd[n]):
        x, y = pos[name]
        width = len(name) * CHAR_KM + 4
        options = [("center", "bottom", x, y + r), ("center", "top", x, y - r),
                   ("left", "center", x + r, y), ("right", "center", x - r, y),
                   ("left", "bottom", x + r * .7, y + r * .7), ("right", "bottom", x - r * .7, y + r * .7),
                   ("left", "top", x + r * .7, y - r * .7), ("right", "top", x - r * .7, y - r * .7)]
        best = None
        for ha, va, tx, ty in options:
            left = tx - width / 2 if ha == "center" else (tx if ha == "left" else tx - width)
            low = ty - LABEL_KM if va == "top" else (ty - LABEL_KM / 2 if va == "center" else ty)
            box = (left, low, left + width, low + LABEL_KM)
            cost = sum(_overlap(box, other) for other in placed) + sum(_overlap(box, d) for d in dots)
            if best is None or cost < best[0]:
                best = (cost, ha, va, tx, ty, box)
            if cost == 0:
                break
        placed.append(best[5])
        spots[name] = best[1:5]
    return spots


def _view_limits(pos):
    x0, y0 = project(VIEW[2], VIEW[0])
    x1, y1 = project(VIEW[3], VIEW[1])
    for x, y in pos.values():  # a university outside the UK widens the view
        x0, x1 = min(x0, x - 40), max(x1, x + 40)
        y0, y1 = min(y0, y - 40), max(y1, y + 40)
    return x0, x1, y0, y1


def _draw_map(graph, pos, ax, colors, highlight):
    ax.set_facecolor(SEA)
    for nation, rings in outline().items():
        face = ABROAD if nation == "ireland" else LAND
        for ring in rings:
            ax.add_patch(Polygon(ring, closed=True, facecolor=face, edgecolor=COAST,
                                 linewidth=0.7, zorder=0))
    nx.draw_networkx_edges(graph, pos, ax=ax, edge_color="#7d8c88", width=0.9, alpha=0.85)
    if highlight:
        nx.draw_networkx_edges(graph, pos, ax=ax, edgelist=highlight, edge_color="red", width=2.8)

    plain = [c == BASE_COLOR for c in colors]
    nodes = nx.draw_networkx_nodes(
        graph, pos, ax=ax, node_color=[MAP_NODE if p else c for c, p in zip(colors, plain)],
        node_size=[55 if p else 120 for p in plain], edgecolors="white", linewidths=1.2)
    nodes.set_zorder(4)

    halo = [effects.withStroke(linewidth=2.4, foreground="white")]
    for name, (ha, va, x, y) in _label_spots(pos).items():
        ax.text(x, y, name, ha=ha, va=va, fontsize=7.5, color=LABEL_COLOR, zorder=5,
                path_effects=halo)

    if graph.number_of_edges() <= MANY_EDGES:
        shown = list(graph.edges)
    else:
        shown = [e for e in highlight if graph.has_edge(*e)]
    labels = {e: graph.edges[e]["weight"] for e in shown}
    if labels:
        texts = nx.draw_networkx_edge_labels(
            graph, pos, ax=ax, edge_labels=labels, font_size=6.5, rotate=False,
            bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.85))
        for text in texts.values():
            text.set_zorder(4.5)  # under the university names

    x0, x1, y0, y1 = _view_limits(pos)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xticks([])
    ax.set_yticks([])
    for side in ax.spines.values():
        side.set_visible(False)
    ax.figure.subplots_adjust(left=0.02, right=0.98, top=0.93, bottom=0.02)


def _draw_plain(graph, pos, ax, colors):
    nx.draw(graph, pos, ax=ax, with_labels=True, node_color=colors,
            node_size=1200, font_size=10)
    nx.draw_networkx_edge_labels(
        graph, pos, ax=ax, edge_labels=nx.get_edge_attributes(graph, "weight")
    )


def draw_graph(graph, title="Graph", node_colors=None, highlight_edges=None, show=True,
               fig=None, positions=None):
    colors = node_colors or [BASE_COLOR] * graph.number_of_nodes()
    highlight = list(highlight_edges or [])
    map_pos = _map_positions(graph, positions)
    fig, ax = _axes(fig)
    if map_pos is not None:
        _draw_map(graph, map_pos, ax, colors, highlight)
    else:
        pos = _layout(graph)
        _draw_plain(graph, pos, ax, colors)
        if highlight:
            nx.draw_networkx_edges(graph, pos, ax=ax, edgelist=highlight,
                                   edge_color="red", width=3)
    return _finish(fig, title, show)


def draw_mst(graph, mst, title="Minimum Spanning Tree", show=True, fig=None, positions=None):
    return draw_graph(graph, title, highlight_edges=mst.edges, show=show, fig=fig,
                      positions=positions)


def path_colors(graph, path):
    colors = []
    for node in graph.nodes:
        if path and node == path[0]:
            colors.append("green")
        elif path and node == path[-1]:
            colors.append("red")
        elif node in path:
            colors.append("blue")
        else:
            colors.append(BASE_COLOR)
    return colors


def draw_path(graph, path, title, show=True, fig=None, positions=None):
    edges = list(zip(path[:-1], path[1:]))
    return draw_graph(graph, title, node_colors=path_colors(graph, path),
                      highlight_edges=edges, show=show, fig=fig, positions=positions)


def draw_route(graph, route, stops, title, show=True, fig=None, positions=None):
    colors = ["purple" if n in stops else BASE_COLOR for n in graph.nodes]
    edges = list(zip(route[:-1], route[1:]))
    return draw_graph(graph, title, node_colors=colors, highlight_edges=edges, show=show,
                      fig=fig, positions=positions)


def draw_regions(graph, region_of, title, show=True, fig=None, positions=None):
    regions = sorted({region_of(n) for n in graph.nodes})
    palette = {r: REGION_PALETTE[i % len(REGION_PALETTE)] for i, r in enumerate(regions)}
    colors = [palette[region_of(n)] for n in graph.nodes]
    fig = draw_graph(graph, title, node_colors=colors, show=False, fig=fig, positions=positions)
    keys = [Line2D([], [], marker="o", linestyle="", color=palette[r], label=r, markersize=8)
            for r in regions]
    fig.legend(handles=keys, loc="center left", fontsize=8, frameon=False, title="Regions")
    if show:
        plt.show()
    return fig


def animate_path(graph, path, title, interval=50, steps_per_edge=25, show=True, fig=None,
                 positions=None):
    # the caller has to keep the returned animation alive or it stops
    if len(path) < 2:
        return None

    map_pos = _map_positions(graph, positions)
    fig, ax = _axes(fig)
    edges = list(zip(path[:-1], path[1:]))
    if map_pos is not None:
        pos = map_pos
        _draw_map(graph, pos, ax, path_colors(graph, path), edges)
    else:
        pos = _layout(graph)
        _draw_plain(graph, pos, ax, path_colors(graph, path))
        nx.draw_networkx_edges(graph, pos, ax=ax, edgelist=edges, edge_color="red", width=2)

    points = []
    for u, v in edges:
        start, end = np.array(pos[u]), np.array(pos[v])
        for t in np.linspace(0, 1, steps_per_edge):
            points.append((1 - t) * start + t * end)

    (dot,) = ax.plot([], [], "ro", markersize=9 if map_pos is not None else 12, zorder=8)

    def update(i):
        dot.set_data([points[i][0]], [points[i][1]])
        return (dot,)

    ani = animation.FuncAnimation(fig, update, frames=len(points),
                                  interval=interval, repeat=False, blit=False)
    _finish(fig, title, show)
    return ani
