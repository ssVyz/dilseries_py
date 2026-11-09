"""Write a session to a formatted Excel workbook.

Sheets:
- Overview: export info, naming settings, one row per series (with links), warnings.
- One sheet per series: per target a step x repeat matrix of Ct values, rows
  labelled with run day and operator.
- Controls: all control measurements.
- Data: every included measurement and target in long format.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from dilseries import __version__
from dilseries.model import NEGATIVE_CALLS, Measurement, TargetResult
from dilseries.naming import NEG_STEP
from dilseries.session import Series, Session
from dilseries.util import natural_key

NOT_DETECTED = "-"
CT_FORMAT = "0.00"
DATE_FORMAT = "yyyy-mm-dd"
DATETIME_FORMAT = "yyyy-mm-dd hh:mm"

_HEADER_FILL = PatternFill("solid", fgColor="D9D9D9")
_DAY_FILL = PatternFill("solid", fgColor="F2F2F2")
_DUPLICATE_FILL = PatternFill("solid", fgColor="FFE699")
_THIN = Side(style="thin", color="A6A6A6")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_BOLD = Font(bold=True)
_TITLE = Font(bold=True, size=14)
_BLOCK_TITLE = Font(bold=True, size=12)
_INVALID_FONT = Font(color="C00000")
_LINK_FONT = Font(color="0563C1", underline="single")
_CENTER = Alignment(horizontal="center", vertical="center")
_INVALID_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")
_PLATFORM_SHORT = {"cobas 5800": "cobas", "LC Pro": "LCPro", "Flow": "Flow"}


def export_workbook(session: Session, path: str | Path) -> None:
    series = session.series()
    wb = Workbook()
    overview = wb.active
    overview.title = "Overview"
    used = {"Overview", "Controls", "Data"}
    sheet_names = {}
    for s in series:
        sheet_names[s.key] = _unique_sheet_name(_series_sheet_name(s), used)
    _write_overview(overview, session, series, sheet_names)
    for s in series:
        _write_series(wb.create_sheet(sheet_names[s.key]), session, s)
    _write_controls(wb.create_sheet("Controls"), session)
    _write_data(wb.create_sheet("Data"), session)
    wb.save(path)


# --------------------------------------------------------------------- sheets
def _write_overview(ws: Worksheet, session: Session, series: list[Series], sheet_names: dict) -> None:
    ws["A1"] = "Dilution series export"
    ws["A1"].font = _TITLE
    info = [
        ("Exported", datetime.now().replace(microsecond=0)),
        ("Tool version", f"dilseries {__version__}"),
        ("Name layout", _naming_description(session)),
    ]
    row = 3
    for label, value in info:
        ws.cell(row, 1, label).font = _BOLD
        cell = ws.cell(row, 2, value)
        if isinstance(value, datetime):
            cell.number_format = DATETIME_FORMAT
            cell.alignment = Alignment(horizontal="left")
        row += 1

    row += 1
    ws.cell(row, 1, "Source files").font = _BOLD
    for loaded in session.files.values():
        ws.cell(row, 2, Path(loaded.path).name)
        ws.cell(row, 3, loaded.format_name)
        ws.cell(row, 4, f"{len(loaded.uids)} measurements")
        superseded = session.superseded_count(loaded.path)
        if superseded:
            ws.cell(row, 5, f"{superseded} not used: same plate imported from Flow results")
        row += 1

    row += 1
    headers = ["Series", "Platform", "Assay / group", "Type", "Steps", "Repeats", "Samples", "Missing", "Duplicates", "Run days", "Sheet"]
    _header_row(ws, row, headers)
    row += 1
    for s in series:
        days = sorted({d.date() for m in s.measurements if (d := session.run_datetime(m))})
        values = [
            s.prefix,
            s.platform,
            s.group,
            s.type,
            len(s.steps),
            len(s.repeats),
            len(s.measurements),
            s.missing,
            s.duplicates,
            ", ".join(d.isoformat() for d in days),
            sheet_names[s.key],
        ]
        for col, value in enumerate(values, start=1):
            ws.cell(row, col, value).border = _BORDER
        link = ws.cell(row, len(values))
        link.hyperlink = f"#'{sheet_names[s.key]}'!A1"
        link.font = _LINK_FONT
        row += 1

    warnings = session.warnings()
    if warnings:
        row += 1
        ws.cell(row, 1, "Warnings").font = _BOLD
        for w in warnings:
            ws.cell(row, 2, w).font = _INVALID_FONT
            row += 1
    _set_widths(ws, {1: 16, 2: 22, 3: 20, 4: 14, 10: 36, 11: 28}, default=10)


def _write_series(ws: Worksheet, session: Session, s: Series) -> None:
    ws["A1"] = f"Series {s.prefix or '(no prefix)'}"
    ws["A1"].font = _TITLE
    meta = [("Platform", s.platform), ("Assay / group", s.group or "—"), ("Type", s.type or "—")]
    for i, (label, value) in enumerate(meta, start=2):
        ws.cell(i, 1, label).font = _BOLD
        ws.cell(i, 2, value)

    first_step_col = 4
    row = len(meta) + 3
    for target, channel in s.targets:
        row = _write_target_block(ws, session, s, target, channel, row, first_step_col) + 2
    last_col = first_step_col + len(s.steps) - 1
    _set_widths(ws, {1: 14, 2: 14, 3: 8} | {c: 9 for c in range(first_step_col, last_col + 1)})


def _write_target_block(ws: Worksheet, session: Session, s: Series, target: str, channel, row: int, first_col: int) -> int:
    title = target if channel is None else f"{target} (Ch.{channel})"
    ws.cell(row, 1, title).font = _BLOCK_TITLE
    row += 1
    last_col = first_col + len(s.steps) - 1
    step_header = ws.cell(row, first_col, "Step")
    step_header.font = _BOLD
    step_header.alignment = _CENTER
    if last_col > first_col:
        ws.merge_cells(start_row=row, start_column=first_col, end_row=row, end_column=last_col)
    row += 1
    _header_row(ws, row, ["Day", "Operator", "Repeat"] + [("neg" if st == NEG_STEP else int(st) if st.isdigit() else st) for st in s.steps])
    row += 1

    previous_day = None
    shaded = False
    for repeat in s.repeats:
        row_ms = [m for st in s.steps for m in s.cells.get((st, repeat), [])]
        days = sorted({d.date() for m in row_ms if (d := session.run_datetime(m))})
        day_value = days[0] if len(days) == 1 else ", ".join(d.isoformat() for d in days)
        if day_value != previous_day:
            shaded = not shaded if previous_day is not None else False
            previous_day = day_value
        operators = sorted({op for m in row_ms if (op := session.run_operator(m))})
        values = [day_value, ", ".join(operators), repeat]
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row, col, value)
            if col == 1 and len(days) == 1:
                cell.number_format = DATE_FORMAT
        for offset, step in enumerate(s.steps):
            _write_ct_cell(ws.cell(row, first_col + offset), session, s.cells.get((step, repeat), []), target)
        for col in range(1, last_col + 1):
            cell = ws.cell(row, col)
            cell.border = _BORDER
            if col >= 3:
                cell.alignment = _CENTER
            if shaded and cell.fill != _DUPLICATE_FILL:
                cell.fill = _DAY_FILL
        row += 1
    return row


def _write_ct_cell(cell, session: Session, measurements: list[Measurement], target: str) -> None:
    if not measurements:
        return
    shown = measurements[-1]
    cell.value = cell_value(shown.result(target))
    if isinstance(cell.value, float):
        cell.number_format = CT_FORMAT
    elif isinstance(cell.value, str) and cell.value != NOT_DETECTED:
        cell.font = _INVALID_FONT
    if len(measurements) > 1:
        cell.fill = _DUPLICATE_FILL
        lines = [f"{len(measurements)} measurements, last one shown:"]
        for m in measurements:
            when = session.run_datetime(m)
            value = cell_value(m.result(target))
            value = f"{value:.2f}" if isinstance(value, float) else (value or "")
            lines.append(f"{m.sample_id} {m.plate_id} {m.well} {when:%Y-%m-%d}: {value}" if when else f"{m.sample_id} {m.plate_id} {m.well}: {value}")
        cell.comment = Comment("\n".join(lines), "dilseries", height=20 + 18 * len(lines), width=320)


def _write_controls(ws: Worksheet, session: Session) -> None:
    headers = ["Platform", "Assay / group", "Plate / run", "Run date", "Operator", "Well", "Control", "Target", "Channel", "Ct", "Result", "Flags", "Source file"]
    _header_row(ws, 1, headers)
    row = 2
    for m in session.controls():
        for r in m.results or [None]:
            values = [
                m.platform,
                session.group_of(m),
                m.plate_id,
                session.run_datetime(m),
                session.run_operator(m),
                m.well,
                m.sample_id,
                r.target if r else "",
                r.channel if r else None,
                cell_value(r) if r else None,
                r.call if r else "",
                r.flags if r else "",
                Path(m.source_file).name,
            ]
            _data_row(ws, row, values, ct_col=10, date_col=4)
            row += 1
    _finish_table(ws, headers, row)


def _write_data(ws: Worksheet, session: Session) -> None:
    ann = session.annotations()
    ordered = sorted(
        (session.measurements[uid] for uid, a in ann.items() if a.included),
        key=lambda m: (m.platform, session.run_datetime(m) or datetime.min, m.plate_id, natural_key(m.well), m.uid),
    )
    extra_keys = list(dict.fromkeys(k for m in ordered for k in m.extra))
    headers = [
        "Platform", "Source file", "Run ID", "Plate / run", "Run date", "Operator", "Assay / group", "Well",
        "Sample ID", "Role", "Series", "Step", "Repeat", "Status", "Target", "Channel", "Ct", "Result", "Flags",
        "Details", "Sample flags", *extra_keys,
    ]
    _header_row(ws, 1, headers)
    row = 2
    for m in ordered:
        a = ann[m.uid]
        for r in m.results or [None]:
            values = [
                m.platform,
                Path(m.source_file).name,
                m.run_id,
                m.plate_id,
                session.run_datetime(m),
                session.run_operator(m),
                a.group,
                m.well,
                m.sample_id,
                str(a.role),
                a.series,
                a.step,
                a.repeat,
                a.status,
                r.target if r else "",
                r.channel if r else None,
                cell_value(r) if r else None,
                r.call if r else "",
                r.flags if r else "",
                r.details if r else "",
                m.flags,
                *(m.extra.get(k, "") for k in extra_keys),
            ]
            _data_row(ws, row, values, ct_col=17, date_col=5)
            row += 1
    _finish_table(ws, headers, row)


# -------------------------------------------------------------------- helpers
def cell_value(result: TargetResult | None) -> float | str | None:
    """Ct as number; '-' when not detected; the call text (e.g. 'IC FAILED', 'Invalid') when no Ct
    is reported for another reason; None if the target was not measured."""
    if result is None:
        return None
    if result.ct is not None:
        return result.ct
    call = " ".join(result.call.split())
    if call.casefold() in NEGATIVE_CALLS:
        return NOT_DETECTED
    return call


def _series_sheet_name(s: Series) -> str:
    parts = [s.prefix or "series", s.group, _PLATFORM_SHORT.get(s.platform, s.platform)]
    return " ".join(p for p in parts if p)


def _unique_sheet_name(name: str, used: set[str]) -> str:
    name = _INVALID_SHEET_CHARS.sub("_", name).strip("'") or "Sheet"
    base = name[:31]
    candidate, n = base, 2
    while candidate.casefold() in {u.casefold() for u in used}:
        suffix = f" ({n})"
        candidate = base[: 31 - len(suffix)] + suffix
        n += 1
    used.add(candidate)
    return candidate


def _naming_description(session: Session) -> str:
    c = session.naming
    order = "step, then repeat" if c.step_first else "repeat, then step"
    digits = f"step digits {c.step_digits or 'auto'}, repeat digits {c.repeat_digits or 'auto'}"
    return f"{order}; {digits}; negative markers {', '.join(c.negative_markers)}"


def _header_row(ws: Worksheet, row: int, headers: list) -> None:
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row, col, header)
        cell.font = _BOLD
        cell.fill = _HEADER_FILL
        cell.border = _BORDER
        cell.alignment = _CENTER


def _data_row(ws: Worksheet, row: int, values: list, ct_col: int, date_col: int) -> None:
    for col, value in enumerate(values, start=1):
        cell = ws.cell(row, col, value)
        if col == ct_col and isinstance(value, float):
            cell.number_format = CT_FORMAT
        elif col == date_col and isinstance(value, datetime):
            cell.number_format = DATETIME_FORMAT


def _finish_table(ws: Worksheet, headers: list[str], end_row: int) -> None:
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(end_row - 1, 1)}"
    widths = {i: max(10, min(30, len(h) + 4)) for i, h in enumerate(headers, start=1)}
    for i, h in enumerate(headers, start=1):
        if h in {"Source file", "Run date", "Plate / run", "Run ID", "Sample ID"}:
            widths[i] = 22
    _set_widths(ws, widths)


def _set_widths(ws: Worksheet, widths: dict[int, float], default: float | None = None) -> None:
    if default is not None:
        for col in range(1, 12):
            ws.column_dimensions[get_column_letter(col)].width = default
    for col, width in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = width
