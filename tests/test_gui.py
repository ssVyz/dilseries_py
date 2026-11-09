"""Smoke test: build the GUI, load files and exercise the plate view without dialogs."""

import tkinter as tk

import pytest


@pytest.fixture
def app():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    root.withdraw()
    from dilseries.gui.app import App

    application = App(root)
    yield application
    root.destroy()


def test_gui_loads_files_and_assigns_groups(app, cobas_zip, lcpro_file):
    app.load_files([str(cobas_zip), str(lcpro_file)])
    assert len(app.session.files) == 2
    for index in range(len(app.tabs)):
        app.notebook.select(index)
        app.update()

    plate_tab = app.tabs[1][0]
    lc_index = next(i for i, key in enumerate(plate_tab.plate_keys) if key[0] == "LC Pro")
    plate_tab.plate_box.current(lc_index)
    plate_tab._load_plate()
    plate_tab.selection = {(0, 0), (1, 0), (2, 0), (3, 0)}  # column 1
    plate_tab.group_var.set("Test A")
    plate_tab._assign_group()
    assert "Test A" in app.session.all_groups()

    plate_tab.selection = {(0, 1)}
    plate_tab._set_included(False)
    assert len(app.session.excluded) == 1

    samples_tab = app.tabs[2][0]
    assert len(samples_tab.table.tree.get_children()) == len(app.session.measurements)
    samples_tab.step_var.set("1")
    samples_tab.repeat_var.set("2")
    samples_tab._apply_naming()
    assert app.session.naming.step_digits == 1
