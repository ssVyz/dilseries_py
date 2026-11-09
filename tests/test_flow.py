from datetime import datetime

from dilseries import importers
from dilseries.export_xlsx import cell_value, export_workbook
from dilseries.importers import flow, lcpro
from dilseries.model import is_internal_control
from dilseries.session import STATUS_SUPERSEDED, Session
from tests.conftest import FLOW_WELLS, flow_csv


def test_flow_reads_results_and_metadata(flow_file):
    result = importers.load(flow_file)
    assert result.format_name == flow.FORMAT_NAME
    assert result.warnings == []
    assert len(result.measurements) == 7
    m = next(m for m in result.measurements if m.well == "B1")
    assert (m.platform, m.plate_id, m.sample_id, m.assay) == ("Flow", "PLATE1", "S2101", "testA")
    assert m.timestamp == datetime(2026, 10, 28)
    assert [(r.target, r.ct, r.call) for r in m.results] == [("t-FAM", 18.1, "REACTIVE"), ("t-IC", 30.0, "REACTIVE")]
    assert m.extra == {
        "Release status": "2nd User Approve",
        "Purification Plate": "0507253000483175",
        "Purification kit": "MP96 Kit",
        "Purification kit lot": "95950320",
    }
    ntc = next(m for m in result.measurements if m.well == "A1")
    assert ntc.timestamp == datetime(2026, 10, 28)  # controls have no date; the plate date is used


def test_flow_ic_failed_cells(flow_file):
    ms = {m.well: m for m in importers.load(flow_file).measurements}
    assert cell_value(ms["A2"].result("t-VIC")) == "IC FAILED"
    assert cell_value(ms["B2"].result("t-VIC")) == 25.5  # detected targets keep their Ct
    assert cell_value(ms["D1"].result("t-FAM")) == "-"


def test_flow_day_first_dates_and_reagents(tmp_path):
    path = tmp_path / "x_Results.csv"
    path.write_text(flow_csv(FLOW_WELLS[:2], date="28/10/2026", reagents=(("testA", "MMX", "Master mix", "L123"),)), encoding="utf-8", newline="")
    m = next(m for m in importers.load(path).measurements if m.well == "B1")
    assert m.timestamp == datetime(2026, 10, 28)
    assert m.extra["PCR reagents"] == "MMX (Master mix) lot L123"


def test_format_detection_does_not_mix_up_csv_formats(flow_file, lcpro_file):
    assert flow.can_read(flow_file) and not lcpro.can_read(flow_file)
    assert lcpro.can_read(lcpro_file) and not flow.can_read(lcpro_file)


def test_column_suffixes_are_ignored():
    assert flow.normalize_column("﻿SampleId_1") == "sampleid"
    assert flow.normalize_column("QuantResult1") == "quantresult"
    assert flow.normalize_column("Plate_Type") == "plate_type"


def test_internal_control_names():
    assert all(is_internal_control(t) for t in ["IC", "CIC", "iso-IC", "iso-aciIC"])
    assert not any(is_internal_control(t) for t in ["MIC", "TOXIC", "iso-16S", "FAM"])


def test_flow_groups_by_test_without_duplicates(flow_file):
    s = Session()
    s.add_file(flow_file)
    assert not s.warnings()
    series = {(sr.group, sr.prefix): sr for sr in s.series()}
    assert set(series) == {("testA", "S2"), ("testB", "S2")}
    assert [t for t, _ in series[("testB", "S2")].targets] == ["t-VIC", "t-aciIC"]  # internal control last
    assert s.suggest_groups(("Flow", "PLATE1")) == {}  # tests already separate the duplicates


def test_flow_supersedes_lcpro_for_same_plate_in_any_order(flow_file, lcpro_file):
    for order in ([lcpro_file, flow_file], [flow_file, lcpro_file]):
        s = Session()
        for path in order:
            s.add_file(path)
        lc_path = s.files[str(lcpro_file.resolve())].path
        assert s.superseded_count(lc_path) == 7
        assert {sr.platform for sr in s.series()} == {"Flow"}
        assert not any("without run date" in w for w in s.warnings())
        lc_run = next(r for r in s.runs() if r.key[0] == "LC Pro")
        assert lc_run.superseded_by == "Flow"

    s.remove_file(s.files[str(flow_file.resolve())].path)
    assert all(a.status != STATUS_SUPERSEDED for a in s.annotations().values())
    assert {sr.platform for sr in s.series()} == {"LC Pro"}


def test_flow_export(flow_file, tmp_path):
    from openpyxl import load_workbook

    s = Session()
    s.add_file(flow_file)
    out = tmp_path / "flow.xlsx"
    export_workbook(s, out)
    wb = load_workbook(out)
    assert wb.sheetnames == ["Overview", "S2 testA Flow", "S2 testB Flow", "Controls", "Data"]
    ws = wb["S2 testB Flow"]
    header = next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value == "Day")
    assert [ws.cell(header + 1, c).value for c in range(3, 6)] == [1, "IC FAILED", "-"]
    assert ws.cell(header + 1, 4).font.color.rgb.endswith("C00000")
    data = wb["Data"]
    headers = [c.value for c in data[1]]
    assert headers[-4:] == ["Release status", "Purification Plate", "Purification kit", "Purification kit lot"]
