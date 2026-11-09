"""Importer for LightCycler PRO result tables (``*_ResultTable.csv``).

The export has one row per well and target (dye channel). It contains no run
date, operator or assay name; those are set by the user in the GUI.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from dilseries.model import ImportResult, Measurement, TargetResult, parse_ct

FORMAT_NAME = "LC Pro result table"
PLATFORM = "LC Pro"
REQUIRED_COLUMNS = {"Well position", "Sample ID", "Target name", "Cq"}
_CONTROL_ROLE_HINTS = ("CONTROL", "NTC")


def can_read(path: Path) -> bool:
    if path.suffix.lower() not in {".csv", ".txt"}:
        return False
    try:
        text = _read_text(path, limit=4096)
    except OSError:
        return False
    first_line = text.splitlines()[0] if text else ""
    header = next(csv.reader([first_line], delimiter=_sniff_delimiter(first_line)), [])
    return REQUIRED_COLUMNS.issubset(h.strip() for h in header)


def read(path: Path) -> ImportResult:
    text = _read_text(path)
    first_line = text.splitlines()[0] if text else ""
    reader = csv.DictReader(io.StringIO(text), delimiter=_sniff_delimiter(first_line))
    reader.fieldnames = [f.strip() for f in reader.fieldnames or []]
    missing = REQUIRED_COLUMNS - set(reader.fieldnames)
    if missing:
        raise ValueError(f"{path.name}: missing columns {', '.join(sorted(missing))}")

    wells: dict[tuple[str, str, str], Measurement] = {}
    warnings: list[str] = []
    for row in reader:
        row = {k: (v or "").strip() for k, v in row.items() if k}
        plate = row.get("Plate ID") or path.stem
        run = row.get("Run ID", "")
        well = row["Well position"]
        key = (plate, run, well)
        m = wells.get(key)
        if m is None:
            role = row.get("Sample role", "").upper()
            m = Measurement(
                platform=PLATFORM,
                source_file=str(path),
                run_id=run,
                plate_id=plate,
                well=well,
                sample_id=row["Sample ID"],
                is_control=any(h in role for h in _CONTROL_ROLE_HINTS),
                external_id=f"{plate}|{run}|{well}",
            )
            wells[key] = m
        elif m.sample_id != row["Sample ID"]:
            warnings.append(f"Well {well}: conflicting sample IDs '{m.sample_id}' and '{row['Sample ID']}'")
        m.results.append(
            TargetResult(
                target=row["Target name"],
                ct=parse_ct(row.get("Cq")),
                call=row.get("Final result") or row.get("Initial result", ""),
                flags=row.get("Flags", ""),
            )
        )
    if not wells:
        warnings.append("No results found in export.")
    return ImportResult(FORMAT_NAME, list(wells.values()), warnings)


def _read_text(path: Path, limit: int | None = None) -> str:
    with path.open("rb") as fh:
        raw = fh.read() if limit is None else fh.read(limit)
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _sniff_delimiter(header_line: str) -> str:
    return max(",;\t", key=header_line.count)
