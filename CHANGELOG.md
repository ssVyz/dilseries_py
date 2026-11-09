# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-11-09

### Added

- Importers for cobas 5800 exports (zip of `ResultData_*.xml`, or a single XML) and LC Pro result tables (`*_ResultTable.csv`); only these formats are supported.
- Sample name classification into series, step, repeat, negatives and controls. Delimited names (`_`, `-`, space) are split directly; for undelimited names the order (step/repeat first) and digit counts are configurable, with automatic digit-count detection as default.
- Session handling: run date/operator per run (required for LC Pro, which exports no dates), groups (test/assay) per well, include/exclude per measurement, manual name overrides, duplicate detection.
- tkinter GUI with tabs for files & runs, plate layout (range selection, group assignment, "Suggest groups" for plates with two tests on the same samples, exclude/include), sample review and series overview.
- Excel export: overview, one sheet per series with a step × repeat Ct matrix per target (day and operator per row, duplicates highlighted with comment), controls sheet and long-format data sheet.
- Dependencies: `openpyxl` (runtime), `pytest` (dev). Test suite with synthetic fixtures.

## [0.1.0] - 2026-11-09

### Added

- Initial project setup (Python 3.13, uv).
- `CHANGELOG.md` and `CLAUDE.md` with repository rules.
- Expanded `.gitignore` (env files, tool caches, IDE and OS files).
