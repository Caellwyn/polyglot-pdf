---
date: 2026-06-12
bead: polyglot-pdf-9w5k
title: "Cloud Run 300s request timeout killed every WebSocket at 5 min (token-expiry hypothesis disproven)"
tags: [postmortem, hotfix]
---

## Trigger

Maintainer live-demo report (2026-06-11): after pausing mid-session and
resuming, the connection spiralled (connecting -> error -> reconnecting,
three hard "WebSocket connection failed" attempts) and Gemini stopped
responding. Filed as polyglot-pdf-9w5k with a token-expiry hypothesis.

## What shipped

The hypothesis was DISPROVEN by Cloud Run request logs: every `/ws/fill`
upgrade in the session shows latency exactly 301.00s -- the service runs
`timeoutSeconds: 300` (the Cloud Run default; neither deploy script set
`--timeout`), so Cloud Run force-kills every live WebSocket at the 5-minute
mark, all session long. The fresh-token-per-reconnect machinery from bd wq0
was already in place and working (zero rejected upgrades server-side); the
implementing agent's token-refresh edit was discarded as fixing a non-bug.
The three hard connection failures left no backend trace at all -- consistent
with client-side network suspension while the user was away, or edge routing
during instance idle; the 5-minute kill cycle is what set the failure up and
is also a major contributor to the reconnect re-greeting cadence (bd vmxx).

Fix: `--timeout=3600` (the Cloud Run maximum) baked into `deploy-all.sh` and
`backend/deploy-new.sh`. WebSocket lifetime is then bounded by Gemini Live
session limits, which the GoAway handling (bd c5t, PR #159) already manages.

NOT done here (maintainer-gated): the one-time config update to the LIVE
demo service (`gcloud run services update polyglot-backend --timeout=3600
--region us-central1`) -- it is deploy-equivalent and waits for an explicit
per-instance yes. Until it runs, the live demo still kills WS at 5 min.

## Lessons

When a connection bug reproduces on a fixed period, check the
infrastructure's request-duration limits before debugging auth or
application code -- `httpRequest.latency` in the Cloud Run logs answered in
one query what code reading could not. Also: a "completed" subagent whose
final message is mid-sentence did not finish -- audit its worktree before
trusting its edit.

## Doc freshness

docs/components/config-deployment.md: backend-deploy bullet updated with the
`--timeout=3600` flag + why it is load-bearing; stamp bumped to this entry.
Other docs flagged by the checker track files this branch did not change
(worktree-creation mtime noise); reviewed and left.

## Files touched

- deploy-all.sh -- `--timeout=3600` on the backend `gcloud run deploy`.
- backend/deploy-new.sh -- same flag on the standalone deploy path.
- docs/components/config-deployment.md -- deploy-flag doc update + stamp.
- docs/journal/entries/2026-06-12-bd-9w5k-cloudrun-ws-timeout.md -- this
  entry.
