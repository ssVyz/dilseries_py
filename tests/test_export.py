from datetime import datetime

from openpyxl import load_workbook

from dilseries.export_xlsx import NOT_DETECTED, export_workbook
from dilseries.session import Session


def _find_row(ws, value, start=1):
    for row in range(start, ws.max_row + 1):
        if ws.cell(row, 1).value == value:
            return row
    raise AssertionError(f"{value!r} not found")


def test_export_cobas_series(cobas_zip, tmp_path):
    s = Session()
    s.add_file(cobas_zip)
    out = tmp_path / "out.xlsx"
    export_workbook(s, out)

    wb = load_workbook(out)
    assert wb.sheetnames == ["Overview", "S1 U_TEST c5800", "Controls", "Data"]
    ws = wb["S1 U_TEST c5800"]
    t1 = _find_row(ws, "T1 (Ch.1)")
    header = t1 + 2
    assert [ws.cell(header, c).value for c in range(1, 7)] == ["Day", "Operator", "Repeat", 1, 2, "neg"]
    first = header + 1
    assert ws.cell(first, 1).value.date() == s.run_datetime(next(iter(s.measurements.values()))).date()
    assert ws.cell(first, 2).value == "alice"
    assert [ws.cell(first, c).value for c in range(3, 7)] == [1, 20.0, 24.0, NOT_DETECTED]
    assert ws.cell(first, 4).number_format == "0.00"
    ic = _find_row(ws, "IC (Ch.5)")
    assert ws.cell(ic + 3, 4).value == 31.2

    data = wb["Data"]
    assert data.cell(1, 9).value == "Sample ID"
    assert data.max_row == 1 + 7 * 3  # 6 samples + 1 control, 3 targets each
    assert wb["Controls"].cell(2, 7).value == "(-) Ctrl"


def test_export_marks_duplicates_and_user_dates(lcpro_file, tmp_path):
    s = Session()
    s.add_file(lcpro_file)
    (run,) = s.runs()
    s.set_run_info([run.key], when=datetime(2026, 10, 20, 9, 0), operator="bob")
    out = tmp_path / "dup.xlsx"
    export_workbook(s, out)

    wb = load_workbook(out)
    ws = wb["S2 LCPro"]
    header = _find_row(ws, "Day")
    cell = ws.cell(header + 1, 4)  # FAM, step 1, repeat 1: measured in B1 and A2
    assert cell.comment is not None and "2 measurements" in cell.comment.text
    assert cell.fill.fgColor.rgb.endswith("FFE699")
    assert ws.cell(header + 1, 1).value == datetime(2026, 10, 20)
    assert ws.cell(header + 1, 2).value == "bob"
    overview = wb["Overview"]
    texts = [c.value for row in overview.iter_rows() for c in row if isinstance(c.value, str)]
    assert any("share series/step/repeat" in t for t in texts)


def test_sheet_names_are_unique_and_valid(tmp_path):
    from tests.conftest import lcpro_csv

    wells = [("A1", "Very/Long:Series*Name101", {"FAM": "20"}), ("A2", "Very/Long:Series*Name102", {"FAM": "21"})]
    path = tmp_path / "names_ResultTable.csv"
    path.write_text(lcpro_csv(wells), encoding="utf-8")
    s = Session()
    s.add_file(path)
    out = tmp_path / "names.xlsx"
    export_workbook(s, out)
    names = load_workbook(out).sheetnames
    series_sheet = names[1]
    assert len(series_sheet) <= 31
    assert not set("[]:*?/\\") & set(series_sheet)
