"""Summary of the series that will be exported."""

from __future__ import annotations

from tkinter import ttk

from dilseries.gui.dialogs import ChoiceDialog
from dilseries.gui.widgets import ScrolledTree

SERIES_TYPES = ["", "Linearity", "LoD"]


class SeriesTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app
        self._keys: dict[str, tuple] = {}
        ttk.Label(
            self,
            text="Each series becomes one sheet in the Excel export (one step × repeat block per target). "
            "A series is identified by platform, assay/group and name prefix.",
            foreground="#555555",
        ).pack(anchor="w", pady=(0, 6))
        self.warnings = ttk.Label(self, text="", foreground="#b00020", justify="left", wraplength=1000)
        self.warnings.pack(side="bottom", anchor="w", pady=(8, 0))
        buttons = ttk.Frame(self)
        buttons.pack(side="bottom", fill="x", pady=(6, 0))
        ttk.Button(buttons, text="Set type…", command=self._set_type).pack(side="left")
        ttk.Button(buttons, text="Export Excel…", command=app.export).pack(side="right")
        self.table = ScrolledTree(
            self,
            [
                ("series", "Series", 110),
                ("platform", "Platform", 100),
                ("group", "Assay / group", 130),
                ("type", "Type", 90),
                ("steps", "Steps", 170),
                ("repeats", "Repeats", 90),
                ("samples", "Samples", 70),
                ("missing", "Missing", 70),
                ("dups", "Duplicates", 80),
                ("targets", "Targets", 330),
            ],
            height=10,
        )
        self.table.pack(fill="both", expand=True)
        self.table.tree.tag_configure("problem", background="#fde2e1")
        self.table.tree.bind("<Double-1>", lambda e: self._set_type())

    def refresh(self) -> None:
        s = self.app.session
        rows = []
        self._keys = {}
        for i, sr in enumerate(s.series()):
            iid = f"s{i}"
            self._keys[iid] = sr.key
            steps = ", ".join(sr.steps)
            repeats = f"{sr.repeats[0]}–{sr.repeats[-1]}" if sr.repeats else ""
            targets = ", ".join(t for t, _ in sr.targets)
            values = (sr.prefix, sr.platform, sr.group, sr.type, steps, repeats, len(sr.measurements), sr.missing, sr.duplicates, targets)
            rows.append((iid, values, ("problem",) if sr.duplicates else ()))
        self.table.set_rows(rows)
        self.warnings.configure(text="\n".join(s.warnings()))

    def _set_type(self) -> None:
        keys = [self._keys[iid] for iid in self.table.selected() if iid in self._keys]
        if not keys:
            self.app.status("Select one or more series first.")
            return
        initial = self.app.session.series_types.get(keys[0], "")
        value = ChoiceDialog(self, "Series type", "Type (free text, e.g. Linearity or LoD):", SERIES_TYPES, initial).result
        if value is None:
            return
        for key in keys:
            self.app.session.set_series_type(key, value)
        self.app.changed()
