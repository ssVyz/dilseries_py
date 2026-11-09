# dilseries

Python 3.13 project managed with uv. Entry point: `main.py`.

- Run: `uv run main.py`
- Version: `pyproject.toml` → `[project].version` is the single source of truth.

## Rules

- Every code change gets a `CHANGELOG.md` entry and a patch version bump (`pyproject.toml` and changelog heading in sync).
- Bump minor or major version only when explicitly requested.
- Do not commit. Git commits are handled by humans.
- Do not modify `.gitignore` or `CLAUDE.md` without permission.
- Ask for permission before adding any external dependency.
- Approved dependencies: `openpyxl` (runtime), `pytest` (dev).
