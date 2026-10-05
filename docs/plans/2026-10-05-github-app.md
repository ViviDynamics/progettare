# Issue 15: GitHub App (M3)

## Problem
A GitHub App starts a progettare run when an issue is assigned or labeled
for it, and posts the blueprint artifacts where the card lives.

## Rulings
- The in-repo deliverable is `progettare/app.py`: trigger recognition,
  idempotent delivery handling, and comment rendering. Deployment, App
  registration, and the live wiring are app-specific stories filed under
  #34, #35, #36; the milestone #15 stays the delivery plan and remains
  open until those land.
- `should_trigger(event, action)`: an open issue, action assigned to the
  app's login or labeled with the trigger label. Login and label are
  configuration, not code.
- `DeliveryLedger`: one run per trigger event, keyed by the delivery GUID;
  the delivery is recorded BEFORE the run starts, so concurrent
  redeliveries dedupe. Restart persistence is story #34's business.
- `handle_event` returns a status document; the comment body carries a
  short lead, the blocked questions as a list, and the outcome document
  verbatim as the replay artifact in a fenced JSON block.
- Tests are offline: canned ceremonies, a recording comment poster, and
  ledger redelivery cases. No GitHub calls in tests.
