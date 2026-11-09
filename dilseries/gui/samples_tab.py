"""Review table of all measurements with their parsed role, series, step and repeat."""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import ttk

from dilseries.gui.dialogs import EditSamplesDialog
from dilseries.gui.widgets import ScrolledTree
from dilseries.naming import NamingConfig, Role
from dilseries.session import PROBLEM_STATUSES, STATUS_CONTROL
from dilseries.util import format_datetime, natural_key

ORDERS = {"Step, then repeat": True, "Repeat, then step": False}
DIGITS = ["auto", "1", "2", "3"]
FILTERS = ["All", "Problems", "Dilution samples", "Controls", "Excluded", "Manually edited"]


class SamplesTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app

        naming = ttk.LabelFrame(self, text="Sample name layout", padding=6)
        naming.pack(fill="x")
        ttk.Label(naming, text="Order:").grid(row=0, column=0, sticky="w")
        self.order_var = tk.StringVar(value="Step, then repeat")
        ttk.Combobox(naming, textvariable=self.order_var, values=list(ORDERS), state="readonly", width=18).grid(row=0, column=1, sticky="w", padx=(4, 12))
        ttk.Label(naming, text="Step digits:").grid(row=0, column=2, sticky="w")
        self.step_var = tk.StringVar(value="auto")
        ttk.Combobox(naming, textvariable=self.step_var, values=DIGITS, state="readonly", width=6).grid(row=0, column=3, sticky="w", padx=(4, 12))
        ttk.Label(naming, text="Repeat digits:").grid(row=0, column=4, sticky="w")
        self.repeat_var = tk.StringVar(value="auto")
        ttk.Combobox(naming, textvariable=self.repeat_var, values=DIGITS, state="readonly", width=6).grid(row=0, column=5, sticky="w", padx=(4, 12))
        ttk.Label(naming, text="Negative markers:").grid(row=0, column=6, sticky="w")
        self.neg_var = tk.StringVar(value=", ".join(app.session.naming.negative_markers))
        ttk.Entry(naming, textvariable=self.neg_var, width=12).grid(row=0, column=7, sticky="w", padx=(4, 12))
        ttk.Label(naming, text="Control names:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.ctrl_var = tk.StringVar(value=", ".join(app.session.naming.control_names))
        ttk.Entry(naming, textvariable=self.ctrl_var, width=70).grid(row=1, column=1, columnspan=6, sticky="we", padx=(4, 12), pady=(4, 0))
        ttk.Button(naming, text="Apply", command=self._apply_naming).grid(row=1, column=7, sticky="w", pady=(4, 0))
        self.layout_label = ttk.Label(
            naming,
            text="",
            foreground="#555555",
            justify="left",
        )
        self.layout_label.grid(row=2, column=0, columnspan=8, sticky="w", pady=(6, 0))
        ttk.Label(
            naming,
            text="Names with _, - or space delimiters are split into series_step_repeat. "
            "Names without delimiters use the digit counts above ('auto' infers them from all names).",
            foreground="#555555",
        ).grid(row=3, column=0, columnspan=8, sticky="w")

        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(8, 4))
        ttk.Label(bar, text="Show:").pack(side="left")
        self.filter_var = tk.StringVar(value="All")
        box = ttk.Combobox(bar, textvariable=self.filter_var, values=FILTERS, state="readonly", width=16)
        box.pack(side="left", padx=4)
        box.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        ttk.Label(bar, text="Search sample ID:").pack(side="left", padx=(12, 0))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self.refresh())
        ttk.Entry(bar, textvariable=self.search_var, width=18).pack(side="left", padx=4)
        self.count_label = ttk.Label(bar, text="")
        self.count_label.pack(side="right")

        buttons = ttk.Frame(self)
        buttons.pack(side="bottom", fill="x", pady=(6, 0))
        ttk.Button(buttons, text="Edit…", command=self._edit).pack(side="left")
        ttk.Button(buttons, text="Reset to automatic", command=self._reset).pack(side="left", padx=4)
        ttk.Button(buttons, text="Include", command=lambda: self._set_included(True)).pack(side="left", padx=(12, 0))
        ttk.Button(buttons, text="Exclude", command=lambda: self._set_included(False)).pack(side="left", padx=4)

        self.table = ScrolledTree(
            self,
            [
                ("inc", "Import", 55),
                ("platform", "Platform", 90),
                ("plate", "Plate / run", 170),
                ("well", "Well", 50),
                ("date", "Run date", 135),
                ("sample", "Sample ID", 130),
                ("group", "Assay / group", 120),
                ("role", "Role", 80),
                ("series", "Series", 90),
                ("step", "Step", 50),
                ("repeat", "Repeat", 60),
                ("status", "Status", 90),
                ("edited", "Edited", 55),
            ],
            height=10,
        )
        self.table.pack(fill="both", expand=True)
        tree = self.table.tree
        tree.tag_configure("problem", background="#fde2e1")
        tree.tag_configure("control", background="#eef3fb")
        tree.tag_configure("excluded", foreground="#8a8a8a")
        tree.bind("<Double-1>", lambda e: self._edit())

    def refresh(self) -> None:
        s = self.app.session
        ann = s.annotations()
        self.layout_label.configure(text="Detected layout: " + ("; ".join(s.layout_notes) if s.layout_notes else "—"))
        flt = self.filter_var.get()
        needle = self.search_var.get().strip().casefold()
        rows = []
        ordered = sorted(
            ann,
            key=lambda u: (s.run_datetime(s.measurements[u]) or datetime.max, s.measurements[u].plate_id, natural_key(s.measurements[u].well)),
        )
        for uid in ordered:
            a = ann[uid]
            m = s.measurements[uid]
            if needle and needle not in m.sample_id.casefold():
                continue
            if flt == "Problems" and a.status not in PROBLEM_STATUSES:
                continue
            if flt == "Dilution samples" and (a.role not in (Role.SAMPLE, Role.NEGATIVE) or not a.included):
                continue
            if flt == "Controls" and a.role != Role.CONTROL:
                continue
            if flt == "Excluded" and a.included:
                continue
            if flt == "Manually edited" and not a.overridden:
                continue
            tags = ()
            if not a.included:
                tags = ("excluded",)
            elif a.status in PROBLEM_STATUSES:
                tags = ("problem",)
            elif a.status == STATUS_CONTROL:
                tags = ("control",)
            values = (
                "yes" if a.included else "no",
                m.platform,
                m.plate_id,
                m.well,
                format_datetime(s.run_datetime(m)),
                m.sample_id,
                a.group,
                str(a.role),
                a.series,
                a.step,
                "" if a.repeat is None else a.repeat,
                a.status,
                "yes" if a.overridden else "",
            )
            rows.append((str(uid), values, tags))
        self.table.set_rows(rows)
        self.count_label.configure(text=f"{len(rows)} of {len(ann)} measurements")

    def _selected_uids(self) -> list[int]:
        return [int(iid) for iid in self.table.selected()]

    def _apply_naming(self) -> None:
        markers = tuple(m.strip() for m in self.neg_var.get().split(",") if m.strip())
        controls = tuple(c.strip() for c in self.ctrl_var.get().split(",") if c.strip())
        step = self.step_var.get()
        repeat = self.repeat_var.get()
        config = NamingConfig(
            step_first=ORDERS[self.order_var.get()],
            step_digits=None if step == "auto" else int(step),
            repeat_digits=None if repeat == "auto" else int(repeat),
            negative_markers=markers,
            control_names=controls,
        )
        self.app.session.set_naming(config)
        self.app.changed()

    def _edit(self) -> None:
        uids = self._selected_uids()
        if not uids:
            self.app.status("Select one or more samples first.")
            return
        initial = {}
        if len(uids) == 1:
            a = self.app.session.annotations()[uids[0]]
            initial = {"role": str(a.role), "series": a.series, "step": a.step, "repeat": "" if a.repeat is None else str(a.repeat)}
        dialog = EditSamplesDialog(self, len(uids), initial)
        if not dialog.result:
            return
        self.app.session.set_override(uids, **dialog.result)
        self.app.changed()

    def _reset(self) -> None:
        uids = self._selected_uids()
        if uids:
            self.app.session.clear_override(uids)
            self.app.changed()

    def _set_included(self, included: bool) -> None:
        uids = self._selected_uids()
        if uids:
            self.app.session.set_included(uids, included)
            self.app.changed()
