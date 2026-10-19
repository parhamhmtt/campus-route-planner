import re
from difflib import SequenceMatcher

from .planner import squash, tidy

HELP = """You can ask things like:
  shortest way from Exeter to Aberdeen
  and from there to Glasgow?
  animate the path from Bristol to Edinburgh
  plan a trip visiting Bristol, Leeds and Edinburgh
  plan a trip starting at Exeter and ending at Aberdeen, visiting Leeds
  which routes should we keep? (minimum spanning tree)
  show the distance matrix
  what is connected to Manchester?
  what is the weight between Bristol and Bath?
  add Plymouth in the South West region connected to Exeter with weight 75
  connect Oxford and Cambridge with weight 130
  remove Swansea
  set capacity of Bristol-Bath to 3
  reserve a seat for Sara on Bristol-Bath priority 1
  cancel Sara's seat on Bristol-Bath
  who is booked on Bristol-Bath?
  undo
You can chain requests with "then", for example:
  connect Oxford and Cambridge with weight 130 then show the tree"""

TOKEN = re.compile(r"-?\d+(?:\.\d+)?|[A-Za-z0-9]+")
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")

NEW_NAME = re.compile(
    r"\b(?:add|create|insert)\s+(?:a\s+|an\s+|the\s+)?(?:new\s+)?"
    r"(?:universit(?:y|ies)\s+|uni\s+|campus\s+)?(?:called\s+|named\s+)?"
    r"(?P<name>[A-Za-z0-9][\w' -]*?)"
    r"(?=\s+(?:in|at|region|connected|connect|linked|link|with|to|and)\b|[,;.]|$)"
    r"(?P<rest>.*)", re.I)
CALLED = re.compile(
    r"\b(?:called|named)\s+(?P<name>[A-Za-z0-9][\w' -]*?)"
    r"(?=\s+(?:in|at|region|connected|connect|linked|link|with|to|and)\b|[,;.]|$)", re.I)
# regions can have up to three words ("South West", "Northern Ireland")
NOT_REGION = r"(?!(?:connected|connect|linked|link|with|to|and|weight|region)\b)"
REGION_WORDS = NOT_REGION + r"[\w-]+(?:\s+" + NOT_REGION + r"[\w-]+){0,2}"
REGION = [
    re.compile(r"\b(?:in|at|of)\s+(?:the\s+)?(?P<r>[\w-]+(?:\s+[\w-]+){0,2}?)\s+region", re.I),
    re.compile(r"\bregion\s*(?:is|=|:)?\s*(?:called\s+|named\s+)?(?P<r>" + REGION_WORDS + ")", re.I),
    re.compile(r"^\s*(?:in|at)\s+(?:the\s+)?(?P<r>" + REGION_WORDS + ")", re.I),
]
STUDENT = re.compile(
    r"\bfor\s+(?P<s>[A-Za-z][\w'.-]*(?:\s+[A-Za-z][\w'.-]*){0,2}?)"
    r"(?=\s+(?:on|from|between|in|at|to|with|priority|seat|route|bus|shuttle)\b|[,;.]|\d|$)",
    re.I)
CANCEL = re.compile(
    r"\bcancel\s+(?:the\s+|a\s+)?(?:(?:reservation|booking|seat)\s+)?(?:for\s+)?"
    r"(?P<s>[A-Za-z][\w.-]*(?:\s+[A-Za-z][\w.-]*){0,2}?)(?:'s)?"
    r"(?=\s+(?:seat|reservation|booking|on|from|between|in|at)\b|[,;.]|$)", re.I)
PRIORITY = re.compile(r"priority\s*(?:of|is|=|:)?\s*(-?\d+)", re.I)
NOT_A_STUDENT = {"on", "from", "between", "in", "at", "my", "the", "a", "this", "that", "it", "all"}

# words the sentence patterns already understand, anything else next to a name is reported
KNOWN_WORDS = set("""
a an the this that these those it its there here me my we us our you your i please can could
would will should shall might may do does did is are was were be been am have has had having
get gets got go goes going let lets and or but then also too just only really maybe so if
when while with without about for from to of in on at by into onto through via between among
near around over under up down out off what whats which who whom whose where why how many
much long far tell show list give find plan make set put change update add create insert
remove delete drop connect link join undo revert cancel reserve book draw plot animate
display visualize trip tour visit visiting visits stops stop itinerary tsp order route
routes path paths way ways shortest quickest fastest cheapest best optimal short quick fast
cheap distance distances weight weights cost costs length direct directly capacity seats
seat reservation reservations booked bookings booking passengers priority student
university universities uni campus campuses region regions new called named graph network
map everything all every each both any mst spanning tree minimum keep matrix heatmap heat
pairs pair connected connections connection neighbor neighbors neighbour neighbours info
start starting begin beginning end ending finish finishing yes no ok okay sure thanks thank
hi hello hey take back last one same another other ll re ve don didn doesn isn aren
lead leads
""".split())

# for the "did you mean" hint: words that point at an action, and an example of it
SUGGESTIONS = [
    ({"route", "path", "way", "shortest", "quickest", "fastest", "get", "go", "travel",
      "distance", "far", "from"}, "shortest way from {a} to {b}"),
    ({"trip", "visit", "visiting", "tour", "stops", "order", "itinerary"},
     "plan a trip visiting {a}, {b} and {c}"),
    ({"mst", "spanning", "tree", "keep", "cheapest", "network"}, "which routes should we keep?"),
    ({"matrix", "distances", "heatmap", "pairs"}, "show the distance matrix"),
    ({"connected", "neighbors", "neighbours", "links", "about", "tell", "info"},
     "what is connected to {a}?"),
    ({"weight", "direct"}, "what is the weight between {a} and {b}?"),
    ({"add", "new", "create"}, "add Allameh in the West region connected to {a} with weight 5"),
    ({"connect", "link", "join"}, "connect {a} and {b} with weight 2"),
    ({"remove", "delete", "drop"}, "remove {c}"),
    ({"capacity", "seats", "seat"}, "set capacity of {a}-{b} to 3"),
    ({"reserve", "book"}, "reserve a seat for Sara on {a}-{b} priority 1"),
    ({"cancel"}, "cancel Sara's seat on {a}-{b}"),
    ({"reservation", "reservations", "booked", "bookings", "passengers"},
     "who is booked on {a}-{b}?"),
    ({"undo", "revert", "back"}, "undo"),
]


def tokenize(text):
    return TOKEN.findall(text)


def is_number(token):
    return NUMBER.fullmatch(token) is not None


class Assistant:
    def __init__(self, planner, on_miss=None):
        self.planner = planner
        self.on_miss = on_miss     # called with every sentence it could not handle
        self.misses = []
        self.pending = None        # university waiting for a yes/no before it is removed
        self.last_names = []       # what the last answer was about, for "from there"
        self.last_kind = None

    @property
    def graph(self):
        return self.planner.graph

    def reply(self, text):
        text = text.strip()
        if not text:
            return ""
        if self.pending:
            name, self.pending = self.pending, None
            answer = text.lower().strip(" .!")
            if answer in ("y", "yes", "yeah", "yep", "sure", "ok", "okay", "confirm"):
                return self.run(self.planner.remove, name)
            if answer in ("n", "no", "nope", "cancel", "stop"):
                return f"Okay, {name} stays."
        parts = [p for p in re.split(r"\s*(?:;|\band\s+then\b|\bthen\b)\s*", text, flags=re.I) if p]
        if len(parts) < 2:
            return self.run(self.dispatch, text)
        answers = []
        for part in parts:
            answers.append(self.run(self.dispatch, part))
            if self.pending:   # a question is waiting, do not go on without the answer
                break
        return "\n".join(a for a in answers if a)

    def run(self, action, *args):
        try:
            return action(*args)
        except ValueError as err:
            return str(err)

    # finding universities in a sentence

    def find_universities(self, tokens, fuzzy=True):
        names = []
        for _, _, name in self.scan(tokens, fuzzy):
            if name not in names:
                names.append(name)
        return names

    def scan(self, tokens, fuzzy=True):
        lowered = [t.lower() for t in tokens]
        taken = set()
        found = []
        for name in sorted(self.graph.nodes, key=lambda n: -len(tokenize(n))):
            parts = tokenize(name)
            size = len(parts)
            for i in range(len(tokens) - size + 1):
                span = set(range(i, i + size))
                if span & taken or lowered[i:i + size] != [p.lower() for p in parts]:
                    continue
                # very short names ("A", "B") must be typed exactly, or "a seat" matches
                if len("".join(parts)) <= 2 and tokens[i:i + size] != parts:
                    continue
                taken |= span
                found.append((i, i + size, name))
        if fuzzy:
            found += self.typos(lowered, taken)
        return sorted(found)

    def typos(self, lowered, taken):
        # one to three words that are close to a name once the spaces are ignored,
        # so "sharfi" and "elm o santa" still work. best matches are taken first
        keys = {name: squash(name) for name in self.graph.nodes}
        options = []
        for size in (1, 2, 3):
            for i in range(len(lowered) - size + 1):
                word = "".join(lowered[i:i + size])
                if len(word) < 5 or any(c.isdigit() for c in word):
                    continue
                if size == 1 and word in KNOWN_WORDS:
                    continue  # "leads" is a word, not a typo of Leeds
                for name, key in keys.items():
                    # names with digits are never guessed: Extra1 is not Extra0
                    if any(c.isdigit() for c in key):
                        continue
                    score = SequenceMatcher(None, word, key).ratio()
                    if score >= 0.8:
                        options.append((score, size, i, name))
        found = []
        for score, size, i, name in sorted(options, key=lambda o: (-o[0], o[1])):
            span = set(range(i, i + size))
            if not span & taken:
                taken |= span
                found.append((i, i + size, name))
        return found

    def unknown_names(self, tokens, matches):
        covered = {i for start, end, _ in matches for i in range(start, end)}
        return [t for i, t in enumerate(tokens)
                if i > 0 and i not in covered and t[0].isupper() and not t.isupper()
                and not t.isdigit()]

    def unmatched(self, tokens, matches):
        covered = {i for start, end, _ in matches for i in range(start, end)}
        words = []
        for i, token in enumerate(tokens):
            low = token.lower()
            if (i not in covered and len(token) > 1 and not is_number(token)
                    and low not in KNOWN_WORDS and low not in words):
                words.append(low)
        return words

    def after_word(self, tokens, matches, words):
        # the university named right after one of the words, as in "starting at Sharif"
        lowered = [t.lower() for t in tokens]
        for k, token in enumerate(lowered):
            if token in words:
                for start, _, name in matches:
                    if k < start <= k + 3:
                        return name
        return None

    def parse_new_name(self, text):
        called = CALLED.search(text)
        found = called or NEW_NAME.search(text)
        if not found:
            return None, ""
        name = found.group("name").strip()
        if called:
            rest = text[:called.start()] + " " + text[called.end("name"):]
        else:
            rest = found.group("rest")
        first = name.split()[0].lower()
        if first in ("route", "routes", "connection", "link", "road", "bus", "shuttle",
                     "in", "at", "to", "with", "region"):
            return None, ""
        existing = self.find_universities(tokenize(name), fuzzy=False)
        if existing and (len(existing) > 1 or squash(existing[0]) != squash(name)):
            return None, ""
        return name, rest

    def remember(self, kind, names):
        self.last_kind = kind
        self.last_names = list(names)

    # the router

    def dispatch(self, text):
        low = text.lower()
        tokens = tokenize(text)
        matches = self.scan(tokens)
        names = list(dict.fromkeys(name for _, _, name in matches))
        numbers = [float(t) for t in tokens if is_number(t)]
        planner = self.planner

        def has(pattern):
            return re.search(pattern, low) is not None

        if re.fullmatch(r"(hi|hello|hey|yo|hola|good (morning|evening))\W*", low):
            return "Hi! Ask me about routes, trips or reservations. Type help for examples."
        if re.fullmatch(r"(thanks|thank you|thx|cheers)\W*", low):
            return "You're welcome."
        if has(r"\b(help|what can you do|commands|examples)\b"):
            return HELP
        if has(r"\b(undo|revert)\b") or re.fullmatch(r"(take that back|go back)\W*", low):
            return planner.undo()

        # follow-ups that lean on the previous answer
        if self.last_names:
            if len(names) == 1 and has(r"\bfrom\s+(there|it|here)\b"):
                names = [self.last_names[-1], names[0]]
            elif not names and has(r"\b(it|there|that one|this one|the same one)\b") \
                    and has(r"\b(connected|neighbou?rs?|links?|about|remove|delete|info)\b"):
                names = [self.last_names[-1]]
            elif len(names) == 1 and self.last_kind and has(r"^(and\s+)?(what|how) about\b"):
                follow = self.follow_up(names[0])
                if follow:
                    return follow

        skip_check = has(r"\b(add|create|insert|reserve|book|cancel|help)\b")
        about_names = has(r"\b(route|path|way|trip|visit|connect|remove|delete|"
                          r"capacity|seats?|distance)\b")
        if not skip_check and (names or about_names):
            unknown = self.unknown_names(tokens, matches)
            if unknown:
                return (f"I don't know {', '.join(unknown)}. "
                        f"The universities I know: {', '.join(self.graph.nodes)}.")
        extra = self.unmatched(tokens, matches)
        ignored = f" (I ignored: {', '.join(extra)}.)" if extra else ""

        if has(r"\bcancel\b"):
            return self.cancel(text, names)
        if has(r"\b(reserve|book)\b"):
            return self.reserve(text, names)
        if has(r"\b(capacity|seats?)\b"):
            if len(names) != 2:
                return self.need_names("change the seats of a route", 2, names, extra)
            if numbers and has(r"\b(set|change|make|update|give|put|should|has|have)\b"):
                return planner.set_capacity(*names, numbers[0])
            return planner.seat_report(*names)
        if has(r"reservation|booked|bookings|passengers|who is on") and len(names) == 2:
            return planner.seat_report(*names)

        if has(r"\b(remove|delete|drop)\b"):
            if len(names) != 1:
                return self.need_names("remove a university", 1, names, extra)
            return self.ask_remove(names)

        new_name, rest = (None, "")
        if has(r"\b(add|create|insert)\b"):
            new_name, rest = self.parse_new_name(text)
        if new_name:
            return self.add_university(new_name, rest)
        connect_verb = has(r"\b(connect|link|join)\b") or (
            has(r"\b(add|create|set|change|update|make)\b")
            and has(r"\b(route|connection|link|road|weight|distance)\b"))
        if connect_verb:
            if len(names) != 2:
                return self.need_names("add a route", 2, names, extra)
            if not numbers:
                return f"What weight should the route between {names[0]} and {names[1]} have?"
            return planner.connect(*names, numbers[0])
        if len(names) == 2 and not numbers and has(r"\b(weight|direct(ly)?)\b"):
            return planner.direct_weight(*names)

        if not self.graph:
            return "There are no universities. Add one first."
        if has(r"matrix|heat ?map|all pairs|every pair|all distances|"
               r"distances between (all|every)"):
            return planner.distance_table()
        if has(r"region") and has(r"\bmst\b|spanning|tree|scalable|large"):
            return planner.region_tree()
        if has(r"\bmst\b|\btree\b|spanning|cheapest (network|way to connect)|routes? (should|to|do) (we )?keep"):
            return planner.spanning_tree()
        if has(r"\b(trip|tour|visit|visiting|itinerary|tsp|salesman|stops)\b") and len(names) >= 2:
            start = self.after_word(tokens, matches, ("start", "starting", "begin", "beginning"))
            end = self.after_word(tokens, matches, ("end", "ending", "finish", "finishing"))
            answer = planner.trip(names, start, end)
            self.remember("trip", names)
            return answer + ("\n" + ignored.strip() if extra else "")
        if len(names) == 2:
            answer = planner.shortest_path(*names, animate=has(r"\b(animate|animation)\b"))
            self.remember("path", names)
            return answer + ignored
        if len(names) > 2:
            return ("For a route I need two universities. "
                    "Say 'trip' if you want to visit several.")
        if has(r"\b(draw|show|plot|display|picture)\b") and has(r"\b(graph|network|map|everything)\b"):
            return planner.show_network()
        if len(names) == 1:
            asks_route = has(r"\b(get|go|travel|route|way|path|distance|far)\b")
            if asks_route and not has(r"connect|neighbo|link|about"):
                return self.need_names("find a route", 2, names, extra,
                                       example="from Sharif to Beheshti")
            self.remember("describe", names)
            return planner.describe(names[0]) + ignored
        if has(r"\b(list|universities|campuses|network|routes|connections|how many)\b"):
            return planner.list_all()
        return self.not_understood(text, tokens)

    def follow_up(self, name):
        planner = self.planner
        if self.last_kind == "path":
            answer = planner.shortest_path(self.last_names[0], name)
            self.remember("path", [self.last_names[0], name])
            return answer
        if self.last_kind == "describe":
            self.remember("describe", [name])
            return planner.describe(name)
        if self.last_kind == "trip":
            stops = self.last_names + [name]
            answer = planner.trip(stops)
            self.remember("trip", stops)
            return answer
        return None

    def need_names(self, what, wanted, names, extra, example=None):
        found = f"I found {', '.join(names)}" if names else "I did not find any"
        count = {1: "one university", 2: "two universities"}[wanted]
        message = f"To {what} I need {count} I know. {found}."
        if extra:
            message += f" I could not match: {', '.join(extra)}."
        message += f" The universities I know: {', '.join(self.graph.nodes)}."
        if example:
            message += f" For example: '{example}'."
        return message

    def not_understood(self, text, tokens):
        self.misses.append(text)
        if self.on_miss:
            self.on_miss(text)
        words = {t.lower() for t in tokens}
        best = max(SUGGESTIONS, key=lambda s: len(words & s[0]))
        if not words & best[0]:
            return "I didn't get that. Type help to see what I can do."
        known = self.planner.names() + ["Sharif", "Tehran", "Beheshti"]
        a, b, c = known[:3]
        return f"I didn't get that. Did you mean something like '{best[1].format(a=a, b=b, c=c)}'?"

    # actions that need a little parsing

    def add_university(self, name, rest):
        region = ""
        for pattern in REGION:
            found = pattern.search(rest)
            if found:
                region = found.group("r")
                rest = rest.replace(found.group(0), " ")
                break

        rest_tokens = tokenize(rest)
        targets = self.find_universities(rest_tokens)
        weights = [float(t) for t in rest_tokens if is_number(t)]
        if targets and len(weights) != len(targets):
            raise ValueError(
                f"I found {len(targets)} connection(s) but {len(weights)} weight(s). "
                "Give one weight per connection, e.g. 'connected to Tehran 5 and Sharif 3'.")

        answer = self.planner.add_university(name, region, list(zip(targets, weights)))
        if not targets:
            answer += f" Connect it, e.g. 'connect {tidy(name)} and Tehran with weight 4'."
        return answer

    def ask_remove(self, names):
        name = names[0]
        self.pending = name
        routes = self.graph.degree[name]
        return f"Remove {name} and its {routes} route{'' if routes == 1 else 's'}? (yes/no)"

    def student_in(self, text, pattern):
        found = pattern.search(text)
        who = found.group("s").strip() if found else ""
        if who.lower() in NOT_A_STUDENT or self.find_universities(tokenize(who), fuzzy=False):
            return ""
        return who

    def reserve(self, text, names):
        if len(names) != 2:
            return ("Which route? Name two universities, e.g. "
                    "'reserve a seat for Sara on Sharif-Tehran priority 1'.")
        self.planner.direct_route(*names)
        student = STUDENT.search(text)
        if not student:
            return "Who is the seat for? Say 'for <name>'."
        priority = PRIORITY.search(text)
        if not priority:
            return "What priority? Add 'priority N' (a lower number is served first)."
        return self.planner.reserve(*names, student.group("s"), int(priority.group(1)))

    def cancel(self, text, names):
        if len(names) != 2:
            return ("Which route? Name two universities, e.g. "
                    "'cancel Sara's seat on Sharif-Tehran'.")
        self.planner.direct_route(*names)
        who = self.student_in(text, STUDENT) or self.student_in(text, CANCEL)
        if not who:
            return "Whose reservation? Say e.g. 'cancel Sara's seat on Sharif-Tehran'."
        return self.planner.cancel_reservation(*names, who)
