# Plan: follow-up survey round (issue 12)

## The mechanism

The blueprint author, working from intake and survey artifacts, may find
a section starved of evidence. It answers with a follow-up request
instead of a blueprint: the same JSON object shape, but with a
`followup` key naming the section and the questions to ask, and no
section content. The orchestrator runs exactly one follow-up survey
round from that request, then the blueprint stage answers again with
both surveys in hand. A request on the second attempt is not honored:
the run fails naming the stage. One follow-up per run, enforced where
the second request would be honored, which is the strongest place to
refuse it.

## Changes

### 1. The blueprint schema and its code boundary (blueprint/stage.py)

- BLUEPRINT_SCHEMA gains the optional key `followup`: an object with
  required `section` (string) and `questions` (array of strings), no
  additional properties. The six section keys stop being required at
  the nare-schema level; `validate_blueprint` remains the code boundary
  that demands either a valid blueprint (all six sections) or a valid
  follow-up request (followup present, no section content, questions a
  non-empty list of non-empty strings, section one of the six), never
  both.
- A request naming more questions than `config.survey_max_questions`
  is invalid: same caps as the first round, enforced at the boundary.

### 2. The blueprint stage returns a third outcome (blueprint/stage.py)

- `BlueprintStageResult` gains `followup: FollowupRequest | None`
  (dataclass: section, questions, sessions, usage). A first-attempt
  follow-up request returns a result with `path is None` and
  `blueprint is None`, having written only the schema file; the budget
  ledger carries the session it ran.
- `run_blueprint_stage` gains a keyword `followup_round: bool = False`.
  On a follow-up round (the retry), a payload that asks for another
  round raises `BlueprintStageError`: "at most one follow-up per run".
  Budget exhaustion and the one re-ask behave exactly as before within
  each attempt.

### 3. The follow-up survey round (survey/questions.py, survey/stage.py)

- `plan_for_followup(ctx, request, config)` builds a SurveyPlan from
  the request: one question per requested question, numbered from 1,
  criterion `blueprint follow-up: {section}`, command budget per
  question identical to the first round, structure re-observed from the
  repository with the same read-only commands.
- `run_survey_stage` gains `round: int = 1`: the artifact is
  `survey.json` for round 1 and `survey2.json` for the follow-up;
  session files gain an `s2` marker (q1-s2-session.json) so the two
  rounds never collide in the run directory. The caps, allowlist, and
  budget accounting are the first round's, unchanged.

### 4. The orchestrator wires it (cli.py)

- After the blueprint stage returns a follow-up request, the
  orchestrator records the ledger under the stage name `followup`,
  calls the refresher, runs the follow-up round, and calls the
  blueprint stage again with the follow-up artifact as the survey,
  `followup_round=True`.
- The manifest's stage ledger lists `followup` when the round ran. A
  complete run's artifact set then contains survey2.json.
- `blueprint.json` gains `followup_round`: 0 when the run needed no
  follow-up, 1 when it did. `blueprint_record` stamps it;
  ARTIFACT_VERSION bumps, since the blueprint artifact's shape grew.

### 5. Tests (offline)

- Stage: a first-attempt follow-up request returns the request, writes
  no blueprint.json, carries the ledger; a followup payload alongside
  section content, an empty questions list, or an over-cap questions
  list is an invalid payload (re-ask path); a request on the follow-up
  round raises; budget exhaustion inside either attempt fails loudly.
- Questions: plan_for_followup numbers, caps, and traces its questions.
- Orchestrator: the full canned sequence survey, followup request,
  follow-up survey session, blueprint, produces a complete run whose
  blueprint.json records followup_round 1, whose manifest lists the
  followup ledger, and whose artifact set contains survey2.json; a
  second-request run fails naming the rule; a no-followup run records
  followup_round 0.

## Rulings

- The follow-up round draws its token budget from
  `budget_survey_stage_tokens` again, not from the run ceiling: the
  issue says the follow-up uses the same caps, and the run ceiling is
  an M2 concern.
- The follow-up request is a valid response, not an invalid one, so it
  does not consume the re-ask; the re-ask remains the correction of an
  unusable payload.
- The stage refuses the second request rather than the orchestrator
  second-guessing a payload: the refusal lives next to the parse.

## Sequencing

1. Schema, boundary, stage outcome, refusal (tests first).
2. plan_for_followup and the survey round parameter (tests first).
3. Orchestrator wiring, manifest ledger, record stamp (tests first).
4. Full gate, ship flow.
