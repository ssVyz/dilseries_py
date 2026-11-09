"""Main window."""

from __future__ import annotations

import os
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk

from dilseries import __version__
from dilseries.export_xlsx import export_workbook
from dilseries.importers import FILE_TYPES
from dilseries.gui.plate_tab import PlateTab
from dilseries.gui.runs_tab import RunsTab
from dilseries.gui.samples_tab import SamplesTab
from dilseries.gui.series_tab import SeriesTab
from dilseries.session import Session


class App(ttk.Frame):
    def __init__(self, root: tk.Tk):
        super().__init__(root)
        self.root = root
        self.session = Session()
        root.title(f"dilseries {__version__} – qPCR dilution series import")
        root.geometry("1280x820")
        root.minsize(1000, 650)
        self.pack(fill="both", expand=True)

        toolbar = ttk.Frame(self, padding=(8, 8, 8, 0))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Add files…", command=self.add_files).pack(side="left")
        ttk.Button(toolbar, text="Export Excel…", command=self.export).pack(side="left", padx=6)
        ttk.Label(toolbar, text="Supported: cobas 5800 export (.zip/.xml), LC Pro result table (.csv)", foreground="#555555").pack(side="left", padx=12)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)
        self.tabs = [
            (RunsTab(self.notebook, self), "1  Files & runs"),
            (PlateTab(self.notebook, self), "2  Plate layout"),
            (SamplesTab(self.notebook, self), "3  Samples"),
            (SeriesTab(self.notebook, self), "4  Series & export"),
        ]
        for tab, title in self.tabs:
            self.notebook.add(tab, text=title)

        self.status_var = tk.StringVar()
        ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w", padding=(6, 2)).pack(fill="x", side="bottom")
        root.bind("<Control-o>", lambda e: self.add_files())
        root.bind("<Control-e>", lambda e: self.export())
        self.changed()

    # ---------------------------------------------------------------- actions
    def add_files(self) -> None:
        paths = filedialog.askopenfilenames(parent=self.root, title="Add export files", filetypes=FILE_TYPES)
        if paths:
            self.load_files(paths)

    def load_files(self, paths) -> None:
        errors = []
        self.root.configure(cursor="watch")
        self.root.update_idletasks()
        try:
            for path in paths:
                try:
                    self.session.add_file(path)
                except Exception as exc:  # report every failing file, keep the others
                    errors.append(f"{Path(path).name}: {exc}")
        finally:
            self.root.configure(cursor="")
        self.changed()
        if errors:
            messagebox.showerror("Some files could not be imported", "\n".join(errors), parent=self.root)

    def export(self) -> None:
        s = self.session
        if not s.series():
            messagebox.showinfo("Export", "Nothing to export yet. Add files with dilution series samples first.", parent=self.root)
            return
        warnings = s.warnings()
        if warnings and not messagebox.askyesno(
            "Export with warnings?", "\n\n".join(warnings) + "\n\nExport anyway?", parent=self.root
        ):
            return
        first = next(iter(s.files), None)
        initial_dir = str(Path(first).parent) if first else None
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Export Excel workbook",
            defaultextension=".xlsx",
            initialdir=initial_dir,
            initialfile=f"dilseries_{date.today():%Y%m%d}.xlsx",
            filetypes=[("Excel workbook", "*.xlsx")],
        )
        if not path:
            return
        try:
            export_workbook(s, path)
        except PermissionError:
            messagebox.showerror("Export failed", f"Cannot write {path}.\nIs the file open in Excel?", parent=self.root)
            return
        self.status(f"Exported {path}")
        open_file = getattr(os, "startfile", None)  # Windows only
        if open_file and messagebox.askyesno("Export finished", f"Saved {Path(path).name}.\n\nOpen it now?", parent=self.root):
            open_file(path)

    # ---------------------------------------------------------------- updates
    def changed(self) -> None:
        """Refresh all views after the session changed."""
        for tab, _ in self.tabs:
            tab.refresh()
        s = self.session
        ann = s.annotations()
        n_problems = len(s.warnings())
        self.status(
            f"{len(s.files)} file(s) · {len(ann)} measurements · {len(s.series())} series"
            + (f" · {n_problems} warning(s), see '4 Series & export'" if n_problems else "")
        )

    def status(self, text: str) -> None:
        self.status_var.set(text)


def run(paths: list[str] | None = None) -> None:
    _enable_dpi_awareness()
    root = tk.Tk()
    _configure_style(root)
    app = App(root)
    if paths:
        root.after(100, lambda: app.load_files(paths))
    root.mainloop()


def _enable_dpi_awareness() -> None:
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass


def _configure_style(root: tk.Tk) -> None:
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    line = tkfont.nametofont("TkDefaultFont").metrics("linespace")
    style.configure("Treeview", rowheight=line + 6)
