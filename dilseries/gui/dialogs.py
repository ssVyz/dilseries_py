"""Modal dialogs."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from dilseries.naming import NEG_STEP, Role
from dilseries.util import parse_user_datetime

KEEP = object()  # sentinel: leave value unchanged


class RunInfoDialog(simpledialog.Dialog):
    """Set run date and operator for one or more runs."""

    def __init__(self, parent, count: int, date_text: str, operator: str):
        self._count = count
        self._date_text = date_text
        self._operator = operator
        self.result: tuple | None = None
        super().__init__(parent, title="Run date and operator")

    def body(self, master):
        ttk.Label(master, text=f"{self._count} run(s) selected.").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        ttk.Label(master, text="Run date:").grid(row=1, column=0, sticky="w")
        self.date_var = tk.StringVar(value=self._date_text)
        entry = ttk.Entry(master, textvariable=self.date_var, width=22)
        entry.grid(row=1, column=1, sticky="w")
        ttk.Label(master, text="YYYY-MM-DD or DD.MM.YYYY, optional HH:MM.\nEmpty = use the date from the export.", foreground="#555555").grid(
            row=2, column=1, sticky="w", pady=(0, 6)
        )
        ttk.Label(master, text="Operator:").grid(row=3, column=0, sticky="w")
        self.operator_var = tk.StringVar(value=self._operator)
        ttk.Entry(master, textvariable=self.operator_var, width=22).grid(row=3, column=1, sticky="w")
        ttk.Label(master, text="Empty = use the operator from the export.", foreground="#555555").grid(row=4, column=1, sticky="w")
        return entry

    def validate(self):
        try:
            self._when = parse_user_datetime(self.date_var.get())
        except ValueError as exc:
            messagebox.showerror("Invalid date", str(exc), parent=self)
            return False
        return True

    def apply(self):
        self.result = (self._when, self.operator_var.get().strip())


class EditSamplesDialog(simpledialog.Dialog):
    """Manually set role, series, step and repeat for selected samples."""

    ROLES = [Role.SAMPLE, Role.NEGATIVE, Role.CONTROL, Role.UNKNOWN]

    def __init__(self, parent, count: int, initial: dict[str, str]):
        self._count = count
        self._initial = initial
        self.result: dict | None = None
        super().__init__(parent, title="Edit samples")

    def body(self, master):
        multi = self._count > 1
        hint = f"{self._count} samples selected. Empty fields stay unchanged." if multi else "Manual values override the automatic name parsing."
        ttk.Label(master, text=hint).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        self.vars = {}
        fields = [("role", "Role"), ("series", "Series"), ("step", f"Step (number or '{NEG_STEP}')"), ("repeat", "Repeat")]
        first = None
        for row, (key, label) in enumerate(fields, start=1):
            ttk.Label(master, text=label + ":").grid(row=row, column=0, sticky="w", pady=2)
            var = tk.StringVar(value=self._initial.get(key, ""))
            if key == "role":
                widget = ttk.Combobox(master, textvariable=var, values=[""] + [str(r) for r in self.ROLES] if multi else [str(r) for r in self.ROLES], state="readonly", width=20)
            else:
                widget = ttk.Entry(master, textvariable=var, width=22)
            widget.grid(row=row, column=1, sticky="w", pady=2)
            self.vars[key] = var
            first = first or widget
        return first

    def validate(self):
        step = self.vars["step"].get().strip()
        repeat = self.vars["repeat"].get().strip()
        if step and step != NEG_STEP and not step.isdigit():
            messagebox.showerror("Invalid step", f"Step must be a number or '{NEG_STEP}'.", parent=self)
            return False
        if repeat and not repeat.isdigit():
            messagebox.showerror("Invalid repeat", "Repeat must be a number.", parent=self)
            return False
        return True

    def apply(self):
        out = {}
        role = self.vars["role"].get().strip()
        if role:
            out["role"] = Role(role)
        series = self.vars["series"].get().strip()
        if series or self._count == 1:
            out["series"] = series
        step = self.vars["step"].get().strip()
        if step:
            out["step"] = step if step == NEG_STEP else str(int(step))
        repeat = self.vars["repeat"].get().strip()
        if repeat:
            out["repeat"] = int(repeat)
        self.result = out


class ChoiceDialog(simpledialog.Dialog):
    """Ask for a value from an editable combobox."""

    def __init__(self, parent, title: str, prompt: str, values: list[str], initial: str = ""):
        self._prompt = prompt
        self._values = values
        self._initial = initial
        self.result: str | None = None
        super().__init__(parent, title=title)

    def body(self, master):
        ttk.Label(master, text=self._prompt).grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.var = tk.StringVar(value=self._initial)
        box = ttk.Combobox(master, textvariable=self.var, values=self._values, width=30)
        box.grid(row=1, column=0, sticky="we")
        return box

    def apply(self):
        self.result = self.var.get().strip()
