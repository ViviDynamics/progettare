# Issue 34: garden cluster deployment with the family's threat-model discipline

## Problem
The app of #37 needs a deployment and a threat-model note, reviewable in
this repo, that the family can apply to the garden cluster.

## Rulings
- `deploy/` carries plain Kubernetes manifests: a namespace, a one-replica
  deployment (the delivery ledger is process-local, and restart-safe
  persistence is the ledger volume's job), a service, and a
  namespace-scoped persistent volume claim for run directories.
- Threat-model discipline, from the family's pattern:
  - the container runs as the image's non-root user (uid 10001), with no
    privilege escalation and a read-only root filesystem;
  - the App's private key and the webhook secret arrive as Kubernetes
    secrets referenced by name, never as files in this repo;
  - the App's GitHub token is least-privilege: issues read/write only, no
    contents, no workflows; the token cannot write code or workflow files;
  - the webhook secret is verified before any payload parsing (the
    receiver's job, wired in #35's story);
  - the run volume is scoped to the app's own namespace.
- The image is the release-published ghcr image; the deployment starts the
  webhook receiver, which #35's story wires to the live endpoint.
- No cluster secrets, keys, or tokens in this repo; the manifests name
  secret objects, and the note says where each value comes from.
