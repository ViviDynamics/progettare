<p align="center">
  <img src="docs/brand/progettare-architect.png" width="240" alt="The Progettare architect, a silver-haired gentleman measuring a plan with a brass drafting compass">
</p>

# <img src="docs/brand/progettare-mark.svg" width="32" alt=""> progettare

A technical-planning agent harness: bounded survey, one blueprint, ceremony
decided by code.

progettare plans software work the way an architect does. Given an issue and
a repository, it runs a bounded, read-only pipeline: code assembles the card
context, bounded [nare](https://github.com/ViviDynamics/nare) sessions survey
the codebase against code-formulated questions, and one session turns that
data into a single structured blueprint: milestones, data model, interfaces,
risks, testable criteria, documentation topics. Code validates the blueprint,
decides the ceremony from its size (a single implementer turn or a milestone
loop; a documenter pass or none), and slices three briefs: exactly what the
implementer implements, what QA verifies, and what the documenter documents.

progettare commits nothing. The repository stays untouched; the blueprint and
its briefs live in run artifacts, version-stamped, and travel to readers as
data. This is the blueprint hand-off from conductor's spec 165, productized,
with the failure modes that motivated it designed out: no unbounded context,
no drift into implementer work, no run that reaps without a plan.

progettare sits beside [nare](https://github.com/ViviDynamics/nare),
[qare](https://github.com/ViviDynamics/qare),
[scrutare](https://github.com/ViviDynamics/scrutare), and
[coordinare](https://github.com/ViviDynamics/coordinare) in the Coordinare
project family: an orchestrator calls nare to develop, progettare to plan,
scrutare to review, and qare to QA.

## Install and plan an issue

With an installer-bearing release, run:

```sh
curl -fsSL https://github.com/ViviDynamics/progettare/releases/latest/download/install.sh | sh
```

The installer verifies the CLI and its private, release-matched Nare runtime. For
a reproducible install, replace `latest/download` with `download/<tag>`. To
configure your checkout and run your first blueprint, follow the
[first-run guide](docs/first-run.md) or give your coding agent this prompt:

> Set up Progettare in this checkout using
> https://github.com/ViviDynamics/progettare/blob/main/docs/first-run.md.
> Preserve existing configuration, ask for the open issue and any missing model
> settings, and keep credentials private. Run one blueprint and show me its
> milestones, acceptance criteria, and generated briefs.

## Design principles

- **Model proposes, code executes.** The model answers bounded questions and
  drafts the blueprint; code decides what is asked, validates what is
  produced, and derives every downstream artifact.
- **Bounded stages, no context accumulation.** Each stage is its own nare
  session with its own budget. Survey results are recorded as data, so no
  stage pays for another stage's history.
- **One output, three readers.** The blueprint is sliced by code into
  exactly what each reader needs, and nothing else.
- **No duplicated prose in the repository.** Nothing lands in the repo but
  the readers' own products.

## Triggering a run

Deployed as a GitHub App, progettare starts one ceremony run per trigger
event and posts the run's outcome as an issue comment where the card
lives. The supported trigger today is the `progettare` label on an open
issue: GitHub does not offer the app's bot account in any assignee picker
and rejects assigning it through the API, so triggering by direct
assignment is not supported (#50). A comment by an authorized reviewer
that addresses the bot starts a bounded revision round.

## Status

The released CLI runs the planning pipeline. The spec, including the staged pipeline, config reference, sizing
rules, escalation and failure paths, and milestones, is in
[docs/SPEC.md](docs/SPEC.md).

## Licensing

progettare is source-available under the [Elastic License 2.0](LICENSE), the
same license as the rest of the Coordinare family. You may run, modify, and
self-host it, including commercially. You may not offer it to third parties as
a hosted or managed service.
