"""Importer for cobas 8800 result exports (``DomainObjects`` XML, one file per export).

Structure (only the parts used here)::

    DomainObjects ApplicationName="c8800System"
      TestOrders/TestOrder            one per sample or control and test
        CT_IC, ICResult               internal control
        TestResults/TestResult        one per target: Name, CT, Result, FinalQualification, Channel
        ProcessOrders/ProcessOrder    sample transfer, sample preparation, PCR, calculation
          ProcessRun RunId            run (batch) ID, shared by all orders of the run
          InventoryItemTrackings      consumables: reagent cassette, system reagents, AD plate
          ProcessResult//RawData/Wells/Well PositionName   well on the AD plate (PCR process)
        OrderGroups/OrderGroup Info   full test definition name
        Specimen/Sample | RDControl   barcode (sample ID) or control name (Info)
      TestsRequested/TestRequested    test ID -> name (e.g. U_ISO_CARB2_01.00)
      ProcessesRequested/ProcessRequested   process ID -> name and requesting user

The files are large (raw fluorescence curves), so they are read incrementally.
Times carry no zone suffix; the system stores them in UTC (the embedded process
step records mark the same values with ``Z``), so they are converted to local time.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from dilseries.model import ImportResult, Measurement, TargetResult, parse_ct

FORMAT_NAME = "cobas 8800"
PLATFORM = "cobas 8800"
_SIGNATURE = re.compile(rb"<DomainObjects\b[^>]*ApplicationName=\"c8800System\"")
_INSTRUMENT_ACTOR = re.compile(r"-\d+$")  # e.g. IM1000-005425, DataManager-200566
_TEST_VERSION = re.compile(r"_\d+\.\d+$")  # U_ISO_CARB2_01.00 -> U_ISO_CARB2
_IC_RESULTS = {"1": "Valid"}
_WELL_ZEROS = re.compile(r"(?<=^[A-Z])0+(?=\d)")  # E05 -> E5


def can_read(path: Path) -> bool:
    if path.suffix.lower() != ".xml":
        return False
    try:
        with path.open("rb") as fh:
            return bool(_SIGNATURE.search(fh.read(4096)))
    except OSError:
        return False


@dataclass
class _Order:
    """Data of one test order, kept until test and process names are known (they follow the orders)."""

    measurement: Measurement
    test_id: str
    process_ids: list[str] = field(default_factory=list)
    failed_process_ids: list[str] = field(default_factory=list)


def read(path: Path) -> ImportResult:
    orders: list[_Order] = []
    tests: dict[str, str] = {}
    processes: dict[str, tuple[str, str]] = {}  # id -> (name, requesting actor)
    try:
        for _event, el in ET.iterparse(path, events=("end",)):
            tag = el.tag
            if tag == "TestOrder":
                orders.append(_parse_order(el, str(path)))
                el.clear()
            elif tag == "TestRequested":
                tests[el.get("Id", "")] = el.get("Name", "")
                el.clear()
            elif tag == "ProcessRequested":
                processes[el.get("Id", "")] = (el.get("Name", ""), el.get("CreationActorId", ""))
                el.clear()
    except ET.ParseError as exc:
        raise ValueError(f"{path.name}: could not parse XML ({exc})") from exc

    measurements = []
    for order in orders:
        m = order.measurement
        full_name = tests.get(order.test_id, "")
        if full_name:
            m.assay = _TEST_VERSION.sub("", full_name)
        users = Counter(
            actor
            for pid in order.process_ids
            if (actor := processes.get(pid, ("", ""))[1]) and not _INSTRUMENT_ACTOR.search(actor)
        )
        if users:
            m.operator = users.most_common(1)[0][0]
        failed = [f"{processes.get(pid, (pid, ''))[0] or pid} failed" for pid in order.failed_process_ids]
        m.flags = "|".join(f for f in [m.flags, *failed] if f)
        measurements.append(m)

    # Control processes are requested by the instrument; use the operator of their run.
    run_operators: dict[str, Counter] = {}
    for m in measurements:
        if m.operator:
            run_operators.setdefault(m.run_id, Counter())[m.operator] += 1
    for m in measurements:
        if not m.operator and m.run_id in run_operators:
            m.operator = run_operators[m.run_id].most_common(1)[0][0]
    warnings = [] if measurements else ["No results found in export."]
    return ImportResult(FORMAT_NAME, measurements, warnings)


def _parse_order(order: ET.Element, source: str) -> _Order:
    specimens = order.find("Specimen")
    specimen = specimens[0] if specimens is not None and len(specimens) else None
    is_control = specimen is not None and (specimen.tag == "RDControl" or specimen.get("SpecimenClass") == "C")
    if specimen is None:
        sample_id = ""
    elif is_control:
        sample_id = specimen.get("Info") or specimen.get("Barcode", "")
    else:
        sample_id = specimen.get("Barcode", "")

    group = order.find("OrderGroups/OrderGroup")
    test_definition = group.get("Info", "") if group is not None else ""
    extra: dict[str, str] = {}
    if test_definition:
        extra["Test definition"] = test_definition
    if specimen is not None and specimen.get("Position"):
        extra["Sample position"] = specimen.get("Position", "")
    if is_control and specimen is not None:
        carrier = specimen.find("Container/Carrier")
        if carrier is not None and carrier.get("LotNumber"):
            extra["Control lot"] = carrier.get("LotNumber", "")

    run_id, plate, well = "", "", ""
    starts: list[datetime] = []
    process_ids: list[str] = []
    failed_ids: list[str] = []
    reagent_lot = ""
    system_reagents: set[str] = set()
    for po in order.iterfind("ProcessOrders/ProcessOrder"):
        process_ids.append(po.get("ProcessRequested", ""))
        if po.get("Failed") not in (None, "", "0"):
            failed_ids.append(po.get("ProcessRequested", ""))
        run = po.find("ProcessRun")
        if run is not None:
            run_id = run_id or run.get("RunId", "")
            if (start := _timestamp(run.get("StartTime"))) is not None:
                starts.append(start)
        raw_well = po.find("ProcessResult/ProcessResultData/RawData/Wells/Well")
        is_pcr = raw_well is not None or (run is not None and "Cycler" in run.get("ModuleId", ""))
        for item in po.iterfind("InventoryItemTrackings/InventoryItemTracking/*"):
            if item.tag == "ReagentContainer" and item.get("ReagentName") and item.get("LotNumber"):
                system_reagents.add(f"{item.get('ReagentName')} {item.get('LotNumber')}")
            elif item.tag == "Carrier" and item.get("LotNumber"):
                reagent_lot = reagent_lot or item.get("LotNumber", "")  # test reagent cassette
            elif item.tag == "Container" and is_pcr and not plate:
                carrier = item.find("Carrier")
                if carrier is not None:
                    plate = carrier.get("InventoryItemId", "")
                    well = well or item.get("Position", "")
        if raw_well is not None and raw_well.get("PositionName"):
            well = raw_well.get("PositionName", "")
    if reagent_lot:
        extra["Reagent lot"] = reagent_lot
    if system_reagents:
        extra["System reagents"] = "; ".join(sorted(system_reagents))

    flag_elements = [*order.iterfind("OrderGroups/OrderGroup/Flags"), *order.iterfind("ProcessOrders/ProcessOrder/Flags")]
    flags = list(dict.fromkeys(f for el in flag_elements if (f := _flags(el))))
    if order.get("IsRetest", "").casefold() in ("yes", "true", "1"):
        flags.insert(0, "Retest")
    measurement = Measurement(
        platform=PLATFORM,
        source_file=source,
        run_id=run_id,
        plate_id=plate or run_id,
        well=_WELL_ZEROS.sub("", well),
        sample_id=sample_id,
        assay=_TEST_VERSION.sub("", test_definition.split(" ")[0]) if test_definition else "",
        timestamp=min(starts) if starts else _timestamp(order.get("CreationDateTime")),
        is_control=is_control,
        external_id=order.get("Id", ""),
        flags="|".join(flags),
        results=_results(order),
        extra=extra,
    )
    return _Order(measurement, order.get("TestRequested", ""), process_ids, failed_ids)


def _results(order: ET.Element) -> list[TargetResult]:
    out = []
    for tr in order.iterfind("TestResults/TestResult"):
        channel = tr.get("Channel", "")
        out.append(
            TargetResult(
                target=tr.get("Name") or f"Ch.{channel}",
                ct=parse_ct(tr.get("CT")),
                call=tr.get("FinalQualification") or tr.get("Result", ""),
                flags=_flags(tr.find("Flags")),
                channel=int(channel) if channel.isdigit() else None,
            )
        )
    ic_ct, ic_code = order.get("CT_IC", ""), order.get("ICResult", "")
    if ic_ct or ic_code:
        out.append(
            TargetResult(
                target="IC",
                ct=parse_ct(ic_ct),
                call=_IC_RESULTS.get(ic_code, f"IC result {ic_code}" if ic_code else ""),
            )
        )
    return out


def _flags(el: ET.Element | None) -> str:
    """Flag texts, or the attributes of flag elements without text."""
    if el is None:
        return ""
    parts = []
    for flag in el:
        text = " ".join(t.strip() for t in flag.itertext() if t.strip())
        if not text:
            text = ", ".join(
                f"{k}={v}" for k, v in flag.attrib.items() if v and k != "Id" and not k.endswith(("DateTime", "ActorId"))
            )
        if text:
            parts.append(text)
    return "|".join(parts)


def _timestamp(text: str | None) -> datetime | None:
    if not text:
        return None
    text = re.sub(r"(\.\d{6})\d+", r"\1", text.strip().removesuffix("Z"))
    try:
        value = datetime.fromisoformat(text)
    except ValueError:
        return None
    return value.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
