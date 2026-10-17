import json

import pytest
from matplotlib.figure import Figure

from campus_route_planner.graph_data import UniversityGraph
from campus_route_planner.planner import Planner
from campus_route_planner.reservation_system import ReservationSystem


@pytest.fixture
def planner():
    return Planner(UniversityGraph(), ReservationSystem(), figure=Figure(), save_path=None)


def test_questions_return_text_and_draw(planner):
    drawn = []
    planner.on_draw = lambda: drawn.append(planner.figure.get_suptitle())
    assert "distance 8" in planner.shortest_path("Sharif", "Beheshti")
    assert "total cost 13" in planner.trip(["Sharif", "Kharazmi", "Beheshti"])
    assert "Total weight 15" in planner.spanning_tree()
    assert "Region-based MST" in planner.region_tree()
    assert planner.distance_table().splitlines()[1].split()[:2] == ["Sharif", "0"]
    assert drawn == [
        "Shortest path from Sharif to Beheshti (distance 8)",
        "TSP route: Beheshti -> Kharazmi -> Sharif (cost 13)",
        "Minimum spanning tree (red)",
        "Region-based MST",
        "",  # the heatmap sets an axes title, not a figure title
    ]


def test_nothing_is_drawn_without_a_figure():
    plain = Planner(UniversityGraph(), ReservationSystem(), save_path=None)
    assert "distance 8" in plain.shortest_path("Sharif", "Beheshti")
    assert "Total weight 15" in plain.spanning_tree()
    assert plain.show_network() == "6 universities, 6 routes."


def test_bad_names_and_choices(planner):
    with pytest.raises(ValueError, match="not found"):
        planner.shortest_path("Sharif", "Oxford")
    with pytest.raises(ValueError, match="two different"):
        planner.shortest_path("Sharif", "Sharif")
    with pytest.raises(ValueError, match="at least two"):
        planner.trip(["Sharif"])
    for i in range(10):
        planner.add_university(f"Extra{i}", "", [])
    assert len(planner.names()) == 16
    with pytest.raises(ValueError, match="At most 15"):
        planner.trip(planner.names())


def test_unreachable_and_empty(planner):
    planner.add_university("Island", "", [])
    assert "no route from Sharif to Island" in planner.shortest_path("Sharif", "Island")
    assert "No route connects" in planner.trip(["Sharif", "Island"])
    for name in planner.names():
        planner.remove(name)
    for action in (planner.spanning_tree, planner.region_tree, planner.distance_table):
        with pytest.raises(ValueError, match="no universities"):
            action()
    assert planner.list_all() == "There are no universities."
    assert planner.show_network() == "0 universities, 0 routes."


def test_add_university_is_all_or_nothing(planner):
    before = (set(planner.graph.nodes), set(planner.graph.edges))
    bad_links = [
        [("Tehran", 5), ("Oxford", 2)],
        [("Tehran", 5), ("Tehran", 6)],
        [("Tehran", 0)],
        [("Tehran", -1)],
        [("Tehran", float("nan"))],
        [("Tehran", float("inf"))],
    ]
    for links in bad_links:
        with pytest.raises(ValueError):
            planner.add_university("Foo", "", links)
    for name in ("", "  ", "Sharif", "sharif", "x" * 100):
        with pytest.raises(ValueError):
            planner.add_university(name, "", [])
    assert (set(planner.graph.nodes), set(planner.graph.edges)) == before


def test_whole_weights_stay_whole(planner):
    planner.add_university("Allameh", "west", [("Tehran", 5.0), ("Sharif", 2.5)])
    assert planner.graph["Allameh"]["Tehran"]["weight"] == 5
    assert isinstance(planner.graph["Allameh"]["Tehran"]["weight"], int)
    assert planner.graph["Allameh"]["Sharif"]["weight"] == 2.5
    assert planner.uni.get_regions()["Allameh"] == "west"
    planner.connect("Allameh", "Kharazmi", 7.0)
    assert isinstance(planner.graph["Allameh"]["Kharazmi"]["weight"], int)
    assert "Changed Kharazmi - Allameh from 7 to 3" in planner.connect("Kharazmi", "Allameh", 3)


def test_connect_cheapest(planner):
    planner.add_university("Foo", "", [])
    text = planner.connect_cheapest("Foo", {"Tehran": 4, "Sharif": 2.5, "Beheshti": 9})
    assert text == "Connected Foo to Sharif with weight 2.5."
    assert list(planner.graph["Foo"]) == ["Sharif"]
    planner.add_university("Bar", "", [])
    with pytest.raises(ValueError, match="at least one"):
        planner.connect_cheapest("Bar", {})
    with pytest.raises(ValueError):
        planner.connect_cheapest("Bar", {"Tehran": -1})
    with pytest.raises(ValueError, match="not found"):
        planner.connect_cheapest("Bar", {"Oxford": 1})
    assert list(planner.graph["Bar"]) == []


def test_changes_are_saved_and_announced(tmp_path):
    path = tmp_path / "graph.json"
    changes, drawings = [], []
    planner = Planner(UniversityGraph(), ReservationSystem(), figure=Figure(), save_path=path,
                      on_draw=lambda: drawings.append(1), on_change=lambda: changes.append(1))
    planner.add_university("Allameh", "West", [("Tehran", 5)])
    planner.connect("Allameh", "Sharif", 9)
    planner.remove("Allameh")
    assert len(changes) == 3 and len(drawings) == 3
    names = [n["name"] for n in json.loads(path.read_text())["nodes"]]
    assert "Allameh" not in names and len(names) == 6


def test_removing_clears_reservations_and_the_animation(planner):
    planner.set_capacity("Sharif", "Tehran", 2)
    planner.shortest_path("Sharif", "Beheshti", animate=True)
    assert planner.animation is not None
    planner.remove("Tehran")
    assert planner.reservations.routes == {}
    assert planner.animation is None


def test_seats(planner):
    with pytest.raises(ValueError, match="no direct route"):
        planner.set_capacity("Sharif", "Beheshti", 2)
    with pytest.raises(ValueError, match="two different"):
        planner.seat_report("Sharif", "Sharif")
    with pytest.raises(ValueError, match="negative"):
        planner.set_capacity("Sharif", "Tehran", -1)
    with pytest.raises(ValueError, match="whole"):
        planner.set_capacity("Sharif", "Tehran", 1.5)
    assert "No capacity" in planner.seat_report("Sharif", "Tehran")
    planner.set_capacity("Sharif", "Tehran", 1)
    assert "Sara now has a seat" in planner.reserve("Sharif", "Tehran", " Sara ", 1)
    assert "full" in planner.reserve("Tehran", "Sharif", "Reza", 0).lower()
    assert "already has a seat" in planner.reserve("Sharif", "Tehran", "Sara", 1)
    with pytest.raises(ValueError, match="name"):
        planner.reserve("Sharif", "Tehran", "  ", 1)
    assert planner.seat_report("Sharif", "Tehran").splitlines() == [
        "Sharif - Tehran: 1 of 1 seat taken.", "  Sara (priority 1)"]
