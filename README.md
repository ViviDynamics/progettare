# progettare

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

## Status

Design. The spec, including the staged pipeline, config reference, sizing
rules, escalation and failure paths, and milestones, is in
[docs/SPEC.md](docs/SPEC.md).

## Licensing

progettare is source-available under the [Elastic License 2.0](LICENSE), the
same license as the rest of the Coordinare family. You may run, modify, and
self-host it, including commercially. You may not offer it to third parties as
a hosted or managed service.
