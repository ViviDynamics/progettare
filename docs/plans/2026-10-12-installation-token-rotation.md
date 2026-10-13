# Issue 43: installation-token rotation for the App's gh subprocess

## Problem
The pod's `gh` subprocess authenticates with an installation token that
dies hourly; a human re-mints it today, and the ceremony 401s when it
lapses. The pod already holds the App's credentials (app-id and
private key arrive as env from the `progettare-app-credentials`
secret), so it can mint its own tokens and refresh them itself.

## Rulings
- New `progettare.auth.InstallationAuth`: mints an App JWT (RS256 over
  the App's private key), looks up the installation, POSTs for an
  access token, caches it, and lazily re-mints when the clock is inside
  a refresh margin. Thread-safe, one process.
- Zero new dependencies: the signer is `openssl dgst -sha256 -sign` via
  subprocess (the image ships it; the ceremony already shells out to
  `gh`), and the GitHub calls go over stdlib `urllib`. Both are seams;
  the tests inject fakes and never touch the network.
- The default refresh margin is five minutes against a one-hour token
  lifetime, so a ceremony started near the boundary still gets a live
  token.
- The wiring reads `PROGETTARE_APP_ID` and `PROGETTARE_APP_PRIVATE_KEY`
  (both already rendered by `deploy/deployment.yaml`) and, when present,
  hands the gh dispatch a `GH_TOKEN` from the auth; when absent, the
  receiver keeps inheriting the environment exactly as before.
- Least privilege is unchanged: the minted token carries only what the
  App carries (issues read/write).

## Acceptance
The receiver survives an hourly token rollover with no human action;
tests prove the lazy re-mint across an expiry boundary offline.
