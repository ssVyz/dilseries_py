"""Import qPCR dilution series exports and assemble them into Excel overviews."""

from pathlib import Path


def _read_version() -> str:
    """Read the version from pyproject.toml, the single source of truth."""
    import tomllib

    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        with pyproject.open("rb") as fh:
            return tomllib.load(fh)["project"]["version"]
    except (OSError, KeyError, ValueError):
        pass
    try:
        from importlib.metadata import version

        return version("dilseries")
    except ImportError:
        return "unknown"


__version__ = _read_version()
