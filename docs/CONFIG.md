# Configuration reference

`progettare.yaml` is the single configuration surface for a run. It is read
and validated once, at startup: unknown keys, missing required values, and
type errors fail the run immediately, naming the offending key. A config
that survives startup is fully trusted for the rest of the run.

## Example

```yaml
survey:
  max_questions: 12
  per_question_command_budget: 8
budgets:
  survey_stage_tokens: 150000
  blueprint_stage_tokens: 60000
  run_max_tokens: 300000
models:
  default:
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

## Keys

Top level: exactly `survey`, `budgets`, `models`, `size`. Anything else is
rejected, and every section is a mapping; a section that is missing, or
present but not a mapping, is an error.

### `survey`

| Key | Type | Required | Meaning |
| --- | --- | --- | --- |
| `max_questions` | integer >= 1 | yes | The most questions the survey stage may ask. |
| `per_question_command_budget` | integer >= 1 | yes | Tool calls (reads and commands) one survey session may spend. |

### `budgets`

Token budgets, enforced by the engine per stage and per run.

| Key | Type | Required | Meaning |
| --- | --- | --- | --- |
| `survey_stage_tokens` | integer >= 1 | yes | Token budget for the whole survey stage. |
| `blueprint_stage_tokens` | integer >= 1 | yes | Token budget for the blueprint stage. |
| `run_max_tokens` | integer >= 1 | yes | Token budget across the entire run. |

### `models`

Model rails. Every stage resolves to one rail: the stage's entry under
`overrides` merged over `default`, else `default` when the stage has no
override. A partial override replaces only the keys it lists; unspecified
keys keep the `default` values.

`models.default` is required. `models.overrides` is optional; its keys are
exactly the stage names `survey` and `blueprint`, and any other name is an
error.

| Key | Type | Required | Meaning |
| --- | --- | --- | --- |
| `provider` | non-empty string | yes (in `default`) | The nare provider, e.g. `anthropic`. |
| `model` | non-empty string | yes (in `default`) | The model name passed to nare. |
| `base_url` | non-empty string | no | An alternate endpoint, e.g. a LiteLLM proxy. |

Within `models.overrides.<stage>`, `provider`, `model`, and `base_url` are
all optional; when present they replace the `default` value. Setting
`base_url` to an explicit `null` in an override is an explicit reset: the
stage calls through the provider's own endpoint even though `default` set
one. Inside `models.default`, `base_url` is optional (omitting it selects
the provider's own endpoint), but a value that is present must be a
non-empty string, so `base_url: null` there is rejected.

### `size`

Sizing thresholds the size stage applies to a blueprint.

| Key | Type | Required | Meaning |
| --- | --- | --- | --- |
| `single_turn_max_milestones` | integer >= 1 | yes | Milestones at or below this count can size as a single turn. |
| `documenter_min_topics` | integer >= 0 | yes | Minimum documentation topics the documenter slice expects. |

## Validation rules

- Unknown keys anywhere, including the top level and nested sections, are
  rejected with the full key path in the message.
- Required values missing are rejected with the full key path.
- Wrong types are rejected: integers must be integers (a YAML `true` is a
  boolean, not an integer), strings must be non-empty strings, and each
  section must be a mapping.
- An optional key written with an explicit null value, such as
  `base_url: null` inside `models.default`, is rejected like any other
  wrong type; in an override, `base_url: null` is an explicit reset.
- A mapping that repeats a key is rejected: safe YAML parsing would
  silently keep only one of the values, and a config that loses a budget
  to a typo must not pass.
- Numbers below their minimum are rejected; the minimum is 1 everywhere
  except `size.documenter_min_topics`, which may be 0.
- A file that does not exist, does not parse as YAML, is not valid UTF-8,
  or does not start with a mapping is rejected, naming the file.
