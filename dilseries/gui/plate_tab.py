"""Plate layout view: select contiguous well ranges, assign groups, include/exclude wells."""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk

from dilseries.gui.dialogs import ChoiceDialog
from dilseries.gui.widgets import color_swatch
from dilseries.naming import Role
from dilseries.util import parse_well

GROUP_COLORS = ["#8ecae6", "#ffb703", "#90be6d", "#f28482", "#cdb4db", "#f9c74f", "#84a59d", "#bde0fe", "#ffafcc", "#a3b18a"]
EMPTY_FILL = "#ffffff"
UNGROUPED_FILL = "#fbfbfb"
EXCLUDED_FILL = "#d0d0d0"
SELECT_OUTLINE = "#1f6feb"
STANDARD_FORMATS = [(4, 6), (8, 12), (16, 24)]
MARGIN_LEFT = 30
MARGIN_TOP = 24


class PlateTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app
        self.plate_keys: list[tuple] = []
        self.wells: dict[tuple[int, int], list[int]] = {}
        self.dims = (8, 12)
        self.selection: set[tuple[int, int]] = set()
        self._drag_start = None
        self._drag_base: set = set()
        self._rects: dict[tuple[int, int], int] = {}
        self._font = tkfont.nametofont("TkDefaultFont").copy()
        self._small = self._font.copy()
        self._small.configure(size=max(7, int(self._font.cget("size")) - 1))

        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="Plate / run:").pack(side="left")
        self.plate_var = tk.StringVar()
        self.plate_box = ttk.Combobox(top, textvariable=self.plate_var, state="readonly", width=80)
        self.plate_box.pack(side="left", padx=6)
        self.plate_box.bind("<<ComboboxSelected>>", lambda e: self._load_plate())
        self.warning = ttk.Label(self, text="", foreground="#b00020", wraplength=900, justify="left")
        self.warning.pack(fill="x", pady=(4, 0))

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, pady=(6, 0))
        canvas_frame = ttk.Frame(body)
        canvas_frame.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(canvas_frame, background="#ffffff", highlightthickness=0)
        xs = ttk.Scrollbar(canvas_frame, orient="horizontal", command=self.canvas.xview)
        ys = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=xs.set, yscrollcommand=ys.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag_start", None))
        self.canvas.bind("<Motion>", self._on_hover)
        self.canvas.bind("<Leave>", lambda e: self.info.configure(text=""))
        self.canvas.bind("<Configure>", self._on_resize)
        self._last_width = 0
        self._redraw_pending = False

        side = ttk.Frame(body, padding=(10, 0, 0, 0), width=290)
        side.pack(side="right", fill="y")
        ttk.Label(
            side,
            text="Drag to select a range. Ctrl+click toggles wells, Shift+drag adds a range. Click a row letter or column number to select it.",
            wraplength=270,
            foreground="#555555",
            justify="left",
        ).pack(anchor="w")
        self.selection_label = ttk.Label(side, text="0 wells selected")
        self.selection_label.pack(anchor="w", pady=(6, 2))
        row = ttk.Frame(side)
        row.pack(fill="x")
        ttk.Button(row, text="Select all", command=self._select_all).pack(side="left")
        ttk.Button(row, text="Clear selection", command=self._clear_selection).pack(side="left", padx=4)

        group_box = ttk.LabelFrame(side, text="Group (test / assay)", padding=6)
        group_box.pack(fill="x", pady=(8, 0))
        self.group_var = tk.StringVar()
        self.group_box = ttk.Combobox(group_box, textvariable=self.group_var, width=28)
        self.group_box.pack(fill="x")
        row = ttk.Frame(group_box)
        row.pack(fill="x", pady=(4, 0))
        ttk.Button(row, text="Assign to selection", command=self._assign_group).pack(side="left")
        ttk.Button(row, text="Remove group", command=self._remove_group).pack(side="left", padx=4)
        row = ttk.Frame(group_box)
        row.pack(fill="x", pady=(4, 0))
        ttk.Button(row, text="Suggest groups", command=self._suggest_groups).pack(side="left")
        ttk.Button(row, text="Rename group…", command=self._rename_group).pack(side="left", padx=4)

        include_box = ttk.LabelFrame(side, text="Import", padding=6)
        include_box.pack(fill="x", pady=(8, 0))
        ttk.Button(include_box, text="Exclude selection", command=lambda: self._set_included(False)).pack(side="left")
        ttk.Button(include_box, text="Include selection", command=lambda: self._set_included(True)).pack(side="left", padx=4)

        self.legend = ttk.LabelFrame(side, text="Legend", padding=6)
        self.legend.pack(fill="x", pady=(8, 0))
        self.info = ttk.Label(side, text="", wraplength=270, justify="left")
        self.info.pack(anchor="w", pady=(8, 0))

    # ------------------------------------------------------------------ data
    def refresh(self) -> None:
        s = self.app.session
        current = self._current_key()
        self.plate_keys = s.plates()
        labels = []
        for r in s.runs():
            labels.append(f"{r.key[0]} · {r.key[1]} · {', '.join(r.files)}")
        self.plate_box.configure(values=labels)
        if current in self.plate_keys:
            self.plate_box.current(self.plate_keys.index(current))
        elif self.plate_keys:
            self.plate_box.current(0)
            self.selection.clear()
        else:
            self.plate_var.set("")
        self.group_box.configure(values=s.all_groups())
        self._load_plate(keep_selection=current == self._current_key())

    def _current_key(self):
        index = self.plate_box.current()
        if 0 <= index < len(self.plate_keys):
            return self.plate_keys[index]
        return None

    def _load_plate(self, keep_selection: bool = False) -> None:
        if not keep_selection:
            self.selection.clear()
        key = self._current_key()
        self.wells = {}
        if key is not None:
            for well, uids in self.app.session.plate_wells(key).items():
                pos = parse_well(well)
                if pos is not None:
                    self.wells.setdefault(pos, []).extend(uids)
        max_row = max((r for r, _ in self.wells), default=0) + 1
        max_col = max((c for _, c in self.wells), default=0) + 1
        self.dims = next(((r, c) for r, c in STANDARD_FORMATS if max_row <= r and max_col <= c), (max_row, max_col))
        self.selection = {p for p in self.selection if p in self.wells}
        self._draw()

    # --------------------------------------------------------------- drawing
    def _on_resize(self, event) -> None:
        if event.width != self._last_width and not self._redraw_pending:
            self._last_width = event.width
            self._redraw_pending = True
            self.after_idle(self._redraw_after_resize)

    def _redraw_after_resize(self) -> None:
        self._redraw_pending = False
        self._draw()

    def _cell_size(self) -> tuple[int, int]:
        """Cells fill the available width (with a minimum; the canvas scrolls beyond that)."""
        rows, cols = self.dims
        line_h = self._font.metrics("linespace")
        available = max(self.canvas.winfo_width(), 300) - MARGIN_LEFT - 6
        if cols > 12:
            return max(44, available // cols), line_h + 8
        return max(56, available // cols), 2 * line_h + 12

    @staticmethod
    def _fit(text: str, font: tkfont.Font, width: int) -> str:
        if font.measure(text) <= width:
            return text
        while text and font.measure(text + "…") > width:
            text = text[:-1]
        return text + "…"

    def _draw(self) -> None:
        c = self.canvas
        c.delete("all")
        self._rects = {}
        s = self.app.session
        ann = s.annotations()
        groups = s.all_groups()
        colors = {g: GROUP_COLORS[i % len(GROUP_COLORS)] for i, g in enumerate(groups)}
        rows, cols = self.dims
        cw, ch = self._cell_size()
        small_plate = cols > 12
        for j in range(cols):
            c.create_text(MARGIN_LEFT + j * cw + cw / 2, MARGIN_TOP / 2, text=str(j + 1), font=self._small)
        for i in range(rows):
            c.create_text(MARGIN_LEFT / 2, MARGIN_TOP + i * ch + ch / 2, text=chr(ord("A") + i), font=self._small)
        duplicates = 0
        for i in range(rows):
            for j in range(cols):
                x0, y0 = MARGIN_LEFT + j * cw, MARGIN_TOP + i * ch
                uids = self.wells.get((i, j), [])
                included = [u for u in uids if ann[u].included]
                if not uids:
                    fill = EMPTY_FILL
                elif not included:
                    fill = EXCLUDED_FILL
                else:
                    group = ann[included[0]].group
                    fill = colors.get(group, UNGROUPED_FILL)
                selected = (i, j) in self.selection
                rect = c.create_rectangle(
                    x0 + 2, y0 + 2, x0 + cw - 2, y0 + ch - 2,
                    fill=fill,
                    outline=SELECT_OUTLINE if selected else "#9a9a9a",
                    width=3 if selected else 1,
                )
                self._rects[(i, j)] = rect
                if not uids:
                    continue
                m = s.measurements[uids[0]]
                label = m.sample_id + (f" +{len(uids) - 1}" if len(uids) > 1 else "")
                color = "#7a7a7a" if not included else "#000000"
                is_dup = any(ann[u].status == "duplicate" for u in included)
                duplicates += is_dup
                if small_plate:
                    c.create_text(x0 + cw / 2, y0 + ch / 2, text=self._fit(label, self._small, cw - 6), font=self._small, fill=color)
                else:
                    c.create_text(x0 + cw / 2, y0 + ch / 2 - ch / 5, text=self._fit(label, self._font, cw - 6), font=self._font, fill=color)
                    role = ann[uids[0]].role
                    sub = "excluded" if not included else ("control" if role == Role.CONTROL else ann[uids[0]].group or "")
                    c.create_text(x0 + cw / 2, y0 + ch / 2 + ch / 4, text=self._fit(sub, self._small, cw - 6), font=self._small, fill="#444444")
                if is_dup:
                    c.create_text(x0 + cw - 8, y0 + 9, text="!", font=self._font, fill="#b00020")
        c.configure(scrollregion=(0, 0, MARGIN_LEFT + cols * cw + 4, MARGIN_TOP + rows * ch + 4))
        self._update_selection_label()
        on_plate = {ann[u].group for uids in self.wells.values() for u in uids if ann[u].included}
        self._update_legend([g for g in groups if g in on_plate], colors)
        key = self._current_key()
        if key is not None and duplicates:
            self.warning.configure(
                text=f"{duplicates} well(s) marked '!' contain sample IDs that also occur elsewhere in the same series. "
                "If different tests ran on this plate, select each block of wells and assign a group "
                "(or use 'Suggest groups'), or exclude wells that should not be imported."
            )
        else:
            self.warning.configure(text="")

    def _update_legend(self, groups: list[str], colors: dict[str, str]) -> None:
        for child in self.legend.winfo_children():
            child.destroy()
        color_swatch(self.legend, UNGROUPED_FILL, "no group").pack(anchor="w")
        color_swatch(self.legend, EXCLUDED_FILL, "excluded").pack(anchor="w")
        for g in groups:
            color_swatch(self.legend, colors[g], g).pack(anchor="w")

    def _refresh_outlines(self) -> None:
        for pos, rect in self._rects.items():
            selected = pos in self.selection
            self.canvas.itemconfigure(rect, outline=SELECT_OUTLINE if selected else "#9a9a9a", width=3 if selected else 1)
        self._update_selection_label()

    def _update_selection_label(self) -> None:
        n_wells = sum(1 for p in self.selection if p in self.wells)
        self.selection_label.configure(text=f"{n_wells} well(s) selected")

    # ----------------------------------------------------------- interaction
    def _hit(self, event) -> tuple[str, int, int] | None:
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        rows, cols = self.dims
        cw, ch = self._cell_size()
        col = int((x - MARGIN_LEFT) // cw) if x >= MARGIN_LEFT else -1
        row = int((y - MARGIN_TOP) // ch) if y >= MARGIN_TOP else -1
        if row < 0 and 0 <= col < cols:
            return ("col", -1, col)
        if col < 0 and 0 <= row < rows:
            return ("row", row, -1)
        if 0 <= row < rows and 0 <= col < cols:
            return ("cell", row, col)
        return None

    def _on_press(self, event) -> None:
        hit = self._hit(event)
        ctrl = bool(event.state & 0x0004)
        shift = bool(event.state & 0x0001)
        if hit is None:
            if not (ctrl or shift):
                self._clear_selection()
            return
        kind, row, col = hit
        rows, cols = self.dims
        if kind in ("row", "col"):
            cells = {(row, j) for j in range(cols)} if kind == "row" else {(i, col) for i in range(rows)}
            self.selection = (self.selection | cells) if (ctrl or shift) else cells
            self._drag_start = None
        elif ctrl:
            self.selection ^= {(row, col)}
            self._drag_start = None
        else:
            self._drag_base = set(self.selection) if shift else set()
            self._drag_start = (row, col)
            self.selection = self._drag_base | {(row, col)}
        self._refresh_outlines()

    def _on_drag(self, event) -> None:
        if self._drag_start is None:
            return
        hit = self._hit(event)
        if hit is None or hit[0] != "cell":
            return
        (r0, c0), (r1, c1) = self._drag_start, (hit[1], hit[2])
        rect = {(i, j) for i in range(min(r0, r1), max(r0, r1) + 1) for j in range(min(c0, c1), max(c0, c1) + 1)}
        self.selection = self._drag_base | rect
        self._refresh_outlines()

    def _on_hover(self, event) -> None:
        hit = self._hit(event)
        if hit is None or hit[0] != "cell":
            self.info.configure(text="")
            return
        uids = self.wells.get((hit[1], hit[2]), [])
        if not uids:
            self.info.configure(text=f"{chr(ord('A') + hit[1])}{hit[2] + 1}: empty")
            return
        s = self.app.session
        ann = s.annotations()
        lines = []
        for uid in uids:
            m, a = s.measurements[uid], ann[uid]
            lines.append(f"{m.well} · {m.sample_id}")
            lines.append(f"role {a.role}, group {a.group or '—'}, status {a.status}")
            detected = [f"{r.target} {r.ct:.2f}" for r in m.results if r.ct is not None]
            lines.append("Detected: " + (", ".join(detected) if detected else "none"))
        self.info.configure(text="\n".join(lines))

    def _selected_uids(self) -> list[int]:
        return [u for pos in self.selection for u in self.wells.get(pos, [])]

    def _select_all(self) -> None:
        self.selection = set(self.wells)
        self._refresh_outlines()

    def _clear_selection(self) -> None:
        self.selection.clear()
        self._refresh_outlines()

    def _require_selection(self) -> list[int] | None:
        uids = self._selected_uids()
        if not uids:
            self.app.status("Select wells on the plate first.")
            return None
        return uids

    def _assign_group(self) -> None:
        uids = self._require_selection()
        if uids is None:
            return
        group = self.group_var.get().strip()
        if not group:
            self.app.status("Enter or pick a group name first.")
            return
        self.app.session.set_group(uids, group)
        self.app.changed()

    def _remove_group(self) -> None:
        uids = self._require_selection()
        if uids is None:
            return
        self.app.session.set_group(uids, "")
        self.app.changed()

    def _set_included(self, included: bool) -> None:
        uids = self._require_selection()
        if uids is None:
            return
        self.app.session.set_included(uids, included)
        self.app.changed()

    def _suggest_groups(self) -> None:
        key = self._current_key()
        if key is None:
            return
        s = self.app.session
        assignment = s.suggest_groups(key)
        if not assignment:
            messagebox.showinfo("Suggest groups", "No sample ID occurs twice on this plate; no split needed.", parent=self)
            return
        names = sorted(set(assignment.values()))
        if not messagebox.askyesno(
            "Suggest groups",
            f"Split this plate into {len(names)} contiguous blocks ({', '.join(names)}) so that no sample ID occurs twice in a block?\n\n"
            "Existing group assignments of these wells are replaced. Check the result on the plate and rename the groups afterwards.",
            parent=self,
        ):
            return
        for name in names:
            s.set_group([u for u, g in assignment.items() if g == name], name)
        self.app.changed()

    def _rename_group(self) -> None:
        s = self.app.session
        groups = sorted(set(s.groups.values()))
        if not groups:
            self.app.status("No user-defined groups to rename.")
            return
        old = ChoiceDialog(self, "Rename group", "Group to rename:", groups, initial=self.group_var.get() if self.group_var.get() in groups else groups[0]).result
        if not old:
            return
        new = ChoiceDialog(self, "Rename group", f"New name for '{old}':", s.all_groups(), initial=old).result
        if not new or new == old:
            return
        s.rename_group(old, new)
        self.app.changed()
