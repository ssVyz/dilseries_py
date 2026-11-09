from datetime import datetime

import pytest

from dilseries import importers
from dilseries.importers import cobas5800, lcpro
from dilseries.model import UnsupportedFileError
from tests.conftest import cobas_xml, lcpro_csv, write_cobas_zip


def test_cobas_zip_reads_samples_and_deduplicates_controls(cobas_zip):
    result = importers.load(cobas_zip)
    assert result.format_name == cobas5800.FORMAT_NAME
    samples = [m for m in result.measurements if not m.is_control]
    controls = [m for m in result.measurements if m.is_control]
    assert len(samples) == 6
    assert len(controls) == 1  # the same control is embedded in every XML
    assert controls[0].sample_id == "(-) Ctrl"

    m = next(m for m in samples if m.sample_id == "S1101")
    assert m.assay == "U_TEST"
    assert m.operator == "alice"
    assert m.run_id == m.plate_id == "5-1485-20261016-0905"
    assert m.timestamp == datetime.fromisoformat("2026-10-16T11:12:48Z").astimezone().replace(tzinfo=None)
    assert [(r.target, r.channel, r.ct, r.call) for r in m.results] == [
        ("T1", 1, 20.0, "Reactive"),
        ("T2", 2, None, "Non-Reactive"),
        ("IC", 5, 31.2, "Valid"),
    ]


def test_cobas_single_xml(tmp_path):
    path = tmp_path / "ResultData_1.xml"
    path.write_text(cobas_xml("A101"), encoding="utf-8")
    result = importers.load(path)
    assert {m.sample_id for m in result.measurements} == {"A101", "(-) Ctrl"}


def test_cobas_bad_xml_entry_is_reported(tmp_path):
    path = write_cobas_zip(tmp_path / "x.zip", [cobas_xml("A101"), "<resultData><broken"])
    result = importers.load(path)
    assert len([m for m in result.measurements if not m.is_control]) == 1
    assert any("could not parse" in w for w in result.warnings)


def test_lcpro_groups_rows_per_well(lcpro_file):
    result = importers.load(lcpro_file)
    assert result.format_name == lcpro.FORMAT_NAME
    assert len(result.measurements) == 7
    m = next(m for m in result.measurements if m.well == "B1")
    assert (m.sample_id, m.plate_id, m.run_id, m.timestamp) == ("S2101", "PLATE1", "100", None)
    assert [(r.target, r.ct, r.call) for r in m.results] == [("FAM", 18.1, "Reactive"), ("CIC", 30.0, "Reactive")]
    ntc = next(m for m in result.measurements if m.well == "A1")
    assert ntc.results[0].ct is None and ntc.results[0].flags == "C08|C09"


def test_lcpro_semicolon_and_decimal_comma(tmp_path):
    text = lcpro_csv([("A1", "S101", {"FAM": "18,5"})]).replace(",", ";").replace("18;5", "18,5")
    path = tmp_path / "semi_ResultTable.csv"
    path.write_text(text, encoding="utf-8")
    m = importers.load(path).measurements[0]
    assert m.results[0].ct == 18.5


def test_lcpro_control_role_marks_control(tmp_path):
    text = lcpro_csv([("A1", "Neg", {"FAM": ""})]).replace("UNKNOWN", "NEGATIVE_CONTROL")
    path = tmp_path / "ctrl_ResultTable.csv"
    path.write_text(text, encoding="utf-8")
    assert importers.load(path).measurements[0].is_control


def test_unsupported_file(tmp_path):
    path = tmp_path / "notes.csv"
    path.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    with pytest.raises(UnsupportedFileError):
        importers.load(path)
