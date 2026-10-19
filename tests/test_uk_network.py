import json
import math
from itertools import combinations
from pathlib import Path

import networkx as nx
import numpy as np
import pytest
from matplotlib.figure import Figure
from matplotlib.patches import Polygon
from matplotlib.path import Path as MPath

from campus_route_planner import visualizer
from campus_route_planner.graph_data import UniversityGraph
from campus_route_planner.uk_data import ROUTES, UNIVERSITIES
from campus_route_planner.visualizer import (CHAR_KM, LABEL_KM, VIEW, _label_spots, _overlap,
                                             _view_limits, draw_graph, draw_path, draw_regions,
                                             outline, project)

PLACES = {name: (lat, lon) for name, _, lat, lon in UNIVERSITIES}
KM = {name: project(lat, lon) for name, (lat, lon) in PLACES.items()}


def haversine(a, b):
    (la1, lo1), (la2, lo2) = PLACES[a], PLACES[b]
    p1, p2 = math.radians(la1), math.radians(la2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


@pytest.fixture(scope="module")
def uk():
    return UniversityGraph()


# the data

def test_the_default_network_is_the_uk(uk):
    graph = uk.get_graph()
    assert graph.number_of_nodes() == 27 >= 20
    assert graph.number_of_edges() == len(ROUTES)
    assert set(uk.get_positions()) == set(graph.nodes) == set(PLACES)
    assert nx.is_connected(graph)


def test_every_university_is_inside_the_uk(uk):
    west, east, south, north = VIEW
    for name, (lat, lon) in uk.get_positions().items():
        assert south < lat < north and west < lon < east, name


def test_regions(uk):
    regions = uk.get_regions()
    assert set(regions.values()) == {"Scotland", "North England", "Midlands", "East", "South East",
                                     "South West", "Wales", "Northern Ireland"}
    for region in set(regions.values()):
        assert list(regions.values()).count(region) >= 1
    assert regions["Edinburgh"] == "Scotland" and regions["Cardiff"] == "Wales"


def test_names_are_clean_and_distinct():
    names = [u[0] for u in UNIVERSITIES]
    assert len(names) == len(set(names))
    squashed = {"".join(c for c in n.lower() if c.isalnum()) for n in names}
    assert len(squashed) == len(names)
    assert all("," not in n and len(n) <= 20 for n in names)


def test_no_two_universities_on_top_of_each_other():
    for a, b in combinations(PLACES, 2):
        assert haversine(a, b) > 15, (a, b)


def test_weights_are_road_distances_in_km():
    for a, b, weight in ROUTES:
        assert isinstance(weight, int) and weight > 0
        assert abs(weight - 1.25 * haversine(a, b)) <= 1, (a, b, weight)


def test_routes_are_listed_once_and_use_known_names():
    pairs = [frozenset(r[:2]) for r in ROUTES]
    assert len(pairs) == len(set(pairs))
    assert all(a in PLACES and b in PLACES and a != b for a, b, _ in ROUTES)


def cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def test_no_two_routes_cross_each_other():
    for (a, b, _), (c, d, _) in combinations(ROUTES, 2):
        if {a, b} & {c, d}:
            continue
        p, q, r, s = KM[a], KM[b], KM[c], KM[d]
        straddle = cross(p, q, r) * cross(p, q, s) < 0 and cross(r, s, p) * cross(r, s, q) < 0
        assert not straddle, f"{a}-{b} crosses {c}-{d}"


def test_only_ferries_and_estuary_bridges_cross_open_water():
    land = [MPath(np.array(ring)) for nation, rings in outline().items() if nation != "ireland"
            for ring in rings]
    allowed = {frozenset(p) for p in [("Liverpool", "Belfast"), ("Belfast", "Glasgow"),
                                      ("Bristol", "Cardiff"), ("Edinburgh", "St Andrews")]}
    for a, b, _ in ROUTES:
        t = np.linspace(0.04, 0.96, 80)[:, None]
        points = (1 - t) * np.array(KM[a]) + t * np.array(KM[b])
        on_land = np.zeros(len(points), bool)
        for polygon in land:
            on_land |= polygon.contains_points(points)
        over_water = 1 - on_land.mean()
        if frozenset((a, b)) not in allowed:
            assert over_water < 0.35, f"{a}-{b} is {over_water:.0%} over water"


def test_the_sample_can_be_reloaded(uk):
    other = UniversityGraph()
    other.add_university("Extra", "East", (52.0, 0.0))
    other.remove_university("Bath")
    other.load_sample()
    assert set(other.get_graph().nodes) == set(PLACES)
    assert "Extra" not in other.get_positions() and "Bath" in other.get_positions()


def test_positions_survive_saving_and_loading(tmp_path, uk):
    path = tmp_path / "graph.json"
    uk.save(path)
    saved = json.loads(path.read_text())
    assert saved["nodes"][0] == {"name": "Exeter", "region": "South West", "lat": 50.7366, "lon": -3.5344}
    fresh = UniversityGraph([("X", "r")], [])
    assert fresh.load(path)
    assert fresh.get_positions() == uk.get_positions()
    assert fresh.get_graph().number_of_edges() == len(ROUTES)


def test_an_old_save_file_without_positions_still_loads(tmp_path):
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"nodes": [{"name": "A", "region": "r"}, {"name": "B"}],
                                "edges": [["A", "B", 3]]}))
    uni = UniversityGraph()
    assert uni.load(path)
    assert uni.get_positions() == {} and list(uni.get_graph().nodes) == ["A", "B"]


def test_custom_networks_do_not_get_the_uk_sample():
    uni = UniversityGraph([("A", "r"), ("B", "r", 51.0, -1.0)], [("A", "B", 5)])
    assert list(uni.get_graph().nodes) == ["A", "B"]
    assert uni.get_positions() == {"B": (51.0, -1.0)}


# the coastline

def test_the_outline_file():
    raw = json.loads(Path(visualizer.__file__).with_name("uk_outline.json").read_text())
    assert set(raw) == {"england", "scotland", "wales", "northern_ireland", "ireland"}
    for rings in raw.values():
        for ring in rings:
            assert len(ring) >= 4
            assert all(-12 < lon < 3 and 49 < lat < 61 for lon, lat in ring)
    assert len(raw["scotland"]) > 5  # the islands are there


def test_projection():
    assert project(visualizer.LAT0, visualizer.LON0) == (0, 0)
    assert project(visualizer.LAT0 + 1, visualizer.LON0)[1] == pytest.approx(110.57)
    east = project(visualizer.LAT0, visualizer.LON0 + 1)[0]
    assert east == pytest.approx(111.32 * math.cos(math.radians(visualizer.LAT0)))


# drawing on the map

def map_figure(**options):
    uni = UniversityGraph()
    fig = Figure(figsize=(7, 5.4))
    draw_graph(uni.get_graph(), "t", fig=fig, show=False, positions=uni.get_positions(), **options)
    return uni, fig


def texts(fig):
    return [t.get_text() for t in fig.axes[0].texts]


def test_the_map_has_the_coastline_and_every_university():
    uni, fig = map_figure()
    ax = fig.axes[0]
    assert sum(isinstance(p, Polygon) for p in ax.patches) >= 20
    assert ax.get_aspect() in (1.0, "equal")
    assert set(PLACES) <= set(texts(fig))
    assert len(ax.collections) >= 2  # routes and dots


def test_a_busy_map_labels_only_the_highlighted_routes():
    uni, fig = map_figure()
    assert not any(t.isdigit() for t in texts(fig))  # 42 routes: no weights at all
    graph = uni.get_graph()
    path = ["Exeter", "Bristol", "Birmingham"]
    fig = Figure()
    draw_path(graph, path, "t", fig=fig, show=False, positions=uni.get_positions())
    assert sorted(t for t in texts(fig) if t.isdigit()) == sorted(
        str(graph[a][b]["weight"]) for a, b in zip(path, path[1:]))


def test_a_small_map_labels_every_route():
    uni = UniversityGraph([("A", "r", 51.0, -1.0), ("B", "r", 52.0, -1.5), ("C", "r", 53.0, -1.0)],
                          [("A", "B", 7), ("B", "C", 9)])
    fig = Figure()
    draw_graph(uni.get_graph(), "t", fig=fig, show=False, positions=uni.get_positions())
    assert sorted(t for t in texts(fig) if t.isdigit()) == ["7", "9"]


def test_labels_do_not_collide():
    uni = UniversityGraph()
    pos = {n: project(*uni.get_positions()[n]) for n in uni.get_graph().nodes}
    boxes = {}
    for name, (ha, va, x, y) in _label_spots(pos).items():
        width = len(name) * CHAR_KM + 4
        left = x - width / 2 if ha == "center" else (x if ha == "left" else x - width)
        low = y - LABEL_KM if va == "top" else (y - LABEL_KM / 2 if va == "center" else y)
        boxes[name] = (left, low, left + width, low + LABEL_KM)
    assert set(boxes) == set(pos)
    clashes = [(a, b) for a, b in combinations(boxes, 2) if _overlap(boxes[a], boxes[b]) > 0]
    assert clashes == []
    on_dots = [(n, m) for n in boxes for m, (x, y) in pos.items()
               if n != m and _overlap(boxes[n], (x - 13, y - 13, x + 13, y + 13)) > 0]
    assert len(on_dots) <= 4


def test_the_view_covers_the_uk_and_grows_for_far_away_places():
    pos = {n: project(*PLACES[n]) for n in PLACES}
    x0, x1, y0, y1 = _view_limits(pos)
    assert x0 < min(p[0] for p in pos.values()) and y1 > max(p[1] for p in pos.values())
    far = dict(pos, Paris=project(48.85, 2.35))
    assert _view_limits(far)[2] < y0  # Paris is south of the UK view


def test_regions_get_a_legend_with_every_region():
    uni = UniversityGraph()
    fig = Figure()
    draw_regions(uni.get_graph(), lambda n: uni.get_regions()[n], "r", fig=fig, show=False,
                 positions=uni.get_positions())
    legend = fig.legends[0]
    assert sorted(t.get_text() for t in legend.get_texts()) == sorted(set(uni.get_regions().values()))
    # eight regions, eight different colours
    handles = legend.legend_handles
    assert len({h.get_color() for h in handles}) == 8


def test_networks_without_coordinates_still_use_the_spring_layout():
    uni = UniversityGraph([("A", "r"), ("B", "r"), ("C", "r")], [("A", "B", 1), ("B", "C", 2)])
    fig = Figure()
    draw_graph(uni.get_graph(), "t", fig=fig, show=False, positions=uni.get_positions())
    assert not any(isinstance(p, Polygon) for p in fig.axes[0].patches)
    assert {"A", "B", "C", "1", "2"} <= set(texts(fig))  # plain drawing: names and every weight


def test_one_university_missing_its_position_falls_back_for_everyone():
    uni = UniversityGraph()
    uni.add_university("Nowhere", "East")
    fig = Figure()
    draw_graph(uni.get_graph(), "t", fig=fig, show=False, positions=uni.get_positions())
    assert not any(isinstance(p, Polygon) for p in fig.axes[0].patches)


def test_a_long_title_wraps_instead_of_running_off_the_figure():
    uni = UniversityGraph()
    fig = Figure()
    stops = ["Exeter", "Southampton", "Bath", "Bristol", "Cardiff", "Swansea", "Oxford"]
    title = "TSP route: " + " -> ".join(stops) + " (cost 999)"
    draw_graph(uni.get_graph(), title, fig=fig, show=False, positions=uni.get_positions())
    lines = fig.get_suptitle().splitlines()
    assert len(lines) == 2 and all(len(line) <= 70 for line in lines)
    short = "Minimum spanning tree (red)"
    draw_graph(uni.get_graph(), short, fig=fig, show=False, positions=uni.get_positions())
    assert fig.get_suptitle() == short


def test_weights_sit_under_the_university_names():
    uni = UniversityGraph()
    fig = Figure()
    draw_path(uni.get_graph(), ["Exeter", "Bristol", "Birmingham"], "t", fig=fig, show=False,
              positions=uni.get_positions())
    ax = fig.axes[0]
    names = [t.get_zorder() for t in ax.texts if t.get_text() in PLACES]
    weights = [t.get_zorder() for t in ax.texts if t.get_text().isdigit()]
    assert weights and min(names) > max(weights)


def test_the_readme_quotes_the_real_numbers():
    readme = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")
    regions = {u[1] for u in UNIVERSITIES}
    assert f"{len(UNIVERSITIES)} real UK" in readme
    assert f"{len(regions)} regions" in readme
    assert f"There are {len(ROUTES)}" in readme
    for image in __import__("re").findall(r'src="([^"]+)"', readme):
        assert (Path(__file__).parent.parent / image).exists(), image
