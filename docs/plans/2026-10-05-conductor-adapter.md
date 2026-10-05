# Issue 14: conductor/coordinare adapter

## Problem
Conductor and coordinare dispatch the architect stage to progettare and
consume its JSON result. They need a thin mapping layer following the nare
conductor-adapter sketch pattern, not a second ceremony.

## Rulings
- `progettare/adapter.py`, two pure functions, no ceremony logic:
  - `card_to_input(card)`: the orchestrator's card context (repo, number,
    repo_path) becomes the intake input the ceremony takes: ref and
    repo_path. The card's text stays the issue's business; the adapter
    validates shape and refuses anything else.
  - `dispatch_payloads(briefs)`: the published briefs record (the
    versioned JSON contract) becomes one dispatch payload per milestone,
    embedding that milestone and the slices' criteria and topics, so a
    conductor hands one payload to one worker with no further mapping.
- Contract versioning does the compatibility work: a briefs record whose
  `artifact_version` is not the current one is refused loudly, naming both
  versions; payloads carry the versions they were cut with.
- Integration tests build the versioned briefs record document exactly as
  the ceremony publishes it and assert on payload shapes: no stage
  internals, no mocks of progettare's own functions.
