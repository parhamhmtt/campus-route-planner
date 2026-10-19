import json

import pytest
from matplotlib.figure import Figure

from sample import small_graph
from campus_route_planner.planner import Planner
from campus_route_planner.reservation_system import ReservationSystem


@pytest.fixture
def planner():
    return Planner(small_graph(), ReservationSystem(), figure=Figure(), save_path=None)


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
    plain = Planner(small_graph(), ReservationSystem(), save_path=None)
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
    planner = Planner(small_graph(), ReservationSystem(), figure=Figure(), save_path=path,
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


# the UK map

from campus_route_planner import planner as planner_module  # noqa: E402
from campus_route_planner.graph_data import UniversityGraph  # noqa: E402
from campus_route_planner.uk_data import ROUTES  # noqa: E402
from campus_route_planner.visualizer import project  # noqa: E402


@pytest.fixture
def uk():
    return Planner(UniversityGraph(), ReservationSystem(), figure=Figure(), save_path=None)


def km_between(planner, a, b):
    places = planner.uni.get_positions()
    return ((project(*places[a])[0] - project(*places[b])[0]) ** 2
            + (project(*places[a])[1] - project(*places[b])[1]) ** 2) ** 0.5


def test_a_new_university_goes_next_to_its_links(uk):
    uk.add_university("Plymouth", "South West", [("Exeter", 75)])
    assert "Plymouth" in uk.uni.get_positions() and "Plymouth" in uk.guessed
    assert km_between(uk, "Plymouth", "Exeter") < 120
    assert all(km_between(uk, "Plymouth", n) > 30 for n in uk.names() if n != "Plymouth")


def test_a_given_position_is_kept_and_checked(uk):
    uk.add_university("Plymouth", "South West", [("Exeter", 75)], position=(50.375, -4.139))
    assert uk.uni.get_positions()["Plymouth"] == (50.375, -4.139)
    assert "Plymouth" not in uk.guessed
    for bad in [(91, 0), (0, 181), (-95, 10), (float("nan"), 0), (0, float("inf"))]:
        with pytest.raises(ValueError, match="Latitude"):
            uk.add_university("Nope", "", [], position=bad)
    assert "Nope" not in uk.names()


def test_a_network_without_coordinates_stays_without(planner):
    planner.add_university("Foo", "", [("Tehran", 4)])
    assert planner.uni.get_positions() == {} and planner.guessed == set()


def test_an_unlinked_university_moves_next_to_the_neighbour_it_gets(uk):
    uk.add_university("Foo", "", [])
    middle = uk.uni.get_positions()["Foo"]
    uk.connect_cheapest("Foo", {"Aberdeen": 100, "Exeter": 300})
    assert uk.uni.get_positions()["Foo"] != middle
    assert km_between(uk, "Foo", "Aberdeen") < 120

    uk.add_university("Bar", "", [], position=(52.0, -1.0))
    uk.connect_cheapest("Bar", {"Aberdeen": 100})
    assert uk.uni.get_positions()["Bar"] == (52.0, -1.0)  # we never move what the user placed


def test_guessed_places_never_pile_up(uk):
    for i in range(15):
        uk.add_university(f"New{i}", "", [])
    new = [f"New{i}" for i in range(15)]
    for i, a in enumerate(new):
        for b in new[i + 1:] + [n for n in uk.names() if n not in new]:
            assert km_between(uk, a, b) > 25, (a, b)


def test_undo_brings_positions_back(uk):
    before = dict(uk.uni.get_positions())
    uk.add_university("Plymouth", "", [("Exeter", 75)])
    uk.undo()
    assert uk.uni.get_positions() == before and uk.guessed == set()
    uk.remove("Bath")
    assert "Bath" not in uk.uni.get_positions()
    uk.undo()
    assert uk.uni.get_positions() == before


def test_start_over_restores_the_sample_and_can_be_undone(tmp_path):
    path = tmp_path / "graph.json"
    uk = Planner(UniversityGraph(), ReservationSystem(), figure=Figure(), save_path=path)
    uk.remove("Bath")
    uk.add_university("Plymouth", "", [("Exeter", 75)])
    uk.set_capacity("Bristol", "Cardiff", 2)
    uk.reserve("Bristol", "Cardiff", "Sara", 1)

    text = uk.reset_to_sample()
    assert text == f"Back to the sample network, 27 universities, {len(ROUTES)} routes."
    assert "Bath" in uk.names() and "Plymouth" not in uk.names()
    assert uk.reservations.routes == {} and uk.guessed == set()
    saved = UniversityGraph([("X", "r")], [])
    saved.load(path)
    assert "Bath" in saved.get_graph() and "Plymouth" not in saved.get_graph()

    uk.undo()
    assert "Plymouth" in uk.names() and "Bath" not in uk.names()
    assert uk.reservations.routes


def test_a_big_distance_table_is_summarised(uk):
    lines = uk.distance_table().splitlines()
    assert lines[0] == "27 universities, the full table is on the map."
    assert lines[1].startswith("Farthest apart: Exeter and Aberdeen (")
    assert lines[2] == "Closest: Bath and Bristol (26)."
    import networkx as nx
    longest = max(max(d.values()) for _, d in nx.all_pairs_dijkstra_path_length(uk.graph))
    assert f"({longest})" in lines[1]
    uk.add_university("Island", "", [], position=(52.0, -4.0))
    assert uk.distance_table().splitlines()[-1] == "27 pairs cannot reach each other."


def test_a_small_table_is_still_printed(planner):
    assert len(planner.distance_table().splitlines()) == 7


def test_the_map_is_drawn_when_there_are_positions(uk, planner):
    from matplotlib.patches import Polygon
    uk.show_network()
    assert any(isinstance(p, Polygon) for p in uk.figure.axes[0].patches)
    planner.show_network()
    assert not any(isinstance(p, Polygon) for p in planner.figure.axes[0].patches)


def test_long_journeys_get_shorter_animations(uk, monkeypatch):
    seen = []
    monkeypatch.setattr(planner_module, "animate_path",
                        lambda graph, path, title, **options: seen.append((len(path) - 1, options["steps_per_edge"])))
    uk.shortest_path("Exeter", "Aberdeen", animate=True)
    uk.shortest_path("Bath", "Bristol", animate=True)
    chain = [(f"U{i}", "r", 50 + i * 0.1, -1.0) for i in range(40)]
    line = Planner(UniversityGraph(chain, [(f"U{i}", f"U{i + 1}", 5) for i in range(39)]),
                   ReservationSystem(), figure=Figure(), save_path=None)
    line.shortest_path("U0", "U39", animate=True)
    assert seen == [(9, 24), (1, 25), (39, 6)]
