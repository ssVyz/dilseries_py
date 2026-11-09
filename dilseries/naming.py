"""Classify sample names of dilution series into series, step and repeat.

A dilution-series sample name consists of a series prefix followed by a step
counter and a repeat counter (by default step first), e.g. ``LE20_3_07`` or,
without delimiters, ``LE20307``. Negative samples use a marker instead of a
step number (``LE20n07``).

Delimited names are split on ``_``, ``-`` or spaces. Names without delimiters
are parsed with fixed digit counts for step and repeat. Digit counts can be
configured or inferred automatically: all names sharing the same stem are
parsed with every candidate layout and the layout that yields the most
consistent step x repeat grid wins.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from itertools import product


class Role(StrEnum):
    SAMPLE = "sample"
    NEGATIVE = "negative"
    CONTROL = "control"
    UNKNOWN = "unknown"


NEG_STEP = "neg"
MAX_DIGITS = 3
DEFAULT_NEGATIVE_MARKERS = ("n", "neg")
DEFAULT_CONTROL_NAMES = ("(-) Ctrl", "(+) Ctrl", "NTC", "NC", "PC", "Neg Ctrl", "Pos Ctrl", "H2O")

_DELIM_CHARS = "_- "
_DELIMITED = re.compile(r"^(?P<prefix>.*?)[_\-\s]+(?P<a>[^_\-\s]+)[_\-\s]+(?P<b>[^_\-\s]+)$")
_NUMBERED_CONTROL_SUFFIX = re.compile(r"[\s_\-]*\d{1,2}")


@dataclass(frozen=True)
class NamingConfig:
    """User-configurable rules for interpreting sample names."""

    step_first: bool = True
    step_digits: int | None = None  # None = infer automatically
    repeat_digits: int | None = None  # None = infer automatically
    negative_markers: tuple[str, ...] = DEFAULT_NEGATIVE_MARKERS
    control_names: tuple[str, ...] = DEFAULT_CONTROL_NAMES


@dataclass(frozen=True)
class ParsedName:
    role: Role
    series: str = ""
    step: str = ""  # "1", "2", ... or NEG_STEP
    repeat: int | None = None
    layout: str = ""


def step_sort_key(step: str) -> tuple[int, int, str]:
    """Numeric steps ascending, negative step last."""
    if step == NEG_STEP:
        return (1, 0, step)
    if step.isdigit():
        return (0, int(step), step)
    return (0, 10**9, step)


def is_control_name(name: str, config: NamingConfig) -> bool:
    """True if the name is a control name, optionally numbered (``NTC``, ``NTC 2``)."""
    norm = " ".join(name.split()).casefold()
    for control in config.control_names:
        ctrl = " ".join(control.split()).casefold()
        if not ctrl:
            continue
        if norm == ctrl:
            return True
        if norm.startswith(ctrl) and _NUMBERED_CONTROL_SUFFIX.fullmatch(norm[len(ctrl):]):
            return True
    return False


def parse_names(names: set[str] | list[str], config: NamingConfig) -> tuple[dict[str, ParsedName], list[str]]:
    """Parse sample names. Returns the parse per name and human-readable layout notes."""
    result: dict[str, ParsedName] = {}
    undelimited: list[str] = []
    for name in sorted(set(names)):
        if is_control_name(name, config):
            result[name] = ParsedName(Role.CONTROL)
            continue
        parsed = _parse_delimited(name, config)
        if parsed is not None:
            result[name] = parsed
        else:
            undelimited.append(name)

    notes: list[str] = []
    families: dict[str, list[str]] = defaultdict(list)
    for name in undelimited:
        families[_family_key(name, config.negative_markers)].append(name)
    for family, members in sorted(families.items()):
        sw, rw, parsed = _choose_widths(members, config)
        layout = f"step {sw} / repeat {rw} digit(s)"
        auto = config.step_digits is None or config.repeat_digits is None
        notes.append(f"{family or '(no prefix)'}…: {layout}{' (auto)' if auto else ''}, {len(parsed)}/{len(members)} names parsed")
        for name in members:
            if name in parsed:
                prefix, step, repeat = parsed[name]
                role = Role.NEGATIVE if step == NEG_STEP else Role.SAMPLE
                result[name] = ParsedName(role, prefix, step, repeat, layout)
            else:
                result[name] = ParsedName(Role.UNKNOWN)
    return result, notes


def _step_label(token: str, markers: tuple[str, ...]) -> str | None:
    if token.casefold() in {m.casefold() for m in markers if m}:
        return NEG_STEP
    if token.isascii() and token.isdigit():
        return str(int(token))
    return None


def _parse_delimited(name: str, config: NamingConfig) -> ParsedName | None:
    m = _DELIMITED.match(name.strip())
    if not m:
        return None
    step_tok, rep_tok = (m["a"], m["b"]) if config.step_first else (m["b"], m["a"])
    step = _step_label(step_tok, config.negative_markers)
    if step is None or not (rep_tok.isascii() and rep_tok.isdigit()):
        return None
    # With fixed digit counts, tokens must match them; otherwise fall back to undelimited parsing
    # (handles names like "LE_20_101" where the last token holds both counters).
    if config.step_digits and step != NEG_STEP and len(step_tok) != config.step_digits:
        return None
    if config.repeat_digits and len(rep_tok) != config.repeat_digits:
        return None
    role = Role.NEGATIVE if step == NEG_STEP else Role.SAMPLE
    return ParsedName(role, m["prefix"].strip(_DELIM_CHARS), step, int(rep_tok), "delimited")


def _family_key(name: str, markers: tuple[str, ...]) -> str:
    """Stem shared by all names of one series family, e.g. 'LE' for LE20101 and LE20n01."""
    stem = name.rstrip("0123456789")
    low = stem.casefold()
    for marker in sorted((m for m in markers if m), key=len, reverse=True):
        if low.endswith(marker.casefold()):
            stem = stem[: len(stem) - len(marker)]
            break
    return stem.rstrip("0123456789").rstrip(_DELIM_CHARS)


def _undelimited_regex(step_digits: int, repeat_digits: int, config: NamingConfig) -> re.Pattern[str]:
    markers = sorted((re.escape(m) for m in config.negative_markers if m), key=len, reverse=True)
    step = f"(?P<step>[0-9]{{{step_digits}}}" + "".join(f"|{m}" for m in markers) + ")"
    rep = f"(?P<rep>[0-9]{{{repeat_digits}}})"
    body = step + rep if config.step_first else rep + step
    return re.compile(f"^(?P<prefix>.*?){body}$", re.IGNORECASE)


def _choose_widths(names: list[str], config: NamingConfig) -> tuple[int, int, dict[str, tuple[str, str, int]]]:
    step_opts = [config.step_digits] if config.step_digits else range(1, MAX_DIGITS + 1)
    rep_opts = [config.repeat_digits] if config.repeat_digits else range(1, MAX_DIGITS + 1)
    best: tuple[tuple[float, int, int], int, int, dict[str, tuple[str, str, int]]] | None = None
    for sw, rw in product(step_opts, rep_opts):
        rx = _undelimited_regex(sw, rw, config)
        parsed: dict[str, tuple[str, str, int]] = {}
        for name in names:
            m = rx.match(name.strip())
            if not m:
                continue
            step = _step_label(m["step"], config.negative_markers)
            if step is None:
                continue
            parsed[name] = (m["prefix"].strip(_DELIM_CHARS), step, int(m["rep"]))
        # Tie-break: fewer total digits, then fewer step digits.
        rank = (_layout_penalty(parsed, len(names)), sw + rw, sw)
        if best is None or rank < best[0]:
            best = (rank, sw, rw, parsed)
    assert best is not None
    return best[1], best[2], best[3]


def _layout_penalty(parsed: dict[str, tuple[str, str, int]], total: int) -> float:
    """Lower is better: few unparsed names, few series, complete consecutive grids."""
    penalty = 100.0 * (total - len(parsed))
    cells_by_prefix: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for prefix, step, repeat in parsed.values():
        cells_by_prefix[prefix].append((step, repeat))
    for cells in cells_by_prefix.values():
        unique = set(cells)
        penalty += 3.0
        penalty += 20.0 * (len(cells) - len(unique))
        steps = {s for s, _ in unique}
        repeats = sorted({r for _, r in unique})
        penalty += 2.0 * (len(steps) * len(repeats) - len(unique)) / len(unique)
        penalty += _sequence_penalty(sorted(int(s) for s in steps if s != NEG_STEP))
        penalty += _sequence_penalty(repeats)
    return penalty


def _sequence_penalty(values: list[int]) -> float:
    if not values:
        return 0.0
    penalty = 0.0
    if values != list(range(values[0], values[0] + len(values))):
        penalty += 5.0
    if values[0] == 0:
        penalty += 2.0
    elif values[0] > 1:
        penalty += 1.0
    return penalty
