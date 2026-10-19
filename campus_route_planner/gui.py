import math
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from .assistant import Assistant
from .graph_data import DEFAULT_SAVE_PATH, UniversityGraph
from .planner import Planner, positive
from .reservation_system import ReservationSystem
from .tsp_solver import MAX_CITIES

PAPER = "#f2f4f3"
PANEL = "#ffffff"
INK = "#1d2830"
MUTED = "#5b6a74"
LINE = "#d2d9d7"
BLUE = "#1b5aa6"
BLUE_DARK = "#154a8a"
SOFT = "#e3ecf6"
RED = "#b3261e"

CHIPS = ["What can you do?", "Which routes should we keep?",
         "Show the distance matrix", "List the universities"]


def first_available(wanted, fallback):
    have = set(tkfont.families())
    return next((name for name in wanted if name in have), fallback)


def number(text, label):
    try:
        value = float(str(text).strip())
    except ValueError:
        raise ValueError(f"{label} must be a number.") from None
    if not math.isfinite(value):
        raise ValueError(f"{label} must be a number.")
    return value


def whole(text, label):
    value = number(text, label)
    if value != int(value):
        raise ValueError(f"{label} must be a whole number.")
    return int(value)


class WeightDialog(tk.Toplevel):
    
    def __init__(self, parent, name, others, ui_font):
        super().__init__(parent, background=PANEL)
        self.title(f"Connect {name}")
        self.transient(parent)
        self.resizable(False, False)
        self.result = None
        self.fields = {}

        ttk.Label(self, style="Panel.TLabel", wraplength=340, justify="left",
                  text=f"{name} has no connections. Enter a weight for each university you "
                       "want to compare. It will be connected to the cheapest one.",
                  ).grid(row=0, column=0, columnspan=2, padx=16, pady=(16, 8), sticky="w")

        area = tk.Canvas(self, height=min(len(others), 7) * 34, width=320,
                         highlightthickness=0, background=PANEL)
        inner = ttk.Frame(area, style="Panel.TFrame")
        area.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: area.configure(scrollregion=area.bbox("all")))
        area.grid(row=1, column=0, padx=(16, 0), sticky="nsew")
        scroll = ttk.Scrollbar(self, orient="vertical", command=area.yview)
        scroll.grid(row=1, column=1, sticky="ns", padx=(0, 16))
        area.configure(yscrollcommand=scroll.set)

        for row, other in enumerate(others):
            ttk.Label(inner, text=other, style="Panel.TLabel", width=24).grid(
                row=row, column=0, sticky="w", pady=3)
            self.fields[other] = tk.StringVar()
            ttk.Entry(inner, textvariable=self.fields[other], width=8).grid(row=row, column=1)

        self.message = ttk.Label(self, style="Error.TLabel", text="")
        self.message.grid(row=2, column=0, columnspan=2, padx=16, sticky="w")
        buttons = ttk.Frame(self, style="Panel.TFrame")
        buttons.grid(row=3, column=0, columnspan=2, padx=16, pady=14, sticky="e")
        ttk.Button(buttons, text="Skip", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Connect", style="Accent.TButton",
                   command=self.accept).pack(side="right")
        self.bind("<Escape>", lambda e: self.destroy())
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.grab_set()
        self.wait_window()

    def accept(self):
        weights = {}
        for other, var in self.fields.items():
            text = var.get().strip()
            if not text:
                continue
            try:
                weights[other] = float(text)
            except ValueError:
                self.message.configure(text=f"The weight for {other} must be a number.")
                return
        if not weights:
            self.message.configure(text="Enter at least one weight, or skip.")
            return
        self.result = weights
        self.destroy()


class App(tk.Tk):
    def __init__(self, save_path=DEFAULT_SAVE_PATH, uni=None):
        super().__init__()
        self.title("Campus Route Planner")
        self.geometry("1280x780")
        self.minsize(1120, 720)
        self.configure(background=PAPER)

        self.ui_font = first_available(
            ["Segoe UI", "Helvetica Neue", "Noto Sans", "DejaVu Sans", "Arial"], "TkDefaultFont")
        self.mono_font = first_available(
            ["Cascadia Mono", "Consolas", "Menlo", "DejaVu Sans Mono", "Courier New"], "TkFixedFont")
        self.make_styles()

        uni = uni or UniversityGraph()
        loaded = bool(save_path) and uni.load(save_path)
        self.figure = Figure(figsize=(7, 5), dpi=100, facecolor=PANEL)
        self.planner = Planner(uni, ReservationSystem(), figure=self.figure, save_path=save_path,
                               on_draw=self.redraw, on_change=self.refresh)
        self.miss_log = Path(save_path).with_name("unrecognised.txt") if save_path else None
        self.assistant = Assistant(self.planner, on_miss=self.log_miss)
        self.history = []
        self.history_at = 0
        self.pending_links = []

        self.build_left()
        self.build_right()
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, minsize=470)
        self.rowconfigure(0, weight=1)

        self.refresh()
        self.planner.show_network()
        self.say(("Loaded your saved network. " if loaded else "") +
                 f"{len(self.planner.names())} universities on the map. Pick something on "
                 "the right, or ask the assistant.")
        self.chat_say("Ask about routes, trips, seats or changes to the network. "
                      "Type help to see examples.", mine=False)
        self.chat_entry.focus_set()
        self.protocol("WM_DELETE_WINDOW", self.close)

    

    def make_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        ui = (self.ui_font, 10)
        style.configure(".", background=PAPER, foreground=INK, font=ui, bordercolor=LINE,
                        focuscolor=SOFT)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=PAPER, foreground=INK)
        style.configure("Panel.TLabel", background=PANEL, foreground=INK)
        style.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=(self.ui_font, 9))
        style.configure("Error.TLabel", background=PANEL, foreground=RED)
        edge = "#b3c0bc"
        style.configure("TButton", background=PANEL, padding=(11, 6), bordercolor=edge,
                        lightcolor=edge, darkcolor=edge)
        style.map("TButton", background=[("active", SOFT), ("pressed", SOFT)])
        style.configure("Tool.TButton", padding=(9, 6))
        style.configure("Accent.TButton", background=BLUE, foreground="#ffffff",
                        bordercolor=BLUE, lightcolor=BLUE, darkcolor=BLUE)
        style.map("Accent.TButton", background=[("active", BLUE_DARK), ("pressed", BLUE_DARK)])
        style.configure("Chip.TButton", background=SOFT, padding=(9, 4), bordercolor=SOFT,
                        lightcolor=SOFT, darkcolor=SOFT, font=(self.ui_font, 9))
        style.map("Chip.TButton", background=[("active", "#d3e2f3")])
        style.configure("TNotebook", background=PAPER, borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure("TNotebook.Tab", padding=(16, 8), background=PAPER, foreground=MUTED,
                        borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", PANEL)], foreground=[("selected", INK)])
        style.configure("TLabelframe", background=PANEL, bordercolor=LINE)
        style.configure("TLabelframe.Label", background=PANEL, foreground=INK,
                        font=(self.ui_font, 10, "bold"))
        style.configure("TEntry", fieldbackground=PANEL, bordercolor=LINE, padding=4)
        style.configure("TCombobox", fieldbackground=PANEL, background=PANEL, bordercolor=LINE,
                        padding=4, arrowsize=15, arrowcolor=MUTED)
        style.map("TEntry", bordercolor=[("focus", BLUE)])
        style.map("TCombobox", bordercolor=[("focus", BLUE)],
                  fieldbackground=[("readonly", PANEL)])
        style.configure("TSpinbox", fieldbackground=PANEL, bordercolor=LINE, padding=4,
                        arrowsize=13, arrowcolor=MUTED)
        self.option_add("*TCombobox*Listbox.font", ui)

    

    def build_left(self):
        left = ttk.Frame(self, padding=(16, 16, 8, 16))
        left.grid(row=0, column=0, sticky="nsew")
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)

        bar = ttk.Frame(left)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        views = [("Network", self.planner.show_network), ("Spanning tree", self.planner.spanning_tree),
                 ("Regions", self.planner.region_tree), ("Distances", self.planner.distance_table)]
        for text, action in views:
            ttk.Button(bar, text=text, style="Tool.TButton",
                       command=lambda a=action: self.attempt(a)).pack(side="left", padx=(0, 6))
        ttk.Button(bar, text="Save picture", style="Tool.TButton",
                   command=self.save_picture).pack(side="right")
        ttk.Button(bar, text="Undo", style="Tool.TButton",
                   command=lambda: self.attempt(self.planner.undo)).pack(side="right", padx=(0, 6))

        frame = tk.Frame(left, background=LINE, padx=1, pady=1)
        frame.grid(row=1, column=0, sticky="nsew")
        self.canvas = FigureCanvasTkAgg(self.figure, master=frame)
        widget = self.canvas.get_tk_widget()
        widget.configure(highlightthickness=0, background=PANEL)
        widget.pack(fill="both", expand=True)

        holder = ttk.Frame(left)
        holder.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        holder.columnconfigure(0, weight=1)
        self.result = tk.Text(holder, height=6, wrap="word", font=(self.mono_font, 10),
                              background=PANEL, foreground=INK, relief="flat", padx=12, pady=9,
                              highlightthickness=1, highlightbackground=LINE, state="disabled",
                              borderwidth=0, cursor="arrow")
        self.result.tag_configure("error", foreground=RED)
        scroll = ttk.Scrollbar(holder, command=self.result.yview)
        self.result.configure(yscrollcommand=scroll.set)
        self.result.grid(row=0, column=0, sticky="ew")
        scroll.grid(row=0, column=1, sticky="ns")

    def build_right(self):
        right = ttk.Frame(self, padding=(8, 16, 16, 16))
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        tabs = ttk.Notebook(right, width=450)
        tabs.grid(row=0, column=0, sticky="nsew")
        self.tabs = tabs
        self.name_boxes = []
        self.optional_boxes = []

        self.chat_tab = self.page(tabs, "Chat")
        self.routes_tab = self.page(tabs, "Routes")
        self.network_tab = self.page(tabs, "Network")
        self.seats_tab = self.page(tabs, "Seats")
        self.build_chat()
        self.build_routes()
        self.build_network()
        self.build_seats()

    def page(self, tabs, title):
        frame = ttk.Frame(tabs, style="Panel.TFrame", padding=14)
        frame.columnconfigure(0, weight=1)
        tabs.add(frame, text=title)
        return frame

    def box(self, parent, variable=None, width=20, editable=False):
        combo = ttk.Combobox(parent, textvariable=variable, width=width,
                             state="normal" if editable else "readonly", font=(self.ui_font, 10))
        if not editable:
            self.name_boxes.append(combo)
        return combo

    def section(self, parent, title, row):
        group = ttk.Labelframe(parent, text=title, padding=12)
        group.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        group.columnconfigure(1, weight=1)
        return group

    def label(self, parent, text, row, column=0, muted=False):
        style = "Muted.TLabel" if muted else "Panel.TLabel"
        label = ttk.Label(parent, text=text, style=style)
        label.grid(row=row, column=column, sticky="w", padx=(0, 10), pady=4)
        return label

    

    def build_chat(self):
        tab = self.chat_tab
        tab.rowconfigure(0, weight=1)
        holder = ttk.Frame(tab, style="Panel.TFrame")
        holder.grid(row=0, column=0, sticky="nsew")
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(0, weight=1)
        self.transcript = tk.Text(holder, wrap="word", font=(self.ui_font, 10), background=PANEL,
                                  foreground=INK, relief="flat", borderwidth=0, padx=4, pady=4,
                                  state="disabled", cursor="arrow", width=40)
        scroll = ttk.Scrollbar(holder, command=self.transcript.yview)
        self.transcript.configure(yscrollcommand=scroll.set)
        self.transcript.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        gap = dict(spacing1=7, spacing3=7, lmargin1=10, lmargin2=10, rmargin=10)
        self.transcript.tag_configure("mine", background=SOFT, foreground=INK, **gap)
        self.transcript.tag_configure("theirs", **gap)
        self.transcript.tag_configure("table", font=(self.mono_font, 9), **gap)

        chips = ttk.Frame(tab, style="Panel.TFrame")
        chips.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        for i, text in enumerate(CHIPS):
            ttk.Button(chips, text=text, style="Chip.TButton",
                       command=lambda t=text: self.send(t)).grid(
                row=i // 2, column=i % 2, sticky="w", padx=(0, 6), pady=3)

        entry_row = ttk.Frame(tab, style="Panel.TFrame")
        entry_row.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        entry_row.columnconfigure(0, weight=1)
        self.chat_entry = ttk.Entry(entry_row, font=(self.ui_font, 10))
        self.chat_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.chat_entry.bind("<Return>", lambda e: self.send())
        self.chat_entry.bind("<Up>", lambda e: self.recall(-1))
        self.chat_entry.bind("<Down>", lambda e: self.recall(1))
        ttk.Button(entry_row, text="Send", style="Accent.TButton", command=self.send).grid(
            row=0, column=1)

    def chat_say(self, text, mine):
        columns = any(line.startswith("  ") for line in text.splitlines())
        tag = "mine" if mine else ("table" if columns else "theirs")
        self.transcript.configure(state="normal")
        self.transcript.insert("end", text + "\n", tag)
        self.transcript.configure(state="disabled")
        self.transcript.see("end")

    def send(self, text=None):
        text = (text if text is not None else self.chat_entry.get()).strip()
        if not text:
            return
        self.chat_entry.delete(0, "end")
        self.history.append(text)
        self.history_at = len(self.history)
        self.chat_say(text, mine=True)
        answer = self.assistant.reply(text)
        if answer:
            self.chat_say(answer, mine=False)
            self.say(answer)

    def recall(self, step):
        if not self.history:
            return "break"
        self.history_at = max(0, min(len(self.history), self.history_at + step))
        self.chat_entry.delete(0, "end")
        if self.history_at < len(self.history):
            self.chat_entry.insert(0, self.history[self.history_at])
        return "break"

    

    def build_routes(self):
        tab = self.routes_tab
        path = self.section(tab, "Shortest path", 0)
        self.source, self.target = tk.StringVar(), tk.StringVar()
        self.label(path, "From", 0)
        self.box(path, self.source).grid(row=0, column=1, sticky="ew", pady=4)
        self.label(path, "To", 1)
        self.box(path, self.target).grid(row=1, column=1, sticky="ew", pady=4)
        row = ttk.Frame(path, style="Panel.TFrame")
        row.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Button(row, text="Find path", style="Accent.TButton", command=self.find_path).pack(
            side="left")
        ttk.Button(row, text="Animate", command=lambda: self.find_path(animate=True)).pack(
            side="left", padx=(8, 0))

        trip = self.section(tab, "Best trip", 1)
        self.label(trip, f"Choose the stops (up to {MAX_CITIES}). Hold Ctrl or Shift to pick several.",
                   0, muted=True).grid(columnspan=2)
        holder = ttk.Frame(trip, style="Panel.TFrame")
        holder.grid(row=1, column=0, columnspan=2, sticky="ew")
        holder.columnconfigure(0, weight=1)
        self.stops = tk.Listbox(holder, selectmode="extended", height=6, exportselection=False,
                                font=(self.ui_font, 10), relief="flat", borderwidth=0,
                                highlightthickness=1, highlightbackground=LINE,
                                highlightcolor=BLUE, selectbackground=SOFT, selectforeground=INK,
                                activestyle="none")
        bar = ttk.Scrollbar(holder, command=self.stops.yview)
        self.stops.configure(yscrollcommand=bar.set)
        self.stops.grid(row=0, column=0, sticky="ew")
        bar.grid(row=0, column=1, sticky="ns")
        self.trip_start, self.trip_end = tk.StringVar(value="Any"), tk.StringVar(value="Any")
        for row, (text, variable) in enumerate((("Start at", self.trip_start),
                                                ("End at", self.trip_end)), start=2):
            self.label(trip, text, row)
            combo = ttk.Combobox(trip, textvariable=variable, state="readonly", width=20,
                                 font=(self.ui_font, 10))
            combo.grid(row=row, column=1, sticky="ew", pady=4)
            self.optional_boxes.append(combo)
        ttk.Button(trip, text="Plan trip", style="Accent.TButton", command=self.plan_trip).grid(
            row=4, column=0, sticky="w", pady=(8, 0))

    def find_path(self, animate=False):
        self.attempt(lambda: self.planner.shortest_path(
            self.need(self.source), self.need(self.target), animate))

    def plan_trip(self):
        names = self.planner.names()
        chosen = [names[i] for i in self.stops.curselection()]
        start, end = (v.get() if v.get() != "Any" else None for v in (self.trip_start, self.trip_end))
        self.attempt(lambda: self.planner.trip(chosen, start, end))

    

    def build_network(self):
        tab = self.network_tab
        add = self.section(tab, "Add a university", 0)
        self.new_name, self.new_region = tk.StringVar(), tk.StringVar()
        self.new_lat, self.new_lon = tk.StringVar(), tk.StringVar()
        self.link_target, self.link_weight = tk.StringVar(), tk.StringVar()
        self.label(add, "Name", 0)
        ttk.Entry(add, textvariable=self.new_name, font=(self.ui_font, 10)).grid(
            row=0, column=1, sticky="ew", pady=4)
        self.label(add, "Region", 1)
        self.region_box = self.box(add, self.new_region, editable=True)
        self.region_box.grid(row=1, column=1, sticky="ew", pady=4)
        self.label(add, "Lat, lon", 2)
        place = ttk.Frame(add, style="Panel.TFrame")
        place.grid(row=2, column=1, sticky="w", pady=4)
        ttk.Entry(place, textvariable=self.new_lat, width=9, font=(self.ui_font, 10)).pack(side="left")
        ttk.Entry(place, textvariable=self.new_lon, width=9, font=(self.ui_font, 10)).pack(
            side="left", padx=(6, 0))
        ttk.Label(place, text="optional", style="Muted.TLabel").pack(side="left", padx=(10, 0))
        self.label(add, "Connect to", 3)
        self.box(add, self.link_target).grid(row=3, column=1, sticky="ew", pady=4)
        self.label(add, "Weight", 4)
        link = ttk.Frame(add, style="Panel.TFrame")
        link.grid(row=4, column=1, sticky="w", pady=4)
        ttk.Entry(link, textvariable=self.link_weight, width=8, font=(self.ui_font, 10)).pack(
            side="left")
        ttk.Button(link, text="Add link", command=self.add_link).pack(side="left", padx=(8, 0))

        self.links = tk.Listbox(add, height=2, exportselection=False, font=(self.ui_font, 10),
                                relief="flat", borderwidth=0, highlightthickness=1,
                                highlightbackground=LINE, highlightcolor=BLUE,
                                selectbackground=SOFT, selectforeground=INK, activestyle="none")
        self.links.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        row = ttk.Frame(add, style="Panel.TFrame")
        row.grid(row=6, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(row, text="Add university", style="Accent.TButton",
                   command=self.add_university).pack(side="left")
        ttk.Button(row, text="Remove link", command=self.remove_link).pack(side="left", padx=(8, 0))

        route = self.section(tab, "Change a route", 1)
        self.route_a, self.route_b, self.route_weight = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.label(route, "Between", 0)
        pair = ttk.Frame(route, style="Panel.TFrame")
        pair.grid(row=0, column=1, sticky="ew", pady=4)
        pair.columnconfigure((0, 1), weight=1)
        self.box(pair, self.route_a, width=10).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.box(pair, self.route_b, width=10).grid(row=0, column=1, sticky="ew")
        self.label(route, "Weight", 1)
        ttk.Entry(route, textvariable=self.route_weight, width=8, font=(self.ui_font, 10)).grid(
            row=1, column=1, sticky="w", pady=4)
        ttk.Button(route, text="Set route", style="Accent.TButton", command=self.set_route).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        remove = self.section(tab, "Remove or start over", 2)
        self.doomed = tk.StringVar()
        self.box(remove, self.doomed).grid(row=0, column=0, sticky="ew", pady=4)
        remove.columnconfigure(0, weight=1)
        ttk.Button(remove, text="Remove", command=self.remove_university).grid(
            row=0, column=1, padx=(8, 0))

        self.label(remove, "Or go back to the 27 UK universities.", 1, muted=True)
        ttk.Button(remove, text="Start over", command=self.reset_network).grid(
            row=1, column=1, padx=(8, 0), pady=(6, 0))

    def add_link(self):
        def add():
            other = self.need(self.link_target)
            weight = positive(number(self.link_weight.get(), "Weight"))
            if any(o == other for o, _ in self.pending_links):
                raise ValueError(f"{other} is already in the list.")
            self.pending_links.append((other, weight))
            self.links.insert("end", f"{other}  ({weight:g})")
            self.link_weight.set("")
            return f"Link to {other} added. Press Add university when you are done."
        self.attempt(add)

    def remove_link(self):
        for index in reversed(self.links.curselection()):
            self.links.delete(index)
            del self.pending_links[index]

    def add_university(self):
        def add():
            name = self.new_name.get()
            place = self.location()
            text = self.planner.add_university(name, self.new_region.get(), self.pending_links, place)
            linked = bool(self.pending_links)
            self.pending_links.clear()
            self.links.delete(0, "end")
            self.new_name.set("")
            self.new_lat.set("")
            self.new_lon.set("")
            if not linked and len(self.planner.names()) > 1:
                added = self.planner.names()[-1]
                others = [n for n in self.planner.names() if n != added]
                weights = self.ask_weights(added, others)
                if weights:
                    text += " " + self.planner.connect_cheapest(added, weights)
            return text
        self.attempt(add)

    def location(self):
        lat, lon = self.new_lat.get().strip(), self.new_lon.get().strip()
        if not lat and not lon:
            return None
        if not lat or not lon:
            raise ValueError("Give both latitude and longitude, or leave both empty.")
        return (number(lat, "Latitude"), number(lon, "Longitude"))

    def ask_weights(self, name, others):
        return WeightDialog(self, name, others, self.ui_font).result

    def set_route(self):
        self.attempt(lambda: self.planner.connect(
            self.need(self.route_a), self.need(self.route_b),
            number(self.route_weight.get(), "Weight")))

    def remove_university(self):
        def remove():
            name = self.need(self.doomed)
            routes = self.planner.graph.degree[name]
            if not self.confirm("Remove university",
                                f"Remove {name} and its {routes} route{'' if routes == 1 else 's'}?"):
                return f"{name} was kept."
            self.doomed.set("")
            return self.planner.remove(name)
        self.attempt(remove)

    def reset_network(self):
        def reset():
            if not self.confirm("Start over", "Replace the current network with the sample "
                                "network? You can undo this."):
                return "The network was left as it is."
            return self.planner.reset_to_sample()
        self.attempt(reset)

    def confirm(self, title, text):
        return messagebox.askyesno(title, text, parent=self)

    

    def build_seats(self):
        tab = self.seats_tab
        route = self.section(tab, "Route", 0)
        self.seat_a, self.seat_b = tk.StringVar(), tk.StringVar()
        self.label(route, "From", 0)
        self.box(route, self.seat_a).grid(row=0, column=1, sticky="ew", pady=4)
        self.label(route, "To", 1)
        self.box(route, self.seat_b).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(route, text="Show reservations", command=self.show_seats).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        capacity = self.section(tab, "Capacity", 1)
        self.capacity = tk.StringVar(value="2")
        self.label(capacity, "Seats", 0)
        ttk.Spinbox(capacity, from_=0, to=99, textvariable=self.capacity, width=6).grid(
            row=0, column=1, sticky="w", pady=4)
        ttk.Button(capacity, text="Set capacity", command=self.set_capacity).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        reserve = self.section(tab, "Reserve a seat", 2)
        self.student, self.priority = tk.StringVar(), tk.StringVar(value="1")
        self.label(reserve, "Student", 0)
        ttk.Entry(reserve, textvariable=self.student, font=(self.ui_font, 10)).grid(
            row=0, column=1, sticky="ew", pady=4)
        self.label(reserve, "Priority", 1)
        ttk.Spinbox(reserve, from_=-99, to=99, textvariable=self.priority, width=6).grid(
            row=1, column=1, sticky="w", pady=4)
        self.label(reserve, "A lower number is served first.", 2, column=1, muted=True)
        row = ttk.Frame(reserve, style="Panel.TFrame")
        row.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Button(row, text="Reserve seat", style="Accent.TButton",
                   command=self.reserve_seat).pack(side="left")
        ttk.Button(row, text="Cancel reservation", command=self.cancel_seat).pack(
            side="left", padx=(8, 0))

    def show_seats(self):
        self.attempt(lambda: self.planner.seat_report(self.need(self.seat_a), self.need(self.seat_b)))

    def set_capacity(self):
        self.attempt(lambda: self.planner.set_capacity(
            self.need(self.seat_a), self.need(self.seat_b), whole(self.capacity.get(), "Seats")))

    def reserve_seat(self):
        self.attempt(lambda: self.planner.reserve(
            self.need(self.seat_a), self.need(self.seat_b), self.student.get(),
            whole(self.priority.get(), "Priority")))

    def cancel_seat(self):
        self.attempt(lambda: self.planner.cancel_reservation(
            self.need(self.seat_a), self.need(self.seat_b), self.student.get()))

    

    def need(self, variable):
        value = variable.get().strip()
        if not value:
            raise ValueError("Choose a university first.")
        return value

    def attempt(self, action):
        try:
            self.say(action())
        except ValueError as err:
            self.say(str(err), error=True)

    def say(self, text, error=False):
        self.result.configure(state="normal")
        self.result.delete("1.0", "end")
        self.result.insert("1.0", text, "error" if error else "")
        self.result.configure(state="disabled")

    def log_miss(self, text):
        if self.miss_log is None:
            return
        try:
            self.miss_log.parent.mkdir(parents=True, exist_ok=True)
            with open(self.miss_log, "a", encoding="utf-8") as handle:
                handle.write(text + "\n")
        except OSError:
            pass

    def redraw(self):
        self.canvas.draw_idle()

    def refresh(self):
        names = self.planner.names()
        for combo in self.name_boxes:
            combo.configure(values=names)
            if combo.get() not in names:
                combo.set("")
        for combo in self.optional_boxes:
            combo.configure(values=["Any"] + names)
            if combo.get() not in names:
                combo.set("Any")
        self.region_box.configure(values=self.planner.region_names())
        self.stops.delete(0, "end")
        for name in names:
            self.stops.insert("end", name)
        if names and not self.source.get():
            self.source.set(names[0])
            self.target.set(names[-1])

    def save_picture(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".png",
                                            filetypes=[("PNG image", "*.png")],
                                            initialfile="campus-routes.png")
        if path:
            self.figure.savefig(path, dpi=150, bbox_inches="tight")
            self.say(f"Saved the picture to {path}.")

    def close(self):
        self.planner.stop_animation()
        self.update_idletasks()  
        self.destroy()


def main():
    App().mainloop()
