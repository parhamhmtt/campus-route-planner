import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np

INF = float("inf")


def build_distance_matrix(graph, node_list):
    lengths = dict(nx.all_pairs_dijkstra_path_length(graph, weight="weight"))
    return [[lengths[a].get(b, INF) for b in node_list] for a in node_list]


def plot_distance_matrix(graph, node_list, show=True, fig=None):
    matrix = np.array(build_distance_matrix(graph, node_list), dtype=float)
    finite = matrix[np.isfinite(matrix)]
    max_val = finite.max() if finite.size else 1
    display = np.where(np.isfinite(matrix), matrix, max_val * 1.1)

    if fig is None:
        fig, ax = plt.subplots(figsize=(8, 6))
    else:
        fig.clear()
        ax = fig.add_subplot()
    norm = mcolors.Normalize(vmin=0, vmax=max_val * 1.1)
    image = ax.imshow(display, cmap=plt.cm.Blues, norm=norm)

    
    size = len(node_list)
    cell_font = min(10, max(4.5, 14 - 0.35 * size))
    tick_font = min(10, max(6, 13 - 0.25 * size))
    ticks = np.arange(size)
    ax.set_xticks(ticks)
    ax.set_yticks(ticks)
    ax.set_xticklabels(node_list, rotation=45, ha="right", fontsize=tick_font)
    ax.set_yticklabels(node_list, fontsize=tick_font)
    ax.set_xticks(ticks - 0.5, minor=True)
    ax.set_yticks(ticks - 0.5, minor=True)
    ax.grid(which="minor", color="black", linewidth=1 if size <= 12 else 0.4)
    ax.tick_params(which="minor", length=0)

    for i in range(len(node_list)):
        for j in range(len(node_list)):
            value = matrix[i][j]
            label = "∞" if value == INF else f"{value:g}"
            dark = display[i][j] > 0.6 * max_val * 1.1  
            ax.text(j, i, label, ha="center", va="center", fontsize=cell_font,
                    color="white" if dark else "black")

    ax.set_title("Shortest Path Distance Matrix")
    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04, label="Distance")
    fig.tight_layout()
    if show:
        plt.show()
    return fig
