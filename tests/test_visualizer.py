import matplotlib.pyplot as plt

from campus_route_planner.distance_matrix import plot_distance_matrix
from campus_route_planner.graph_data import UniversityGraph
from campus_route_planner.mst import compute_mst
from campus_route_planner.visualizer import animate_path, draw_graph, draw_mst, draw_path


def test_drawing_functions_run_headless():
    graph = UniversityGraph().get_graph()
    draw_graph(graph, "all", show=False)
    draw_mst(graph, compute_mst(graph), show=False)
    draw_path(graph, ["Sharif", "Tehran"], "path", show=False)
    plot_distance_matrix(graph, list(graph.nodes), show=False)
    anim = animate_path(graph, ["Sharif", "Tehran"], "anim", show=False)
    assert anim is not None
    assert animate_path(graph, [], "empty", show=False) is None
    plt.close("all")
