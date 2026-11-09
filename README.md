# dilseries

Imports qPCR dilution series experiments (linearity / LoD) from instrument exports and
assembles them into a formatted Excel workbook.

Supported exports:

- **cobas 5800**: result export zip (`*_Export_*.zip` with `ResultData_*.xml`), or a single XML
- **LC Pro**: result table (`*_ResultTable.csv`)

## Usage

```
uv run main.py [files...]
```

1. **Files & runs**: add exports. Set the run date (and operator) for runs without one; LC Pro tables contain no dates.
2. **Plate layout**: if one plate holds several tests on the same samples, select contiguous well ranges
   and assign a group per test ("Suggest groups" proposes a split). Exclude wells that should not be imported.
3. **Samples**: check how sample names were parsed into series / step / repeat. Configure the name layout
   (order, digits per counter, negative markers, control names) or edit samples manually.
4. **Series & export**: review the series and export the Excel workbook.

## Sample names

A name is `<series><step><repeat>`, e.g. `LE20307` (series `LE20`, step 3, repeat 07) or
`LE20_3_07`. Negative samples use a marker instead of the step (`LE20n07`). Without delimiters the
digit counts are detected automatically; set them explicitly when names are ambiguous
(e.g. `LIN0101` could be series `LIN0` step 1 or series `LIN` step 01).

## Development

```
uv run pytest
```

Tests in `tests/test_examples.py` use the real exports in `examples/` (gitignored) and are skipped when absent.
