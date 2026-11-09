"""Importer for Roche Flow result exports (``*_Results.csv``).

The file holds several CSV sections separated by blank lines:

1. Results: one row per well and target, with sample ID, PCR test (assay),
   target name, Ct (``FinalResult``), call (``CalculatedResult``), plate barcode,
   well, release status and the date the worklist was sent.
2. PCR reagents per test (``PCRTest, Reagent, Reagent_Type, Lot``).
3. Purification plates per sample (``PlateId, Plate_Type, Reagent, Reagent_Type, Lot``),
   where ``Reagent`` holds the sample ID.

Column names carry numeric suffixes (``SampleId_1``, ``assayName_11``); they are
matched without the suffix and case-insensitively.
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from dilseries.model import ImportResult, Measurement, TargetResult, parse_ct

FORMAT_NAME = "Flow results"
PLATFORM = "Flow"
REQUIRED_COLUMNS = {"sampleid", "assayname", "finalresult", "wellid"}
_REAGENT_SECTION = {"pcrtest", "reagent", "reagent_type", "lot"}
_PURIFICATION_SECTION = {"plateid", "plate_type", "reagent", "reagent_type", "lot"}
_DATE_FORMATS_MONTH_FIRST = ("%m/%d/%Y", "%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %I:%M:%S %p")
_DATE_FORMATS_DAY_FIRST = ("%d/%m/%Y", "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S")
_DATE_FORMATS_OTHER = ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y", "%d.%m.%Y %H:%M")


def normalize_column(name: str) -> str:
    """'SampleId_1' -> 'sampleid', 'QuantResult1' -> 'quantresult', 'Plate_Type' -> 'plate_type'."""
    return re.sub(r"[_\s]*\d+$", "", name.strip().lstrip("﻿")).casefold()


def can_read(path: Path) -> bool:
    if path.suffix.lower() not in {".csv", ".txt"}:
        return False
    try:
        with path.open("rb") as fh:
            head = _decode(fh.read(4096))
    except OSError:
        return False
    first_line = head.splitlines()[0] if head else ""
    header = next(csv.reader([first_line], delimiter=_sniff_delimiter(first_line)), [])
    return REQUIRED_COLUMNS.issubset(normalize_column(h) for h in header)


def read(path: Path) -> ImportResult:
    with path.open("rb") as fh:
        text = _decode(fh.read())
    sections = _split_sections(text)
    if not sections:
        raise ValueError(f"{path.name}: empty file")
    warnings: list[str] = []
    results, *others = sections
    measurements = _read_results(results, path, warnings)

    for header, rows in others:
        keys = set(header)
        if _PURIFICATION_SECTION.issubset(keys):
            _apply_purification(rows, measurements)
        elif _REAGENT_SECTION.issubset(keys):
            _apply_reagents(rows, measurements)
        else:
            warnings.append(f"Ignored section with columns: {', '.join(header)}")
    if not measurements:
        warnings.append("No results found in export.")
    return ImportResult(FORMAT_NAME, measurements, warnings)


def _read_results(section: tuple[list[str], list[list[str]]], path: Path, warnings: list[str]) -> list[Measurement]:
    header, rows = section
    missing = REQUIRED_COLUMNS - set(header)
    if missing:
        raise ValueError(f"{path.name}: missing columns {', '.join(sorted(missing))}")
    records = [dict(zip(header, row)) for row in rows]
    dates = _parse_dates({r.get("worklistsent", "") for r in records})

    wells: dict[tuple[str, str], Measurement] = {}
    for r in records:
        plate = r.get("pcrplate") or path.stem
        well = r.get("wellid", "")
        if not well or not r.get("sampleid"):
            warnings.append(f"Skipped incomplete row: {', '.join(v for v in r.values() if v)}")
            continue
        m = wells.get((plate, well))
        if m is None:
            extra = {}
            if r.get("status"):
                extra["Release status"] = r["status"]
            m = Measurement(
                platform=PLATFORM,
                source_file=str(path),
                run_id="",
                plate_id=plate,
                well=well,
                sample_id=r["sampleid"],
                assay=r.get("pcrtestname", ""),
                timestamp=dates.get(r.get("worklistsent", "")),
                external_id=f"{plate}|{well}",
                extra=extra,
            )
            wells[(plate, well)] = m
        elif m.sample_id != r["sampleid"]:
            warnings.append(f"Well {well}: conflicting sample IDs '{m.sample_id}' and '{r['sampleid']}'")
        if m.timestamp is None:
            m.timestamp = dates.get(r.get("worklistsent", ""))
        details = []
        if r.get("tmvalue"):
            details.append(f"Tm {r['tmvalue']}")
        if r.get("quantresult"):
            details.append(f"Quant {r['quantresult']} {r.get('concentrationunits', '')}".strip())
        m.results.append(
            TargetResult(
                target=r["assayname"],
                ct=parse_ct(r.get("finalresult")),
                call=r.get("calculatedresult", ""),
                details="; ".join(details),
            )
        )

    # Controls (NTC) carry no date; use the most common date of their plate.
    plate_dates: dict[str, Counter] = {}
    for m in wells.values():
        if m.timestamp is not None:
            plate_dates.setdefault(m.plate_id, Counter())[m.timestamp] += 1
    for m in wells.values():
        if m.timestamp is None and m.plate_id in plate_dates:
            m.timestamp = plate_dates[m.plate_id].most_common(1)[0][0]
    return list(wells.values())


def _apply_purification(rows: list[list[str]], measurements: list[Measurement]) -> None:
    by_sample: dict[str, list[Measurement]] = {}
    for m in measurements:
        by_sample.setdefault(m.sample_id, []).append(m)
    for row in rows:
        plate_id, plate_type, sample, kit, lot = (row + [""] * 5)[:5]
        for m in by_sample.get(sample, []):
            m.extra[plate_type or "Purification plate"] = plate_id
            m.extra["Purification kit"] = kit
            m.extra["Purification kit lot"] = lot


def _apply_reagents(rows: list[list[str]], measurements: list[Measurement]) -> None:
    by_test: dict[str, list[str]] = {}
    for row in rows:
        test, reagent, reagent_type, lot = (row + [""] * 4)[:4]
        label = f"{reagent} ({reagent_type})" if reagent_type else reagent
        by_test.setdefault(test, []).append(f"{label} lot {lot}".strip())
    for m in measurements:
        if m.assay in by_test:
            m.extra["PCR reagents"] = "; ".join(by_test[m.assay])


def _split_sections(text: str) -> list[tuple[list[str], list[list[str]]]]:
    """Split into (normalized header, rows) blocks separated by blank lines."""
    sections = []
    block: list[str] = []
    for line in text.splitlines() + [""]:
        if line.strip(", \t;"):
            block.append(line)
            continue
        if block:
            delimiter = _sniff_delimiter(block[0])
            parsed = list(csv.reader(block, delimiter=delimiter))
            header = [normalize_column(h) for h in parsed[0]]
            rows = [[c.strip() for c in row] for row in parsed[1:] if any(c.strip() for c in row)]
            sections.append((header, rows))
            block = []
    return sections


def _parse_dates(texts: set[str]) -> dict[str, datetime]:
    """Parse all dates of a file consistently. Slash dates are month-first unless a day > 12 proves otherwise."""
    texts = {t.strip() for t in texts if t and t.strip()}
    day_first = any(int(m.group(1)) > 12 for t in texts if (m := re.match(r"(\d{1,2})/\d{1,2}/\d{4}", t)))
    formats = (_DATE_FORMATS_DAY_FIRST if day_first else _DATE_FORMATS_MONTH_FIRST) + _DATE_FORMATS_OTHER
    out = {}
    for t in texts:
        for fmt in formats:
            try:
                out[t] = datetime.strptime(t, fmt)
                break
            except ValueError:
                continue
    return out


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _sniff_delimiter(line: str) -> str:
    return max(",;\t", key=line.count)
