# Plan your first issue

Install from the release command in the README. In the project checkout, run
`progettare --version` (use the printed absolute executable path if needed).
Have Git and the GitHub CLI available. Run `gh auth status` and confirm that
the authenticated account can read the open issue. A local blueprint run
reads the issue and checkout and writes artifacts beside the checkout.

If `progettare.yaml` already exists, use its settings. Otherwise create it
with the following starter values. Choose a model available to your provider
and supply its credential through your usual private environment or secret
manager. For OpenAI, the credential variable is `OPENAI_API_KEY`.

```yaml
survey:
  max_questions: 5
  per_question_command_budget: 4
budgets:
  survey_stage_tokens: 30000
  blueprint_stage_tokens: 15000
  run_max_tokens: 60000
models:
  default:
    provider: openai
    model: gpt-4.1
size:
  single_turn_max_milestones: 2
  documenter_min_topics: 1
```

For example, in a checkout where open issue 12 asks for a CSV export, run:

```sh
progettare blueprint --repo . --issue 12
```

Substitute an open issue from your own checkout. A completed run prints a JSON
object with `status: complete` and `run_dir`. Open `blueprint.json` there to
review the milestones and acceptance criteria, then inspect the role briefs
under `briefs/`. If the run is blocked, use the stage and reason printed on
stderr to resolve the missing input. The standalone CLI does not need a GitHub
App installation. See the [configuration reference](CONFIG.md) for separate
survey and blueprint model settings.
