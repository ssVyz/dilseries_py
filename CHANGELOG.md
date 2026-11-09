# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.3] - 2026-11-09

### Added

- Importer for cobas 8800 result exports (`DomainObjects` XML, `ApplicationName="c8800System"`), platform label "cobas 8800": test (version suffix removed, e.g. `U_ISO_CARB2`), target Ct and call, IC Ct, AD plate barcode and well, run ID, run start, operator (user who requested the processes; controls get the operator of their run). Extra columns: test definition, sample rack position, reagent cassette lot, system reagent lots, control lot. Failed processes and flags are recorded as sample flags. Large exports are read incrementally.
- Two tests run on the same AD plate appear as one plate/run with one group per test.

### Changed

- Sheet name suffix for cobas 5800 series is now `c5800` (was `cobas`), to distinguish it from `c8800`.

## [0.1.2] - 2026-11-09

### Added

- Importer for Roche Flow result exports (`*_Results.csv`), platform label "Flow": test (assay) per well, target names, Ct and call, worklist date as run date (also applied to controls), release status, purification plate and kit lot, PCR reagent lots.
- When the same plate is imported from an LC Pro result table and from Flow results, Flow is used and the LC Pro wells are marked "superseded" (shown in the file and run lists and the export overview).
- Data sheet: "Details" column (Tm, quantitative result) and extra per-sample columns provided by the export.

### Changed

- Results without Ct whose call is not a negative call (e.g. `IC FAILED`, `Invalid`) are shown with their call text in red instead of `-`.
- Internal controls are recognized by name (`IC`, `CIC`, names ending in `IC` such as `iso-aciIC`) and listed last.
- "Suggest groups" also starts a new block at a repeated control (e.g. a second NTC) and only acts on plates with unresolved duplicates; on the example plate it now reproduces the real test assignment.
- Run dates at midnight are displayed as date only.

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
