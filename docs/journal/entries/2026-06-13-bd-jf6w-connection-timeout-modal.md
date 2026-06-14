---
date: 2026-06-13
bead: polyglot-pdf-jf6w
title: "Connection-timeout modal -> session-restore: investigation + first three child beads"
tags: [feature, frontend, webFormConnection, voice, reconnect, i18n, epic-jf6w]
---

## Trigger

Maintainer asked whether epics jf6w (connection-timeout modal -> session-restore)
and l3a (Live API session management) had enough overlap to merge. Conclusion: no
-- jf6w is the product/UX layer that *consumes* l3a's reconnect primitives, at a
different altitude and maturity (l3a ~77% done and winding down; jf6w unscoped).
They were wired as `related` edges (jf6w -> vmxx, l3a.2, l3a.3) rather than
merged. The maintainer then approved running jf6w's investigation pass and
building the resulting child-bead breakdown.

## Investigation findings (jf6w first deliverable)

Three parallel readers swept the FE reconnect path, the backend handshake/resume
path, and the modal-translation surface. Headline: the session-restore *engine*
already exists and is on `dev`.

- Auto-reconnect with exponential backoff, full client state in `sessionStorage`,
  and a handshake that rebuilds Gemini context on every (re)connect are all
  shipped.
- **vmxx (silent resume) is functionally shipped** -- its code merged in PR #156
  (commit 50b62ec) under the banner bead wq9y, but the vmxx *bead* was never
  closed. Its only unmet acceptance clause is "verified live on the demo" (a
  maintainer/live-test gate). Recorded as a tracker-lag note on vmxx; not closed
  unilaterally.
- The real jf6w gap is narrow: a user-facing connection-timeout *modal* (new UI)
  that triggers the existing restore path.

57d (cloud-resume across devices) is a distinct future P3, correctly out of scope.

## What shipped (three child beads, one PR)

- **jf6w.1** (bd polyglot-pdf-18ff): `connectionTimeoutTranslations.ts` --
  `CONNECTION_TIMEOUT_TRANSLATIONS` (title/message/reconnect/cancel) for all 18
  `SPOKEN_LANGUAGES`, mirroring the DisclaimerModal inline-map house pattern (no
  i18n library) with English fallback. Non-English strings are a machine-generated
  first draft flagged for native-speaker review before user-facing ship; English
  is authoritative until then.
- **jf6w.3** (bd polyglot-pdf-g17r): a distinct terminal `reconnect_failed`
  `ConnectionStatus`, set in `handleClose` only when `reconnectAttempts` reaches
  `maxReconnectAttempts` on an unexpected drop. Separates "auto-recovery gave up"
  from the generic `disconnected` (which also covers intentional teardown), so the
  UI can surface the modal on genuine give-up and stay silent for transient blips.
  Propagates as-is through `connection.ts` `onStatusChange`; no mapping changes.
- **jf6w.2** (bd polyglot-pdf-s3n5): `ConnectionTimeoutModal` (+ CSS mirroring
  DisclaimerModal), rendered in **both** `VoiceOverlay` and `VoiceOverlayMobile`.
  Opens when `status === reconnect_failed` and not user-dismissed; the reconnect
  button re-runs the overlay's existing `handleConnect` restore path (vmxx
  silent-resume picks up the current field); a "not now" dismissal resets once the
  connection leaves the terminal state.

Tests: 7 modal component tests + 4 reconnect-failed status tests; full FE
typecheck + production build green; existing overlay/durability tests unaffected
(303 backend pass at closeout prep).

## Doc-freshness review (closeout)

`scripts/check_doc_freshness.py` flagged several docs. Triaged against this
branch's actual changes:

- **websocket-routing.md** -- UPDATED: added a "Terminal reconnect failure" section
  documenting `reconnect_failed` + the modal, and bumped the stamp. This doc tracks
  `webFormConnection.ts`, which this branch changed materially.
- **stateless-architecture.md** -- reviewed, NO content change needed. The modal +
  status are pure client-side UI; the stateless invariant and warm-reconnect
  description are unchanged. Flagged only because it tracks `webFormConnection.ts`.
- **voice-and-vad.md** -- reviewed, NO content change needed. `reconnect_failed` is
  not a VAD concern; `shouldSendMicChunk` already drops mic on any non-`connected`
  status, so the modal state is handled correctly with no doc change.
- **beads-remote-bootstrap.md, pdf-filling.md** -- pre-existing drift from files
  this branch did not touch (`bd_prime.py`, `pdfFiller.ts`); out of scope here.

Stale `hrn` bead (P1 harness-tuning, in_progress >1d) is unrelated to this PR and
left as-is.

## Why this shape

jf6w.1/.2/.3 are tightly coupled (copy -> modal -> trigger) and individually too
small to each warrant a full review cycle, so they bundle into one PR per the
bead/PR contract. The verbal-recovery path (`sendRecoveryPrompt`) stays
wired-but-inert per the epic's product decision (future accessibility feature),
not deleted.
