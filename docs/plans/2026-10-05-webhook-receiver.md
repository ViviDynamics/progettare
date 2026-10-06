# Issue 35: register the App and wire the garden cluster webhook

## Problem
The app needs to receive deliveries: a webhook receiver that verifies the
signature, dedupes on the delivery GUID, dispatches into the trigger core
of #37, and posts comments back as `gh` calls. The org-side registration
and the live endpoint stay family operations; this story ships the
receiver they wire.

## Rulings
- `progettare serve-webhook`: a stdlib `http.server` speaking POST
  /webhook, no new dependency, the same install as the CLI.
- The signature is verified before any payload parsing: HMAC-SHA256 of
  the raw bytes against `PROGETTARE_WEBHOOK_SECRET`, compared in constant
  time; an unverified delivery is refused with 401 and never parsed.
- The delivery GUID comes from the `X-GitHub-Delivery` header and feeds
  the delivery ledger, so one event is one run even when GitHub retries.
- Login, trigger label, secret, and repo path are configuration: env vars
  `PROGETTARE_APP_LOGIN`, `PROGETTARE_TRIGGER_LABEL`,
  `PROGETTARE_WEBHOOK_SECRET`, `PROGETTARE_REPO_PATH`. Nothing app
  specific is code.
- The comment poster is the same seam shape #37 tests use, backed by
  `gh api repos/<full_name>/issues/<number>/comments` with the App's
  token; the ceremony is the MCP server's ceremony, so the run's blocked
  and complete semantics are the CLI's.
- The dispatch is a pure seam (`webhook_response`) so the tests verify
  signature refusal, dedupe, and the trigger path offline.
- The live registration and smee relay remain the family operations this
  issue names; the issue stays open until they land.
