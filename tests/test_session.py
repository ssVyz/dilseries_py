from datetime import datetime

from dilseries.naming import NEG_STEP, Role
from dilseries.session import STATUS_DUPLICATE, STATUS_EXCLUDED, STATUS_OK, STATUS_UNPARSED, Session


def _uid(session, sample_id, well=None):
    return next(
        uid for uid, m in session.measurements.items() if m.sample_id == sample_id and (well is None or m.well == well)
    )


def test_cobas_series_assembled(cobas_zip):
    s = Session()
    s.add_file(cobas_zip)
    series = s.series()
    assert len(series) == 1
    sr = series[0]
    assert (sr.platform, sr.group, sr.prefix) == ("cobas 5800", "U_TEST", "S1")
    assert sr.steps == ["1", "2", NEG_STEP]
    assert sr.repeats == [1, 2]
    assert [t for t, _ in sr.targets] == ["T1", "T2", "IC"]
    assert sr.missing == 0 and sr.duplicates == 0
    assert len(s.controls()) == 1


def test_adding_same_file_twice_is_ignored(cobas_zip):
    s = Session()
    s.add_file(cobas_zip)
    s.add_file(cobas_zip)
    assert len(s.measurements) == 7


def test_remove_file_drops_measurements_and_decisions(cobas_zip, lcpro_file):
    s = Session()
    s.add_file(cobas_zip)
    lc = s.add_file(lcpro_file)
    s.set_included(lc.uids[:2], False)
    s.remove_file(lc.path)
    assert len(s.measurements) == 7
    assert not s.excluded


def test_duplicates_flagged_and_resolved_by_suggested_groups(lcpro_file):
    s = Session()
    s.add_file(lcpro_file)
    ann = s.annotations()
    assert ann[_uid(s, "S2101", "B1")].status == STATUS_DUPLICATE
    assert s.plate_has_duplicates(("LC Pro", "PLATE1"))

    assignment = s.suggest_groups(("LC Pro", "PLATE1"))
    assert assignment[_uid(s, "S2101", "B1")] == "Test 1"
    assert assignment[_uid(s, "NTC")] == "Test 1"
    assert assignment[_uid(s, "S2101", "A2")] == "Test 2"
    for name in set(assignment.values()):
        s.set_group([u for u, g in assignment.items() if g == name], name)

    assert all(a.status != STATUS_DUPLICATE for a in s.annotations().values())
    groups = sorted((sr.group, sr.prefix, len(sr.measurements)) for sr in s.series())
    assert groups == [("Test 1", "S2", 3), ("Test 2", "S2", 3)]


def test_suggest_groups_empty_without_duplicates(cobas_zip):
    s = Session()
    s.add_file(cobas_zip)
    assert s.suggest_groups(("cobas 5800", "5-1485-20261016-0905")) == {}


def test_exclude_removes_from_series(lcpro_file):
    s = Session()
    s.add_file(lcpro_file)
    s.set_included([_uid(s, "S2101", "A2"), _uid(s, "S2102", "B2"), _uid(s, "S2n01", "C2")], False)
    assert s.annotations()[_uid(s, "S2101", "A2")].status == STATUS_EXCLUDED
    assert s.annotations()[_uid(s, "S2101", "B1")].status == STATUS_OK
    (sr,) = s.series()
    assert len(sr.measurements) == 3


def test_run_date_override(lcpro_file):
    s = Session()
    s.add_file(lcpro_file)
    (run,) = s.runs()
    assert run.date_source == "missing"
    assert any("without run date" in w for w in s.warnings())
    when = datetime(2026, 10, 20, 9, 30)
    s.set_run_info([run.key], when=when, operator="bob")
    (run,) = s.runs()
    assert (run.when, run.date_source, run.operators) == (when, "user", ["bob"])
    m = next(iter(s.measurements.values()))
    assert s.run_datetime(m) == when and s.run_operator(m) == "bob"


def test_manual_override_for_unparsed_name(tmp_path):
    from tests.conftest import lcpro_csv

    path = tmp_path / "odd_ResultTable.csv"
    path.write_text(lcpro_csv([("A1", "weird name", {"FAM": "20"}), ("A2", "X101", {"FAM": "21"})]), encoding="utf-8")
    s = Session()
    s.add_file(path)
    uid = _uid(s, "weird name")
    assert s.annotations()[uid].status == STATUS_UNPARSED
    s.set_override([uid], role=Role.SAMPLE, series="X", step="1", repeat=2)
    a = s.annotations()[uid]
    assert (a.role, a.series, a.step, a.repeat, a.status, a.overridden) == (Role.SAMPLE, "X", "1", 2, STATUS_OK, True)
    (sr,) = s.series()
    assert sorted(sr.cells) == [("1", 1), ("1", 2)]
    s.clear_override([uid])
    assert s.annotations()[uid].status == STATUS_UNPARSED


def test_group_rename(lcpro_file):
    s = Session()
    s.add_file(lcpro_file)
    s.set_group(list(s.measurements), "Test A")
    s.rename_group("Test A", "CARB")
    assert s.all_groups() == ["CARB"]
