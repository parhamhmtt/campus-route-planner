import random
import string

import pytest
from matplotlib.figure import Figure

from campus_route_planner.assistant import Assistant
from campus_route_planner.graph_data import UniversityGraph
from campus_route_planner.planner import Planner
from campus_route_planner.reservation_system import ReservationSystem


PATH_TITLE = "Shortest path from Sharif to Beheshti (distance 8)"
TRIP_TITLE = "TSP route: Beheshti -> Kharazmi -> Sharif (cost 13)"


def make_bot(uni=None, save_path=None):
    planner = Planner(uni or UniversityGraph(), ReservationSystem(), figure=Figure(),
                      save_path=save_path)
    return Assistant(planner)


@pytest.fixture
def bot():
    return make_bot()


def test_shortest_path_phrasings(bot):
    questions = [
        "shortest way from Sharif to Beheshti",
        "What's the quickest route from sharif to BEHESHTI?",
        "how do I get from Sharif to Beheshti",
        "distance between Sharif and Beheshti",
        "Sharif to Beheshti",
        "from sharfi to beheshti",
    ]
    for q in questions:
        assert "Sharif -> Tehran -> Elm-o-Sanat -> Beheshti (distance 8)" in bot.reply(q), q


def test_path_direction_follows_the_sentence(bot):
    assert "Beheshti -> Elm-o-Sanat -> Tehran -> Sharif" in bot.reply("from Beheshti to Sharif")


def test_same_university_twice_and_unreachable(bot):
    assert "two universities" in bot.reply("route from Sharif to Sharif")
    bot.reply("add Island")
    assert "no route from Sharif to Island" in bot.reply("route from Sharif to Island")


def test_route_needs_two_universities(bot):
    assert "two universities" in bot.reply("how do I get to Beheshti")
    assert "two universities" in bot.reply("shortest path Sharif Tehran Beheshti")


def test_trip(bot):
    answer = bot.reply("plan a trip visiting Sharif, Kharazmi and Beheshti")
    assert "total cost 13" in answer
    assert "passes through Amirkabir" in answer
    assert "cost" in bot.reply("tsp for Sharif Beheshti")
    assert "at least" not in bot.reply("tour Sharif Tehran")


def test_trip_with_too_many_stops(bot):
    for i in range(12):
        bot.reply(f"add Extra{i} connected to Sharif {i + 1}")
    names = " ".join(n for n in bot.graph.nodes)
    assert "At most 15" in bot.reply(f"trip visiting {names}")


def test_mst_and_region_mst(bot):
    answer = bot.reply("which routes should we keep? show the minimum spanning tree")
    assert "Total weight 15" in answer
    assert "Elm-o-Sanat - Beheshti (1)" in answer
    assert "Region-based MST" in bot.reply("region based mst")


def test_distance_matrix(bot):
    rows = bot.reply("show the distance matrix").splitlines()
    assert len(rows) == 7
    assert rows[1].split()[:2] == ["Sharif", "0"]


def test_describe_and_list(bot):
    answer = bot.reply("what is connected to Tehran?")
    assert "Tehran (Central) connects to Elm-o-Sanat (4), Sharif (3)" in answer
    assert "Tehran (Central)" in bot.reply("tell me about tehran")
    assert "Tehran (Central)" in bot.reply("Tehran")
    listing = bot.reply("list the universities")
    assert listing.startswith("6 universities:") and "Sharif (Central)" in listing


def test_add_university_variants(bot):
    assert "Added Allameh (West), connected to Tehran (5)" in bot.reply(
        "Add Allameh in the West region, connected to Tehran with weight 5.")
    assert bot.graph["Allameh"]["Tehran"]["weight"] == 5
    assert bot.planner.uni.get_regions()["Allameh"] == "West"

    bot.reply("add a new university called Imam Sadiq connected to Sharif 4 and Tehran 2.5")
    assert bot.graph["Imam Sadiq"]["Sharif"]["weight"] == 4
    assert bot.graph["Imam Sadiq"]["Tehran"]["weight"] == 2.5

    bot.reply("create a university in the North region called Tabriz, linked to Kharazmi 9")
    assert bot.planner.uni.get_regions()["Tabriz"] == "North"
    assert bot.graph["Tabriz"]["Kharazmi"]["weight"] == 9

    bot.reply("add shiraz region south connected to Sharif 7")
    assert bot.planner.uni.get_regions()["Shiraz"] == "south"
    bot.reply("add Mashhad region SOUTH connected to Sharif 7")
    assert bot.planner.uni.get_regions()["Mashhad"] == "south"  # reuses the existing spelling


def test_region_number_is_not_a_weight(bot):
    bot.reply("add Foo in region 2 connected to Tehran 5")
    assert bot.graph["Foo"]["Tehran"]["weight"] == 5


def test_add_without_connections_says_so(bot):
    assert "no connections" in bot.reply("add Lonely")
    assert "Lonely" in bot.graph


def test_add_rejects_duplicates(bot):
    for text in ("add Sharif", "add sharif connected to Tehran 3", "add elm o sanat"):
        assert "already exists" in bot.reply(text), text
    assert len(bot.graph) == 6


def test_add_rejects_bad_weights_completely(bot):
    for text in ("add Foo connected to Tehran 0", "add Foo connected to Tehran -4",
                 "add Foo connected to Tehran", "add Foo connected to Tehran and Sharif 3"):
        bot.reply(text)
        assert "Foo" not in bot.graph, text


def test_connect_and_change_weight(bot):
    answer = bot.reply("connect Sharif and Beheshti with weight 2")
    assert "Connected Sharif and Beheshti with weight 2" in answer
    assert "from 2 to 6" in bot.reply("change the route between Beheshti and Sharif to 6")
    assert "What weight" in bot.reply("link Sharif and Tehran")
    assert "positive" in bot.reply("connect Sharif and Beheshti weight -1")
    assert bot.graph["Sharif"]["Beheshti"]["weight"] == 6


def test_remove_asks_first(bot):
    assert "Remove Kharazmi and its 2 routes? (yes/no)" in bot.reply("remove Kharazmi")
    assert "stays" in bot.reply("no")
    assert "Kharazmi" in bot.graph
    bot.reply("delete kharazmi")
    assert bot.reply("yes") == "Removed Kharazmi and its connections."
    assert "Kharazmi" not in bot.graph


def test_remove_confirmation_is_cancelled_by_another_question(bot):
    bot.reply("remove Kharazmi")
    assert "distance 8" in bot.reply("shortest way from Sharif to Beheshti")
    assert "Kharazmi" in bot.graph
    assert "didn't get" in bot.reply("yes")  # nothing is pending any more


def test_remove_needs_exactly_one_name(bot):
    assert "one university I know" in bot.reply("remove")
    assert "I found Sharif, Tehran" in bot.reply("remove Sharif and Tehran")
    assert len(bot.graph) == 6


def test_reservations(bot):
    assert "No capacity" in bot.reply("who is booked on Sharif-Tehran")
    assert "now has 2 seats" in bot.reply("set capacity of Sharif-Tehran to 2")
    assert "Sara now has a seat" in bot.reply("Reserve a seat for Sara on Sharif-Tehran, priority 5")
    answer = bot.reply("book a seat for Sara Ahmadi from Tehran to Sharif priority 1")
    assert "Sara Ahmadi now has a seat" in answer
    assert "full" in bot.reply("reserve a seat for Reza on Sharif-Tehran priority 0").lower()
    answer = bot.reply("who is booked on Sharif-Tehran?")
    assert "2 of 2 seats taken" in answer
    assert answer.index("Sara Ahmadi") < answer.index("Sara (")  # priority order
    assert "2 of 2" in bot.reply("how many seats are left on Sharif and Tehran")


def test_reservation_mistakes(bot):
    bot.reply("set capacity of Sharif-Tehran to 2")
    assert "no direct route" in bot.reply("reserve a seat for Ali on Sharif-Beheshti priority 1")
    assert "no direct route" in bot.reply("set capacity of Sharif-Beheshti to 3")
    assert "Who is the seat for" in bot.reply("reserve a seat on Sharif-Tehran priority 1")
    assert "What priority" in bot.reply("reserve a seat for Ali on Sharif-Tehran")
    assert "Which route" in bot.reply("reserve a seat for Ali priority 1")
    assert "whole number" in bot.reply("set capacity of Sharif-Tehran to 2.5")
    assert "negative" in bot.reply("set capacity of Sharif-Tehran to -2")
    assert bot.reply("who is booked on Sharif-Tehran").startswith("Sharif - Tehran: 0 of 2")


def test_removing_a_university_drops_its_reservations(bot):
    bot.reply("set capacity of Sharif-Tehran to 2")
    bot.reply("remove Tehran")
    bot.reply("yes")
    assert bot.planner.reservations.routes == {}


def test_single_letter_names_do_not_match_ordinary_words():
    uni = UniversityGraph()
    for name in list(uni.get_graph().nodes):
        uni.remove_university(name)
    for name in "AB":
        uni.add_university(name)
    uni.add_connection("A", "B", 3)
    bot = make_bot(uni)
    bot.reply("set capacity of A-B to 1")
    assert "Ali now has a seat on A - B" in bot.reply("Reserve a seat for Ali on A-B priority 1")
    assert "A -> B (distance 3)" in bot.reply("route from A to B")
    assert "B -> A (distance 3)" in bot.reply("give me a route from B to A")


def test_changes_are_saved(tmp_path):
    path = tmp_path / "graph.json"
    bot = make_bot(save_path=path)
    bot.reply("add Allameh connected to Tehran 5")
    bot.reply("connect Allameh and Sharif with weight 9")
    saved = UniversityGraph()
    assert saved.load(path)
    assert saved.get_graph()["Allameh"]["Sharif"]["weight"] == 9
    bot.reply("remove Allameh")
    bot.reply("yes")
    reloaded = UniversityGraph()
    reloaded.load(path)
    assert "Allameh" not in reloaded.get_graph()


@pytest.mark.parametrize("text,title", [
    ("draw the graph", "University graph"),
    ("draw the mst", "Minimum spanning tree (red)"),
    ("plot the region mst", "Region-based MST"),
    ("show the distance matrix heatmap", None),
    ("draw the shortest path from Sharif to Beheshti", PATH_TITLE),
    ("animate the path from Sharif to Beheshti", PATH_TITLE),
    ("draw a trip through Sharif, Kharazmi, Beheshti", TRIP_TITLE),
])
def test_pictures_are_drawn_into_the_figure(bot, text, title):
    drawn = []
    bot.planner.on_draw = lambda: drawn.append(True)
    assert bot.reply(text)
    assert drawn
    if title:
        assert bot.planner.figure.get_suptitle() == title
    assert bot.planner.figure.axes


def test_animation_is_kept_and_replaced(bot):
    bot.reply("animate the path from Sharif to Beheshti")
    first = bot.planner.animation
    assert first is not None
    bot.reply("draw the graph")
    assert bot.planner.animation is None


def test_animation_needs_two_universities(bot):
    assert "two universities" in bot.reply("animate the path from Sharif to Sharif")


def test_help_greeting_and_fallback(bot):
    assert "shortest way from" in bot.reply("help")
    assert bot.reply("hello").startswith("Hi")
    assert "You're welcome" in bot.reply("thanks!")
    assert "didn't get" in bot.reply("what is the meaning of life")
    assert bot.reply("   ") == ""


def test_empty_network():
    uni = UniversityGraph()
    for name in list(uni.get_graph().nodes):
        uni.remove_university(name)
    bot = make_bot(uni)
    for text in ("show the distance matrix", "draw the graph", "minimum spanning tree",
                 "region mst", "list the universities"):
        assert "no universities" in bot.reply(text).lower(), text
    assert "Added Solo" in bot.reply("add Solo")


def test_never_crashes_on_nonsense(bot):
    rng = random.Random(7)
    words = ["Sharif", "Tehran", "add", "remove", "to", "from", "5", "-3", "0", "capacity", "seat",
             "reserve", "priority", "for", "trip", "mst", "draw", "connect", "weight", "region",
             "yes", "no", "called", "and", "the", ",", ".", "Beheshti", "99999999", "1e5", "nan"]
    for _ in range(1500):
        if rng.random() < 0.7:
            text = " ".join(rng.choice(words) for _ in range(rng.randint(1, 12)))
        else:
            alphabet = string.printable + "äöüé漢字"
            text = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 60)))
        assert isinstance(bot.reply(text), str), text


def test_numbered_names_are_not_confused_with_each_other(bot):
    bot.reply("add Extra0 connected to Sharif 1")
    assert "Added Extra1" in bot.reply("add Extra1 connected to Sharif 2")
    assert "Extra1 -> Sharif (distance 2)" in bot.reply("route from Extra1 to Sharif")
    assert "I don't know Extra5" in bot.reply("route from Extra5 to Sharif")


def test_unknown_capitalised_names_are_reported(bot):
    assert "I don't know Oxford" in bot.reply("plan a trip visiting Sharif, Kharazmi and Oxford")
    assert "I don't know Oxford" in bot.reply("connect Sharif and Oxford with weight 3")
    assert "I don't know Oxford" in bot.reply("remove Oxford")
    assert "Oxford" not in bot.graph
    # student names and ordinary capitals must not trigger it
    bot.reply("set capacity of Sharif-Tehran to 1")
    assert "Sara now has" in bot.reply("reserve a seat for Sara on Sharif-Tehran priority 1")
    assert "distance 8" in bot.reply("Can I get from Sharif to Beheshti?")
    assert "Total weight" in bot.reply("What is the MST?")
