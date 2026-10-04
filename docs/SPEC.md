# progettare specification

Status: design. Approved through discovery on 2026-10-04.

## 1. Goal

Progettare is a standalone technical-planning meta harness. Given an issue
and a repository, it produces one structured blueprint through a bounded,
read-only pipeline, decides the ceremony from the blueprint's size in code,
and hands each downstream reader exactly its own slice. It fills the
architect role for [conductor](https://github.com/ViviDynamics/conductor) and
[coordinare](https://github.com/ViviDynamics/coordinare), and works standalone
for any repository through its CLI and MCP server.

Every model call goes through [nare](https://github.com/ViviDynamics/nare),
the family rule. The harness is read-only end to end: it writes nothing to
the repository it surveys.

### Non-goals

- Progettare does not implement, review, QA, or document. It plans, sizes,
  and slices. Its only outputs are blueprint artifacts.
- Progettare does not commit to the repository, open PRs, or manage boards.
- The blueprint's structure is code-validated; its truthfulness is the
  model's responsibility, and the survey artifacts exist to audit it.

## 2. Architecture

Approach: a staged state machine in which the model proposes and code
executes.

Why this shape: conductor's live architect rounds failed in three ways, all
structural. The persona drifted into implementer work (55 tool calls, a
migration written), context grew until every call was slow, and two rounds
ran to the ceiling and were reaped with no plan committed. A free-form agent
session cannot bound itself. A fixed sequence of bounded stages, each with
its own nare session and budget, can.

### Repository layout

```
src/progettare/
  engine/      staged pipeline runner, budgets, stage validation
  survey/      question formulation, command caps, read-only nare runners
  blueprint/   schema validation, sizing, reader slicing (pure code)
  interfaces/  cli.py, mcp server (m2), app (m3)
```

### Stages

1. **Intake** (code only): fetch the issue's title, body, acceptance
   criteria, and any clarifying questions and answers; assemble card context;
   detect missing or conflicting criteria. If context is insufficient, return
   `blocked` with specific questions for the human, spending no model calls.
2. **Survey** (bounded model): code formulates survey questions from the
   acceptance criteria and the repository structure (tree, files touched by
   the criteria, entry points, test layout). Each question is answered by its
   own bounded read-only nare session; results are recorded as data, not as
   conversation history, so no stage pays for another stage's context.
3. **Blueprint** (bounded model): one nare session turns intake plus survey
   data into a single structured blueprint. The schema is enforced by code
   with one bounded re-ask on invalid output, then a loud failure.
4. **Size** (code only): classify complexity from the blueprint (single
   implementer turn vs milestone loop; documenter pass yes/no) and derive the
   per-reader slices.
5. **Report** (code only): write the three reader briefs as run-directory
   artifacts and emit a versioned JSON result on stdout.

### Milestones

- **M1 (MVP)**: CLI, the five-stage pipeline, blueprint schema, sizing,
  slicing, run artifacts, replay, config, failure paths
- **M2**: MCP server mirroring the CLI's versioned JSON contract;
  conductor/coordinare integration via a thin nare-adapter-style adapter
- **M3**: GitHub App watching for issues assigned or labeled to it, deployed
  to the garden cluster; threat-model discipline as in conductor

## 3. Config surface

```yaml
survey:
  max_questions: 12
  per_question_command_budget: 8
budgets:
  survey_stage_tokens: 150000
  blueprint_stage_tokens: 60000
  run_max_tokens: 300000
models:
  default:                 # per-stage overrides, like scrutare personas
    provider: anthropic
    model: <model>
  overrides:
    survey:
      provider: openai
      base_url: https://litellm.internal/v1
      model: <cheap-survey-model>
    blueprint:
      model: <best-reasoning-model>
size:
  single_turn_max_milestones: 2
  documenter_min_topics: 1
```

- The blueprint schema: milestones, data model, interfaces, risks, testable
  criteria, documentation topics. Structure is code-enforced.
- Budgets are per stage and per run, enforced by the engine. Survey-stage
  exhaustion marks the survey partial (missing data noted) and continues;
  blueprint-stage exhaustion fails the run.
- Model rails resolve per stage: a cheap model surveys, the best reasoning
  model blueprints, and either can be overridden.

## 4. Escalation and failure paths

- Blocked at intake: return `blocked` plus the specific questions, no model
  call spent.
- Stage output invalid after one re-ask: run fails, artifacts name the stage
  and the validation error. No partial blueprint is published.
- Budget exhausted: survey partial is survivable; blueprint exhaustion fails
  the run, since a partial blueprint is useless.
- Issue closes or merges mid-run: abort, discard, post nothing.
- Nare dependency policy: a capability nare lacks is filed as an issue on
  nare's repository, and the dependent progettare feature is marked blocked
  by it, in the issue body and on the board. The M1 needs are met by
  existing nare flags: `--system`, `--tools`, `--provider`, `--base-url`,
  `--model`, `--max-tokens`, `--session`, `--resume`, and the JSONL result
  line that carries usage. No silent workarounds.

## 5. Replay and audit

`progettare replay <dir>` recomputes size classification and the three
reader slices from the stored blueprint, in code alone, no model and no
network, and says whether they are byte-identical with the run's artifacts.
The survey artifacts exist so a blueprint's claims can be traced to what was
actually observed in the codebase.

## 6. Risks

1. Survey question quality: code-formulated questions can miss things. The
   blueprint stage may request exactly one bounded follow-up survey round.
2. Blueprint hallucination: schema enforces structure; the survey artifacts
   are the audit trail for the blueprint's claims.
3. Cost: per-stage budgets; a cheap model surveys and the best model
   blueprints, per config.
4. Scope drift: the pipeline is read-only end to end, so the worst failure is
   a bad blueprint at bounded cost.
5. Interface drift: the CLI's JSON output is a versioned contract, so
   conductor/coordinare adapters stay thin.
