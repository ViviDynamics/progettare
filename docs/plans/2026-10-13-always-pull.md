# Issue 51: restart always takes the newest image

## Problem
`deploy/deployment.yaml` runs `imagePullPolicy: IfNotPresent` on the
`latest` tag, so a rollout restart on a node that already cached
`latest` reuses the stale image — the token-rotation fix in PR 44 sat
unactivated behind exactly this trap.

## Rulings
- `imagePullPolicy: Always`: every pod start pulls the newest `latest`
  from the registry, so a restart is always enough to ship a merged
  main. The cost is a registry round-trip per pod start, which the
  one-replica, restart-rarely deployment can afford.
- No tag bump and no node-side work: the restart story stays a
  single command.

## Acceptance
The manifest says `Always`; a restart takes the newest image without
a tag change.
