from __future__ import annotations

import csv
import json
import re
import tkinter as tk
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, colorchooser, simpledialog, ttk
from typing import Any

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.pdfgen import canvas as pdf_canvas

    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False


APP_TITLE = "PixelTracker Desktop"
STORAGE_FILE = Path.home() / ".pixeltracker_db.json"
THEME_FILE = Path.home() / ".pixeltracker_theme.json"
PALETTE = [
    "#e6007e",
    "#2563eb",
    "#f59e0b",
    "#16a34a",
    "#7c3aed",
    "#dc2626",
    "#0891b2",
    "#65a30d",
]


# ---------- Data model ----------


def uid() -> str:
    return f"{int(datetime.now().timestamp() * 1_000_000):x}"[-10:]


def today_iso() -> str:
    return date.today().isoformat()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Repair:
    id: str
    type: str
    date: str
    initials: str
    status: str
    color: str
    note: str
    pixels: list[list[int]] = field(default_factory=list)


@dataclass
class Module:
    id: str
    company: str
    name: str
    sn: str
    width: int
    height: int
    updatedAt: str
    repairs: list[Repair] = field(default_factory=list)


@dataclass
class AppState:
    activeId: str | None
    modules: dict[str, Module] = field(default_factory=dict)


def default_state() -> AppState:
    mid = uid()
    rep = Repair(
        id=uid(),
        type="Pixel",
        date=today_iso(),
        initials="KV",
        status="Open",
        color="#e6007e",
        note="",
        pixels=[[1, 190], [2, 190]],
    )
    mod = Module(
        id=mid,
        company="Bazelmans",
        name="Absen 2.9mm",
        sn="SN 000205",
        width=192,
        height=192,
        updatedAt=now_iso(),
        repairs=[rep],
    )
    return AppState(activeId=mid, modules={mid: mod})


# ---------- App ----------


class PixelTrackerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1520x930")
        self.minsize(1180, 760)

        self.state_data = self.load_state()
        self.selected_pixels: set[tuple[int, int]] = set()
        self.cell_size = 10
        self.last_initials = ""

        self.undo_stack: list[str] = []
        self.redo_stack: list[str] = []

        self.drag_start: tuple[int, int] | None = None
        self.drag_anchor_selection: set[tuple[int, int]] = set()
        self.space_down = False
        self.is_panning = False
        self.pan_origin: tuple[int, int, float, float] | None = None

        self.theme_mode = self.load_theme_mode()
        self.colors = {}

        self.init_style()
        self.build_ui()
        self.apply_theme(self.theme_mode)
        self.bind_shortcuts()
        self.render_all()

    # ---------- Setup ----------

    def init_style(self) -> None:
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.style.configure("Title.TLabel", font=("Helvetica", 13, "bold"))
        self.style.configure("Head.TLabel", font=("Helvetica", 10, "bold"))
        self.style.configure("App.TFrame")
        self.style.configure("Card.TLabelframe", borderwidth=1, relief=tk.SOLID)
        self.style.configure("Card.TLabelframe.Label", font=("Helvetica", 10, "bold"))
        self.style.configure("App.TLabel", font=("Helvetica", 10))
        self.style.configure("Muted.TLabel", font=("Helvetica", 10))
        self.style.configure("Accent.TButton", font=("Helvetica", 10, "bold"))
        self.style.map(
            "Accent.TButton",
            background=[("active", "#c40068")],
            foreground=[("disabled", "#f8d6e8")],
        )

    def build_ui(self) -> None:
        self.build_menu()

        root = ttk.Frame(self, style="App.TFrame")
        root.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)

        root.columnconfigure(0, weight=0)
        root.columnconfigure(1, weight=1)
        root.columnconfigure(2, weight=0)
        root.rowconfigure(0, weight=1)
        root.rowconfigure(1, weight=0)

        self.left = ttk.Frame(root, width=290, style="App.TFrame")
        self.mid = ttk.Frame(root, style="App.TFrame")
        self.right = ttk.Frame(root, width=360, style="App.TFrame")

        self.left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.mid.grid(row=0, column=1, sticky="nsew")
        self.right.grid(row=0, column=2, sticky="nsew", padx=(10, 0))

        self.bottom = ttk.LabelFrame(root, text="Alle modules - database", style="Card.TLabelframe")
        self.bottom.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(12, 0))

        self.build_left_column()
        self.build_middle_column()
        self.build_right_column()
        self.build_bottom_table()

        self.footer = ttk.Label(
            self,
            text="PixelTracker Desktop - data wordt lokaal opgeslagen",
            style="Muted.TLabel",
        )
        self.footer.pack(side=tk.BOTTOM, pady=(0, 8))

    def build_menu(self) -> None:
        menubar = tk.Menu(self)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Opslaan als JSON...", command=self.save_json_as)
        file_menu.add_command(label="Laden van JSON...", command=self.load_json_from)
        file_menu.add_separator()
        file_menu.add_command(label="Reparaties exporteren als CSV...", command=self.export_csv)
        file_menu.add_command(label="A3 export geselecteerde module (PDF)...", command=self.export_selected_a3)
        file_menu.add_command(label="A3 export hele database (PDF)...", command=self.export_database_a3)
        file_menu.add_command(label="Print schermweergave...", command=self.export_canvas_postscript)
        file_menu.add_separator()
        file_menu.add_command(label="Nieuwe lege database", command=self.new_empty_db)
        file_menu.add_command(label="Afsluiten", command=self.on_close)

        menubar.add_cascade(label="Bestand", menu=file_menu)
        self.config(menu=menubar)

    def build_left_column(self) -> None:
        add_card = ttk.LabelFrame(self.left, text="+ Module toevoegen", style="Card.TLabelframe")
        add_card.pack(fill=tk.X)

        def row(parent: ttk.Frame, text: str) -> ttk.Entry:
            ttk.Label(parent, text=text, style="App.TLabel").pack(anchor="w", pady=(8, 3), padx=8)
            entry = ttk.Entry(parent)
            entry.pack(fill=tk.X, padx=8)
            return entry

        self.in_company = row(add_card, "Bedrijf")
        self.in_name = row(add_card, "Naam / label *")
        self.in_width = row(add_card, "Breedte (px) *")
        self.in_width.insert(0, "192")
        self.in_height = row(add_card, "Hoogte (px) *")
        self.in_height.insert(0, "192")
        self.in_sn = row(add_card, "Locatie / SN")

        self.batch_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            add_card,
            text="Batch modus (SN automatisch ophogen)",
            variable=self.batch_var,
        ).pack(anchor="w", padx=8, pady=8)

        ttk.Button(add_card, text="Toevoegen", style="Accent.TButton", command=self.add_module_from_form).pack(
            fill=tk.X, padx=8, pady=(0, 10)
        )

        list_card = ttk.LabelFrame(self.left, text="Database", style="Card.TLabelframe")
        list_card.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.render_module_list())
        ttk.Entry(list_card, textvariable=self.search_var).pack(fill=tk.X, padx=8, pady=8)

        self.module_listbox = tk.Listbox(list_card, activestyle="none")
        self.module_listbox.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.module_listbox.bind("<<ListboxSelect>>", self.on_module_select)

        actions = ttk.Frame(list_card)
        actions.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Button(actions, text="SN bewerken", command=self.edit_sn_active).pack(side=tk.LEFT)
        ttk.Button(actions, text="Verwijderen", command=self.delete_active_module).pack(side=tk.RIGHT)

    def build_middle_column(self) -> None:
        top = ttk.Frame(self.mid, style="App.TFrame")
        top.pack(fill=tk.X)

        title_wrap = ttk.Frame(top, style="App.TFrame")
        title_wrap.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.module_title = ttk.Label(title_wrap, style="Title.TLabel", text="Geen module geselecteerd")
        self.module_title.pack(anchor="w")
        self.module_sub = ttk.Label(title_wrap, text="")
        self.module_sub.pack(anchor="w")

        right_controls = ttk.Frame(top, style="App.TFrame")
        right_controls.pack(side=tk.RIGHT)

        self.theme_btn = ttk.Button(right_controls, text="Donkere modus", command=self.toggle_theme)
        self.theme_btn.pack(side=tk.RIGHT, padx=(8, 0))

        ttk.Label(right_controls, text="Zoom").pack(side=tk.LEFT, padx=(0, 6))
        self.zoom_var = tk.IntVar(value=self.cell_size)
        self.zoom_scale = ttk.Scale(
            right_controls,
            from_=3,
            to=30,
            orient=tk.HORIZONTAL,
            variable=self.zoom_var,
            command=self.on_zoom_change,
            length=170,
        )
        self.zoom_scale.pack(side=tk.LEFT)

        toolbar = ttk.Frame(self.mid, style="App.TFrame")
        toolbar.pack(fill=tk.X, pady=(8, 8))
        self.clear_sel_btn = ttk.Button(toolbar, text="Selectie wissen", command=self.clear_selection)
        self.clear_sel_btn.pack(side=tk.LEFT)
        self.add_repair_btn = ttk.Button(toolbar, text="+ Reparatie (0 px)", style="Accent.TButton", command=self.open_add_repair)
        self.add_repair_btn.pack(side=tk.LEFT, padx=(8, 0))

        hint = ttk.Label(
            self.mid,
            text=(
                "Klik/sleep voor blokselectie, Shift+klik voegt toe, "
                "Ctrl+A = Pixel opgelost, Ctrl+B = Pad opgelost, Esc = selectie wissen"
            ),
            style="Muted.TLabel",
        )
        hint.pack(anchor="w", pady=(0, 8))

        stats = ttk.Frame(self.mid, style="App.TFrame")
        stats.pack(fill=tk.X, pady=(0, 8))
        self.stats_var = tk.StringVar(value="")
        ttk.Label(stats, textvariable=self.stats_var, style="App.TLabel").pack(anchor="w")

        canvas_shell = ttk.Frame(self.mid, style="Card.TLabelframe")
        canvas_shell.pack(fill=tk.BOTH, expand=True)
        canvas_shell.rowconfigure(0, weight=1)
        canvas_shell.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            canvas_shell,
            bg="#f2f2f4",
            highlightthickness=1,
            highlightbackground="#cccccc",
            cursor="crosshair",
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")

        ybar = ttk.Scrollbar(canvas_shell, orient=tk.VERTICAL, command=self.canvas.yview)
        ybar.grid(row=0, column=1, sticky="ns")
        xbar = ttk.Scrollbar(canvas_shell, orient=tk.HORIZONTAL, command=self.canvas.xview)
        xbar.grid(row=1, column=0, sticky="ew")
        self.canvas.configure(xscrollcommand=xbar.set, yscrollcommand=ybar.set)

        self.canvas.bind("<Button-1>", self.on_canvas_down)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_up)
        self.canvas.bind("<MouseWheel>", self.on_canvas_wheel)

    def build_bottom_table(self) -> None:
        cols = ("company", "name", "dim", "sn", "repairs", "open_px", "updated")
        self.mod_tree = ttk.Treeview(self.bottom, columns=cols, show="headings", height=8)
        self.mod_tree.heading("company", text="Company")
        self.mod_tree.heading("name", text="Naam")
        self.mod_tree.heading("dim", text="Afmeting")
        self.mod_tree.heading("sn", text="Locatie / SN")
        self.mod_tree.heading("repairs", text="Reparaties")
        self.mod_tree.heading("open_px", text="Open px")
        self.mod_tree.heading("updated", text="Laatst gewijzigd")

        self.mod_tree.column("company", width=140, anchor=tk.W)
        self.mod_tree.column("name", width=220, anchor=tk.W)
        self.mod_tree.column("dim", width=120, anchor=tk.W)
        self.mod_tree.column("sn", width=220, anchor=tk.W)
        self.mod_tree.column("repairs", width=80, anchor=tk.E)
        self.mod_tree.column("open_px", width=75, anchor=tk.E)
        self.mod_tree.column("updated", width=110, anchor=tk.W)

        self.mod_tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.mod_tree.bind("<Double-1>", self.on_bottom_module_open)

    def build_right_column(self) -> None:
        card = ttk.LabelFrame(self.right, text="Reparaties", style="Card.TLabelframe")
        card.pack(fill=tk.BOTH, expand=True)

        cols = ("type", "date", "initials", "status", "pixels")
        self.rep_tree = ttk.Treeview(card, columns=cols, show="headings", height=18)
        self.rep_tree.heading("type", text="Wat")
        self.rep_tree.heading("date", text="Wanneer")
        self.rep_tree.heading("initials", text="Wie")
        self.rep_tree.heading("status", text="Status")
        self.rep_tree.heading("pixels", text="px")

        self.rep_tree.column("type", width=90, anchor=tk.W)
        self.rep_tree.column("date", width=95, anchor=tk.W)
        self.rep_tree.column("initials", width=65, anchor=tk.W)
        self.rep_tree.column("status", width=85, anchor=tk.W)
        self.rep_tree.column("pixels", width=45, anchor=tk.E)

        self.rep_tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.rep_tree.bind("<Double-1>", self.edit_selected_repair)

        btns = ttk.Frame(card)
        btns.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Button(btns, text="Bewerken", command=self.edit_selected_repair).pack(side=tk.LEFT)
        ttk.Button(btns, text="Verwijderen", command=self.delete_selected_repair).pack(side=tk.RIGHT)

    def bind_shortcuts(self) -> None:
        self.bind_all("<Control-z>", lambda _: self.undo())
        self.bind_all("<Control-Z>", lambda _: self.redo())
        self.bind_all("<Escape>", lambda _: self.clear_selection())
        self.bind_all("<Control-a>", lambda e: self.quick_add_repair(e, "Pixel", "#e6007e"))
        self.bind_all("<Control-b>", lambda e: self.quick_add_repair(e, "Pad", "#2563eb"))
        self.bind_all("<KeyPress-space>", self.on_space_press)
        self.bind_all("<KeyRelease-space>", self.on_space_release)
        self.in_sn.bind("<Return>", lambda _: self.add_module_from_form())
        self.in_name.bind("<Return>", lambda _: self.in_sn.focus_set())
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- Persistence ----------

    def serialize_state(self) -> dict[str, Any]:
        return {
            "activeId": self.state_data.activeId,
            "modules": {
                mid: {
                    "id": m.id,
                    "company": m.company,
                    "name": m.name,
                    "sn": m.sn,
                    "width": m.width,
                    "height": m.height,
                    "updatedAt": m.updatedAt,
                    "repairs": [asdict(r) for r in m.repairs],
                }
                for mid, m in self.state_data.modules.items()
            },
        }

    def deserialize_state(self, payload: dict[str, Any]) -> AppState:
        modules: dict[str, Module] = {}
        raw_mods = payload.get("modules")
        if not isinstance(raw_mods, dict):
            raise ValueError("Ongeldige database structuur")
        for mid, raw in raw_mods.items():
            repairs = []
            for rr in raw.get("repairs", []):
                repairs.append(
                    Repair(
                        id=str(rr.get("id", uid())),
                        type=str(rr.get("type", "Pixel")),
                        date=str(rr.get("date", today_iso())),
                        initials=str(rr.get("initials", "")),
                        status=str(rr.get("status", "Open")),
                        color=str(rr.get("color", "#e6007e")),
                        note=str(rr.get("note", "")),
                        pixels=[list(map(int, p)) for p in rr.get("pixels", [])],
                    )
                )
            modules[mid] = Module(
                id=str(raw.get("id", mid)),
                company=str(raw.get("company", "")),
                name=str(raw.get("name", "")),
                sn=str(raw.get("sn", "")),
                width=int(raw.get("width", 192)),
                height=int(raw.get("height", 192)),
                updatedAt=str(raw.get("updatedAt", now_iso())),
                repairs=repairs,
            )
        active = payload.get("activeId")
        if active not in modules:
            active = next(iter(modules), None)
        return AppState(activeId=active, modules=modules)

    def save_state(self) -> None:
        STORAGE_FILE.write_text(json.dumps(self.serialize_state(), indent=2), encoding="utf-8")

    def load_state(self) -> AppState:
        if not STORAGE_FILE.exists():
            state = default_state()
            STORAGE_FILE.write_text(json.dumps(self.serialize_state_static(state), indent=2), encoding="utf-8")
            return state
        try:
            payload = json.loads(STORAGE_FILE.read_text(encoding="utf-8"))
            return self.deserialize_state(payload)
        except Exception:
            return default_state()

    @staticmethod
    def serialize_state_static(state: AppState) -> dict[str, Any]:
        return {
            "activeId": state.activeId,
            "modules": {
                mid: {
                    "id": m.id,
                    "company": m.company,
                    "name": m.name,
                    "sn": m.sn,
                    "width": m.width,
                    "height": m.height,
                    "updatedAt": m.updatedAt,
                    "repairs": [asdict(r) for r in m.repairs],
                }
                for mid, m in state.modules.items()
            },
        }

    def load_theme_mode(self) -> str:
        if not THEME_FILE.exists():
            return "dark"
        try:
            payload = json.loads(THEME_FILE.read_text(encoding="utf-8"))
            mode = payload.get("mode", "light")
            return "dark" if mode == "dark" else "light"
        except Exception:
            return "light"

    def save_theme_mode(self) -> None:
        THEME_FILE.write_text(json.dumps({"mode": self.theme_mode}), encoding="utf-8")

    def apply_theme(self, mode: str) -> None:
        self.theme_mode = "dark" if mode == "dark" else "light"
        if self.theme_mode == "dark":
            self.colors = {
                "canvas_bg": "#2a2a2f",
                "canvas_grid": "#3c3c42",
                "canvas_major": "#4c4c54",
                "canvas_border": "#4a4a52",
                "empty_text": "#b7b7be",
                "root_bg": "#17171a",
                "panel_bg": "#1f1f23",
                "panel_border": "#333338",
                "text": "#ececf0",
                "muted": "#a0a0a8",
                "accent": "#e6007e",
                "list_bg": "#232327",
                "list_fg": "#ececf0",
                "list_sel": "#331226",
                "hint_fg": "#a0a0a8",
                "tree_head": "#28282d",
                "tree_body": "#222227",
            }
            if hasattr(self, "theme_btn"):
                self.theme_btn.config(text="Lichte modus")
        else:
            self.colors = {
                "canvas_bg": "#eeeeee",
                "canvas_grid": "#d9d9de",
                "canvas_major": "#bcbcc2",
                "canvas_border": "#cccccc",
                "empty_text": "#666666",
                "root_bg": "#f6f6f7",
                "panel_bg": "#ffffff",
                "panel_border": "#dcdce0",
                "text": "#1c1c1e",
                "muted": "#666666",
                "accent": "#e6007e",
                "list_bg": "#ffffff",
                "list_fg": "#1c1c1e",
                "list_sel": "#f4d3e8",
                "hint_fg": "#666666",
                "tree_head": "#f3f3f5",
                "tree_body": "#ffffff",
            }
            if hasattr(self, "theme_btn"):
                self.theme_btn.config(text="Donkere modus")

        try:
            self.style.configure("App.TFrame", background=self.colors["root_bg"])
            self.style.configure(
                "Card.TLabelframe",
                background=self.colors["panel_bg"],
                bordercolor=self.colors["panel_border"],
                relief=tk.SOLID,
                borderwidth=1,
            )
            self.style.configure(
                "Card.TLabelframe.Label",
                background=self.colors["panel_bg"],
                foreground=self.colors["muted"],
            )
            self.style.configure("App.TLabel", background=self.colors["panel_bg"], foreground=self.colors["text"])
            self.style.configure("Muted.TLabel", background=self.colors["root_bg"], foreground=self.colors["muted"])
            self.style.configure("Title.TLabel", background=self.colors["panel_bg"], foreground=self.colors["text"])
            self.style.configure("Head.TLabel", background=self.colors["panel_bg"], foreground=self.colors["muted"])
            self.style.configure(
                "TButton",
                background=self.colors["panel_bg"],
                foreground=self.colors["text"],
                bordercolor=self.colors["panel_border"],
            )
            self.style.map("TButton", background=[("active", self.colors["list_sel"])])
            self.style.configure(
                "Accent.TButton",
                background=self.colors["accent"],
                foreground="#ffffff",
                bordercolor=self.colors["accent"],
            )
            self.style.configure("TCheckbutton", background=self.colors["panel_bg"], foreground=self.colors["text"])
            self.style.configure("TEntry", fieldbackground=self.colors["list_bg"], foreground=self.colors["text"])
            self.style.configure(
                "Treeview",
                background=self.colors["tree_body"],
                fieldbackground=self.colors["tree_body"],
                foreground=self.colors["text"],
                bordercolor=self.colors["panel_border"],
            )
            self.style.configure(
                "Treeview.Heading",
                background=self.colors["tree_head"],
                foreground=self.colors["muted"],
                bordercolor=self.colors["panel_border"],
            )
            self.configure(bg=self.colors["root_bg"])
            self.module_listbox.configure(
                bg=self.colors["list_bg"],
                fg=self.colors["list_fg"],
                selectbackground=self.colors["list_sel"],
                selectforeground=self.colors["list_fg"],
            )
            self.canvas.configure(
                bg=self.colors["canvas_bg"],
                highlightbackground=self.colors["canvas_border"],
                highlightcolor=self.colors["canvas_border"],
            )
            self.footer.configure(style="Muted.TLabel")
        except Exception:
            pass

        self.save_theme_mode()
        if hasattr(self, "canvas"):
            self.render_canvas()

    def toggle_theme(self) -> None:
        self.apply_theme("light" if self.theme_mode == "dark" else "dark")

    # ---------- Helpers ----------

    def active_module(self) -> Module | None:
        if self.state_data.activeId is None:
            return None
        return self.state_data.modules.get(self.state_data.activeId)

    def touch_module(self, module: Module) -> None:
        module.updatedAt = now_iso()

    def evaluate_expr(self, text: str, fallback: int) -> int:
        cleaned = text.replace(",", ".").strip()
        if not re.fullmatch(r"[0-9+\-*/().\s]+", cleaned):
            return fallback
        try:
            value = eval(cleaned, {"__builtins__": {}}, {})
            return max(1, int(round(float(value))))
        except Exception:
            return fallback

    @staticmethod
    def increment_serial(sn: str) -> str:
        m = re.search(r"(\d+)(?!.*\d)", sn)
        if not m:
            return sn
        raw = m.group(1)
        inc = str(int(raw) + 1).zfill(len(raw))
        return sn[: m.start()] + inc + sn[m.end() :]

    def push_history(self) -> None:
        self.undo_stack.append(json.dumps(self.serialize_state()))
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def restore_snapshot(self, snap: str) -> None:
        self.state_data = self.deserialize_state(json.loads(snap))
        self.selected_pixels.clear()
        self.save_state()
        self.render_all()

    # ---------- Rendering ----------

    def render_all(self) -> None:
        self.render_module_list()
        self.render_all_modules_table()
        self.render_module_header()
        self.render_stats()
        self.render_repairs_table()
        self.render_canvas()
        self.update_toolbar_state()

    def render_module_list(self) -> None:
        self.module_listbox.delete(0, tk.END)
        query = self.search_var.get().strip().lower()
        modules = sorted(self.state_data.modules.values(), key=lambda m: m.updatedAt, reverse=True)
        self._module_id_by_list_index: list[str] = []

        for m in modules:
            label = f"{m.name}  |  {m.width}x{m.height}  |  {len(m.repairs)} rep"
            if m.sn:
                label += f"  |  {m.sn}"
            haystack = f"{m.name} {m.company} {m.sn}".lower()
            if query and query not in haystack:
                continue
            self.module_listbox.insert(tk.END, label)
            self._module_id_by_list_index.append(m.id)

        if self.state_data.activeId in self._module_id_by_list_index:
            idx = self._module_id_by_list_index.index(self.state_data.activeId)
            self.module_listbox.selection_set(idx)

    def render_all_modules_table(self) -> None:
        self.mod_tree.delete(*self.mod_tree.get_children())
        modules = sorted(self.state_data.modules.values(), key=lambda m: m.updatedAt, reverse=True)
        for m in modules:
            open_px = sum(len(r.pixels) for r in m.repairs if r.status == "Open")
            iid = f"m-{m.id}"
            self.mod_tree.insert(
                "",
                tk.END,
                iid=iid,
                values=(
                    m.company or "-",
                    m.name,
                    f"{m.width} x {m.height} px",
                    m.sn or "-",
                    len(m.repairs),
                    open_px,
                    (m.updatedAt or "")[:10],
                ),
            )

        if self.state_data.activeId:
            active_iid = f"m-{self.state_data.activeId}"
            if self.mod_tree.exists(active_iid):
                self.mod_tree.selection_set(active_iid)

    def on_bottom_module_open(self, _event: Any = None) -> None:
        sel = self.mod_tree.selection()
        if not sel:
            return
        iid = str(sel[0])
        if not iid.startswith("m-"):
            return
        module_id = iid[2:]
        if module_id not in self.state_data.modules:
            return
        self.state_data.activeId = module_id
        self.selected_pixels.clear()
        self.save_state()
        self.render_all()

    def render_module_header(self) -> None:
        m = self.active_module()
        if not m:
            self.module_title.configure(text="Geen module geselecteerd")
            self.module_sub.configure(text="")
            return
        self.module_title.configure(text=m.name)
        details = f"{m.width} x {m.height} px"
        if m.company:
            details = f"{m.company} | " + details
        if m.sn:
            details += f" | {m.sn}"
        self.module_sub.configure(text=details)

    def render_stats(self) -> None:
        m = self.active_module()
        if not m:
            self.stats_var.set("")
            return
        total_px = sum(len(r.pixels) for r in m.repairs)
        open_px = sum(len(r.pixels) for r in m.repairs if r.status == "Open")
        self.stats_var.set(f"Meldingen: {len(m.repairs)}    Open px: {open_px}    Totaal px: {total_px}")

    def render_repairs_table(self) -> None:
        self.rep_tree.delete(*self.rep_tree.get_children())
        m = self.active_module()
        if not m:
            return
        ordered = sorted(m.repairs, key=lambda r: r.date or "", reverse=True)
        for rep in ordered:
            self.rep_tree.insert(
                "",
                tk.END,
                iid=rep.id,
                values=(rep.type, rep.date, rep.initials, rep.status, len(rep.pixels)),
            )

    def repair_pixel_map(self, m: Module) -> dict[tuple[int, int], tuple[str, bool]]:
        pixel_map: dict[tuple[int, int], tuple[str, bool]] = {}
        for rep in m.repairs:
            solved = rep.status == "Opgelost"
            for p in rep.pixels:
                if len(p) < 2:
                    continue
                px = (int(p[0]), int(p[1]))
                pixel_map[px] = (rep.color, solved)
        return pixel_map

    def render_canvas(self) -> None:
        self.canvas.delete("all")
        m = self.active_module()
        if not m:
            self.canvas.config(scrollregion=(0, 0, 0, 0))
            self.canvas.create_text(
                20,
                20,
                anchor="nw",
                text="Selecteer of voeg eerst een module toe",
                fill=self.colors.get("empty_text", "#666666"),
            )
            return

        w = m.width * self.cell_size
        h = m.height * self.cell_size
        self.canvas.config(scrollregion=(0, 0, w, h))

        self.canvas.create_rectangle(0, 0, w, h, fill=self.colors.get("canvas_bg", "#eeeeee"), outline="")
        pixel_map = self.repair_pixel_map(m)

        # Alleen gewijzigde pixels tekenen houdt het sneller bij grote modules.
        for (x, y), (color, solved) in pixel_map.items():
            alpha_color = self.mix_with_white(color, 0.45) if solved else color
            x1 = x * self.cell_size
            y1 = y * self.cell_size
            self.canvas.create_rectangle(x1, y1, x1 + self.cell_size, y1 + self.cell_size, fill=alpha_color, outline="")

        if self.cell_size >= 10:
            for x in range(0, m.width + 1):
                xx = x * self.cell_size
                self.canvas.create_line(xx, 0, xx, h, fill=self.colors.get("canvas_grid", "#d9d9de"))
            for y in range(0, m.height + 1):
                yy = y * self.cell_size
                self.canvas.create_line(0, yy, w, yy, fill=self.colors.get("canvas_grid", "#d9d9de"))

        for x in range(0, m.width + 1, 10):
            xx = x * self.cell_size
            self.canvas.create_line(xx, 0, xx, h, fill=self.colors.get("canvas_major", "#bcbcc2"), width=1)
        for y in range(0, m.height + 1, 10):
            yy = y * self.cell_size
            self.canvas.create_line(0, yy, w, yy, fill=self.colors.get("canvas_major", "#bcbcc2"), width=1)

        for x, y in self.selected_pixels:
            x1 = x * self.cell_size
            y1 = y * self.cell_size
            self.canvas.create_rectangle(
                x1,
                y1,
                x1 + self.cell_size,
                y1 + self.cell_size,
                fill="#5da8ff",
                outline="#2563eb",
                width=1,
                stipple="gray25",
            )

    @staticmethod
    def mix_with_white(hex_color: str, ratio: float) -> str:
        ratio = min(1.0, max(0.0, ratio))
        hex_color = hex_color.lstrip("#")
        if len(hex_color) != 6:
            return "#cccccc"
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        r = int(r + (255 - r) * ratio)
        g = int(g + (255 - g) * ratio)
        b = int(b + (255 - b) * ratio)
        return f"#{r:02x}{g:02x}{b:02x}"

    def update_toolbar_state(self) -> None:
        m = self.active_module()
        has_sel = bool(self.selected_pixels)
        self.clear_sel_btn.config(state=tk.NORMAL if has_sel else tk.DISABLED)
        self.add_repair_btn.config(state=tk.NORMAL if (m and has_sel) else tk.DISABLED)
        self.add_repair_btn.config(text=f"+ Reparatie ({len(self.selected_pixels)} px)")

    # ---------- Module actions ----------

    def add_module_from_form(self) -> None:
        name = self.in_name.get().strip()
        if not name:
            messagebox.showwarning("Naam vereist", "Geef de module een naam of label.")
            self.in_name.focus_set()
            return

        self.push_history()
        company = self.in_company.get().strip()
        width = self.evaluate_expr(self.in_width.get(), 192)
        height = self.evaluate_expr(self.in_height.get(), 192)
        sn = self.in_sn.get().strip()

        mid = uid()
        module = Module(
            id=mid,
            company=company,
            name=name,
            sn=sn,
            width=width,
            height=height,
            updatedAt=now_iso(),
            repairs=[],
        )
        self.state_data.modules[mid] = module
        self.state_data.activeId = mid

        self.in_name.delete(0, tk.END)
        if self.batch_var.get() and sn:
            self.in_sn.delete(0, tk.END)
            self.in_sn.insert(0, self.increment_serial(sn))
            self.in_name.focus_set()
        else:
            self.in_sn.delete(0, tk.END)
            self.in_sn.focus_set()

        self.selected_pixels.clear()
        self.save_state()
        self.render_all()

    def on_module_select(self, _event: Any = None) -> None:
        sel = self.module_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < 0 or idx >= len(self._module_id_by_list_index):
            return
        mid = self._module_id_by_list_index[idx]
        self.state_data.activeId = mid
        self.selected_pixels.clear()
        self.save_state()
        self.render_all()

    def edit_sn_active(self) -> None:
        m = self.active_module()
        if not m:
            return
        value = simpledialog.askstring("SN bewerken", f"SN voor {m.name}", initialvalue=m.sn)
        if value is None:
            return
        self.push_history()
        m.sn = value.strip()
        self.touch_module(m)
        self.save_state()
        self.render_all()

    def delete_active_module(self) -> None:
        m = self.active_module()
        if not m:
            return
        if not messagebox.askyesno("Bevestigen", f"Module {m.name} verwijderen?"):
            return
        self.push_history()
        del self.state_data.modules[m.id]
        self.state_data.activeId = next(iter(self.state_data.modules), None)
        self.selected_pixels.clear()
        self.save_state()
        self.render_all()

    # ---------- Canvas interactions ----------

    def event_to_cell(self, event: tk.Event) -> tuple[int, int] | None:
        m = self.active_module()
        if not m:
            return None
        x = int(self.canvas.canvasx(event.x) // self.cell_size)
        y = int(self.canvas.canvasy(event.y) // self.cell_size)
        if x < 0 or y < 0 or x >= m.width or y >= m.height:
            return None
        return x, y

    def on_space_press(self, _event: tk.Event) -> None:
        self.space_down = True
        if not self.is_panning:
            self.canvas.config(cursor="hand2")

    def on_space_release(self, _event: tk.Event) -> None:
        self.space_down = False
        if not self.is_panning:
            self.canvas.config(cursor="crosshair")

    def on_canvas_down(self, event: tk.Event) -> None:
        if self.space_down:
            self.is_panning = True
            self.pan_origin = (
                int(event.x),
                int(event.y),
                float(self.canvas.xview()[0]),
                float(self.canvas.yview()[0]),
            )
            self.canvas.config(cursor="fleur")
            return
        cell = self.event_to_cell(event)
        if not cell:
            return
        self.drag_start = cell
        self.drag_anchor_selection = set(self.selected_pixels if (event.state & 0x0001) else set())

    def on_canvas_drag(self, event: tk.Event) -> None:
        if self.is_panning and self.pan_origin is not None:
            start_x, start_y, x_start, y_start = self.pan_origin
            m = self.active_module()
            if not m:
                return
            total_w = max(1, m.width * self.cell_size)
            total_h = max(1, m.height * self.cell_size)
            dx = (event.x - start_x) / total_w
            dy = (event.y - start_y) / total_h
            self.canvas.xview_moveto(max(0.0, min(1.0, x_start - dx)))
            self.canvas.yview_moveto(max(0.0, min(1.0, y_start - dy)))
            return
        if self.drag_start is None:
            return
        cur = self.event_to_cell(event)
        if not cur:
            return
        x1, y1 = self.drag_start
        x2, y2 = cur
        min_x, max_x = sorted((x1, x2))
        min_y, max_y = sorted((y1, y2))
        block = {(x, y) for y in range(min_y, max_y + 1) for x in range(min_x, max_x + 1)}
        self.selected_pixels = set(self.drag_anchor_selection) | block
        self.render_canvas()
        self.update_toolbar_state()

    def on_canvas_up(self, event: tk.Event) -> None:
        if self.is_panning:
            self.is_panning = False
            self.pan_origin = None
            self.canvas.config(cursor="hand2" if self.space_down else "crosshair")
            return
        if self.drag_start is None:
            return
        start = self.drag_start
        end = self.event_to_cell(event)
        self.drag_start = None
        if not end:
            return

        if start == end:
            key = start
            shift = bool(event.state & 0x0001)
            if shift:
                if key in self.selected_pixels:
                    self.selected_pixels.remove(key)
                else:
                    self.selected_pixels.add(key)
            else:
                if self.selected_pixels == {key}:
                    self.selected_pixels.clear()
                else:
                    self.selected_pixels = {key}

        self.render_canvas()
        self.update_toolbar_state()

    def on_canvas_wheel(self, event: tk.Event) -> None:
        if not (event.state & 0x0004):
            return
        delta = 1 if event.delta > 0 else -1
        self.cell_size = max(3, min(30, self.cell_size + delta))
        self.zoom_var.set(self.cell_size)
        self.render_canvas()

    def on_zoom_change(self, _value: Any = None) -> None:
        self.cell_size = int(round(self.zoom_var.get()))
        self.render_canvas()

    def clear_selection(self) -> None:
        self.selected_pixels.clear()
        self.render_canvas()
        self.update_toolbar_state()

    # ---------- Repair actions ----------

    def open_add_repair(self) -> None:
        if not self.selected_pixels:
            return
        self.open_repair_modal(None)

    def selected_repair_id(self) -> str | None:
        sel = self.rep_tree.selection()
        if not sel:
            return None
        return str(sel[0])

    def edit_selected_repair(self, _event: Any = None) -> None:
        rid = self.selected_repair_id()
        if not rid:
            return
        m = self.active_module()
        if not m:
            return
        rep = next((r for r in m.repairs if r.id == rid), None)
        if not rep:
            return
        self.selected_pixels = {(int(p[0]), int(p[1])) for p in rep.pixels if len(p) >= 2}
        self.open_repair_modal(rep)

    def delete_selected_repair(self) -> None:
        rid = self.selected_repair_id()
        m = self.active_module()
        if not rid or not m:
            return
        rep = next((r for r in m.repairs if r.id == rid), None)
        if not rep:
            return
        if not messagebox.askyesno("Bevestigen", "Deze reparatie verwijderen?"):
            return
        self.push_history()
        m.repairs = [r for r in m.repairs if r.id != rid]
        self.touch_module(m)
        self.selected_pixels.clear()
        self.save_state()
        self.render_all()

    def open_repair_modal(self, rep: Repair | None) -> None:
        m = self.active_module()
        if not m:
            return

        win = tk.Toplevel(self)
        win.title("Reparatie bewerken" if rep else "Reparatie toevoegen")
        win.transient(self)
        win.grab_set()
        win.geometry("420x470")

        frm = ttk.Frame(win)
        frm.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        ttk.Label(frm, text=f"Geselecteerde pixels: {len(self.selected_pixels)}").pack(anchor="w")

        def field(label: str, value: str = "") -> ttk.Entry:
            ttk.Label(frm, text=label).pack(anchor="w", pady=(8, 3))
            e = ttk.Entry(frm)
            e.insert(0, value)
            e.pack(fill=tk.X)
            return e

        type_var = tk.StringVar(value=rep.type if rep else "Pixel")
        ttk.Label(frm, text="Wat (type)").pack(anchor="w", pady=(8, 3))
        type_box = ttk.Combobox(frm, textvariable=type_var, values=["Pixel", "Pad", "Module", "Voeding", "Kabel", "Overig"], state="readonly")
        type_box.pack(fill=tk.X)

        in_date = field("Wanneer (YYYY-MM-DD)", rep.date if rep else today_iso())
        in_initials = field("Wie (initialen)", rep.initials if rep else self.last_initials)

        status_var = tk.StringVar(value=rep.status if rep else "Open")
        ttk.Label(frm, text="Status").pack(anchor="w", pady=(8, 3))
        status_box = ttk.Combobox(frm, textvariable=status_var, values=["Open", "Opgelost"], state="readonly")
        status_box.pack(fill=tk.X)

        color_val = tk.StringVar(value=rep.color if rep else PALETTE[len(m.repairs) % len(PALETTE)])
        ttk.Label(frm, text="Kleur").pack(anchor="w", pady=(8, 3))
        row = ttk.Frame(frm)
        row.pack(fill=tk.X)
        color_entry = ttk.Entry(row, textvariable=color_val)
        color_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def pick_color() -> None:
            chosen = colorchooser.askcolor(color_val.get(), parent=win)
            if chosen and chosen[1]:
                color_val.set(chosen[1])

        ttk.Button(row, text="Kies...", command=pick_color).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(frm, text="Notitie").pack(anchor="w", pady=(8, 3))
        note = tk.Text(frm, height=5)
        note.pack(fill=tk.BOTH, expand=True)
        if rep:
            note.insert("1.0", rep.note)

        btns = ttk.Frame(frm)
        btns.pack(fill=tk.X, pady=(10, 0))

        def save_modal() -> None:
            pixels = [[x, y] for x, y in sorted(self.selected_pixels)]
            if not pixels:
                messagebox.showwarning("Geen selectie", "Selecteer minstens een pixel.", parent=win)
                return

            data = Repair(
                id=rep.id if rep else uid(),
                type=type_var.get().strip() or "Pixel",
                date=in_date.get().strip() or today_iso(),
                initials=in_initials.get().strip(),
                status=status_var.get().strip() or "Open",
                color=color_val.get().strip() or "#e6007e",
                note=note.get("1.0", tk.END).strip(),
                pixels=pixels,
            )

            self.push_history()
            if rep:
                for idx, old in enumerate(m.repairs):
                    if old.id == rep.id:
                        m.repairs[idx] = data
                        break
            else:
                m.repairs.append(data)

            if data.initials:
                self.last_initials = data.initials

            self.touch_module(m)
            self.selected_pixels.clear()
            self.save_state()
            win.destroy()
            self.render_all()

        ttk.Button(btns, text="Annuleren", command=win.destroy).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Opslaan", command=save_modal).pack(side=tk.RIGHT, padx=(0, 8))

    def quick_add_repair(self, event: tk.Event, kind: str, color: str) -> None:
        widget = self.focus_get()
        if isinstance(widget, (tk.Entry, ttk.Entry, tk.Text, ttk.Combobox)):
            return
        m = self.active_module()
        if not m or not self.selected_pixels:
            return
        event.widget = self
        self.push_history()
        rep = Repair(
            id=uid(),
            type=kind,
            date=today_iso(),
            initials=self.last_initials,
            status="Opgelost",
            color=color,
            note="",
            pixels=[[x, y] for x, y in sorted(self.selected_pixels)],
        )
        m.repairs.append(rep)
        self.touch_module(m)
        self.selected_pixels.clear()
        self.save_state()
        self.render_all()

    # ---------- Undo / Redo ----------

    def undo(self) -> None:
        if not self.undo_stack:
            return
        self.redo_stack.append(json.dumps(self.serialize_state()))
        self.restore_snapshot(self.undo_stack.pop())

    def redo(self) -> None:
        if not self.redo_stack:
            return
        self.undo_stack.append(json.dumps(self.serialize_state()))
        self.restore_snapshot(self.redo_stack.pop())

    # ---------- File actions ----------

    def save_json_as(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Database opslaan",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile=f"pixeltracker-database_{today_iso()}.json",
        )
        if not path:
            return
        Path(path).write_text(json.dumps(self.serialize_state(), indent=2), encoding="utf-8")

    def load_json_from(self) -> None:
        path = filedialog.askopenfilename(title="Database laden", filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            loaded = self.deserialize_state(payload)
        except Exception as exc:
            messagebox.showerror("Fout", f"Kon JSON niet laden:\n{exc}")
            return

        if not messagebox.askyesno("Bevestigen", "Huidige database vervangen?"):
            return

        self.push_history()
        self.state_data = loaded
        self.selected_pixels.clear()
        self.save_state()
        self.render_all()

    def export_csv(self) -> None:
        m = self.active_module()
        if not m:
            messagebox.showwarning("Geen module", "Selecteer eerst een module.")
            return
        path = filedialog.asksaveasfilename(
            title="Reparaties exporteren",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile=f"reparaties_{m.name.replace(' ', '_')}.csv",
        )
        if not path:
            return

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Wat", "Wanneer", "Wie", "Status", "Kleur", "Pixels", "Notitie"])
            for r in m.repairs:
                px = " ".join(f"({x},{y})" for x, y in r.pixels)
                writer.writerow([r.type, r.date, r.initials, r.status, r.color, px, r.note])

    def export_selected_a3(self) -> None:
        m = self.active_module()
        if not m:
            messagebox.showwarning("Geen module", "Selecteer eerst een module.")
            return
        self.export_a3_modules([m], f"pixeltracker_{m.name.replace(' ', '_')}_a3.pdf")

    def export_database_a3(self) -> None:
        modules = sorted(self.state_data.modules.values(), key=lambda m: m.updatedAt, reverse=True)
        if not modules:
            messagebox.showwarning("Lege database", "Er zijn geen modules om te exporteren.")
            return
        self.export_a3_modules(modules, f"pixeltracker_database_{today_iso()}_a3.pdf")

    def export_a3_modules(self, modules: list[Module], default_name: str) -> None:
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror(
                "reportlab ontbreekt",
                "A3 PDF-export vereist reportlab. Installeer met: pip install reportlab",
            )
            return

        path = filedialog.asksaveasfilename(
            title="A3 export",
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile=default_name,
        )
        if not path:
            return

        pdf = pdf_canvas.Canvas(path, pagesize=landscape(A3))
        for module in modules:
            self.draw_a3_page(pdf, module)
            pdf.showPage()
        pdf.save()
        messagebox.showinfo("Export klaar", f"A3-export opgeslagen:\n{path}")

    def draw_a3_page(self, pdf: Any, module: Module) -> None:
        page_w, page_h = landscape(A3)
        margin = 28
        gap = 18
        left_w = (page_w - margin * 2 - gap) * 0.68
        right_w = page_w - margin * 2 - gap - left_w
        left_h = page_h - margin * 2

        pixel_map = self.repair_pixel_map(module)
        grid_w = module.width
        grid_h = module.height
        cell = max(1.0, min((left_w - 20) / max(1, grid_w), (left_h - 20) / max(1, grid_h)))
        draw_w = grid_w * cell
        draw_h = grid_h * cell
        x0 = margin + (left_w - draw_w) / 2
        y0 = margin + (left_h - draw_h) / 2

        pdf.setStrokeColor(colors.HexColor("#c8c8ce"))
        pdf.rect(margin, margin, left_w, left_h)

        for y in range(grid_h):
            for x in range(grid_w):
                key = (x, y)
                fill = "#f2f2f4"
                if key in pixel_map:
                    c, solved = pixel_map[key]
                    fill = self.mix_with_white(c, 0.45) if solved else c
                pdf.setFillColor(colors.HexColor(fill))
                pdf.rect(x0 + x * cell, y0 + (grid_h - 1 - y) * cell, cell, cell, stroke=0, fill=1)

        pdf.setStrokeColor(colors.HexColor("#d8d8df"))
        for x in range(0, grid_w + 1, 10):
            xx = x0 + x * cell
            pdf.line(xx, y0, xx, y0 + draw_h)
        for y in range(0, grid_h + 1, 10):
            yy = y0 + y * cell
            pdf.line(x0, yy, x0 + draw_w, yy)

        rx = margin + left_w + gap
        ry = page_h - margin
        total_px = sum(len(r.pixels) for r in module.repairs)
        open_px = sum(len(r.pixels) for r in module.repairs if r.status == "Open")

        pdf.setFont("Helvetica-Bold", 15)
        pdf.setFillColor(colors.black)
        pdf.drawString(rx, ry, module.name)
        meta = f"{module.company + ' | ' if module.company else ''}{module.width} x {module.height} px"
        if module.sn:
            meta += f" | {module.sn}"
        meta += f" | {total_px} reparatie-pixels ({open_px} open) | export {today_iso()}"

        pdf.setFont("Helvetica", 9)
        pdf.setFillColor(colors.HexColor("#555555"))
        pdf.drawString(rx, ry - 16, meta)

        top = ry - 40
        headers = ["Wat", "Wanneer", "Wie", "Status", "px"]
        widths = [right_w * 0.30, right_w * 0.22, right_w * 0.16, right_w * 0.18, right_w * 0.10]
        x = rx
        pdf.setFont("Helvetica-Bold", 9)
        pdf.setFillColor(colors.HexColor("#444444"))
        for h, w in zip(headers, widths):
            pdf.drawString(x, top, h)
            x += w

        y = top - 14
        pdf.setFont("Helvetica", 8)
        for rep in sorted(module.repairs, key=lambda r: r.date or "", reverse=True):
            if y < margin + 10:
                break
            pdf.setStrokeColor(colors.HexColor("#e0e0e5"))
            pdf.line(rx, y - 3, rx + right_w, y - 3)
            row = [rep.type, rep.date, rep.initials, rep.status, str(len(rep.pixels))]
            x = rx
            for val, w in zip(row, widths):
                text = (val or "")[:26]
                pdf.setFillColor(colors.HexColor("#111111"))
                pdf.drawString(x, y, text)
                x += w
            y -= 12

    def export_canvas_postscript(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Print schermweergave",
            defaultextension=".ps",
            filetypes=[("PostScript", "*.ps")],
            initialfile=f"pixeltracker_canvas_{today_iso()}.ps",
        )
        if not path:
            return
        self.canvas.postscript(file=path, colormode="color")
        messagebox.showinfo("Printbestand klaar", f"PostScript opgeslagen:\n{path}")

    def new_empty_db(self) -> None:
        if not messagebox.askyesno("Bevestigen", "Alle modules en reparaties verwijderen?"):
            return
        self.push_history()
        self.state_data = AppState(activeId=None, modules={})
        self.selected_pixels.clear()
        self.save_state()
        self.render_all()

    def on_close(self) -> None:
        try:
            self.save_state()
        finally:
            self.destroy()


def main() -> None:
    app = PixelTrackerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
