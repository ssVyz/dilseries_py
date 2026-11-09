"""Registry of supported export formats.

Only formats implemented here are supported. To add a format, create a module
with ``FORMAT_NAME``, ``can_read(path)`` and ``read(path) -> ImportResult`` and
register it in ``IMPORTERS``.
"""

from __future__ import annotations

from pathlib import Path

from dilseries.importers import cobas5800, cobas8800, flow, lcpro
from dilseries.model import ImportResult, UnsupportedFileError

IMPORTERS = (cobas5800, cobas8800, flow, lcpro)

SUPPORTED_DESCRIPTION = (
    "Flow results (.csv), cobas 5800 export (.zip/.xml), cobas 8800 export (.xml), LC Pro result table (.csv)"
)

FILE_TYPES = [
    ("Supported exports", "*.zip *.xml *.csv"),
    ("Flow results", "*.csv"),
    ("cobas 5800 export", "*.zip *.xml"),
    ("cobas 8800 export", "*.xml"),
    ("LC Pro result table", "*.csv"),
    ("All files", "*.*"),
]


def load(path: str | Path) -> ImportResult:
    path = Path(path)
    for importer in IMPORTERS:
        if importer.can_read(path):
            return importer.read(path)
    raise UnsupportedFileError(f"{path.name}: not a supported export ({SUPPORTED_DESCRIPTION})")
