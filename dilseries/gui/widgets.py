"""Reusable tkinter widgets."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from dilseries.util import natural_key


class ScrolledTree(ttk.Frame):
    """Treeview with scrollbars, sortable columns and selection kept across refreshes."""

    def __init__(self, master, columns: list[tuple[str, str, int]], selectmode: str = "extended", height: int = 12):
        super().__init__(master)
        self.tree = ttk.Treeview(self, columns=[c[0] for c in columns], show="headings", selectmode=selectmode, height=height)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self._headings = {}
        for cid, heading, width in columns:
            self._headings[cid] = heading
            self.tree.heading(cid, text=heading, command=lambda c=cid: self.sort_by(c, toggle=True))
            self.tree.column(cid, width=width, minwidth=30, stretch=False, anchor="w")
        self._sort: tuple[str | None, bool] = (None, False)

    def set_rows(self, rows: list[tuple[str, tuple, tuple[str, ...]]]) -> None:
        """Replace all rows. rows = [(iid, values, tags)]."""
        selected = set(self.tree.selection())
        focus = self.tree.focus()
        yview = self.tree.yview()
        self.tree.delete(*self.tree.get_children())
        for iid, values, tags in rows:
            self.tree.insert("", "end", iid=iid, values=values, tags=tags)
        if self._sort[0]:
            self.sort_by(self._sort[0], toggle=False)
        keep = [iid for iid in selected if self.tree.exists(iid)]
        if keep:
            self.tree.selection_set(keep)
        if focus and self.tree.exists(focus):
            self.tree.focus(focus)
        self.tree.yview_moveto(yview[0])

    def sort_by(self, column: str, toggle: bool) -> None:
        current, descending = self._sort
        if toggle:
            descending = not descending if current == column else False
        items = [(self.tree.set(iid, column), iid) for iid in self.tree.get_children("")]
        items.sort(key=lambda x: natural_key(x[0]), reverse=descending)
        for index, (_, iid) in enumerate(items):
            self.tree.move(iid, "", index)
        for cid, heading in self._headings.items():
            arrow = (" ▼" if descending else " ▲") if cid == column else ""
            self.tree.heading(cid, text=heading + arrow)
        self._sort = (column, descending)

    def selected(self) -> list[str]:
        return list(self.tree.selection())


def labeled(master, text: str, widget_factory, row: int, column: int, **grid):
    ttk.Label(master, text=text).grid(row=row, column=column, sticky="w", padx=(0, 4), pady=2)
    widget = widget_factory(master)
    widget.grid(row=row, column=column + 1, sticky="w", pady=2, **grid)
    return widget


def color_swatch(master, color: str, text: str) -> ttk.Frame:
    frame = ttk.Frame(master)
    box = tk.Canvas(frame, width=14, height=14, highlightthickness=0)
    box.create_rectangle(1, 1, 13, 13, fill=color, outline="#777777")
    box.pack(side="left", padx=(0, 4))
    ttk.Label(frame, text=text).pack(side="left")
    return frame
