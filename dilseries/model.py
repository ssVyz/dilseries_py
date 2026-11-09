"""Platform-independent data model for imported measurements."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

# Target names treated as internal controls (sorted last in outputs): 'IC', 'CIC', or ending in
# 'IC' after a non-capital (e.g. 'iso-IC', 'iso-aciIC').
_INTERNAL_CONTROL_TARGET = re.compile(r"^C?IC$|(?:^|[^A-Z])IC$")

# Calls that mean "no Ct because nothing was detected" (shown as '-'); other calls without Ct
# (e.g. 'IC FAILED', 'Invalid') are shown as text.
NEGATIVE_CALLS = frozenset({"", "ntd", "nd", "nonreactive", "non-reactive", "negative", "not detected", "valid"})


def is_internal_control(target: str) -> bool:
    return bool(_INTERNAL_CONTROL_TARGET.search(target.strip()))


@dataclass
class TargetResult:
    """Result of one target (channel) of one measurement."""

    target: str
    ct: float | None
    call: str = ""
    flags: str = ""
    channel: int | None = None
    details: str = ""


@dataclass
class Measurement:
    """One sample measured in one well/position of one run."""

    platform: str
    source_file: str
    run_id: str
    plate_id: str
    well: str
    sample_id: str
    assay: str = ""
    operator: str = ""
    timestamp: datetime | None = None
    is_control: bool = False
    external_id: str = ""
    flags: str = ""
    results: list[TargetResult] = field(default_factory=list)
    extra: dict[str, str] = field(default_factory=dict)
    uid: int = -1

    def result(self, target: str) -> TargetResult | None:
        for r in self.results:
            if r.target == target:
                return r
        return None


@dataclass
class ImportResult:
    """Measurements read from one export file."""

    format_name: str
    measurements: list[Measurement]
    warnings: list[str] = field(default_factory=list)


class UnsupportedFileError(Exception):
    """Raised when no importer recognizes a file."""


def parse_ct(text: str | None) -> float | None:
    """Parse a Ct/Cq value; empty or non-numeric values mean 'not detected'."""
    if text is None:
        return None
    text = text.strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None
