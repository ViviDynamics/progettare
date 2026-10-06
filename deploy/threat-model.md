# Threat model: the progettare GitHub App on the garden cluster

The family's discipline, applied to this app. The note names every
secret, where it lives, and what each principal may do; anything the
manifests reference is defined here.

## Principals and least privilege

| Principal | May | May not |
| --- | --- | --- |
| the GitHub App | read issues, read/write issue comments | write code, write workflow files, read repository contents beyond the issue it plans |
| the pod | run the ceremony against one repo path | touch anything outside its namespace and volume |
| a webhook caller | POST delivery events | be trusted without the signature |

The App is registered with the issues permission only (read and write),
and no repository contents or workflows permission, so its token
physically cannot write code or workflow files even if the pod is
compromised. The pod has no Git push path at all: the ceremony reads the
checkout it is given and writes run artifacts to its own volume.

## Secrets and where they come from

| Secret object | Keys | Provisioned by |
| --- | --- | --- |
| `progettare-webhook` | `secret` | the family secret store, from the App's webhook settings |
| `progettare-app-credentials` | `app-id`, `private-key.pem` | the family secret store, from the App registration |

No key material lives in this repo; the manifests reference the secret
objects by name and the deployment story keeps the values out of Git.

## Trust boundaries

1. Garden cluster ingress to the pod: the service exposes the webhook
   route only. The webhook secret is verified before any payload parsing,
   so unauthenticated bytes never reach the ceremony dispatcher.
2. Pod to GitHub: issue reads, comment writes, and the ceremony's issue
   refresh go out as `gh` subprocesses with the App's token.
3. Pod to the filesystem: the only writable paths are the runs volume and
   `/tmp`; the root filesystem is read-only, so a compromised process
   cannot plant code that later merges.

## Failure and replay

One replica keeps the delivery ledger process-local; redeliveries while
the pod is up dedupe against it, and the Recreate strategy plus the runs
volume mean a replaced pod redoes nothing that wrote its artifacts. The
live end-to-end verification is story #36.

## What is out of scope here

Cluster admission policy, network policy between namespaces, and the
App's org-side registration (story #35) belong to the family's cluster
operations and are prerequisites for applying these manifests.
