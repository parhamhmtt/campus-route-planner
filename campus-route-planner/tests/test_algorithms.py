import itertools

import networkx as nx
import pytest

from campus_route_planner.distance_matrix import build_distance_matrix
from campus_route_planner.graph_data import UniversityGraph
from campus_route_planner.mst import compute_mst
from campus_route_planner.scalable_graph import ScalableGraph
from campus_route_planner.shortest_path import find_shortest_path
from campus_route_planner.tsp_solver import expand_route, tsp_dp


@pytest.fixture
def uni():
    return UniversityGraph()


def total_weight(graph):
    return sum(d["weight"] for _, _, d in graph.edges(data=True))


def test_mst_matches_networkx(uni):
    graph = uni.get_graph()
    mst = compute_mst(graph)
    expected = nx.minimum_spanning_tree(graph)
    assert total_weight(mst) == total_weight(expected)
    assert mst.number_of_edges() == graph.number_of_nodes() - 1


def test_mst_empty_and_disconnected():
    assert compute_mst(nx.Graph()).number_of_nodes() == 0
    g = nx.Graph()
    g.add_edge("A", "B", weight=1)
    g.add_node("C")
    mst = compute_mst(g)
    assert set(mst.nodes) == {"A", "B", "C"}
    assert mst.number_of_edges() == 1


def test_shortest_path(uni):
    dist, path = find_shortest_path(uni.get_graph(), "Sharif", "Beheshti")
    assert dist == 8
    assert path[0] == "Sharif" and path[-1] == "Beheshti"


def test_shortest_path_unreachable_and_unknown(uni):
    uni.add_university("Island")
    assert find_shortest_path(uni.get_graph(), "Sharif", "Island") == (float("inf"), [])
    with pytest.raises(ValueError):
        find_shortest_path(uni.get_graph(), "Sharif", "Nowhere")


def test_distance_matrix_symmetric(uni):
    nodes = list(uni.get_graph().nodes)
    m = build_distance_matrix(uni.get_graph(), nodes)
    for i, j in itertools.product(range(len(nodes)), repeat=2):
        assert m[i][j] == m[j][i]
    assert all(m[i][i] == 0 for i in range(len(nodes)))


def test_tsp_matches_brute_force(uni):
    graph = uni.get_graph()
    cities = ["Sharif", "Beheshti", "Kharazmi", "Tehran"]
    cost, order = tsp_dp(graph, cities)
    m = {a: {b: find_shortest_path(graph, a, b)[0] for b in cities} for a in cities}
    brute = min(
        sum(m[a][b] for a, b in zip(p, p[1:])) for p in itertools.permutations(cities)
    )
    assert cost == brute
    assert sorted(order) == sorted(cities)


def test_tsp_edge_cases(uni):
    graph = uni.get_graph()
    assert tsp_dp(graph, []) == (0, [])
    assert tsp_dp(graph, ["Sharif"]) == (0, ["Sharif"])
    with pytest.raises(ValueError):
        tsp_dp(graph, ["Sharif", "Nowhere"])
    uni.add_university("Island")
    assert tsp_dp(graph, ["Sharif", "Island"]) == (float("inf"), [])


def test_expand_route_is_connected(uni):
    graph = uni.get_graph()
    _, order = tsp_dp(graph, ["Sharif", "Beheshti", "Kharazmi"])
    route = expand_route(graph, order)
    assert all(graph.has_edge(a, b) for a, b in zip(route, route[1:]))


def test_scalable_graph_connects_regions(uni):
    final = ScalableGraph(uni.get_graph(), uni.get_regions()).build()
    assert set(final.nodes) == set(uni.get_graph().nodes)
    assert nx.is_connected(final)
    assert final.number_of_edges() == final.number_of_nodes() - 1


def test_scalable_graph_unassigned_nodes(uni):
    uni.add_university("Newcomer")
    uni.add_connection("Newcomer", "Sharif", 2)
    final = ScalableGraph(uni.get_graph(), uni.get_regions()).build()
    assert final.has_edge("Newcomer", "Sharif")
