import pytest

from campus_route_planner.graph_data import UniversityGraph
from campus_route_planner.reservation_system import ReservationSystem


def test_save_and_load_round_trip(tmp_path):
    uni = UniversityGraph()
    uni.add_university("Newcomer", "West")
    uni.add_connection("Newcomer", "Sharif", 7)
    path = tmp_path / "graph.json"
    uni.save(path)

    other = UniversityGraph()
    assert other.load(path)
    assert other.get_graph()["Newcomer"]["Sharif"]["weight"] == 7
    assert other.get_regions()["Newcomer"] == "West"


def test_load_missing_file_keeps_defaults(tmp_path):
    uni = UniversityGraph()
    assert not uni.load(tmp_path / "missing.json")
    assert "Sharif" in uni.get_graph()


def test_graph_validation():
    uni = UniversityGraph()
    with pytest.raises(ValueError):
        uni.add_university("Sharif")
    with pytest.raises(ValueError):
        uni.add_connection("Sharif", "Nowhere", 1)
    with pytest.raises(ValueError):
        uni.add_connection("Sharif", "Tehran", -1)
    with pytest.raises(ValueError):
        uni.remove_university("Nowhere")


def test_remove_university_drops_edges_and_region():
    uni = UniversityGraph()
    uni.remove_university("Tehran")
    assert "Tehran" not in uni.get_graph()
    assert "Tehran" not in uni.get_regions()


def test_reservations_follow_priority_and_capacity():
    system = ReservationSystem()
    assert not system.reserve("A", "B", "Ali", 1)[0]
    system.set_capacity("A", "B", 2)
    assert system.reserve("A", "B", "Ali", 5)[0]
    assert system.reserve("B", "A", "Sara", 1)[0]
    assert not system.reserve("A", "B", "Reza", 0)[0]
    assert system.view_reservations("A", "B") == [(1, "Sara"), (5, "Ali")]


def test_duplicate_reservation_rejected():
    system = ReservationSystem()
    system.set_capacity("A", "B", 3)
    system.reserve("A", "B", "Ali", 1)
    assert not system.reserve("A", "B", "Ali", 2)[0]


def test_cancel_a_reservation():
    system = ReservationSystem()
    system.set_capacity("A", "B", 2)
    system.reserve("A", "B", "Sara", 2)
    system.reserve("B", "A", "Reza", 1)
    assert system.cancel("B", "A", "Reza") == (True, "Reza's reservation was cancelled.")
    assert system.view_reservations("A", "B") == [(2, "Sara")]
    assert system.cancel("A", "B", "Reza") == (False, "Reza has no seat on this route.")
    assert system.cancel("A", "C", "Sara")[0] is False  # no such route
    # the freed seat can be used again and the queue is still ordered by priority
    assert system.reserve("A", "B", "Ali", 0)[0]
    assert system.reserve("A", "B", "Mina", 5) == (False, "Route is full.")
    assert system.view_reservations("A", "B") == [(0, "Ali"), (2, "Sara")]
