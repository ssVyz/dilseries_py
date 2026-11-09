"""Tab listing loaded files and runs; run dates and operators are edited here."""

from __future__ import annotations

from pathlib import Path
from tkinter import ttk

from dilseries.gui.dialogs import RunInfoDialog
from dilseries.gui.widgets import ScrolledTree
from dilseries.util import format_datetime


class RunsTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app
        self._run_keys: dict[str, tuple] = {}
        self._file_paths: dict[str, str] = {}

        files_box = ttk.LabelFrame(self, text="Files", padding=6)
        files_box.pack(fill="x")
        self.files = ScrolledTree(
            files_box,
            [("file", "File", 420), ("format", "Format", 160), ("count", "Measurements", 110), ("skipped", "Skipped (already loaded)", 180), ("warnings", "Warnings", 360)],
            height=5,
        )
        self.files.pack(fill="x", expand=True)
        buttons = ttk.Frame(files_box)
        buttons.pack(fill="x", pady=(6, 0))
        ttk.Button(buttons, text="Add files…", command=app.add_files).pack(side="left")
        ttk.Button(buttons, text="Remove selected files", command=self._remove_files).pack(side="left", padx=6)

        runs_box = ttk.LabelFrame(self, text="Runs / plates", padding=6)
        runs_box.pack(fill="both", expand=True, pady=(8, 0))
        ttk.Label(
            runs_box,
            text="Runs without a date are highlighted. LC Pro result tables contain no run date or operator; set them here (double-click a run).",
            foreground="#555555",
        ).pack(anchor="w", pady=(0, 4))
        ttk.Button(runs_box, text="Set run date / operator…", command=self._edit_runs).pack(side="bottom", anchor="w", pady=(6, 0))
        self.runs = ScrolledTree(
            runs_box,
            [
                ("platform", "Platform", 100),
                ("plate", "Plate / run", 190),
                ("run", "Run ID", 170),
                ("date", "Run date", 130),
                ("source", "Date source", 95),
                ("operator", "Operator", 110),
                ("count", "Measurements", 110),
                ("note", "Note", 240),
                ("files", "Files", 420),
            ],
            height=8,
        )
        self.runs.pack(fill="both", expand=True)
        self.runs.tree.tag_configure("missing", background="#fde2e1")
        self.runs.tree.tag_configure("superseded", foreground="#8a8a8a")
        self.runs.tree.bind("<Double-1>", lambda e: self._edit_runs())

    def refresh(self) -> None:
        s = self.app.session
        self._file_paths = {f"f{i}": path for i, path in enumerate(s.files)}
        rows = []
        for iid, path in self._file_paths.items():
            f = s.files[path]
            notes = list(f.warnings)
            superseded = s.superseded_count(path)
            if superseded:
                notes.insert(0, f"{superseded} wells not used: same plate imported from Flow results")
            rows.append((iid, (Path(path).name, f.format_name, len(f.uids), f.skipped, "; ".join(notes)), ()))
        self.files.set_rows(rows)
        self._run_keys = {}
        rows = []
        for i, r in enumerate(s.runs()):
            iid = f"run{i}"
            self._run_keys[iid] = r.key
            note = f"not used: plate imported from {r.superseded_by}" if r.superseded_by else ""
            values = (r.key[0], r.key[1], ", ".join(r.run_ids), format_datetime(r.when), r.date_source, ", ".join(r.operators), r.count, note, ", ".join(r.files))
            tags = ("superseded",) if r.superseded_by else ("missing",) if r.date_source == "missing" else ()
            rows.append((iid, values, tags))
        self.runs.set_rows(rows)

    def _remove_files(self) -> None:
        paths = [self._file_paths[iid] for iid in self.files.selected() if iid in self._file_paths]
        if not paths:
            self.app.status("Select one or more files first.")
            return
        for path in paths:
            self.app.session.remove_file(path)
        self.app.changed()

    def _edit_runs(self) -> None:
        keys = [self._run_keys[iid] for iid in self.runs.selected() if iid in self._run_keys]
        if not keys:
            self.app.status("Select one or more runs first.")
            return
        s = self.app.session
        first = s.run_overrides.get(keys[0])
        date_text = format_datetime(first.when) if first and first.when else ""
        operator = first.operator if first and first.operator else ""
        dialog = RunInfoDialog(self, len(keys), date_text, operator)
        if dialog.result is None:
            return
        when, operator = dialog.result
        s.set_run_info(keys, when=when, operator=operator)
        self.app.changed()
