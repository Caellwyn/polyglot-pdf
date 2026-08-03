---
date: 2026-08-03
bead: polyglot-pdf-xp4q
title: "The field-1 opener skips silently on the live demo; ship the diagnostic before the fix"
tags: [voice, websocket, observability]
---

## Trigger

Blast-radius verification of the opener bug (bd `polyglot-pdf-xp4q`) ended at an
impasse that only instrumentation can break. Established, each independently:

- The field-1 opener -- the post-I-Agree `change_spoken_language` auto-send whose
  backend handler renders field-1's guidance into the initiating message (bd
  `j748`) -- works locally in EVERY configuration: dev server and production
  build, W-7 (2,019-char guidance) and i-90 (922-char), clean human-paced flow.
- On the DEPLOYED demo it skipped in 3/3 observed real-auth sessions (Cloud Run
  logs, 36h): disclaimer accepted, re-handshake occurred, then nothing. The
  model starts blind, invents field ids (`p2_checkbox2[5]`), and only recovers
  once `switch_to_field`/`confirm_field` responses hand it guidance -- which is
  why the demo LOOKS mostly functional.
- The deployed bundle contains the auto-send code (grepped the live JS), so it
  is not a stale build.
- Every LOCAL failure in the earlier investigation was self-inflicted harness
  state-surgery (`sessionStorage.removeItem` before I Agree ->
  `switchToFirstSection` bails silently on null state). That includes the run
  that spawned bd `oaiv`.

The discriminating variable is real Firebase auth vs the harness's mock-auth
boot -- and agents cannot run a real-auth session (credentials). The skipping
gate (`webFormConnection.handleSessionReady`) checked three conditions with no
else-branch and no logging, so production logs cannot say WHICH condition
fails. Diagnosis is stuck until a skip names itself.

## What shipped

Observability only -- deliberately NO behavior change and NO speculative fix
(re-ordering the state refresh ahead of the gate might fix it, but shipping a
blind fix alongside the diagnostic would leave the failing condition forever
unidentified if it worked, and muddy the diagnosis if it did not).

1. The gate now computes its three conditions explicitly and, when the opener
   was EXPECTED but skipped, emits one `console.warn` plus one new
   frontend->backend `client_diagnostic` message carrying the gate booleans
   (`was_section_switch`, `disclaimer_accepted`, `has_selected_language`,
   `has_next_field_hint`). "Expected" = a section-switch session_ready (the
   post-I-Agree path) or an accepted-disclaimer reconnect. The first connect of
   a session (no switch, not yet accepted) is the one legitimate skip and stays
   silent, so the diagnostic is signal, not noise.
2. A backend `client_diagnostic` arm logs a WHITELISTED warning -- named, coerced
   fields only; the payload is raw client input and nothing else may reach the
   log line (no-PII policy, same rule as the unknown-field-id redaction). One
   way, no ack.
3. `docs/standards/ws-protocol.md` gains the type row; the protocol contract
   tests (88) pass with the new type wired through all three sync points
   (backend arm, FE send site, doc table).

Deploy-skew: my first claim here -- "the old backend's unknown_control reply is
benign, the client tolerates it" -- was WRONG, and both independent Opus outer
reviewers refuted it with the same end-to-end trace: `handleServerError` treated
EVERY error reply as session-fatal (fail the in-flight switch, or fire onError
-> the overlay swaps to a dead Reconnect button), so on a frontend-first rollout
the diagnostic would have broken the exact flow it observes. Fixed by an
explicit early-out: `unknown_control` is the backend saying "I don't recognize
that message type", which is never session-fatal by definition; the client now
warns and continues. Pinned by a test that delivers the old backend's reply in
the worst window (mid-switch) and asserts the session survives.

## Verification

- FE: 4 new tests drive the production message path (real `session_ready`
  inbound, real `startSection` reconnect for the switch case): opener fires
  with no diagnostic; the live signature (post-switch, un-accepted state)
  emits exactly one diagnostic; accepted-but-no-hint emits one naming
  `has_next_field_hint=false`; first connect stays silent. Full FE suite 1187
  passed. The switch-case test initially failed by holding the OLD socket --
  `startSection` disconnects and re-handshakes, so `session_ready` must be
  delivered on the NEW socket, exactly like the real reconnect.
- BE: a functional TestClient test sends a POISONED payload (PII-shaped extra
  keys, oversized event token, non-bool values) through the real route:
  whitelist holds, values never reach the line, event token capped at 64,
  message is reply-less and the receive loop continues. Mutation-verified
  (removing the cap fails exactly this test).
- Live smoke on the real local stack: healthy clean flow post-change -- opener
  fired (2,312-char initiating message; grown from the overnight recital PRs)
  and ZERO diagnostics. No false positives end-to-end.

## What the outer reviews added

Beyond the skew fix, the two independent Opus passes reshaped the payload from
five booleans to seven plus a hardened event field:

- `is_form_complete` (Sonnet round): a completed form's reconnect has a
  correctly-empty hint -- without this flag it is byte-identical in the log to a
  broken opener.
- `storage_disclaimer_accepted`: the persisted flag alongside the in-memory one
  the gate read -- a divergence names the state-staleness hypothesis in one
  glance. Landing this exposed a subtlety worth recording: `handleSessionReady`
  itself PERSISTS `this.state` via its entry mutators (setSessionId/setJitMode/
  setContinuousSession), so a storage read at the diagnostic site can only echo
  the in-memory value back -- the capture must happen at handler ENTRY, before
  the handler's own writes. The divergence test failed against a same-site read
  and proved the point.
- `continuous_session`: `has_next_field_hint` is section-scoped in the
  deprecated non-continuous mode, so "no hint" at a section boundary is benign
  there; this flag says which reading applies.
- `event` is now a STRICT token allowlist backend-side (`field1_opener_skipped`,
  `section_switch_watchdog_timeout`, else the literal `invalid`): `str()` on a
  structured value would have rendered its CONTENT verbatim under any length
  cap -- the one hole in the whitelist, found by attacking it.
- A second emit site: the section-switch watchdog. A switch that never reaches
  `session_ready` produces zero opener diagnostics, which would read as "no
  bug"; the `section_switch_watchdog_timeout` token names that outcome.

## Next

Deploy to the demo (per-instance ask), then one real-auth session -- the
maintainer's 2-minute click-through -- makes the failing condition a
read-the-log question: `client_diagnostic` in Cloud Run names it, and the fix
follows evidence instead of speculation.
