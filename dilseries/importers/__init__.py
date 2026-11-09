"""Registry of supported export formats.

Only formats implemented here are supported. To add a format, create a module
with ``FORMAT_NAME``, ``can_read(path)`` and ``read(path) -> ImportResult`` and
register it in ``IMPORTERS``.
"""

from __future__ import annotations

from pathlib import Path

from dilseries.importers import cobas5800, lcpro
from dilseries.model import ImportResult, UnsupportedFileError

IMPORTERS = (cobas5800, lcpro)

FILE_TYPES = [
    ("Supported exports", "*.zip *.xml *.csv"),
    ("cobas 5800 export", "*.zip *.xml"),
    ("LC Pro result table", "*.csv"),
    ("All files", "*.*"),
]


def load(path: str | Path) -> ImportResult:
    path = Path(path)
    for importer in IMPORTERS:
        if importer.can_read(path):
            return importer.read(path)
    raise UnsupportedFileError(f"{path.name}: not a supported export (cobas 5800 zip/xml, LC Pro result table csv)")
