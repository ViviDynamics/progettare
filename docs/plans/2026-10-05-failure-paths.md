# Plan: failure paths and stage validation (issue 11)

## Goal

Loud, named failures at every boundary: a run's result states complete,
blocked, and failed each carry the stage that stopped it and the reason;
a failed run never publishes a blueprint; an issue that closes mid-run
aborts the run, discards its state, and posts nothing.

## What is already there (verified against the merged code)

- The blueprint stage already honors "no publish without validation":
  `blueprint.json` is written only from a payload that passed
  `validate_blueprint`, invalid output earns exactly one funded re-ask,
  and the failure after that re-ask raises `BlueprintStageError`
  carrying the full validation error list, the session files, and the
  usage (src/progettare/blueprint/stage.py).
- `ensure_issue_open` exists in src/progettare/github.py and its
  docstring promises the engine calls it before each stage publishes,
  but nothing calls it. The promise is unfulfilled.
- `run_manifest` records `status` and `failing_stage`, but not the
  reason a stage stopped the run, so artifacts do not name the
  validation error today.

## Changes

### 1. The manifest names the reason

`run_manifest(config, status, written_at, stages, failing_stage=None,
failing_reason=None)`:

- `failing_reason` must be None exactly when the run is complete; a
  failed or blocked run carries a non-empty reason string.
- The payload gains `"failing_reason"`.
- `RUN_MANIFEST_VERSION` bumps to 2: the artifact's schema changed, and
  a consumer keying on version 1 should notice.

### 2. The orchestrator states the reason, not just the stage

In `run_blueprint` (src/progettare/cli.py):

- the blocked-intake manifest passes
  `failing_reason="; ".join(context.blocked_questions)`;
- every failure manifest passes `failing_reason=str(error)`;
- the survey stage's `partial_reasons` are honored again: a survey that
  came back partial blocks the run at survey, with the joined reasons
  as the manifest's reason, and no blueprint is published. The merged
  orchestrator dropped this branch; the unfunded-survey case must
  block again, not sail into the blueprint stage.

### 3. Issue closure mid-run aborts, discards, and posts nothing

- `run_blueprint` gains a `refresher` seam defaulting to
  `ensure_issue_open`, called before each of the survey, blueprint,
  size, and briefs stages, with the run's issue ref.
- When the refresher raises `IssueClosedError`, the orchestrator
  removes the run directory it created (`shutil.rmtree`), writes no
  manifest, and returns a failed outcome naming the stage the run was
  entering and a reason that says the issue closed mid-run. Nothing is
  posted: the harness is read-only, so discard is the whole story.
- The CLI maps that outcome to exit 1 with the reason on stderr, like
  every other failure.

### 4. Tests (offline, in tests/test_cli.py)

1. Blueprint payload invalid after its one re-ask: the runner replays
   two invalid sessions; the outcome is failed, `run.json` names
   blueprint and the validation error, and `blueprint.json` does not
   exist in the run directory.
2. Survey partial: the survey session comes back under budget with
   partial reasons; the outcome is blocked, `run.json` names survey
   with the joined reason, and `blueprint.json` does not exist.
3. Closure mid-run: the refresher stub raises on the first mid-run
   check; the run directory is gone after the call, the outcome is
   failed, and no manifest was written.
4. A blocked-intake run's manifest carries its reason (extends the
   existing blocked test's assertions).

## Rulings

- "Failed runs never publish a blueprint" means the blueprint artifact
  exists only in a run whose blueprint stage passed. A failure at size
  or briefs leaves the validated blueprint in place; the manifest names
  the later stage. Publishing is the blueprint stage's act, and it
  already refuses to publish anything unchecked.
- Closure abort is a failed run, not blocked: blocked means progettare
  can resume once a human answers; a closed issue is terminal.
- `ensure_issue_open` stays behind a seam so the offline tests inject
  it; the real one shells out to gh.

## Sequencing

1. Manifest reason + version bump (tests first).
2. Orchestrator: survey-blocked branch, failure reasons, closure abort
   with discard (tests first, one behavior per test).
3. Full gate, ship flow.
