import matplotlib.animation as animation
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np

LAYOUT_SEED = 42
BASE_COLOR = "skyblue"
REGION_PALETTE = ["#4c9be8", "#f2a541", "#6bbf59", "#c77dd6", "#e8645a", "#8d8d8d"]


def _layout(graph):
    return nx.spring_layout(graph, seed=LAYOUT_SEED)


def _finish(fig, title, show):
    fig.suptitle(title, fontsize=10, fontweight="bold")
    if show:
        plt.show()
    return fig


def draw_graph(graph, title="Graph", node_colors=None, highlight_edges=None, show=True):
    """Draw the graph with edge weights; optionally colour nodes and highlight edges."""
    pos = _layout(graph)
    fig, ax = plt.subplots()
    colors = node_colors or [BASE_COLOR] * graph.number_of_nodes()
    nx.draw(graph, pos, ax=ax, with_labels=True, node_color=colors,
            node_size=1200, font_size=10)
    nx.draw_networkx_edge_labels(
        graph, pos, ax=ax, edge_labels=nx.get_edge_attributes(graph, "weight")
    )
    if highlight_edges:
        nx.draw_networkx_edges(graph, pos, ax=ax, edgelist=list(highlight_edges),
                               edge_color="red", width=3)
    return _finish(fig, title, show)


def draw_mst(graph, mst, title="Minimum Spanning Tree", show=True):
    """Original graph with the MST edges drawn in red."""
    return draw_graph(graph, title, highlight_edges=mst.edges, show=show)


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


def draw_path(graph, path, title, show=True):
    edges = list(zip(path[:-1], path[1:]))
    return draw_graph(graph, title, node_colors=path_colors(graph, path),
                      highlight_edges=edges, show=show)


def draw_route(graph, route, stops, title, show=True):
    """Draw a multi-stop route; the stops are purple and the route edges red."""
    colors = ["purple" if n in stops else BASE_COLOR for n in graph.nodes]
    edges = list(zip(route[:-1], route[1:]))
    return draw_graph(graph, title, node_colors=colors, highlight_edges=edges, show=show)


def draw_regions(graph, region_of, title, show=True):
    regions = sorted({region_of(n) for n in graph.nodes})
    palette = {r: REGION_PALETTE[i % len(REGION_PALETTE)] for i, r in enumerate(regions)}
    colors = [palette[region_of(n)] for n in graph.nodes]
    return draw_graph(graph, title, node_colors=colors, show=show)


def animate_path(graph, path, title, interval=50, steps_per_edge=25, show=True):
    """Animate a dot travelling along the path. Keep the returned object alive."""
    if len(path) < 2:
        return None

    pos = _layout(graph)
    fig, ax = plt.subplots()
    edges = list(zip(path[:-1], path[1:]))
    nx.draw(graph, pos, ax=ax, with_labels=True, node_color=path_colors(graph, path),
            node_size=1200, font_size=10)
    nx.draw_networkx_edge_labels(
        graph, pos, ax=ax, edge_labels=nx.get_edge_attributes(graph, "weight")
    )
    nx.draw_networkx_edges(graph, pos, ax=ax, edgelist=edges, edge_color="red", width=2)

    points = []
    for u, v in edges:
        start, end = np.array(pos[u]), np.array(pos[v])
        for t in np.linspace(0, 1, steps_per_edge):
            points.append((1 - t) * start + t * end)

    (dot,) = ax.plot([], [], "ro", markersize=12)

    def update(i):
        dot.set_data([points[i][0]], [points[i][1]])
        return (dot,)

    ani = animation.FuncAnimation(fig, update, frames=len(points),
                                  interval=interval, repeat=False, blit=False)
    _finish(fig, title, show)
    return ani
