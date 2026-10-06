"""Tkinter UI for Trainz .im attachment editing — light modern list layout."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from .core import CAB_DEFAULT, ImDocument
except ImportError:
    from core import CAB_DEFAULT, ImDocument

# Workshop / instrument panel — light, cool slate + teal (not aqua-dark, not purple)
BG = "#eef1f4"
SURFACE = "#ffffff"
SURFACE_2 = "#f7f8fa"
INK = "#152028"
MUTED = "#5c6b75"
LINE = "#d0d7de"
ACCENT = "#1f6b5c"
ACCENT_HOVER = "#185548"
SELECT_BG = "#1f6b5c"
SELECT_FG = "#ffffff"
ROW_ALT = "#f3f6f8"
MONO = ("Menlo", 12)
UI = ("Helvetica Neue", 13)
UI_SM = ("Helvetica Neue", 11)
UI_BD = ("Helvetica Neue", 13, "bold")
UI_TITLE = ("Helvetica Neue", 18, "bold")


class ImEditorApp(tk.Tk):
    def __init__(self, initial: Path | None = None) -> None:
        super().__init__()
        self.title("IM Attachment Editor")
        self.geometry("1080x640")
        self.minsize(860, 500)
        self.configure(bg=BG)

        self.doc = ImDocument()
        self._filter = tk.StringVar()
        self._name = tk.StringVar()
        self._x = tk.StringVar()
        self._y = tk.StringVar()
        self._z = tk.StringVar()
        self._step = tk.StringVar(value="0.01")
        self._status = tk.StringVar(value="Open an .im file to begin.")
        self._path_label = tk.StringVar(value="No file open")
        self._count_label = tk.StringVar(value="0")
        self._list_indices: list[int] = []
        self._iid_to_doc: dict[str, int] = {}

        self._style()
        self._build()
        self._bind_keys()
        self.protocol("WM_DELETE_WINDOW", self._on_quit)

        if initial and initial.is_file():
            self._open_path(initial)
        elif CAB_DEFAULT.is_file():
            self._status.set(f"Ready — drop in {CAB_DEFAULT.name} via Open, or pass path to start.sh")

    def _style(self) -> None:
        style = ttk.Style(self)
        # clam honors custom colors; aqua on mac ignores most of them
        style.theme_use("clam")

        style.configure(".", background=BG, foreground=INK, font=UI, borderwidth=0)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=SURFACE)
        style.configure("Toolbar.TFrame", background=SURFACE)
        style.configure("TLabel", background=BG, foreground=INK, font=UI)
        style.configure("Card.TLabel", background=SURFACE, foreground=INK, font=UI)
        style.configure("Muted.TLabel", background=SURFACE, foreground=MUTED, font=UI_SM)
        style.configure("Title.TLabel", background=SURFACE, foreground=INK, font=UI_TITLE)
        style.configure("Brand.TLabel", background=SURFACE, foreground=ACCENT, font=UI_BD)
        style.configure("Count.TLabel", background=ACCENT, foreground="#fff", font=UI_SM)
        style.configure("Status.TLabel", background=SURFACE_2, foreground=MUTED, font=UI_SM)
        style.configure("Path.TLabel", background=SURFACE, foreground=MUTED, font=UI_SM)

        style.configure(
            "Tool.TButton",
            background=SURFACE_2,
            foreground=INK,
            font=UI_SM,
            padding=(12, 7),
            borderwidth=1,
            relief="flat",
        )
        style.map(
            "Tool.TButton",
            background=[("active", LINE), ("pressed", LINE)],
            foreground=[("disabled", "#9aa5ab")],
        )
        style.configure(
            "Primary.TButton",
            background=ACCENT,
            foreground="#ffffff",
            font=UI_BD,
            padding=(14, 10),
            borderwidth=0,
        )
        style.map(
            "Primary.TButton",
            background=[("active", ACCENT_HOVER), ("pressed", ACCENT_HOVER)],
        )
        style.configure(
            "Nudge.TButton",
            background=SURFACE_2,
            foreground=INK,
            font=UI_BD,
            padding=(10, 8),
            width=4,
        )
        style.map("Nudge.TButton", background=[("active", LINE)])

        style.configure(
            "Search.TEntry",
            fieldbackground=SURFACE_2,
            foreground=INK,
            insertcolor=INK,
            padding=8,
            bordercolor=LINE,
            lightcolor=LINE,
            darkcolor=LINE,
        )
        style.configure(
            "Field.TEntry",
            fieldbackground=SURFACE_2,
            foreground=INK,
            insertcolor=INK,
            padding=6,
            bordercolor=LINE,
            lightcolor=LINE,
            darkcolor=LINE,
            font=MONO,
        )

        style.configure(
            "Att.Treeview",
            background=SURFACE,
            fieldbackground=SURFACE,
            foreground=INK,
            rowheight=28,
            font=MONO,
            borderwidth=0,
            relief="flat",
        )
        style.configure(
            "Att.Treeview.Heading",
            background=SURFACE_2,
            foreground=MUTED,
            font=UI_SM,
            relief="flat",
            borderwidth=0,
            padding=(8, 8),
        )
        style.map(
            "Att.Treeview",
            background=[("selected", SELECT_BG)],
            foreground=[("selected", SELECT_FG)],
        )
        style.configure(
            "Att.Vertical.TScrollbar",
            background=SURFACE_2,
            troughcolor=SURFACE,
            bordercolor=SURFACE,
            arrowcolor=MUTED,
        )

    def _build(self) -> None:
        # —— header ——
        header = ttk.Frame(self, style="Toolbar.TFrame", padding=(16, 12))
        header.pack(fill=tk.X)
        ttk.Label(header, text="IM Editor", style="Brand.TLabel").pack(side=tk.LEFT)
        ttk.Label(header, text="  Attachment points", style="Muted.TLabel").pack(side=tk.LEFT)
        ttk.Label(header, textvariable=self._path_label, style="Path.TLabel").pack(
            side=tk.RIGHT
        )

        # thin rule
        tk.Frame(self, bg=LINE, height=1).pack(fill=tk.X)

        # —— toolbar ——
        bar = ttk.Frame(self, style="Toolbar.TFrame", padding=(12, 8))
        bar.pack(fill=tk.X)
        for text, cmd in (
            ("Open", self._open),
            ("Save", self._save),
            ("Save As", self._save_as),
            ("Undo", self._undo),
            ("Redo", self._redo),
            ("Revert", self._revert),
        ):
            ttk.Button(bar, text=text, style="Tool.TButton", command=cmd).pack(
                side=tk.LEFT, padx=3
            )

        tk.Frame(self, bg=LINE, height=1).pack(fill=tk.X)

        # —— body ——
        body = ttk.Frame(self, padding=14)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=0, minsize=300)
        body.rowconfigure(0, weight=1)

        # list card
        list_card = ttk.Frame(body, style="Card.TFrame", padding=0)
        list_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        list_card.columnconfigure(0, weight=1)
        list_card.rowconfigure(2, weight=1)

        list_head = ttk.Frame(list_card, style="Card.TFrame", padding=(14, 12, 14, 8))
        list_head.grid(row=0, column=0, sticky="ew")
        ttk.Label(list_head, text="Attachments", style="Title.TLabel").pack(side=tk.LEFT)
        count_wrap = tk.Frame(list_head, bg=ACCENT, padx=8, pady=2)
        count_wrap.pack(side=tk.LEFT, padx=(10, 0))
        tk.Label(
            count_wrap,
            textvariable=self._count_label,
            bg=ACCENT,
            fg="#ffffff",
            font=UI_SM,
        ).pack()

        search_row = ttk.Frame(list_card, style="Card.TFrame", padding=(14, 0, 14, 10))
        search_row.grid(row=1, column=0, sticky="ew")
        search_row.columnconfigure(0, weight=1)
        ent = ttk.Entry(search_row, textvariable=self._filter, style="Search.TEntry")
        ent.grid(row=0, column=0, sticky="ew")
        ent.insert(0, "")
        self._filter_hint = "Filter by name…"
        self._filter_entry = ent
        ent.bind("<FocusIn>", self._filter_focus_in)
        ent.bind("<FocusOut>", self._filter_focus_out)
        self._filter.set(self._filter_hint)
        ent.configure(foreground=MUTED)
        self._filter.trace_add("write", lambda *_: self._on_filter_change())

        tree_wrap = ttk.Frame(list_card, style="Card.TFrame", padding=(8, 0, 8, 8))
        tree_wrap.grid(row=2, column=0, sticky="nsew")
        tree_wrap.columnconfigure(0, weight=1)
        tree_wrap.rowconfigure(0, weight=1)

        cols = ("name", "x", "y", "z")
        self.tree = ttk.Treeview(
            tree_wrap,
            columns=cols,
            show="headings",
            style="Att.Treeview",
            selectmode="browse",
        )
        self.tree.heading("name", text="NAME", anchor="w")
        self.tree.heading("x", text="X", anchor="e")
        self.tree.heading("y", text="Y", anchor="e")
        self.tree.heading("z", text="Z", anchor="e")
        self.tree.column("name", width=280, minwidth=140, stretch=True, anchor="w")
        self.tree.column("x", width=100, minwidth=80, stretch=False, anchor="e")
        self.tree.column("y", width=100, minwidth=80, stretch=False, anchor="e")
        self.tree.column("z", width=100, minwidth=80, stretch=False, anchor="e")
        self.tree.tag_configure("odd", background=SURFACE)
        self.tree.tag_configure("even", background=ROW_ALT)

        # tk.Scrollbar tracks drag more smoothly than clam ttk on macOS
        self._scroll = tk.Scrollbar(
            tree_wrap,
            orient=tk.VERTICAL,
            command=self.tree.yview,
            width=12,
            bg=SURFACE_2,
            activebackground=LINE,
            troughcolor=SURFACE,
            highlightthickness=0,
            bd=0,
            relief=tk.FLAT,
        )
        self.tree.configure(yscrollcommand=self._scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self._scroll.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self._wire_smooth_scroll(self.tree)
        self._wire_smooth_scroll(tree_wrap)
        self._wire_smooth_scroll(self._scroll)
        self._wire_smooth_scroll(list_card)

        # edit card
        edit = ttk.Frame(body, style="Card.TFrame", padding=16)
        edit.grid(row=0, column=1, sticky="ns")

        ttk.Label(edit, text="Inspector", style="Title.TLabel").pack(anchor="w")
        ttk.Label(edit, text="Edit the selected attachment", style="Muted.TLabel").pack(
            anchor="w", pady=(2, 14)
        )

        ttk.Label(edit, text="NAME", style="Muted.TLabel").pack(anchor="w")
        ttk.Entry(edit, textvariable=self._name, style="Field.TEntry").pack(
            fill=tk.X, pady=(4, 12)
        )

        xyz = ttk.Frame(edit, style="Card.TFrame")
        xyz.pack(fill=tk.X, pady=(0, 12))
        for i, (lab, var) in enumerate((("X", self._x), ("Y", self._y), ("Z", self._z))):
            cell = ttk.Frame(xyz, style="Card.TFrame")
            cell.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 0))
            xyz.columnconfigure(i, weight=1)
            ttk.Label(cell, text=lab, style="Muted.TLabel").pack(anchor="w")
            ttk.Entry(cell, textvariable=var, style="Field.TEntry", width=10).pack(
                fill=tk.X, pady=(4, 0)
            )

        ttk.Button(edit, text="Apply changes", style="Primary.TButton", command=self._apply).pack(
            fill=tk.X, pady=(0, 16)
        )

        ttk.Label(edit, text="NUDGE", style="Muted.TLabel").pack(anchor="w")
        step_row = ttk.Frame(edit, style="Card.TFrame")
        step_row.pack(fill=tk.X, pady=(4, 8))
        ttk.Label(step_row, text="Step", style="Card.TLabel").pack(side=tk.LEFT)
        ttk.Entry(step_row, textvariable=self._step, style="Field.TEntry", width=8).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        nudge = ttk.Frame(edit, style="Card.TFrame")
        nudge.pack(fill=tk.X)
        for r, row in enumerate(
            (
                (("−X", -1, 0, 0), ("+X", 1, 0, 0)),
                (("−Y", 0, -1, 0), ("+Y", 0, 1, 0)),
                (("−Z", 0, 0, -1), ("+Z", 0, 0, 1)),
            )
        ):
            for c, (label, dx, dy, dz) in enumerate(row):
                ttk.Button(
                    nudge,
                    text=label,
                    style="Nudge.TButton",
                    command=lambda a=dx, b=dy, c_=dz: self._nudge(a, b, c_),
                ).grid(row=r, column=c, sticky="ew", padx=2, pady=2)
            nudge.columnconfigure(0, weight=1)
            nudge.columnconfigure(1, weight=1)

        ttk.Label(
            edit,
            text="Save writes ATCH into the .im.\n"
            "First save creates .im.bak once.\n"
            "Undo/Redo = session · Revert = baseline.",
            style="Muted.TLabel",
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(18, 0))

        # status
        tk.Frame(self, bg=LINE, height=1).pack(fill=tk.X)
        status = ttk.Frame(self, style="Toolbar.TFrame", padding=(14, 8))
        status.pack(fill=tk.X, side=tk.BOTTOM)
        # reuse SURFACE_2 via configure
        status.configure(style="Toolbar.TFrame")
        ttk.Label(status, textvariable=self._status, style="Status.TLabel").pack(anchor="w")
        # force status strip bg
        for w in (status,):
            w.configure(style="Toolbar.TFrame")

        # menubar (native)
        menubar = tk.Menu(self)
        file_m = tk.Menu(menubar, tearoff=0)
        file_m.add_command(label="Open…", command=self._open, accelerator="⌘O")
        file_m.add_command(label="Save", command=self._save, accelerator="⌘S")
        file_m.add_command(label="Save As…", command=self._save_as)
        file_m.add_separator()
        file_m.add_command(label="Revert to Open/Save", command=self._revert)
        file_m.add_separator()
        file_m.add_command(label="Quit", command=self._on_quit)
        edit_m = tk.Menu(menubar, tearoff=0)
        edit_m.add_command(label="Undo", command=self._undo, accelerator="⌘Z")
        edit_m.add_command(label="Redo", command=self._redo, accelerator="⇧⌘Z")
        edit_m.add_separator()
        edit_m.add_command(label="Apply fields", command=self._apply, accelerator="⌘Return")
        menubar.add_cascade(label="File", menu=file_m)
        menubar.add_cascade(label="Edit", menu=edit_m)
        self.config(menu=menubar)

    def _wire_smooth_scroll(self, widget) -> None:
        widget.bind("<MouseWheel>", self._on_mousewheel, add="+")
        widget.bind("<Option-MouseWheel>", self._on_mousewheel_page, add="+")
        widget.bind("<Shift-MouseWheel>", self._on_mousewheel_page, add="+")
        widget.bind("<Button-4>", lambda e: self._scroll_units(-3), add="+")
        widget.bind("<Button-5>", lambda e: self._scroll_units(3), add="+")

    def _scroll_units(self, units: int) -> str:
        self.tree.yview_scroll(units, "units")
        return "break"

    def _on_mousewheel(self, event) -> str:
        # macOS trackpad: many small deltas → fractional moveto feels continuous
        first, _last = self.tree.yview()
        delta = float(event.delta)
        if delta == 0:
            return "break"
        if abs(delta) >= 60:
            frac = -delta / 120.0 * 0.08
        else:
            frac = -delta * 0.012
        self.tree.yview_moveto(max(0.0, min(1.0, first + frac)))
        return "break"

    def _on_mousewheel_page(self, event) -> str:
        first, _last = self.tree.yview()
        step = -0.18 if event.delta > 0 else 0.18
        self.tree.yview_moveto(max(0.0, min(1.0, first + step)))
        return "break"

    def _filter_focus_in(self, _e=None) -> None:
        if self._filter.get() == self._filter_hint:
            self._filter.set("")
            self._filter_entry.configure(foreground=INK)

    def _filter_focus_out(self, _e=None) -> None:
        if not self._filter.get().strip():
            self._filter.set(self._filter_hint)
            self._filter_entry.configure(foreground=MUTED)

    def _filter_text(self) -> str:
        t = self._filter.get().strip()
        if t == self._filter_hint:
            return ""
        return t

    def _on_filter_change(self) -> None:
        if self._filter.get() == self._filter_hint:
            return
        self._refresh_list()

    def _bind_keys(self) -> None:
        self.bind_all("<Command-o>", lambda e: self._open())
        self.bind_all("<Command-s>", lambda e: self._save())
        self.bind_all("<Command-z>", lambda e: self._undo())
        self.bind_all("<Command-Z>", lambda e: self._redo())
        self.bind_all("<Shift-Command-z>", lambda e: self._redo())
        self.bind_all("<Command-Return>", lambda e: self._apply())

    def _set_title(self) -> None:
        name = self.doc.path.name if self.doc.path else "Untitled"
        mark = " •" if self.doc.dirty else ""
        self.title(f"IM Attachment Editor — {name}{mark}")
        if self.doc.path:
            self._path_label.set(str(self.doc.path))
        else:
            self._path_label.set("No file open")

    def _selected_doc_index(self) -> int | None:
        sel = self.tree.selection()
        if not sel:
            return None
        return self._iid_to_doc.get(sel[0])

    def _refresh_list(self, *, keep_name: str | None = None) -> None:
        filt = self._filter_text().lower()
        prev = keep_name
        if prev is None:
            idx = self._selected_doc_index()
            if idx is not None and 0 <= idx < len(self.doc.atts):
                prev = self.doc.atts[idx].name

        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._list_indices = []
        self._iid_to_doc.clear()
        select_iid = None
        row_i = 0
        for i, a in enumerate(self.doc.atts):
            if filt and filt not in a.name.lower():
                continue
            x, y, z = a.pos
            tag = "even" if row_i % 2 else "odd"
            iid = self.tree.insert(
                "",
                tk.END,
                values=(a.name, f"{x:.6f}", f"{y:.6f}", f"{z:.6f}"),
                tags=(tag,),
            )
            self._list_indices.append(i)
            self._iid_to_doc[iid] = i
            if prev and a.name == prev:
                select_iid = iid
            row_i += 1

        shown = len(self._list_indices)
        total = len(self.doc.atts)
        self._count_label.set(f"{shown}" if shown == total else f"{shown}/{total}")

        if select_iid is not None:
            self.tree.selection_set(select_iid)
            self.tree.focus(select_iid)
            self.tree.see(select_iid)
            self._load_fields(self._iid_to_doc[select_iid])
        elif not self._list_indices:
            self._clear_fields()
        self._set_title()

    def _clear_fields(self) -> None:
        self._name.set("")
        self._x.set("")
        self._y.set("")
        self._z.set("")

    def _load_fields(self, index: int) -> None:
        a = self.doc.atts[index]
        self._name.set(a.name)
        self._x.set(f"{a.pos[0]:.6f}")
        self._y.set(f"{a.pos[1]:.6f}")
        self._z.set(f"{a.pos[2]:.6f}")

    def _on_select(self, _evt=None) -> None:
        idx = self._selected_doc_index()
        if idx is not None:
            self._load_fields(idx)

    def _confirm_discard(self) -> bool:
        if not self.doc.dirty:
            return True
        return messagebox.askyesno("Unsaved changes", "Discard unsaved changes?", parent=self)

    def _open(self) -> None:
        if not self._confirm_discard():
            return
        initial = self.doc.path.parent if self.doc.path else (
            CAB_DEFAULT.parent if CAB_DEFAULT.parent.is_dir() else Path.home()
        )
        path = filedialog.askopenfilename(
            parent=self,
            title="Open Trainz .im",
            initialdir=str(initial),
            filetypes=[("Trainz indexed mesh", "*.im"), ("All files", "*.*")],
        )
        if path:
            self._open_path(Path(path))

    def _open_path(self, path: Path) -> None:
        try:
            self.doc.open(path)
        except Exception as e:
            messagebox.showerror("Open failed", str(e), parent=self)
            return
        self._status.set(f"Opened · {len(self.doc.atts)} attachments")
        self._refresh_list()

    def _save(self) -> None:
        if self.doc.path is None:
            self._save_as()
            return
        try:
            self.doc.save()
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self)
            return
        self._status.set(f"Saved · {self.doc.path.name}")
        self._set_title()

    def _save_as(self) -> None:
        initial = self.doc.path.parent if self.doc.path else Path.home()
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save .im As",
            initialdir=str(initial),
            defaultextension=".im",
            filetypes=[("Trainz indexed mesh", "*.im")],
        )
        if not path:
            return
        try:
            self.doc.save(Path(path))
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self)
            return
        self._status.set(f"Saved · {self.doc.path.name}")
        self._set_title()

    def _undo(self) -> None:
        name = None
        idx = self._selected_doc_index()
        if idx is not None:
            name = self.doc.atts[idx].name
        if not self.doc.undo():
            self._status.set("Nothing to undo")
            return
        self._status.set("Undo")
        self._refresh_list(keep_name=name)

    def _redo(self) -> None:
        name = None
        idx = self._selected_doc_index()
        if idx is not None:
            name = self.doc.atts[idx].name
        if not self.doc.redo():
            self._status.set("Nothing to redo")
            return
        self._status.set("Redo")
        self._refresh_list(keep_name=name)

    def _revert(self) -> None:
        if self.doc.path is None:
            return
        if not messagebox.askyesno(
            "Revert",
            "Restore attachments to last Open/Save baseline?",
            parent=self,
        ):
            return
        self.doc.revert_opened()
        self._status.set("Reverted to Open/Save baseline")
        self._refresh_list()

    def _parse_xyz(self) -> tuple[float, float, float]:
        try:
            return float(self._x.get()), float(self._y.get()), float(self._z.get())
        except ValueError as e:
            raise ValueError("X/Y/Z must be numbers") from e

    def _apply(self) -> None:
        idx = self._selected_doc_index()
        if idx is None:
            messagebox.showinfo("Apply", "Select an attachment first.", parent=self)
            return
        name = self._name.get().strip()
        if not name:
            messagebox.showerror("Apply", "Name cannot be empty.", parent=self)
            return
        try:
            pos = self._parse_xyz()
        except ValueError as e:
            messagebox.showerror("Apply", str(e), parent=self)
            return
        if any(i != idx and a.name == name for i, a in enumerate(self.doc.atts)):
            messagebox.showerror("Apply", f"Name already used: {name}", parent=self)
            return
        try:
            self.doc.update_one(idx, name=name, pos=pos)
        except Exception as e:
            messagebox.showerror("Apply", str(e), parent=self)
            return
        self._status.set(f"Updated · {name}")
        self._refresh_list(keep_name=name)

    def _nudge(self, sx: int, sy: int, sz: int) -> None:
        idx = self._selected_doc_index()
        if idx is None:
            return
        try:
            step = float(self._step.get())
        except ValueError:
            messagebox.showerror("Nudge", "Step must be a number.", parent=self)
            return
        name = self.doc.atts[idx].name
        self.doc.nudge(idx, sx * step, sy * step, sz * step)
        self._status.set(f"Nudged · {name}")
        self._refresh_list(keep_name=name)

    def _on_quit(self) -> None:
        if not self._confirm_discard():
            return
        self.destroy()


def main(argv: list[str] | None = None) -> None:
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    initial = Path(args[0]) if args else None
    app = ImEditorApp(initial=initial)
    app.mainloop()


if __name__ == "__main__":
    main()
