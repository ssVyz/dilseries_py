from datetime import datetime, timezone

from openpyxl import load_workbook

from dilseries import importers
from dilseries.export_xlsx import export_workbook
from dilseries.importers import cobas5800, cobas8800
from dilseries.session import Session
from tests.conftest import C8800_PLATE, C8800_RUN, C8800_SAMPLES, c8800_xml


def _local(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)


def test_c8800_reads_orders(c8800_file):
    result = importers.load(c8800_file)
    assert result.format_name == cobas8800.FORMAT_NAME
    assert result.warnings == []
    ms = {m.sample_id: m for m in result.measurements}
    assert set(ms) == {"(-) Ctrl", "S3101", "S3102", "S3n01", "S3n02"}
    m = ms["S3101"]
    assert (m.platform, m.run_id, m.plate_id, m.well, m.assay, m.operator) == (
        "cobas 8800",
        C8800_RUN,
        C8800_PLATE,
        "B1",
        "U_TEST",
        "alice",
    )
    assert m.timestamp == _local("2026-11-09T09:18:20.614547")  # stored in UTC
    assert [(r.target, r.ct, r.call, r.channel) for r in m.results] == [
        ("T1", 20.5, "Reactive", 1),
        ("T2", 22.1, "Reactive", 2),
        ("IC", 31.5, "Valid", None),
    ]
    assert m.extra == {
        "Test definition": "U_TEST_01.00 V01.00 (08/05/2020 09:19:29)",
        "Sample position": "0025-2",
        "Reagent lot": "KIT_031126.P04542",
        "System reagents": "Lysis P14437; MGP P13459",
    }
    t2 = ms["S3102"].results[1]
    assert (t2.ct, t2.call) == (None, "NonReactive")


def test_c8800_control_and_flags(c8800_file):
    ms = {m.sample_id: m for m in importers.load(c8800_file).measurements}
    ctrl = ms["(-) Ctrl"]
    assert ctrl.is_control and ctrl.well == "A1"
    assert ctrl.operator == "alice"  # processes requested by the instrument: operator of the run
    assert ctrl.extra["Control lot"] == "N30167"
    assert ms["S3n02"].flags == "Code=P01, Description=Clot detected|NG Sample Preparation failed"
    assert ms["S3n01"].flags == ""


def test_c8800_detection(c8800_file, tmp_path):
    assert cobas8800.can_read(c8800_file)
    assert not cobas5800.can_read(c8800_file)
    other = tmp_path / "other.xml"
    other.write_text('<?xml version="1.0"?><DomainObjects ApplicationName="otherSystem"/>', encoding="utf-8")
    assert not cobas8800.can_read(other)


def test_c8800_two_tests_on_one_plate(tmp_path):
    first = tmp_path / "a.xml"
    second = tmp_path / "b.xml"
    first.write_text(c8800_xml(C8800_SAMPLES, test="U_TEST_01.00"), encoding="utf-8")
    second.write_text(c8800_xml([(s, f"{w[0]}2", t) for s, w, t in C8800_SAMPLES], test="U_OTHER_01.00"), encoding="utf-8")
    s = Session()
    s.add_file(first)
    s.add_file(second)
    assert not s.warnings()
    assert [r.key for r in s.runs()] == [("cobas 8800", C8800_PLATE)]
    series = {(sr.group, sr.prefix): sr for sr in s.series()}
    assert set(series) == {("U_TEST", "S3"), ("U_OTHER", "S3")}
    assert series[("U_TEST", "S3")].steps == ["1", "neg"]
    assert [t for t, _ in series[("U_TEST", "S3")].targets] == ["T1", "T2", "IC"]

    out = tmp_path / "c8800.xlsx"
    export_workbook(s, out)
    assert load_workbook(out).sheetnames == ["Overview", "S3 U_OTHER c8800", "S3 U_TEST c8800", "Controls", "Data"]
