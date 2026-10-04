# House rules for progettare

These rules bind every agent and human working in this repository. The spec,
[docs/SPEC.md](docs/SPEC.md), is the source of truth for architecture and
behavior. Do not invent architecture on your own: if the spec does not cover a
design decision, stop and ask.

## The family rule

Every model call goes through nare, the family rule. Use nare's existing
flags: `--system`, `--tools`, `--provider`, `--base-url`, `--model`,
`--max-tokens`, `--session`, `--resume`. No direct provider calls. A
capability nare lacks is filed as an issue on ViviDynamics/nare, and the
dependent progettare feature is marked blocked by it, in the issue body and on
the board. No silent workarounds.

## Architecture discipline

- Model proposes, code executes. Code formulates survey questions, validates
  stage output, sizes ceremony, and slices briefs. The model answers questions
  and drafts the blueprint, nothing more.
- The harness is read-only end to end against the surveyed repository. All
  outputs are run-directory artifacts: intake.json, survey.json,
  blueprint.json, size.json, briefs/.
- Bounded stages, no context accumulation: one nare session per survey
  question, one for the blueprint, each with its own budget from config.
- One bounded re-ask on invalid stage output, then fail loudly. No partial
  blueprint is ever published.
- The CLI's JSON output is a versioned contract. Do not break it silently.

## Engineering

- Python via uv, typed, tested. Follow nare's repo conventions: src/ layout,
  pyproject.toml, ruff, strict mypy, pytest, container image.
- Strict TDD: no implementation code before its failing test.
- Never disable, skip, or weaken a test to make CI green.

## Voice

- No em dashes anywhere: issues, PRs, commit messages, docs, code comments.
  Use periods, commas, or parentheses. Sentences stay plain and direct.

## Workflow

- Claim an issue before working it, and leave it alone when it is someone
  else's. Never adopt another agent's branch or PR.
- Squash merges only, with the family's merge flags.
- Prose we publish (PR bodies, comments, docs) uses no em dashes.
