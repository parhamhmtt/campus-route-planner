import inspect
import json

import networkx as nx
import pytest

from campus_route_planner.graph_data import UniversityGraph
from campus_route_planner.tools import TOOL_SCHEMAS, TOOLS, PlannerSession


@pytest.fixture
def session(tmp_path):
    return PlannerSession(save_path=tmp_path / "graph.json", output_dir=tmp_path / "out")


def ok(result):
    assert "error" not in result, result
    return result


# ---- schema / dispatch ---------------------------------------------------- #
def test_every_schema_matches_a_method_signature():
    for spec in TOOL_SCHEMAS:
        method = getattr(PlannerSession, spec["name"])
        params = {
            p.name: p for p in inspect.signature(method).parameters.values()
            if p.name != "self"
        }
        schema = spec["input_schema"]
        assert set(schema["properties"]) == set(params), spec["name"]
        required = {n for n, p in params.items() if p.default is inspect.Parameter.empty}
        assert set(schema["required"]) == required, spec["name"]
    assert len(TOOLS) == len(TOOL_SCHEMAS)  # no duplicate names


def test_every_result_is_json_serialisable(session):
    session.call("set_route_capacity", {"university_a": "Sharif", "university_b": "Tehran",
                                        "capacity": 2})
    calls = {
        "list_universities": {},
        "find_shortest_path": {"source": "Sharif", "destination": "Beheshti"},
        "plan_multi_stop_trip": {"stops": ["Sharif", "Kharazmi", "Beheshti"]},
        "get_minimum_spanning_tree": {},
        "get_region_mst": {},
        "get_distance_matrix": {},
        "view_reservations": {"university_a": "Sharif", "university_b": "Tehran"},
    }
    for name, args in calls.items():
        json.dumps(ok(session.call(name, args)), allow_nan=False)


def test_dispatch_never_raises_on_bad_input(session):
    assert "Unknown tool" in session.call("drop_database", {})["error"]
    assert "Missing" in session.call("find_shortest_path", {"source": "Sharif"})["error"]
    assert "Unexpected argument" in session.call("list_universities", {"x": 1})["error"]
    assert "JSON object" in session.call("list_universities", ["nope"])["error"]
    assert "error" in session.call("plan_multi_stop_trip", {"stops": "Sharif"})
    assert "error" in session.call("save_plot", {"kind": "nope"})


# ---- name resolution ------------------------------------------------------ #
def test_names_are_matched_loosely_but_typos_only_suggest(session):
    assert session.resolve("sharif") == "Sharif"
    assert session.resolve("  elm o sanat ") == "Elm-o-Sanat"
    with pytest.raises(ValueError, match="Did you mean: Sharif"):
        session.resolve("Sharfi")
    with pytest.raises(ValueError, match="not found"):
        session.resolve("Oxford")
    with pytest.raises(ValueError):
        session.resolve("")
    with pytest.raises(ValueError):
        session.resolve(None)


# ---- algorithms through the tools ---------------------------------------- #
def test_shortest_path(session):
    result = ok(session.call("find_shortest_path",
                             {"source": "sharif", "destination": "BEHESHTI"}))
    assert result["reachable"]
    assert result["distance"] == 8
    assert result["path"] == ["Sharif", "Tehran", "Elm-o-Sanat", "Beheshti"]
    same = ok(session.call("find_shortest_path", {"source": "Sharif", "destination": "Sharif"}))
    assert same["distance"] == 0 and same["path"] == ["Sharif"]


def test_unreachable_is_reported_not_raised(session):
    ok(session.call("add_university", {"name": "Island"}))
    result = ok(session.call("find_shortest_path",
                             {"source": "Sharif", "destination": "Island"}))
    assert result["reachable"] is False
    trip = ok(session.call("plan_multi_stop_trip", {"stops": ["Sharif", "Island"]}))
    assert trip["possible"] is False
    matrix = ok(session.call("get_distance_matrix"))
    i, j = matrix["universities"].index("Sharif"), matrix["universities"].index("Island")
    assert matrix["matrix"][i][j] is None


def test_trip_plan(session):
    result = ok(session.call("plan_multi_stop_trip",
                             {"stops": ["Sharif", "Kharazmi", "Beheshti", "sharif"]}))
    assert result["possible"]
    assert sorted(result["visit_order"]) == ["Beheshti", "Kharazmi", "Sharif"]  # deduped
    assert result["full_route"][0] == result["visit_order"][0]
    assert result["full_route"][-1] == result["visit_order"][-1]
    # the full route must really be a walk in the graph with the claimed cost
    graph = session.uni.get_graph()
    route = result["full_route"]
    cost = sum(graph[a][b]["weight"] for a, b in zip(route, route[1:]))
    assert cost == result["total_cost"]

    assert "at least two" in session.call("plan_multi_stop_trip", {"stops": ["Sharif"]})["error"]
    too_many = [f"U{i}" for i in range(16)]
    assert "error" in session.call("plan_multi_stop_trip", {"stops": too_many})


def test_mst_and_region_mst(session):
    mst = ok(session.call("get_minimum_spanning_tree"))
    expected = nx.minimum_spanning_tree(session.uni.get_graph()).size(weight="weight")
    assert mst["total_weight"] == expected == 15
    assert len(mst["edges"]) == 5 and mst["network_is_connected"]

    regions = ok(session.call("get_region_mst"))
    assert set(regions["regions"]) == {"Central", "East", "North"}
    assert len(regions["edges"]) == 5  # connected: one edge fewer than universities


def test_distance_matrix(session):
    matrix = ok(session.call("get_distance_matrix"))
    names = matrix["universities"]
    assert matrix["matrix"][names.index("Sharif")][names.index("Beheshti")] == 8
    assert all(matrix["matrix"][i][i] == 0 for i in range(len(names)))


# ---- editing the network -------------------------------------------------- #
def test_add_university_validates_then_saves(session, tmp_path):
    ok(session.call("add_university", {
        "name": "Allameh", "region": "central",
        "connections": [{"university": "tehran", "weight": 5}],
    }))
    graph = session.uni.get_graph()
    assert graph["Allameh"]["Tehran"]["weight"] == 5
    assert session.uni.get_regions()["Allameh"] == "Central"  # matched existing region

    reloaded = UniversityGraph()
    assert reloaded.load(tmp_path / "graph.json")
    assert reloaded.get_graph().has_edge("Allameh", "Tehran")


@pytest.mark.parametrize("bad", [
    {"name": "Sharif"},                                   # exists
    {"name": "SHARIF"},                                   # exists, different case
    {"name": "elm-o sanat"},                              # same after normalising
    {"name": "  "},
    {"name": "A,B"},
    {"name": "!!!"},
    {"name": "x" * 200},
    {"name": "New", "connections": [{"university": "Nowhere", "weight": 1}]},
    {"name": "New", "connections": [{"university": "Sharif", "weight": 0}]},
    {"name": "New", "connections": [{"university": "Sharif", "weight": -3}]},
    {"name": "New", "connections": [{"university": "Sharif", "weight": float("nan")}]},
    {"name": "New", "connections": [{"university": "Sharif", "weight": float("inf")}]},
    {"name": "New", "connections": [{"university": "Sharif", "weight": True}]},
    {"name": "New", "connections": [{"university": "Sharif", "weight": "heavy"}]},
    {"name": "New", "connections": [{"university": "Sharif"}]},
])
def test_add_university_rejects_bad_input_without_changing_graph(session, bad):
    before = session.uni.get_graph().copy()
    assert "error" in session.call("add_university", bad)
    after = session.uni.get_graph()
    assert set(after.nodes) == set(before.nodes)
    assert set(after.edges) == set(before.edges)


def test_add_university_without_connections_warns(session):
    result = ok(session.call("add_university", {"name": "Lonely"}))
    assert "warning" in result


def test_numeric_strings_are_accepted(session):
    ok(session.call("add_university", {
        "name": "Strs", "connections": [{"university": "Sharif", "weight": "2.5"}]}))
    assert session.uni.get_graph()["Strs"]["Sharif"]["weight"] == 2.5


def test_connect_universities_adds_and_replaces(session):
    first = ok(session.call("connect_universities", {
        "university_a": "Sharif", "university_b": "Beheshti", "weight": 1}))
    assert "replaced_previous_weight" not in first
    again = ok(session.call("connect_universities", {
        "university_a": "Beheshti", "university_b": "Sharif", "weight": 2}))
    assert again["replaced_previous_weight"] == 1
    assert "itself" in session.call("connect_universities", {
        "university_a": "Sharif", "university_b": "sharif", "weight": 1})["error"]
    assert "error" in session.call("connect_universities", {
        "university_a": "Sharif", "university_b": "Tehran", "weight": 0})


def test_remove_university(session, tmp_path):
    ok(session.call("set_route_capacity", {"university_a": "Sharif", "university_b": "Tehran",
                                           "capacity": 1}))
    result = ok(session.call("remove_university", {"name": "tehran"}))
    assert result["removed"] == "Tehran"
    assert sorted(result["connections_removed"]) == ["Elm-o-Sanat", "Sharif"]
    assert result["reservation_routes_cleared"] == 1
    assert "Tehran" not in session.uni.get_graph()
    assert "error" in session.call("remove_university", {"name": "Tehran"})
    reloaded = PlannerSession(save_path=tmp_path / "graph.json", output_dir=tmp_path)
    assert "Tehran" not in reloaded.uni.get_graph()
    assert reloaded.reservations.routes == {}


# ---- reservations --------------------------------------------------------- #
def test_reservation_flow(session):
    route = {"university_a": "Sharif", "university_b": "Tehran"}
    assert "no capacity" in ok(session.call(
        "reserve_seat", {**route, "student_name": "Ali", "priority": 1}))["message"].lower()
    ok(session.call("set_route_capacity", {**route, "capacity": 2}))
    assert ok(session.call("reserve_seat", {**route, "student_name": "Ali", "priority": 5}))["success"]
    assert ok(session.call("reserve_seat", {"university_a": "tehran", "university_b": "sharif",
                                            "student_name": "Sara", "priority": 1}))["success"]
    full = ok(session.call("reserve_seat", {**route, "student_name": "Reza", "priority": 0}))
    assert full["success"] is False and "full" in full["message"].lower()
    dup = ok(session.call("reserve_seat", {**route, "student_name": "Ali", "priority": 1}))
    assert dup["success"] is False

    view = ok(session.call("view_reservations", route))
    assert view["capacity"] == 2 and view["seats_left"] == 0
    assert [r["student"] for r in view["reservations"]] == ["Sara", "Ali"]


def test_reservations_need_direct_routes_and_valid_numbers(session):
    far = {"university_a": "Sharif", "university_b": "Beheshti"}  # connected, but not directly
    assert "no direct route" in session.call("set_route_capacity", {**far, "capacity": 3})["error"]
    assert "no direct route" in session.call("view_reservations", far)["error"]
    same = {"university_a": "Sharif", "university_b": "Sharif"}
    assert "error" in session.call("set_route_capacity", {**same, "capacity": 3})

    route = {"university_a": "Sharif", "university_b": "Tehran"}
    for capacity in (-1, 2.5, "many", True):
        assert "error" in session.call("set_route_capacity", {**route, "capacity": capacity})
    ok(session.call("set_route_capacity", {**route, "capacity": 1}))
    for priority in (1.5, "high", None, True):
        assert "error" in session.call(
            "reserve_seat", {**route, "student_name": "Ali", "priority": priority})
    assert "error" in session.call(
        "reserve_seat", {**route, "student_name": " ", "priority": 1})


def test_reservations_survive_a_restart(tmp_path):
    kwargs = dict(save_path=tmp_path / "graph.json", output_dir=tmp_path / "out")
    first = PlannerSession(**kwargs)
    route = {"university_a": "Sharif", "university_b": "Tehran"}
    ok(first.call("set_route_capacity", {**route, "capacity": 3}))
    ok(first.call("reserve_seat", {**route, "student_name": "Ali", "priority": 5}))
    ok(first.call("reserve_seat", {**route, "student_name": "Sara", "priority": 1}))

    second = PlannerSession(**kwargs)
    view = ok(second.call("view_reservations", route))
    assert [(r["student"], r["priority"]) for r in view["reservations"]] == [("Sara", 1), ("Ali", 5)]
    assert view["seats_left"] == 1
    # the restored queue is still a working heap
    assert ok(second.call("reserve_seat", {**route, "student_name": "Reza", "priority": 0}))["success"]
    assert [r["student"] for r in ok(second.call("view_reservations", route))["reservations"]] \
        == ["Reza", "Sara", "Ali"]


def test_orphaned_reservations_are_dropped_on_load(tmp_path):
    kwargs = dict(save_path=tmp_path / "graph.json", output_dir=tmp_path / "out")
    first = PlannerSession(**kwargs)
    ok(first.call("set_route_capacity", {"university_a": "Sharif", "university_b": "Tehran",
                                         "capacity": 3}))
    first.uni.remove_university("Tehran")  # e.g. deleted from the menu CLI
    first.uni.save(kwargs["save_path"])
    assert PlannerSession(**kwargs).reservations.routes == {}


def test_persist_false_touches_no_files(tmp_path):
    ephemeral = PlannerSession(save_path=tmp_path / "g.json", output_dir=tmp_path, persist=False)
    ok(ephemeral.call("add_university", {"name": "Temp"}))
    ok(ephemeral.call("set_route_capacity", {"university_a": "Sharif", "university_b": "Tehran",
                                             "capacity": 1}))
    assert list(tmp_path.iterdir()) == []


# ---- plots ---------------------------------------------------------------- #
@pytest.mark.parametrize("args,suffix,magic", [
    ({"kind": "graph"}, ".png", b"\x89PNG"),
    ({"kind": "mst"}, ".png", b"\x89PNG"),
    ({"kind": "region_mst"}, ".png", b"\x89PNG"),
    ({"kind": "distance_matrix"}, ".png", b"\x89PNG"),
    ({"kind": "shortest_path", "source": "Sharif", "destination": "Beheshti"}, ".png", b"\x89PNG"),
    ({"kind": "trip", "stops": ["Sharif", "Kharazmi", "Beheshti"]}, ".png", b"\x89PNG"),
    ({"kind": "path_animation", "source": "Sharif", "destination": "Beheshti"}, ".gif", b"GIF8"),
])
def test_plots_are_written(session, args, suffix, magic):
    from pathlib import Path
    result = ok(session.call("save_plot", args))
    path = Path(result["file"])
    assert path.suffix == suffix and path.stat().st_size > 1000
    assert path.read_bytes()[:4] == magic


def test_plot_errors(session):
    assert "required" in session.call("save_plot", {"kind": "shortest_path"})["error"]
    assert "required" in session.call("save_plot", {"kind": "trip"})["error"]
    assert "different" in session.call(
        "save_plot", {"kind": "path_animation", "source": "Sharif", "destination": "Sharif"})["error"]
    ok(session.call("add_university", {"name": "Island"}))
    assert "no route" in session.call(
        "save_plot", {"kind": "shortest_path", "source": "Sharif", "destination": "Island"})["error"].lower()
    assert "not found" in session.call(
        "save_plot", {"kind": "shortest_path", "source": "Sharif", "destination": "Oxford"})["error"]


def test_empty_graph_plot(session):
    for name in list(session.uni.get_graph().nodes):
        session.uni.remove_university(name)
    assert "empty" in session.call("save_plot", {"kind": "graph"})["error"]
    assert ok(session.call("list_universities"))["count"] == 0
    assert ok(session.call("get_minimum_spanning_tree"))["edges"] == []


# ---- gaps found by mutation testing -------------------------------------- #
def test_deleted_routes_do_not_resurrect_old_reservations(tmp_path):
    kwargs = dict(save_path=tmp_path / "graph.json", output_dir=tmp_path / "out")
    first = PlannerSession(**kwargs)
    route = {"university_a": "Sharif", "university_b": "Tehran"}
    ok(first.call("set_route_capacity", {**route, "capacity": 2}))
    ok(first.call("reserve_seat", {**route, "student_name": "Ali", "priority": 1}))
    ok(first.call("remove_university", {"name": "Tehran"}))
    ok(first.call("add_university", {"name": "Tehran", "region": "Central",
                                     "connections": [{"university": "Sharif", "weight": 3}]}))

    second = PlannerSession(**kwargs)  # fresh start, reads the files again
    view = ok(second.call("view_reservations", route))
    assert view["capacity"] is None and view["reservations"] == []


def test_trip_reports_universities_it_passes_through(session):
    result = ok(session.call("plan_multi_stop_trip", {"stops": ["Sharif", "Beheshti"]}))
    assert result["visit_order"] in (["Sharif", "Beheshti"], ["Beheshti", "Sharif"])
    assert set(result["passes_through_other_universities"]) == {"Tehran", "Elm-o-Sanat"}
    assert result["total_cost"] == 8


def test_cannot_reserve_on_a_non_route(session):
    far = {"university_a": "Sharif", "university_b": "Beheshti"}
    assert "no direct route" in session.call(
        "reserve_seat", {**far, "student_name": "Ali", "priority": 1})["error"]
