---
date: 2026-06-12
bead: polyglot-pdf-dlbr polyglot-pdf-pub polyglot-pdf-ppf1 polyglot-pdf-jkb5
title: "P3 cleanup bundle: dead branch removal, disclaimer reconnect guard, deploy-script nit, typeless-send already fixed"
sprint: 3
tags: [bugfix, chore, frontend, voice, deploy]
---

## Trigger

Backlog flush: four small P3 beads with no surface conflicts, bundled to avoid
one full PR cycle per trivial change.

## What shipped

### dlbr -- remove dead `request_next_field_hint` branch

`handleFormUpdated` in `webFormConnection.ts` read
`data.request_next_field_hint || false` (~L596) and had an 18-line if-block
(~L688-702) that would have sent a `next_field_hint_response` when that flag was
truthy. The backend never sets `request_next_field_hint` in `form_updated`
payloads -- hints flow via the separate `get_next_field_hint` message. Dead code
removed: the variable declaration and the if-block. `grep` confirms no remaining
references.

### ppf1 -- handleDisclaimerAgree reconnect fall-through guard

A medium-confidence hazard in both `VoiceOverlay.tsx` and
`VoiceOverlayMobile.tsx`: on the stale-connection branch of `handleDisclaimerAgree`,
`await handleConnect()` was trusted to signal failure by throwing. It does NOT --
on a connection timeout it calls `setError(...)` and **returns normally**, so
control fell through to the `if (connectionManager && selectedLanguage)` block and
called `switchToFirstSection()` on a dead WebSocket, producing an unhandled
`'Connection not initialized'` rejection.

Fix: after `await handleConnect()` on the reconnect branch, re-check
`connectionManager?.getStatus()`. If the status is not `'connected'` /
`'switching_section'`, call `setError(...)` and `return` before reaching
`switchToFirstSection`. Both overlays patched identically.

The successful-reconnect path is unchanged -- `reconnected = true` and
`switchToFirstSection` still fire when the status confirms success.

### jkb5 -- typeless WS send (already fixed, no code change)

Investigation found the bug was in `getHandshakePayload` (legacy path): before
commit `50b62ec` (bd vmxx/wq9y, PR #157, 2026-06-11) the return object had no
`type` field, causing the `[WebFormConnection] SUSPICIOUS: Sending message without
type!` console error at every initial connect. That commit added `type: 'handshake'`
to the legacy path as part of the resume-flag work. Bead closed as already-fixed;
no code change in this PR.

### pub -- deploy-production.sh `--all` arg-parsing nit

`deploy-production.sh` only checked `$1` for `--all` in the initial guard. The
`for arg in "$@"` loop only checked `--frontend`. So `--all` as a non-first
positional arg would not set `DEPLOY_RULES=true`. Cosmetically wrong (all real
invocations pass `--all` solo), but the intent was always "any arg == --all OR
--frontend sets the flag." Fixed: merged into a single loop that checks both
flags at every position. Syntax-verified with `bash -n`.

## Stale docs note

`check_doc_freshness` flagged eleven additional stale docs (auth.md,
context-compression.md, schema-forms.md, tool-call-flow.md, ai-models.md,
hipaa-pii-policy.md, logging-and-cost.md, risk-rating.md,
stateless-architecture.md, terminology.md, testing.md, technical_guide.md).
All track files whose mtimes on dev are from prior PRs (wpw.4, vmxx, uov.1,
etc.) -- none were touched by this branch's commits. These are pre-existing
staleness not caused by this bundle; the corresponding doc-update beads
(5df, rvz, b11, jh8, m3f, etc.) remain open in the backlog.

## Decisions

- **jkb5 closed without a code change.** The typeless send is already fixed by
  commit `50b62ec`. Investigated exhaustively (every `send({...})` call in
  `webFormConnection.ts` and `connection.ts`), confirmed via `git show` on the
  parent commit that `getHandshakePayload` lacked `type` before that fix.
  Closing as resolved-by-other-PR rather than adding a no-op change or leaving it
  open.
- **pub scoped to deploy-production.sh only.** `deploy-demo.sh` has a similar
  `$1`-only check but it is a different pattern and the bead explicitly called out
  only `deploy-production.sh`. Left alone per bead scope.
- **Doc stamps bumped for three docs**, not for pre-existing staleness. Only docs
  tracking files I actually changed (websocket-routing.md, voice-and-vad.md,
  config-deployment.md) received a bump. Pre-existing stale docs are tracked by
  open backlog beads.
