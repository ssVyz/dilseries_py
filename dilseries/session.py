"""Import session: loaded measurements plus all user decisions.

User decisions (run dates, groups, include/exclude, manual name overrides) are
stored separately from the imported data, so re-parsing names with a new
naming configuration keeps them.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

from dilseries import importers
from dilseries.importers import flow, lcpro
from dilseries.model import Measurement, is_internal_control
from dilseries.naming import NEG_STEP, NamingConfig, ParsedName, Role, parse_names, step_sort_key
from dilseries.util import natural_key, parse_well

PlateKey = tuple[str, str]  # (platform, plate id)
SeriesKey = tuple[str, str, str]  # (platform, group, series prefix)

STATUS_OK = "ok"
STATUS_DUPLICATE = "duplicate"
STATUS_UNPARSED = "unparsed"
STATUS_INCOMPLETE = "incomplete"
STATUS_CONTROL = "control"
STATUS_EXCLUDED = "excluded"
STATUS_SUPERSEDED = "superseded"
PROBLEM_STATUSES = frozenset({STATUS_DUPLICATE, STATUS_UNPARSED, STATUS_INCOMPLETE})

# platform -> platform whose import of the same plate (barcode) replaces it
SUPERSEDED_BY = {lcpro.PLATFORM: flow.PLATFORM}

_UNSET = object()


@dataclass
class LoadedFile:
    path: str
    format_name: str
    uids: list[int]
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class RunOverride:
    when: datetime | None = None
    operator: str | None = None


@dataclass
class NameOverride:
    role: Role | None = None
    series: str | None = None
    step: str | None = None
    repeat: int | None = None


@dataclass(frozen=True)
class Annotation:
    """Effective classification of one measurement."""

    role: Role
    series: str
    step: str
    repeat: int | None
    group: str
    included: bool
    status: str
    overridden: bool
    layout: str = ""


@dataclass
class RunSummary:
    key: PlateKey
    run_ids: list[str]
    files: list[str]
    when: datetime | None
    date_source: str  # "export", "user" or "missing"
    operators: list[str]
    count: int
    superseded_by: str = ""  # platform whose import of the same plate replaces this run


@dataclass
class Series:
    platform: str
    group: str
    prefix: str
    cells: dict[tuple[str, int], list[Measurement]] = field(default_factory=dict)
    steps: list[str] = field(default_factory=list)
    repeats: list[int] = field(default_factory=list)
    targets: list[tuple[str, int | None]] = field(default_factory=list)
    type: str = ""

    @property
    def key(self) -> SeriesKey:
        return (self.platform, self.group, self.prefix)

    @property
    def label(self) -> str:
        return " · ".join(p for p in (self.prefix or "(no prefix)", self.group, self.platform) if p)

    @property
    def measurements(self) -> list[Measurement]:
        return [m for ms in self.cells.values() for m in ms]

    @property
    def missing(self) -> int:
        return len(self.steps) * len(self.repeats) - len(self.cells)

    @property
    def duplicates(self) -> int:
        return sum(1 for ms in self.cells.values() if len(ms) > 1)


class Session:
    def __init__(self) -> None:
        self.files: dict[str, LoadedFile] = {}
        self.measurements: dict[int, Measurement] = {}
        self.naming = NamingConfig()
        self.overrides: dict[int, NameOverride] = {}
        self.excluded: set[int] = set()
        self.groups: dict[int, str] = {}
        self.run_overrides: dict[PlateKey, RunOverride] = {}
        self.series_types: dict[SeriesKey, str] = {}
        self.layout_notes: list[str] = []
        self._next_uid = 0
        self._external_ids: dict[tuple[str, str], int] = {}
        self._annotations: dict[int, Annotation] | None = None

    # ----------------------------------------------------------------- loading
    def add_file(self, path: str | Path) -> LoadedFile:
        path = str(Path(path).resolve())
        if path in self.files:
            return self.files[path]
        result = importers.load(path)
        loaded = LoadedFile(path, result.format_name, [], warnings=list(result.warnings))
        for m in result.measurements:
            ext_key = (m.platform, m.external_id)
            if m.external_id and ext_key in self._external_ids:
                loaded.skipped += 1
                continue
            m.uid = self._next_uid
            self._next_uid += 1
            self.measurements[m.uid] = m
            if m.external_id:
                self._external_ids[ext_key] = m.uid
            loaded.uids.append(m.uid)
        self.files[path] = loaded
        self.invalidate()
        return loaded

    def remove_file(self, path: str) -> None:
        loaded = self.files.pop(path, None)
        if loaded is None:
            return
        for uid in loaded.uids:
            m = self.measurements.pop(uid)
            self._external_ids.pop((m.platform, m.external_id), None)
            self.overrides.pop(uid, None)
            self.excluded.discard(uid)
            self.groups.pop(uid, None)
        self.invalidate()

    def invalidate(self) -> None:
        self._annotations = None

    # ------------------------------------------------------------- user input
    def set_naming(self, config: NamingConfig) -> None:
        self.naming = config
        self.invalidate()

    def set_included(self, uids, included: bool) -> None:
        for uid in uids:
            if included:
                self.excluded.discard(uid)
            else:
                self.excluded.add(uid)
        self.invalidate()

    def set_group(self, uids, group: str) -> None:
        group = group.strip()
        for uid in uids:
            if group:
                self.groups[uid] = group
            else:
                self.groups.pop(uid, None)
        self.invalidate()

    def rename_group(self, old: str, new: str) -> None:
        for uid, group in list(self.groups.items()):
            if group == old:
                self.set_group([uid], new)
        self.invalidate()

    def set_override(self, uids, role=_UNSET, series=_UNSET, step=_UNSET, repeat=_UNSET) -> None:
        for uid in uids:
            o = self.overrides.setdefault(uid, NameOverride())
            if role is not _UNSET:
                o.role = role
            if series is not _UNSET:
                o.series = series
            if step is not _UNSET:
                o.step = step
            if repeat is not _UNSET:
                o.repeat = repeat
        self.invalidate()

    def clear_override(self, uids) -> None:
        for uid in uids:
            self.overrides.pop(uid, None)
        self.invalidate()

    def set_run_info(self, keys, when=_UNSET, operator=_UNSET) -> None:
        for key in keys:
            o = self.run_overrides.setdefault(key, RunOverride())
            if when is not _UNSET:
                o.when = when
            if operator is not _UNSET:
                o.operator = operator or None
        self.invalidate()

    def set_series_type(self, key: SeriesKey, type_: str) -> None:
        self.series_types[key] = type_.strip()

    # ------------------------------------------------------------- derived data
    @staticmethod
    def plate_key(m: Measurement) -> PlateKey:
        return (m.platform, m.plate_id)

    def run_datetime(self, m: Measurement) -> datetime | None:
        o = self.run_overrides.get(self.plate_key(m))
        if o is not None and o.when is not None:
            return o.when
        return m.timestamp

    def run_operator(self, m: Measurement) -> str:
        o = self.run_overrides.get(self.plate_key(m))
        if o is not None and o.operator:
            return o.operator
        return m.operator

    def group_of(self, m: Measurement) -> str:
        return self.groups.get(m.uid) or m.assay

    def all_groups(self) -> list[str]:
        groups = {self.group_of(m) for m in self.measurements.values()}
        groups.discard("")
        return sorted(groups, key=natural_key)

    def superseding_platform(self, m: Measurement) -> str:
        """Platform that replaces this measurement because the same plate was imported from it, or ''."""
        other = SUPERSEDED_BY.get(m.platform)
        if other and m.plate_id in self._plates_by_platform().get(other, set()):
            return other
        return ""

    def _plates_by_platform(self) -> dict[str, set[str]]:
        plates: dict[str, set[str]] = defaultdict(set)
        for m in self.measurements.values():
            plates[m.platform].add(m.plate_id)
        return plates

    def superseded_count(self, path: str) -> int:
        ann = self.annotations()
        return sum(1 for uid in self.files[path].uids if ann[uid].status == STATUS_SUPERSEDED)

    def annotations(self) -> dict[int, Annotation]:
        if self._annotations is not None:
            return self._annotations
        plates = self._plates_by_platform()
        superseded = {
            uid
            for uid, m in self.measurements.items()
            if m.platform in SUPERSEDED_BY and m.plate_id in plates.get(SUPERSEDED_BY[m.platform], set())
        }
        names = {m.sample_id for m in self.measurements.values() if not m.is_control}
        parsed, self.layout_notes = parse_names(names, self.naming)
        base: dict[int, Annotation] = {}
        for uid, m in self.measurements.items():
            p = ParsedName(Role.CONTROL) if m.is_control else parsed.get(m.sample_id, ParsedName(Role.UNKNOWN))
            role, series, step, repeat = p.role, p.series, p.step, p.repeat
            o = self.overrides.get(uid)
            if o is not None:
                role = o.role if o.role is not None else role
                series = o.series if o.series is not None else series
                step = o.step if o.step is not None else step
                repeat = o.repeat if o.repeat is not None else repeat
            if role == Role.NEGATIVE:
                step = NEG_STEP
            elif role == Role.SAMPLE and step == NEG_STEP:
                role = Role.NEGATIVE
            base[uid] = Annotation(
                role=role,
                series=series,
                step=step,
                repeat=repeat,
                group=self.group_of(m),
                included=uid not in self.excluded and uid not in superseded,
                status=STATUS_SUPERSEDED if uid in superseded else "",
                overridden=o is not None,
                layout=p.layout,
            )

        cell_counts: Counter = Counter()
        for uid, a in base.items():
            if a.included and a.role in (Role.SAMPLE, Role.NEGATIVE) and a.step and a.repeat is not None:
                cell_counts[self._cell_key(uid, a)] += 1

        result: dict[int, Annotation] = {}
        for uid, a in base.items():
            if a.status == STATUS_SUPERSEDED:
                status = STATUS_SUPERSEDED
            elif not a.included:
                status = STATUS_EXCLUDED
            elif a.role == Role.CONTROL:
                status = STATUS_CONTROL
            elif a.role == Role.UNKNOWN:
                status = STATUS_UNPARSED
            elif not a.step or a.repeat is None:
                status = STATUS_INCOMPLETE
            elif cell_counts[self._cell_key(uid, a)] > 1:
                status = STATUS_DUPLICATE
            else:
                status = STATUS_OK
            result[uid] = replace(a, status=status)
        self._annotations = result
        return result

    def _cell_key(self, uid: int, a: Annotation) -> tuple:
        m = self.measurements[uid]
        return (m.platform, a.group, a.series, a.step, a.repeat)

    def series(self) -> list[Series]:
        ann = self.annotations()
        by_key: dict[SeriesKey, Series] = {}
        for uid, a in ann.items():
            if not a.included or a.role not in (Role.SAMPLE, Role.NEGATIVE) or not a.step or a.repeat is None:
                continue
            m = self.measurements[uid]
            key = (m.platform, a.group, a.series)
            s = by_key.get(key)
            if s is None:
                s = by_key[key] = Series(m.platform, a.group, a.series, type=self.series_types.get(key, ""))
            s.cells.setdefault((a.step, a.repeat), []).append(m)
        for s in by_key.values():
            s.steps = sorted({step for step, _ in s.cells}, key=step_sort_key)
            s.repeats = sorted({rep for _, rep in s.cells})
            s.targets = target_order(s.measurements)
            for ms in s.cells.values():
                ms.sort(key=lambda m: (self.run_datetime(m) or datetime.min, m.uid))
        return sorted(by_key.values(), key=lambda s: (natural_key(s.prefix), s.platform, natural_key(s.group)))

    def controls(self) -> list[Measurement]:
        ann = self.annotations()
        ms = [self.measurements[uid] for uid, a in ann.items() if a.included and a.role == Role.CONTROL]
        return sorted(ms, key=lambda m: (m.platform, self.run_datetime(m) or datetime.min, m.plate_id, natural_key(m.well)))

    def runs(self) -> list[RunSummary]:
        groups: dict[PlateKey, list[Measurement]] = defaultdict(list)
        for m in self.measurements.values():
            groups[self.plate_key(m)].append(m)
        out = []
        for key, ms in groups.items():
            o = self.run_overrides.get(key)
            stamps = [m.timestamp for m in ms if m.timestamp]
            if o is not None and o.when is not None:
                when, source = o.when, "user"
            elif stamps:
                when, source = min(stamps), "export"
            else:
                when, source = None, "missing"
            operators = [o.operator] if o is not None and o.operator else sorted({m.operator for m in ms if m.operator})
            out.append(
                RunSummary(
                    key=key,
                    run_ids=sorted({m.run_id for m in ms if m.run_id}),
                    files=sorted({Path(m.source_file).name for m in ms}),
                    when=when,
                    date_source=source,
                    operators=operators,
                    count=len(ms),
                    superseded_by=self.superseding_platform(ms[0]),
                )
            )
        return sorted(out, key=lambda r: (r.when or datetime.max, r.key))

    def plates(self) -> list[PlateKey]:
        return [r.key for r in self.runs()]

    def plate_wells(self, key: PlateKey) -> dict[str, list[int]]:
        wells: dict[str, list[int]] = defaultdict(list)
        for uid, m in self.measurements.items():
            if self.plate_key(m) == key:
                wells[m.well].append(uid)
        return dict(wells)

    def suggest_groups(self, key: PlateKey, name_template: str = "Test {}") -> dict[int, str]:
        """Split a plate into contiguous blocks in which no sample or control name occurs twice.

        Wells are walked column-wise and row-wise; the order giving fewer blocks
        wins. A repeated control name (e.g. a second NTC) also starts a new block,
        as each test usually has its own controls. Returns an empty dict when the
        plate has no duplicates within its current groups (no split needed, e.g.
        Flow results, where every well carries its test name).
        """
        if not self.plate_has_duplicates(key):
            return {}
        ann = self.annotations()
        wells = self.plate_wells(key)
        positioned = [(parse_well(w), w) for w in wells]
        positioned = [(pos, w) for pos, w in positioned if pos is not None]
        best: list[list[int]] | None = None
        for order in (lambda p: (p[0][1], p[0][0]), lambda p: (p[0][0], p[0][1])):
            blocks: list[list[int]] = [[]]
            seen: set[str] = set()
            for _, well in sorted(positioned, key=order):
                uids = [u for u in wells[well] if ann[u].included]
                names = {self.measurements[u].sample_id for u in uids if ann[u].role != Role.UNKNOWN}
                if names & seen:
                    blocks.append([])
                    seen = set()
                seen |= names
                blocks[-1].extend(uids)
            blocks = [b for b in blocks if b]
            if best is None or len(blocks) < len(best):
                best = blocks
        if not best or len(best) < 2:
            return {}
        return {uid: name_template.format(i) for i, block in enumerate(best, start=1) for uid in block}

    def plate_has_duplicates(self, key: PlateKey) -> bool:
        ann = self.annotations()
        uids = [u for us in self.plate_wells(key).values() for u in us]
        return any(ann[u].status == STATUS_DUPLICATE for u in uids)

    def warnings(self) -> list[str]:
        ann = self.annotations()
        out = []
        missing_dates = [r for r in self.runs() if r.date_source == "missing" and not r.superseded_by]
        if missing_dates:
            out.append(f"{len(missing_dates)} run(s) without run date: " + ", ".join(r.key[1] for r in missing_dates))
        counts = Counter(a.status for a in ann.values())
        if counts[STATUS_UNPARSED]:
            out.append(f"{counts[STATUS_UNPARSED]} sample(s) with unrecognized names")
        if counts[STATUS_INCOMPLETE]:
            out.append(f"{counts[STATUS_INCOMPLETE]} sample(s) without step or repeat")
        if counts[STATUS_DUPLICATE]:
            plates = sorted({self.measurements[u].plate_id for u, a in ann.items() if a.status == STATUS_DUPLICATE})
            out.append(
                f"{counts[STATUS_DUPLICATE]} measurement(s) share series/step/repeat with another measurement "
                f"(plates: {', '.join(plates)}). Assign groups on the plate layout or exclude wells."
            )
        return out


def target_order(measurements: list[Measurement]) -> list[tuple[str, int | None]]:
    channels: dict[str, int | None] = {}
    for m in measurements:
        for r in m.results:
            if r.target not in channels or channels[r.target] is None:
                channels[r.target] = r.channel
    return sorted(
        channels.items(),
        key=lambda tc: (is_internal_control(tc[0]), tc[1] if tc[1] is not None else 10**6, natural_key(tc[0])),
    )
