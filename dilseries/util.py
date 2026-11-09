"""Small helpers shared by the GUI, session and export."""

from __future__ import annotations

import re
from datetime import datetime

_USER_DATE_FORMATS = (
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y",
)

_WELL = re.compile(r"^\s*([A-Za-z])0*(\d{1,2})\s*$")


def parse_user_datetime(text: str) -> datetime | None:
    """Parse a user-entered run date. Empty text returns None.

    Accepts YYYY-MM-DD or DD.MM.YYYY, each optionally followed by HH:MM.
    """
    text = " ".join(text.split())
    if not text:
        return None
    for fmt in _USER_DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date '{text}'. Use YYYY-MM-DD or DD.MM.YYYY, optionally with HH:MM.")


def format_datetime(value: datetime | None, with_time: bool = True) -> str:
    """Format a run date; a time of exactly midnight is treated as 'date only'."""
    if value is None:
        return ""
    if not with_time or (value.hour, value.minute, value.second) == (0, 0, 0):
        return value.strftime("%Y-%m-%d")
    return value.strftime("%Y-%m-%d %H:%M")


def parse_well(well: str) -> tuple[int, int] | None:
    """Convert a well name like 'B7' or 'B07' to zero-based (row, column)."""
    m = _WELL.match(well or "")
    if not m:
        return None
    return ord(m.group(1).upper()) - ord("A"), int(m.group(2)) - 1


def natural_key(value: object) -> tuple:
    """Sort key that orders embedded numbers numerically ('A2' < 'A10')."""
    parts = re.split(r"(\d+)", str(value).casefold())
    return tuple((0, int(p)) if p.isdigit() else (1, p) for p in parts)
