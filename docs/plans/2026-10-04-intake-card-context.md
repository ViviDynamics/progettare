# M1: intake and card context assembly

Issue #1

## Scope

In: the repo bootstrap this issue needs to ship (skills wiring, CI, the Python
scaffold from nare's conventions), plus the intake stage itself: issue
reference parsing, issue fetch through gh, acceptance criteria parsing,
clarifying question extraction, blocked detection, and the version-stamped
intake.json artifact.

Out: survey, blueprint, sizing, and report stages (issues #2 through #6).
Config file loading (#8). The run-directory abstraction and version stamping
module (#7 takes that further; this issue stamps intake.json itself). Full CLI
and release packaging (#9). nare is not called by this stage: intake is code
only and spends no model calls, per the spec.

## Assumptions

- Intake lives in `src/progettare/engine/intake.py`. The spec names four
  packages (engine, survey, blueprint, interfaces) and no intake package;
  intake is the pipeline's first stage, so it belongs to the engine.
- Issue fetch goes through the `gh` CLI with an injectable command runner, so
  tests run offline and auth stays gh's problem.
- Acceptance criteria come from an "Acceptance:" or "Acceptance criteria:"
  line or heading in the issue body, followed by `-` bullets. The list is
  stable: order preserved, ids `c1` through `cN` assigned in order.
- Conflicting criteria are detected in code as: two criteria with identical
  normalized text, or two criteria naming the same setting (a `key: value` or
  `key = value` pair) with different values. Semantic conflicts beyond that
  are the human's call, reached through blocked.
- Clarifying questions are issue comments containing `Q:` or `Question:` lines.
  Answers are `A:` or `Answer:` lines in the same comment, or a later comment
  starting with `A:` or `Answer:`. An unanswered question means insufficient
  context: blocked, with the unanswered questions asked back to the human.
- The issue state is fetched fresh immediately before intake.json is written.
  A closed issue aborts the run, discards partial state, and writes nothing.
- intake.json carries `schema_version: 1`. Issue #6 owns the versioned output
  contract and #7 owns run-directory stamping; both can absorb this shape.
- Version is a static 0.1.0 until #9 adds release packaging.

## Tasks

- [x] 1. Repo wiring: repo.env.example, .gitignore entries, AGENTS.md house
  rules, .agents/test-commands.md, skills install with skills-lock.json, the
  .opencode symlink, bin/build, and the CI workflows. Proven by
  check-wiring passing and the CI workflow mirroring .agents/test-commands.md.
- [x] 2. Python scaffold: pyproject.toml, src/ layout with the four spec
  packages, uv.lock, a smoke test, strict mypy and ruff clean. Proven by
  `uv run pytest -q`, `uv run mypy src tests`, and `uv run ruff check src tests`.
- [x] 3. Issue reference parsing: URL and owner/repo#number forms to
  (owner, repo, number); invalid forms raise a typed error. Proven by a test
  asserting each accepted and rejected form.
- [x] 4. Issue fetch through gh with an injectable runner: returns a typed
  card context, and reports the issue state. Proven by a test with a fake
  runner, including the closed and completed states.
- [x] 5. Acceptance criteria parsing into a stable id-assigned list, with
  missing detection. Proven by tests for the bullet forms, order stability,
  and the missing case.
- [x] 6. Conflicting criteria detection (identical text, same setting with
  different values). Proven by tests for each conflict kind and a clean list.
- [x] 7. Clarifying question extraction from comments, with answers paired
  in order and unanswered questions surfaced. Proven by tests.
- [x] 8. intake.json writing (schema_version 1) and the blocked result with
  specific questions, plus the fresh-state abort that discards state and
  writes nothing. Proven by tests on a temporary run directory, including the
  abort case that removes a partial artifact.
- [x] 9. Minimal CLI entry point: `progettare intake <ref> --repo <path>`
  writing to the run directory. Proven by a test through the CLI entry point.
