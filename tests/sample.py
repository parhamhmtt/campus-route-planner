from campus_route_planner.graph_data import UniversityGraph

# the small network the tests were first written against, no coordinates
UNIVERSITIES = [
    ("Sharif", "Central"), ("Tehran", "Central"), ("Amirkabir", "Central"),
    ("Elm-o-Sanat", "East"), ("Kharazmi", "East"), ("Beheshti", "North"),
]
ROUTES = [
    ("Sharif", "Tehran", 3), ("Sharif", "Amirkabir", 2), ("Tehran", "Elm-o-Sanat", 4),
    ("Amirkabir", "Kharazmi", 6), ("Kharazmi", "Beheshti", 5), ("Elm-o-Sanat", "Beheshti", 1),
]


def small_graph():
    return UniversityGraph(UNIVERSITIES, ROUTES)
