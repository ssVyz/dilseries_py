"""Builders for small synthetic export files (real examples are not in the repo)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def cobas_xml(
    sample_id: str,
    *,
    run_id: str = "5-1485-20261016-0905",
    well: str = "A1",
    start: str = "2026-10-16T11:12:48Z",
    assay: str = "U_TEST",
    operator: str = "alice",
    targets: tuple[tuple[str, int, str, str], ...] = (("T1", 1, "20.5", "Reactive"), ("T2", 2, "", "Non-Reactive")),
    ic_ct: str = "31.2",
    control_id: str = "ctrl-1",
    work_order_id: str | None = None,
) -> str:
    def target_results(display: bool) -> str:
        parts = []
        for name, channel, ct, call in targets:
            parts.append(
                f"<targetResult><channelNumber>{channel}</channelNumber><ct>{ct}</ct>"
                f"<displayResultQualification>{call if display else ''}</displayResultQualification><flags/>"
                f"<systemValidatedResultQualification>{call if display else 'Valid'}</systemValidatedResultQualification>"
                f"<targetName>{name}</targetName></targetResult>"
            )
        return "".join(parts)

    return f"""<?xml version="1.0" encoding="UTF-8"?><resultData>
  <controlWorkOrders>
    <controlWorkOrder id="{control_id}">
      <creationDateTime>2026-10-16T11:00:00Z</creationDateTime>
      <processingInfo>
        <processingStartDateTime>{start}</processingStartDateTime>
        <runId>{run_id}</runId>
        <measurementData><positionName>D6</positionName>
          <specimen><discriminator>ControlInformation</discriminator><controlName>(-) Ctrl</controlName></specimen>
        </measurementData>
      </processingInfo>
      <result><icResult><qualification>Valid</qualification><channelNumber>5</channelNumber><ct>31.0</ct></icResult>
        <targetResults>{target_results(False)}</targetResults></result>
      <orderProperties><controlName>(-) Ctrl</controlName><controlType>Negative</controlType><asap><name>{assay}</name></asap></orderProperties>
    </controlWorkOrder>
  </controlWorkOrders>
  <testOrders>
    <testOrder id="to-{sample_id}-{run_id}">
      <actorCreatingOrder>{operator}</actorCreatingOrder>
      <sampleWorkOrders>
        <sampleWorkOrder>
          <processingInfo>
            <processingStartDateTime>{start}</processingStartDateTime>
            <runId>{run_id}</runId>
            <measurementData><positionName>{well}</positionName></measurementData>
          </processingInfo>
          <result>
            <icResult><qualification>Valid</qualification><channelNumber>5</channelNumber><ct>{ic_ct}</ct></icResult>
            <targetResults>{target_results(True)}</targetResults>
          </result>
          <id>{work_order_id or f"wo-{sample_id}-{run_id}"}</id>
        </sampleWorkOrder>
      </sampleWorkOrders>
      <orderProperties><sampleId>{sample_id}</sampleId><asap><name>{assay}</name></asap></orderProperties>
    </testOrder>
  </testOrders>
</resultData>"""


def write_cobas_zip(path: Path, xmls: list[str]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for i, xml in enumerate(xmls):
            zf.writestr(f"ResultData_{i}.xml", xml)
    return path


LCPRO_HEADER = "Plate ID,Run ID,Well position,Sample ID,Sample role,Target name,Initial result,Final result,Cq,EPF,Flags"


def lcpro_csv(wells: list[tuple[str, str, dict[str, str]]], plate: str = "PLATE1", run: str = "100") -> str:
    """wells = [(well, sample_id, {target: cq})]; empty cq = not detected."""
    lines = [LCPRO_HEADER]
    for well, sample, targets in wells:
        for target, cq in targets.items():
            call = "Reactive" if cq else "NonReactive"
            flags = "" if cq else '"C08|C09"'
            lines.append(f"{plate},{run},{well},{sample},UNKNOWN,{target},{call},{call},{cq},1.00,{flags}")
    return "\n".join(lines) + "\n"


FLOW_HEADER = (
    "SampleId_1,assayName_11,FinalResult_11,TmValue,CalculatedResult_11,QuantResult1,ConcentrationUnits1,"
    "PCRPlate_1,WellId_11,PCRTestName_1,ISOBarcodeId_1,Status_1,WorklistSent_1"
)


def flow_csv(
    wells: list[tuple[str, str, str, dict[str, tuple[str, str]]]],
    plate: str = "PLATE1",
    date: str = "10/28/2026",
    purification: tuple[str, ...] = (),
    reagents: tuple[tuple[str, str, str, str], ...] = (),
) -> str:
    """wells = [(well, sample_id, test, {target: (ct, call)})]. Controls (NTC) get no date, as in real exports."""
    lines = [FLOW_HEADER]
    for well, sample, test, targets in wells:
        sent = "" if sample == "NTC" else date
        for target, (ct, call) in targets.items():
            lines.append(f"{sample},{target},{ct},,{call},,UI/ml,{plate},{well},{test},cobasIC,2nd User Approve,{sent}")
    lines += ["", "PCRTest_1,Reagent_1,Reagent_Type,Lot_1"]
    lines += [",".join(r) for r in reagents]
    lines += ["", "PlateId_2,Plate_Type,Reagent_2,Reagent_Type1,Lot_2"]
    lines += [f"0507253000483175,Purification Plate,{s},MP96 Kit,95950320" for s in purification]
    return "﻿" + "\r\n".join(lines) + "\r\n"


FLOW_WELLS = [
    ("A1", "NTC", "testA", {"t-FAM": ("", "NTD"), "t-IC": ("", "NTD")}),
    ("B1", "S2101", "testA", {"t-FAM": ("18.10", "REACTIVE"), "t-IC": ("30.00", "REACTIVE")}),
    ("C1", "S2102", "testA", {"t-FAM": ("18.30", "REACTIVE"), "t-IC": ("30.10", "REACTIVE")}),
    ("D1", "S2n01", "testA", {"t-FAM": ("", "NTD"), "t-IC": ("30.20", "REACTIVE")}),
    ("A2", "S2101", "testB", {"t-VIC": ("", "IC FAILED"), "t-aciIC": ("", "IC FAILED")}),
    ("B2", "S2102", "testB", {"t-VIC": ("25.50", "REACTIVE"), "t-aciIC": ("", "IC FAILED")}),
    ("C2", "S2n01", "testB", {"t-VIC": ("", "NTD"), "t-aciIC": ("31.20", "REACTIVE")}),
]


@pytest.fixture
def flow_file(tmp_path: Path) -> Path:
    """Flow results for the same plate as `lcpro_file`: two tests (testA, testB) on the same samples."""
    path = tmp_path / "plate_Results.csv"
    path.write_text(flow_csv(FLOW_WELLS, purification=("S2101", "S2102")), encoding="utf-8", newline="")
    return path


@pytest.fixture
def cobas_zip(tmp_path: Path) -> Path:
    """Series S1: steps 1-2 + neg, repeats 01-02, all on one run sharing one control."""
    xmls = []
    wells = iter(f"{r}{c}" for c in range(1, 7) for r in "ABCD")
    for step in ("1", "2", "n"):
        for rep in ("01", "02"):
            ct = {"1": "20.0", "2": "24.0", "n": ""}[step]
            xmls.append(
                cobas_xml(
                    f"S1{step}{rep}",
                    well=next(wells),
                    targets=(("T1", 1, ct, "Reactive" if ct else "Non-Reactive"), ("T2", 2, "", "Non-Reactive")),
                )
            )
    return write_cobas_zip(tmp_path / "cobas_export.zip", xmls)


@pytest.fixture
def lcpro_file(tmp_path: Path) -> Path:
    """Plate with two tests on the same samples (duplicate sample IDs in two contiguous blocks)."""
    wells = [
        ("A1", "NTC", {"FAM": "", "CIC": ""}),
        ("B1", "S2101", {"FAM": "18.1", "CIC": "30.0"}),
        ("C1", "S2102", {"FAM": "18.3", "CIC": "30.1"}),
        ("D1", "S2n01", {"FAM": "", "CIC": "30.2"}),
        ("A2", "S2101", {"FAM": "", "CIC": "31.0"}),
        ("B2", "S2102", {"FAM": "", "CIC": "31.1"}),
        ("C2", "S2n01", {"FAM": "", "CIC": "31.2"}),
    ]
    path = tmp_path / "plate_ResultTable.csv"
    path.write_text(lcpro_csv(wells), encoding="utf-8")
    return path


C8800_RUN = "0bd71b8f-1ddc-f111-81c2-000060ee1342"
C8800_PLATE = "0302280909603233"


def _c8800_order(index: int, sample: str, well: str, targets: dict[str, str], start: str, failed: bool) -> str:
    control = sample.startswith("(")
    results = []
    for channel, (target, ct) in enumerate(targets.items(), start=1):
        call = "Valid" if control else "Reactive" if ct else "NonReactive"
        ct_attr = f' CT="{ct}"' if ct else ""
        results.append(f'<TestResult Name="{target}" Channel="{channel}" Result="{call}" FinalQualification="{call}"{ct_attr}/>')
    if control:
        specimen = (
            f'<RDControl Barcode="C123" Info="{sample}" Position="1614-2" SpecimenClass="C" ControlType="NC">'
            '<Container><Carrier LotNumber="N30167"/></Container></RDControl>'
        )
    else:
        specimen = f'<Sample Barcode="{sample}" Position="0025-{index + 1}" SpecimenClass="S"/>'
    flag = '<Flag Code="P01" Description="Clot detected"/>' if failed else ""
    raw_well = f"{well[0]}{int(well[1:]):02d}"
    return f"""<TestOrder Id="{{test}}-order-{index}" CreationDateTime="2026-11-09T09:12:00.000000" CT_IC="31.5" ICResult="1"
  IsRetest="No" TestRequested="test-1">
<TestResults>{"".join(results)}</TestResults>
<ProcessOrders>
  <ProcessOrder ProcessRequested="st-{index}" Failed="0">
    <ProcessRun ModuleId="SampleCell" RunId="{C8800_RUN}" StartTime="{start}"/><Flags/>
    <InventoryItemTrackings><InventoryItemTracking><Container Position="{well}"><Carrier InventoryItemId="0102280805806960"/></Container></InventoryItemTracking></InventoryItemTrackings>
  </ProcessOrder>
  <ProcessOrder ProcessRequested="ng-{index}" Failed="{int(failed)}">
    <ProcessRun ModuleId="ProcessCellA" RunId="{C8800_RUN}" StartTime="2026-11-09T09:34:08.191398"/><Flags>{flag}</Flags>
    <InventoryItemTrackings>
      <InventoryItemTracking><Carrier LotNumber="KIT_031126.P04542" MaterialNumber="U_TEST.9052011190_A"/></InventoryItemTracking>
      <InventoryItemTracking><ReagentContainer ReagentName="Lysis" LotNumber="P14437"/></InventoryItemTracking>
      <InventoryItemTracking><ReagentContainer ReagentName="MGP" LotNumber="P13459"/></InventoryItemTracking>
    </InventoryItemTrackings>
  </ProcessOrder>
  <ProcessOrder ProcessRequested="pcr-{index}" Failed="0">
    <ProcessRun ModuleId="AnalyticCyclerA1" RunId="{C8800_RUN}" StartTime="2026-11-09T10:32:55.671313"/><Flags/>
    <InventoryItemTrackings><InventoryItemTracking><Container Position="{well}"><Carrier InventoryItemId="{C8800_PLATE}"/></Container></InventoryItemTracking></InventoryItemTrackings>
    <ProcessResult><ProcessResultData><RawData><Wells><Well Position="1" PositionName="{raw_well}"/></Wells></RawData></ProcessResultData></ProcessResult>
  </ProcessOrder>
</ProcessOrders>
<OrderGroups><OrderGroup OrderId="29471" Info="{{test}} V01.00 (08/05/2020 09:19:29)"><Flags/></OrderGroup></OrderGroups>
<Specimen>{specimen}</Specimen>
</TestOrder>"""


def c8800_xml(
    samples: list[tuple[str, str, dict[str, str]]],
    *,
    test: str = "U_TEST_01.00",
    operator: str = "alice",
    start: str = "2026-11-09T09:18:20.614547",
    failed_well: str = "",
) -> str:
    """cobas 8800 export of one test. samples = [(sample_id, well, {target: ct})]; empty ct = not detected.
    A sample ID starting with '(' becomes the run's control; its processes are requested by the instrument."""
    orders = "".join(
        _c8800_order(i, sample, well, targets, start, well == failed_well).replace("{test}", test)
        for i, (sample, well, targets) in enumerate(samples)
    )
    requested = []
    for i, (sample, _, _) in enumerate(samples):
        for kind, name in (("st", "ST Sample Transfer"), ("ng", "NG Sample Preparation"), ("pcr", "PCR_0003033")):
            actor = "IM1000-005425" if sample.startswith("(") or kind == "pcr" else operator
            requested.append(f'<ProcessRequested Id="{kind}-{i}" Name="{name}" CreationActorId="{actor}"/>')
    return f"""<?xml version="1.0" encoding="utf-8"?>
<DomainObjects Version="2.0" ApplicationName="c8800System" SoftwareVersion="01.04.07.1003" UserId="exporter">
<TestOrders>{orders}</TestOrders>
<TestsRequested><TestRequested Id="test-1" Name="{test}" CreationActorId="admin"/></TestsRequested>
<ProcessesRequested>{"".join(requested)}</ProcessesRequested>
</DomainObjects>
"""


C8800_SAMPLES = [
    ("(-) Ctrl", "A1", {"T1": "", "T2": ""}),
    ("S3101", "B1", {"T1": "20.5", "T2": "22.1"}),
    ("S3102", "C1", {"T1": "20.7", "T2": ""}),
    ("S3n01", "D1", {"T1": "", "T2": ""}),
    ("S3n02", "E1", {"T1": "", "T2": ""}),
]


@pytest.fixture
def c8800_file(tmp_path: Path) -> Path:
    path = tmp_path / "29471_s3_test_2026_11_09_13_50_37.xml"
    path.write_text(c8800_xml(C8800_SAMPLES, failed_well="E1"), encoding="utf-8")
    return path
