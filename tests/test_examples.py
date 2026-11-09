"""Checks against the real example exports. Skipped when examples/ is not present (it is gitignored)."""

from collections import Counter

import pytest

from dilseries.export_xlsx import export_workbook
from dilseries.session import STATUS_DUPLICATE, Session
from tests.conftest import EXAMPLES

pytestmark = pytest.mark.skipif(not (EXAMPLES / "cobas").is_dir() or not (EXAMPLES / "lcpro").is_dir(), reason="examples/ not available")


def _load_all() -> Session:
    s = Session()
    for path in sorted((EXAMPLES / "cobas").glob("*.zip")) + sorted((EXAMPLES / "lcpro").glob("*.csv")):
        s.add_file(path)
    return s


def test_examples_parse_into_complete_series(tmp_path):
    s = _load_all()
    statuses = Counter(a.status for a in s.annotations().values())
    assert statuses["unparsed"] == 0
    assert statuses["incomplete"] == 0
    cobas = {(sr.group, sr.prefix): sr for sr in s.series() if sr.platform == "cobas 5800"}
    assert set(cobas) == {("U_ISO_CARB1", "LE10"), ("U_ISO_CARB1", "LE20"), ("U_ISO_ACI", "LE30"), ("U_ISO_ACI", "LE40"), ("U_ISO_CARB1", "LE40")}
    for key, sr in cobas.items():
        assert sr.missing == 0 and sr.duplicates == 0, key
    assert cobas[("U_ISO_ACI", "LE30")].repeats == list(range(1, 10))

    # LC Pro plate 2 holds two tests on the same samples; suggested groups resolve all duplicates.
    plate2 = ("LC Pro", "4B670240")
    assert s.plate_has_duplicates(plate2)
    assignment = s.suggest_groups(plate2)
    for name in set(assignment.values()):
        s.set_group([u for u, g in assignment.items() if g == name], name)
    assert not any(a.status == STATUS_DUPLICATE for a in s.annotations().values())

    export_workbook(s, tmp_path / "examples.xlsx")


@pytest.mark.skipif(not (EXAMPLES / "flow_example").is_dir(), reason="examples/flow_example not available")
def test_flow_examples_and_suggested_groups_match_flow_tests(tmp_path):
    s = Session()
    for path in sorted((EXAMPLES / "flow_example").glob("*.csv")):
        s.add_file(path)
    assert not s.warnings()
    series = {(sr.group, sr.prefix): sr for sr in s.series()}
    assert set(series) == {("isoAci", "LE30"), ("isoAci", "LE40"), ("isoCarb1", "LE40")}
    for key, sr in series.items():
        assert sr.missing == 0 and sr.duplicates == 0, key
    assert series[("isoAci", "LE30")].repeats == list(range(4, 10))
    flow_test = {m.well: m.assay for m in s.measurements.values() if m.plate_id == "4B670240"}

    # Without Flow, the same plate from the LC Pro result table needs manual grouping;
    # the suggested split must reproduce Flow's test assignment.
    lc = Session()
    lc.add_file(EXAMPLES / "lcpro" / "plate2_ResultTable.csv")
    suggestion = lc.suggest_groups(("LC Pro", "4B670240"))
    blocks: dict[str, set[str]] = {}
    for uid, group in suggestion.items():
        blocks.setdefault(group, set()).add(flow_test[lc.measurements[uid].well])
    assert sorted(map(len, blocks.values())) == [1, 1]
    assert {next(iter(b)) for b in blocks.values()} == {"isoAci", "isoCarb1"}

    # Loading both: the LC Pro table of the same plate is superseded by Flow.
    s.add_file(EXAMPLES / "lcpro" / "plate2_ResultTable.csv")
    assert {sr.platform for sr in s.series()} == {"Flow"}
    export_workbook(s, tmp_path / "flow_examples.xlsx")


@pytest.mark.skipif(not (EXAMPLES / "c8800_example").is_dir(), reason="examples/c8800_example not available")
def test_c8800_examples_two_tests_on_one_plate(tmp_path):
    s = Session()
    for path in sorted((EXAMPLES / "c8800_example").glob("*.xml")):
        s.add_file(path)
    assert not s.warnings()
    statuses = Counter(a.status for a in s.annotations().values())
    assert statuses == {"ok": 60, "control": 2}
    assert len(s.runs()) == 1  # both tests ran on the same AD plate
    series = {(sr.group, sr.prefix): sr for sr in s.series()}
    assert set(series) == {("U_ISO_CARB2", "LE50"), ("U_ISO_GPR", "LE50")}
    for key, sr in series.items():
        assert sr.missing == 0 and sr.duplicates == 0, key
        assert sr.steps == ["1", "2", "3", "4", "5", "6", "7", "8", "9", "neg"] and sr.repeats == [1, 2, 3]
    carb2 = series[("U_ISO_CARB2", "LE50")]
    assert [t for t, _ in carb2.targets] == ["GES", "GIM", "CTXM", "IC"]
    assert carb2.cells[("3", 2)][0].result("GES").ct == 22.89
    export_workbook(s, tmp_path / "c8800_examples.xlsx")
