import pytest

tk = pytest.importorskip("tkinter")
from tkinter import ttk  # noqa: E402

from campus_route_planner import gui  # noqa: E402
from campus_route_planner.gui import App, WeightDialog  # noqa: E402

NAMES = ["Sharif", "Tehran", "Amirkabir", "Elm-o-Sanat", "Kharazmi", "Beheshti"]


def make_app(path):
    try:
        window = App(save_path=path)
    except tk.TclError:
        pytest.skip("no display available")
    window.geometry("1240x780+-3000+0")  # keep the test window off the screen
    window.update()
    return window


@pytest.fixture
def app(tmp_path):
    window = make_app(tmp_path / "graph.json")
    yield window
    try:
        window.close()
    except tk.TclError:
        pass


def find(widget, text):
    for child in widget.winfo_children():
        if isinstance(child, ttk.Button) and child.cget("text") == text:
            return child
        found = find(child, text)
        if found:
            return found
    return None


def press(app, text):
    button = find(app, text)
    assert button is not None, f"no button called {text}"
    button.invoke()


def result(app):
    return app.result.get("1.0", "end").strip()


def failed(app):
    return bool(app.result.tag_ranges("error"))


def transcript(app):
    return app.transcript.get("1.0", "end")


def test_starts_with_the_network_on_the_map(app):
    assert app.planner.names() == NAMES
    assert app.figure.get_suptitle() == "University graph"
    assert "6 universities" in result(app)
    for box in app.name_boxes:
        assert list(box["values"]) == NAMES
    assert (app.source.get(), app.target.get()) == ("Sharif", "Beheshti")
    assert list(app.stops.get(0, "end")) == NAMES


def test_toolbar_views(app):
    press(app, "Spanning tree")
    assert "Total weight 15" in result(app)
    assert app.figure.get_suptitle() == "Minimum spanning tree (red)"
    press(app, "Regions")
    assert app.figure.get_suptitle() == "Region-based MST"
    press(app, "Distances")
    assert result(app).splitlines()[1].split()[:2] == ["Sharif", "0"]
    assert len(app.figure.axes) == 2  # heatmap and its colour bar
    press(app, "Network")
    assert app.figure.get_suptitle() == "University graph"
    assert not failed(app)


def test_shortest_path_and_its_errors(app):
    press(app, "Find path")
    assert "Sharif -> Tehran -> Elm-o-Sanat -> Beheshti (distance 8)" in result(app)
    assert "Shortest path from Sharif to Beheshti" in app.figure.get_suptitle()
    assert not failed(app)

    app.target.set("Sharif")
    press(app, "Find path")
    assert failed(app) and "two different" in result(app)

    app.source.set("")
    press(app, "Find path")
    assert failed(app) and "Choose a university" in result(app)


def test_animation_starts_and_stops(app):
    press(app, "Animate")
    assert app.planner.animation is not None
    app.update()
    press(app, "Spanning tree")
    assert app.planner.animation is None


def test_trip(app):
    press(app, "Plan trip")
    assert failed(app) and "at least two" in result(app)
    for name in ("Sharif", "Kharazmi", "Beheshti"):
        app.stops.selection_set(NAMES.index(name))
    press(app, "Plan trip")
    assert not failed(app)
    assert "total cost 13" in result(app) and "passes through Amirkabir" in result(app)
    assert app.figure.get_suptitle().startswith("TSP route")


def test_add_university_with_links(app, tmp_path):
    app.new_name.set("Allameh")
    app.new_region.set("West")
    app.link_target.set("Tehran")
    app.link_weight.set("5")
    press(app, "Add link")
    app.link_target.set("Sharif")
    app.link_weight.set("2.5")
    press(app, "Add link")
    assert list(app.links.get(0, "end")) == ["Tehran  (5)", "Sharif  (2.5)"]
    press(app, "Add university")

    assert result(app) == "Added Allameh (West), connected to Tehran (5), Sharif (2.5)."
    assert app.planner.graph["Allameh"]["Tehran"]["weight"] == 5
    assert app.new_name.get() == "" and app.pending_links == [] and app.links.size() == 0
    assert "Allameh" in app.planner.names()
    for box in app.name_boxes:
        assert "Allameh" in box["values"]
    assert "Allameh" in app.stops.get(0, "end")
    assert (tmp_path / "graph.json").exists()


def test_add_link_mistakes(app):
    app.link_target.set("Tehran")
    for bad, message in (("", "must be a number"), ("abc", "must be a number"), ("0", "positive"),
                         ("-3", "positive"), ("nan", "must be a number"), ("inf", "must be a number")):
        app.link_weight.set(bad)
        press(app, "Add link")
        assert failed(app) and message in result(app), bad
    assert app.pending_links == []
    app.link_weight.set("3")
    press(app, "Add link")
    app.link_weight.set("4")
    press(app, "Add link")
    assert "already in the list" in result(app)
    app.links.selection_set(0)
    press(app, "Remove link")
    assert app.pending_links == [] and app.links.size() == 0


def test_add_university_mistakes_change_nothing(app):
    for name in ("", "sharif", "Sharif"):
        app.new_name.set(name)
        press(app, "Add university")
        assert failed(app), name
    assert app.planner.names() == NAMES


def test_without_links_the_cheapest_candidate_is_connected(app):
    asked = []

    def fake_dialog(name, others):
        asked.append((name, others))
        return {"Tehran": 4, "Sharif": 2, "Beheshti": 9}

    app.ask_weights = fake_dialog
    app.new_name.set("Foo")
    press(app, "Add university")
    assert asked == [("Foo", NAMES)]
    assert result(app) == ("Added Foo (Unassigned) with no connections yet. "
                           "Connected Foo to Sharif with weight 2.")
    assert list(app.planner.graph["Foo"]) == ["Sharif"]


def test_skipping_the_dialog_leaves_the_university_alone(app):
    app.ask_weights = lambda name, others: None
    app.new_name.set("Foo")
    press(app, "Add university")
    assert "Foo" in app.planner.names() and list(app.planner.graph["Foo"]) == []
    assert not failed(app)


def test_the_first_university_needs_no_dialog(app):
    for name in NAMES:
        app.planner.remove(name)
    app.ask_weights = lambda *args: pytest.fail("there is nobody to compare with")
    app.new_name.set("Solo")
    press(app, "Add university")
    assert app.planner.names() == ["Solo"] and not failed(app)


def test_weight_dialog_checks_input_before_closing(app):
    seen = {}

    def drive():
        dialog = next(w for w in app.winfo_children() if isinstance(w, WeightDialog))
        sharif, tehran = list(dialog.fields)
        dialog.accept()
        seen["empty"] = dialog.message.cget("text")
        dialog.fields[sharif].set("abc")
        dialog.accept()
        seen["bad"] = dialog.message.cget("text")
        seen["still_open"] = bool(dialog.winfo_exists())
        dialog.fields[sharif].set("3")
        dialog.fields[tehran].set("1.5")
        dialog.accept()

    app.after(150, drive)
    answer = app.ask_weights("Foo", ["Sharif", "Tehran"])
    assert answer == {"Sharif": 3.0, "Tehran": 1.5}
    assert "at least one" in seen["empty"]
    assert "Sharif must be a number" in seen["bad"] and seen["still_open"]


def test_weight_dialog_can_be_skipped(app):
    def drive():
        dialog = next(w for w in app.winfo_children() if isinstance(w, WeightDialog))
        find(dialog, "Skip").invoke()

    app.after(150, drive)
    assert app.ask_weights("Foo", ["Sharif"]) is None


def test_change_a_route(app):
    app.route_a.set("Sharif")
    app.route_b.set("Beheshti")
    press(app, "Set route")
    assert failed(app) and "must be a number" in result(app)
    app.route_weight.set("2")
    press(app, "Set route")
    assert result(app) == "Connected Sharif and Beheshti with weight 2."
    app.route_weight.set("6")
    press(app, "Set route")
    assert "from 2 to 6" in result(app)
    app.route_b.set("Sharif")
    press(app, "Set route")
    assert failed(app) and "itself" in result(app)


def test_remove_a_university_asks_first(app):
    app.doomed.set("Kharazmi")
    asked = []
    app.confirm = lambda title, text: asked.append(text) or False
    press(app, "Remove")
    assert asked == ["Remove Kharazmi and its 2 routes?"]
    assert "Kharazmi" in app.planner.names() and "was kept" in result(app)

    app.confirm = lambda title, text: True
    press(app, "Remove")
    assert "Kharazmi" not in app.planner.names()
    assert app.doomed.get() == ""
    for box in app.name_boxes:
        assert "Kharazmi" not in box["values"]
    press(app, "Remove")
    assert failed(app) and "Choose a university" in result(app)


def test_seats(app):
    press(app, "Show reservations")
    assert failed(app) and "Choose a university" in result(app)
    app.seat_a.set("Sharif")
    app.seat_b.set("Tehran")
    press(app, "Show reservations")
    assert "No capacity has been set" in result(app)

    press(app, "Set capacity")
    assert result(app) == "Sharif - Tehran now has 2 seats."
    app.student.set("Sara")
    press(app, "Reserve seat")
    assert result(app) == "Sara now has a seat on Sharif - Tehran."
    app.student.set("Reza")
    app.priority.set("0")
    press(app, "Reserve seat")
    app.student.set("Ali")
    press(app, "Reserve seat")
    assert "full" in result(app).lower()
    press(app, "Show reservations")
    assert result(app).splitlines() == [
        "Sharif - Tehran: 2 of 2 seats taken.", "  Reza (priority 0)", "  Sara (priority 1)"]


def test_seat_mistakes(app):
    app.seat_a.set("Sharif")
    app.seat_b.set("Beheshti")
    press(app, "Set capacity")
    assert "no direct route" in result(app)
    app.seat_b.set("Tehran")
    for value, message in (("abc", "Seats must be a number"), ("1.5", "whole number"),
                           ("-2", "negative")):
        app.capacity.set(value)
        press(app, "Set capacity")
        assert failed(app) and message in result(app), value
    app.capacity.set("1")
    press(app, "Set capacity")
    for value, message in (("abc", "Priority must be a number"), ("1.5", "whole number")):
        app.student.set("Ali")
        app.priority.set(value)
        press(app, "Reserve seat")
        assert failed(app) and message in result(app), value
    app.priority.set("1")
    app.student.set("  ")
    press(app, "Reserve seat")
    assert failed(app) and "name" in result(app)


def test_chat(app):
    app.chat_entry.insert(0, "shortest way from Sharif to Beheshti")
    press(app, "Send")
    text = transcript(app)
    assert "shortest way from Sharif to Beheshti" in text
    assert "Sharif -> Tehran -> Elm-o-Sanat -> Beheshti (distance 8)" in text
    assert app.chat_entry.get() == ""
    assert "distance 8" in app.figure.get_suptitle()      # the map followed the question
    assert "distance 8" in result(app)                    # and so did the result panel
    assert app.transcript.tag_ranges("mine") and app.transcript.tag_ranges("theirs")


def test_chat_history_and_empty_input(app):
    press(app, "Send")
    assert app.history == []
    app.send("hello")
    app.send("list the universities")
    app.recall(-1)
    assert app.chat_entry.get() == "list the universities"
    app.recall(-1)
    assert app.chat_entry.get() == "hello"
    app.recall(-1)
    assert app.chat_entry.get() == "hello"
    app.recall(1)
    app.recall(1)
    assert app.chat_entry.get() == ""


def test_chat_shortcuts(app):
    press(app, "Which routes should we keep?")
    assert "Total weight 15" in transcript(app)
    assert app.figure.get_suptitle() == "Minimum spanning tree (red)"
    press(app, "List the universities")
    assert app.transcript.tag_ranges("table")  # lists and tables use the fixed-width font
    press(app, "What can you do?")
    assert "shortest way from Sharif to Beheshti" in transcript(app)


def test_editing_by_chat_updates_the_forms(app):
    app.send("add Allameh connected to Tehran 5")
    assert "Allameh" in app.stops.get(0, "end")
    app.send("remove Kharazmi")
    assert "(yes/no)" in transcript(app)
    app.send("yes")
    assert "Kharazmi" not in app.planner.names()
    for box in app.name_boxes:
        assert "Kharazmi" not in box["values"]
    assert "Allameh" in app.stops.get(0, "end") and "Kharazmi" not in app.stops.get(0, "end")


def test_save_picture(app, tmp_path, monkeypatch):
    target = tmp_path / "picture.png"
    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", lambda **options: str(target))
    press(app, "Save picture")
    assert target.read_bytes()[:4] == b"\x89PNG"
    assert str(target) in result(app)
    target.unlink()
    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", lambda **options: "")
    press(app, "Save picture")
    assert not target.exists()


def test_changes_survive_a_restart(tmp_path):
    path = tmp_path / "graph.json"
    first = make_app(path)
    first.send("add Allameh in the West region connected to Tehran with weight 5")
    first.close()
    second = make_app(path)
    try:
        assert "Allameh" in second.planner.names()
        assert second.planner.region_of("Allameh") == "West"
        assert "Loaded your saved network" in result(second)
    finally:
        second.close()


def test_closing_stops_the_animation(tmp_path):
    window = make_app(tmp_path / "graph.json")
    press(window, "Animate")
    assert window.planner.animation is not None
    planner = window.planner
    window.close()
    assert planner.animation is None
    with pytest.raises(tk.TclError):
        window.winfo_exists()
