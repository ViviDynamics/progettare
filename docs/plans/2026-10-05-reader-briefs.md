# Plan: M1 reader slicing and versioned JSON output contract (issue 6)

Claimed 2026-10-05 (claim: Jason733i, no prior holders). Base: main
e95fe78 (blueprint stage PR 22 and sizing stage PR 23 are merged). Pure
code slices the validated blueprint into exactly three reader briefs and
returns a versioned JSON result for orchestrators.

## Facts this plan builds on

- The blueprint stage (PR 22) publishes blueprint.json: six typed fields,
  code-enforced by ``validate_blueprint``; the sizing stage (PR 23) writes
  size.json with ``classification`` (implementer: single_turn or
  milestone_loop, documenter: boolean) and ``inputs``, stamped
  intake-style with CONFIG_VERSION.
- contract.py: the artifact schema version (ARTIFACT_VERSION) and the
  package version (PROGETTARE_VERSION) stamp every artifact; the file's
  docstring already names briefs/ as part of the run-artifact contract and
  pins the versioning rule: breaking changes bump the version, additive
  changes keep it.
- engine/run.py gives atomic_write_json; the survey, blueprint, and size
  stages give the loud ordering-fault style to mirror.

## Rulings (binding for the implementation)

1. The slicing is pure code over the validated blueprint shape: the
   implementer brief carries the milestones (title and criteria) and
   nothing else; the QA brief maps each entry of the blueprint's criteria
   array to a verification target (each criterion quoted verbatim, with
   its index); the documenter brief carries the documentation topics. No
   model, no network, no clock: written_at arrives from the caller.
2. Exactly three briefs when the sizing turned the documenter on;
   otherwise the documenter brief is absent, not empty. The returned JSON
   always states the documenter decision, so a consumer can tell a skipped
   pass from a missing file.
3. Briefs land in ``briefs/`` in the run directory and the stage returns
   the versioned JSON result: a typed, json-serializable result whose
   ``schema_version`` is ARTIFACT_VERSION, carrying the three brief
   payloads and the documenter decision. The schema-version field is the
   M2 stdout contract's version anchor: it goes out with the result, not
   only on the files.
4. Ordering faults are loud and named: a missing or unparseable
   blueprint.json or size.json, a blueprint that fails re-validation, or
   a size.json whose classification is not well-typed is a
   ``BriefsError`` naming the stage. The documenter boolean is read from
   size.json, never recomputed, so the two stages cannot disagree.
5. Files under briefs/ are written atomically and stamped like every
   artifact (artifact "brief", artifact_version 1, progettare,
   written_at), then the payload. No partial publication: the result is
   returned only after all files are written.

## Task

One task. ``src/progettare/briefs/briefs.py``: ``BriefsError``, the
typed brief payloads (ImplementerBrief, QaBrief, DocumenterBrief,
frozen dataclasses), ``slice_blueprint`` (pure), ``briefs_result``
(the versioned JSON result boundary), ``write_briefs`` (files plus
result), ``run_briefs_stage`` (reads blueprint.json and size.json,
loud ordering faults, emits briefs/ and returns the typed result).
Exports from ``src/progettare/briefs/__init__.py`` in the established
package style. Tests offline and pure.

## Test strategy

Offline, pure, no runner seam (the stage never imports nare). The three
slices from one blueprint fixture: implementer carries milestones only,
QA quotes each criterion verbatim with its index, documenter carries the
topics. The documenter-off path: two files, the result still names the
documenter decision. Loud faults: missing blueprint.json, missing
size.json, unparseable or non-object records, invalid blueprint, and a
size.json with a non-boolean documenter, each naming the stage with no
files written. The result JSON parses back with schema_version 1; the
files parse back stamped intake-style.
