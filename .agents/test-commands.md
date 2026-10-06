# What must pass before a PR, by area. Preflight runs the rows whose
# path globs match the branch's changed files; "always" runs every time.

| Area | Paths | Command |
|---|---|---|
| full build | always | `bin/build` |
| tests | src/**,tests/** | `uv run pytest -q` |
| lint | src/**,tests/** | `uv run ruff check src tests` |
| format | src/**,tests/** | `uv run ruff format --check src tests` |
| types | src/**,tests/** | `uv run mypy src tests` |
