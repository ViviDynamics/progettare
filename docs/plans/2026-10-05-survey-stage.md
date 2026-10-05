# Plan: issue 3, survey stage with bounded read-only nare sessions

Issue: M1: survey stage with bounded read-only nare sessions.
Branch: feat/tkt-3-survey-stage off main 43ccaf4 (which already ships intake
PR 16, config PR 17, and survey question formulation PR 18).

## Scope

Execute the survey stage: each formulated question is answered by its own
bounded nare session with read-only tools, results are recorded as data into
survey.json in the run directory, and survey-stage budget exhaustion marks the
survey partial with the missing data noted, and the stage continues.

## What already exists (shipped)

- survey/questions.py: SurveyPlan, SurveyQuestion (number, text, criterion,
  command_budget), formulate/plan_for. Question cap truncation already notes
  partial_reason.
- survey/commands.py: validate_session_command(s) over a read-only allowlist
  (cat, find, grep, head, ls, rg, tail, tree, wc, git subcommands).
- survey/artifact.py: SurveyAnswer (question, commands, findings),
  survey_record (validates budgets, allowlist, non-empty findings, one answer
  per question), write_survey (atomic, via engine.run.atomic_write_json).
- config.py: survey_max_questions, survey_per_question_command_budget,
  budget_survey_stage_tokens, survey_rail (provider, model, base_url).
- engine/run.py: create_run_dir, atomic_write_json, intake_payload pattern
  (artifact, artifact_version, progettare, written_at stamps).
- contract.py: ARTIFACT_VERSION = 1, PROGETTARE_VERSION.

## nare facts this plan relies on (from nare README, contract doc, and the
scrutare adapter precedent)

- `nare run [prompt]` prints typed JSONL on stdout, terminated by one
  `result` line carrying status, usage, and stop_reason. `--session PATH`
  writes the session; `--resume PATH` continues it (unused here: one fresh
  session per question).
- Read-only confinement: `--tools read --root DIR` offers only the read tool
  and confines it to DIR. `--tools none` is the no-tools form.
- The answer is data via `--schema FILE` (nare validates the subset: type,
  properties, required, items, enum, additionalProperties; one re-ask on
  violation, then stop_reason=schema_violation with no partial object).
- `--jsonl --contract 1` pins the stream contract. `--budget-tokens N` bounds
  one run's tokens. `--system`, `--provider`, `--model`, `--base-url` are the
  family adapter flags from the issue body.
- The CLI's only approval policy is approve_all behind --yes; there is no
  stdin-mediated approval, so a survey session runs no model-driven shell
  commands. Sessions get `--tools read --root <surveyed repo>`, matching the
  scrutare adapter precedent (`--tools read --root`).

## Rulings

1. Sessions are `--tools read --root <surveyed repo>`. The structured answer
   carries `commands` (the session's read trace as allowlisted command lines)
   and `findings`. artifact.py already refuses over-budget or non-allowlisted
   commands at recording time, so a fabricated or forbidden trace fails the
   stage loudly rather than shipping. Replayed reads (issue 10) audit the
   trace against the findings. Why: keeps the harness read-only end to end
   with the family adapter shape; there is no nare CLI seam to mediate bash.
   Cost if wrong: an answer-schema version bump.
2. Stage budget is a cumulative token ledger over sessions, seeded from
   budgets.survey_stage_tokens. Each session launches with
   --budget-tokens set to its fair share: remaining // questions_remaining,
   and unused share rolls forward. Why: one question can never starve the
   stage, and the math is deterministic and testable. Cost if wrong: a
   different share formula is a one-function change.
3. A session that does not produce a usable answer (stop_reason budget or
   schema_violation, or an unusable status) marks that question unanswered,
   contributes to partial_reason, and the stage continues. A missing nare
   executable or a contract refusal raises NareError (loud, typed): those are
   installation faults, not budget exhaustion.
4. survey.json is stamped like intake.json: the stage adds artifact,
   artifact_version, progettare, and written_at around survey_record's
   payload, keeping survey_record's own version key as the record version.

## Tasks

1. survey/nare.py, the adapter: NareUsage, NareResult (status, stop_reason,
   usage, output), NareRunner protocol, NareError, session_argv builder
   (family flags: --system, --tools, --provider, --base-url when set,
   --model, --jsonl, --contract 1, --schema, --budget-tokens, --session,
   --root, --yes), and nare_runner (subprocess, JSONL decode, final result
   line required). Injectable for offline tests.
2. survey/stage.py, one session: the nare-subset answer schema (commands,
   findings), the fixed survey system prompt, fair_share helper, and
   answer_one_question(plan, question, runner, config, run_dir, budget) ->
   SurveyAnswer | None plus the observed usage and stop reason.
3. survey/stage.py, the stage: run_survey_stage(plan, runner, config,
   run_dir) -> SurveyStageResult (record path, answers, usage, partial
   reason(s)): fair-share ledger across questions, unanswered questions
   noted, stamps added, artifact written via survey_record and write_survey.
   Export the new names from survey/__init__.py.

## Test strategy

Strict TDD, one commit per task, bin/build green before each commit. All
tests offline: the runner is a fake (no nare binary, no network). argv
assertions pin the family flags. JSONL streams are simulated lines ending in
a result line; missing result line, nonzero exit, and contract refusal are
NareError cases. Stage tests cover: full success, one question unanswered by
budget (partial, others still attempted or skipped per the ledger), stage
exhaustion mid-list (partial, remaining skipped, artifact still written),
over-budget or forbidden command in an answer (SurveyRecordError from
artifact.py, loud), and the exact stamped shape of survey.json.
