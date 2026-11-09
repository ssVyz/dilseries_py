"""Importer for cobas 5800 result exports (zip of ResultData_*.xml files).

Each XML file holds one test order (sample) with its sample work order(s) and
the associated control work orders of the run.
"""

from __future__ import annotations

import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from dilseries.model import ImportResult, Measurement, TargetResult, parse_ct

FORMAT_NAME = "cobas 5800"
PLATFORM = "cobas 5800"
_ROOT_TAG = b"<resultData"


def can_read(path: Path) -> bool:
    suffix = path.suffix.lower()
    try:
        if suffix == ".zip":
            with zipfile.ZipFile(path) as zf:
                xml_names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
                if not xml_names:
                    return False
                with zf.open(xml_names[0]) as fh:
                    return _ROOT_TAG in fh.read(4096)
        if suffix == ".xml":
            with path.open("rb") as fh:
                return _ROOT_TAG in fh.read(4096)
    except (OSError, zipfile.BadZipFile):
        return False
    return False


def read(path: Path) -> ImportResult:
    warnings: list[str] = []
    measurements: list[Measurement] = []
    seen: set[str] = set()
    for entry_name, data in _iter_xml(path):
        try:
            root = ET.fromstring(data)
        except ET.ParseError as exc:
            warnings.append(f"{entry_name}: could not parse XML ({exc})")
            continue
        for m in _parse_result_data(root, str(path)):
            if m.external_id and m.external_id in seen:
                continue
            seen.add(m.external_id)
            measurements.append(m)
    if not measurements:
        warnings.append("No results found in export.")
    return ImportResult(FORMAT_NAME, measurements, warnings)


def _iter_xml(path: Path):
    if path.suffix.lower() == ".xml":
        yield path.name, path.read_bytes()
        return
    with zipfile.ZipFile(path) as zf:
        for name in sorted(zf.namelist()):
            if name.lower().endswith(".xml"):
                yield name, zf.read(name)


def _parse_result_data(root: ET.Element, source: str) -> list[Measurement]:
    out: list[Measurement] = []
    for cwo in root.findall("controlWorkOrders/controlWorkOrder"):
        out.append(_control_measurement(cwo, source))
    for order in root.findall("testOrders/testOrder"):
        props = order.find("orderProperties")
        sample_id = _text(props, "sampleId")
        assay = _text(props, "asap/name") or _text(props, "requestedTests/requestedTests/name")
        operator = _text(order, "actorCreatingOrder")
        for swo in order.findall("sampleWorkOrders/sampleWorkOrder"):
            out.append(
                Measurement(
                    platform=PLATFORM,
                    source_file=source,
                    run_id=_text(swo, "processingInfo/runId"),
                    plate_id=_text(swo, "processingInfo/runId"),
                    well=_text(swo, "processingInfo/measurementData/positionName"),
                    sample_id=sample_id,
                    assay=assay,
                    operator=operator,
                    timestamp=_timestamp(swo),
                    is_control=False,
                    external_id=_text(swo, "id") or f"{order.get('id', '')}:{_text(swo, 'processingInfo/runId')}",
                    flags=_flags(swo.find("processingInfo/flags")),
                    results=_results(swo.find("result")),
                )
            )
    return out


def _control_measurement(cwo: ET.Element, source: str) -> Measurement:
    props = cwo.find("orderProperties")
    return Measurement(
        platform=PLATFORM,
        source_file=source,
        run_id=_text(cwo, "processingInfo/runId"),
        plate_id=_text(cwo, "processingInfo/runId"),
        well=_text(cwo, "processingInfo/measurementData/positionName"),
        sample_id=_text(props, "controlName") or _text(cwo, "processingInfo/measurementData/specimen/controlName"),
        assay=_text(props, "asap/name"),
        timestamp=_timestamp(cwo),
        is_control=True,
        external_id=cwo.get("id", ""),
        flags=_flags(cwo.find("processingInfo/flags")),
        results=_results(cwo.find("result")),
    )


def _results(result: ET.Element | None) -> list[TargetResult]:
    if result is None:
        return []
    out: list[TargetResult] = []
    for tr in result.findall("targetResults/targetResult"):
        call = (
            _text(tr, "displayResultQualification")
            or _text(tr, "systemValidatedResultQualification")
            or _text(tr, "preliminaryResultQualification")
        )
        out.append(
            TargetResult(
                target=_text(tr, "targetName") or f"Ch.{_text(tr, 'channelNumber')}",
                ct=parse_ct(_text(tr, "ct")),
                call=call,
                flags=_flags(tr.find("flags")),
                channel=_int(_text(tr, "channelNumber")),
            )
        )
    ic = result.find("icResult")
    if ic is not None and (_text(ic, "ct") or _text(ic, "qualification")):
        out.append(
            TargetResult(
                target="IC",
                ct=parse_ct(_text(ic, "ct")),
                call=_text(ic, "qualification"),
                channel=_int(_text(ic, "channelNumber")),
            )
        )
    return out


def _timestamp(work_order: ET.Element) -> datetime | None:
    for path in ("processingInfo/processingStartDateTime", "creationDateTime"):
        text = _text(work_order, path)
        if text:
            try:
                # Export times are UTC; convert to the local time zone of this computer.
                return datetime.fromisoformat(text).astimezone().replace(tzinfo=None)
            except ValueError:
                continue
    return None


def _flags(el: ET.Element | None) -> str:
    if el is None:
        return ""
    return "|".join(t.strip() for t in el.itertext() if t.strip())


def _text(el: ET.Element | None, path: str) -> str:
    if el is None:
        return ""
    found = el.find(path)
    return (found.text or "").strip() if found is not None else ""


def _int(text: str) -> int | None:
    try:
        return int(text)
    except ValueError:
        return None
