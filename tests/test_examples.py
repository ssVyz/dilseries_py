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
