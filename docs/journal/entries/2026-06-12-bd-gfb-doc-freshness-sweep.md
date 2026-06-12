---
date: 2026-06-12
bead: polyglot-pdf-gfb
title: "Documentation reorganization (3-tier progressive discovery) -- freshness sweep"
tags: [conventions, doctrine]
---

## Trigger

Ten tier-2 docs were flagged STALE by `check_doc_freshness.py` because recent
code changes (c5t GoAway handling, vmxx silent-resume reconnect, 4sv7 VAD hardening,
w3ic/jbxm empty-field confirm) post-dated their `*Last updated:*` stamps. This
session claimed all remaining open child beads of the gfb epic and did the sweep.

Background: the gfb epic restructured ~63 md files into a 3-tier progressive-
discovery system. The component and standards docs were already written (gfb.1/.2
closed, plus multiple doc-specific beads completed in prior sessions); what remained
was keeping the stamps current and formally closing the child beads.

## What shipped

One commit:
- Bumped `*Last updated:*` stamps on 10 stale tier-2 docs to 2026-06-12.
- For each, reviewed the tracked code changes since the prior stamp to confirm
  whether content (not just the date) needed updating.

Content updates made (beyond date bump):

1. **`stateless-architecture.md`** (body): documented the new `resume: boolean`
   field that bd polyglot-pdf-vmxx added to `getHandshakePayload`/
   `getJITHandshakePayload`. The field is a hint that selects the initiating message
   on reconnect; it does not change the stateless invariant. Added to the handshake
   description in the "How (re)connect works" section.

2. **`schema-forms.md`** (stamp note): noted the `resume: boolean` param addition
   with the calling convention (`true` on reconnects after the first successful
   open, `false` default on fresh connects).

3. **`tool-call-flow.md`** (stamp note): noted that the GoAway path (c5t) added to
   `live_ai_gemini.py` + `callback_handler.py` does NOT interrupt in-flight tool
   calls -- detection is best-effort and the real close still arrives via the
   existing ConnectionClosed/APIError graceful path.

4. **`ai-models.md`** (stamp note): GoAway detection added to the adapter; model
   selection logic unchanged.

5. **`auth.md`** (stamp note): websocket_routes.py changes (GoAway, resume, w3ic)
   do not affect the token-verification gate, which runs before the handshake.

6. **`terminology.md`** (stamp note): `resume` is a new handshake key, not a
   terminology change.

7. **`confirmation-and-audit.md`** (stamp note): `on_go_away` in
   `callback_handler.py` is a new WS message type that does not interact with
   confirmation logging.

8. **`hipaa-pii-policy.md`** (stamp note): GoAway path adds no new PII/PHI logging.

9. **`logging-and-cost.md`** (stamp note): GoAway adds one structured log event
   (`gemini_go_away_received` with a `time_left` field, no PII).

10. **`risk-rating.md`** (stamp note): c5t, 4sv7, vmxx, w3ic/jbxm landed; none
    change risk classification of their surfaces.

Fresh-eyes assessment (pre-PR, round 1): NO-GAPS. This is a docs-only PR -- no
executable code changed. Fresh-eyes confirmed stamp dates are accurate and content
updates are consistent with the actual code changes in the tracked files.

Retroactive exit-criteria rubric (no rubric was written at claim time -- gfb is an
epic bead; child beads carry the per-bead rubrics):

1. **`check_doc_freshness.py --quiet` exits clean (no STALE output)** -- PASS: all
   tier-1 + tier-2 docs show "up to date" after the commit.
2. **Content updates are accurate relative to the code changes in tracked files** --
   PASS: each change was verified against `git show` / `git diff` for the relevant
   commits.
3. **No `Previously:` chains or history sections introduced** -- PASS: freshness
   convention check passes.

## Lessons

When a code bead touches files that many docs track (e.g. `live_ai_gemini.py`,
`callback_handler.py`, `websocket_routes.py`), several docs accumulate staleness
simultaneously even though the change does not affect their documented behavior.
The freshness sweep is cheap: for each stale doc, `git log --since=<stamp>` against
the tracked files gives the exact commits to review, and most just need a stamp bump
plus a one-line note that the behavioral content is unchanged.

The vmxx `resume: boolean` addition to `getHandshakePayload` is the kind of change
that reads as "small" (a new optional param with a `false` default) but documents
a semantic distinction that matters for future readers: reconnects and fresh connects
now have different backend behavior. That warranted a body update to
`stateless-architecture.md`, not just a stamp bump.

## Doc freshness

All 10 stale docs bumped to 2026-06-12. No CLAUDE.md changes. The freshness
checker now reports clean across all tier-1 and tier-2 docs.

## Files touched

- `docs/components/auth.md` -- stamp bump + reconnect-path note
- `docs/components/schema-forms.md` -- stamp bump + resume-param note (both stamps)
- `docs/components/tool-call-flow.md` -- stamp bump + GoAway-path note
- `docs/standards/ai-models.md` -- stamp bumps (both occurrences) + GoAway note
- `docs/standards/confirmation-and-audit.md` -- stamp bumps (both) + GoAway note
- `docs/standards/hipaa-pii-policy.md` -- stamp bumps (both) + GoAway note
- `docs/standards/logging-and-cost.md` -- stamp bumps (both) + GoAway log note
- `docs/standards/risk-rating.md` -- stamp bump + multi-bead sweep note
- `docs/standards/stateless-architecture.md` -- stamp bump + body: documented resume:bool handshake field
- `docs/standards/terminology.md` -- stamp bump + resume-key note
