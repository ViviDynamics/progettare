# Test commands

Run by `preflight` before every push. A row runs only when the branch's diff touches
its paths; rows run top to bottom, cheapest first, and stop at the first failure.
`{files}` is the changed files the row matched. These mirror CI: ruff format and
check, strict mypy, then pytest.

| Area | Paths | Command |
| --- | --- | --- |
| Formatting, changed files | *.py | uv run ruff format --check {files} |
| Lint, changed files | *.py | uv run ruff check {files} |
| Whole-tree lint and format | pyproject.toml, uv.lock | uv run ruff format --check src tests && uv run ruff check src tests |
| Types | src/*.py, tests/*.py, pyproject.toml | uv run mypy src tests |
| Changed tests | tests/*.py | uv run pytest -q {files} |
| Tests | src/*, tests/*, pyproject.toml, uv.lock | uv run pytest -q |
| Skills wiring | .agents/*, repo.env.example | .agents/skills/ci-safety/scripts/check-wiring |
