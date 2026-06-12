---
date: 2026-06-12
bead: polyglot-pdf-wnt
title: "Session resumption decision REVISED: adopt for unintentional disconnects only (cause-based split)"
tags: [doctrine]
---

## Trigger

Right after the wnt no-go shipped (PR #161), the maintainer reframed it: "If it's
an unintentional disconnect, I don't see a problem resuming the same session. If
it's one of our intentional session resets, the purpose is to CLEAR context, which
is only possible by restarting a new session, not resuming." That distinction is
sharper than the original evaluation and changes the recommendation, so wnt was
reopened.

## What shipped (the revised decision)

**Conditional GO: adopt `session_resumption` for the unintentional-disconnect path
ONLY; keep fresh-restart for intentional resets.** Updated
`context-compression.md` to replace the no-go with this.

Why the original no-go was wrong: it weighed resumption against `vmxx` as if they
solved the SAME event. They don't. The decision turns on the CAUSE of the
reconnect, which already maps onto two distinct code paths:

| Event | Initiator | WebSocket | Want context? | Tool |
|-------|-----------|-----------|---------------|------|
| Network drop / GoAway | client re-handshakes | closed -> new | YES, keep it | session_resumption |
| Section switch (form_filling_service `finalize` -> `start_session`, L622) | backend | stays open | NO, clear it | fresh session (current) |
| Idle-farewell `restart_gemini_session` (L400) | backend | stays open | NO | fresh session (current) |

The two paths are ALREADY separate code: intentional resets run SERVER-side (the WS
stays open), unintentional drops run CLIENT-side (the WS actually closed; the
frontend re-handshakes). So distinguishing them is structural, not a new
classification problem -- only the client re-handshake path would ever carry a
resumption handle.

Why this beats `vmxx` alone on the unintentional case: vmxx only SUPPRESSES the
re-greeting; the session genuinely lost its context, so vmxx papers over a real
loss. Resumption means there is nothing to paper over -- the same Gemini context
continues, so the reconnect is truly invisible. vmxx becomes the FALLBACK when no
valid handle exists (expired >2h, or first connect).

Design: capture `new_handle` from `LiveServerSessionResumptionUpdate`, store it
client-side (`sessionStorage`), pass it via `SessionResumptionConfig(handle=...)`
on the reconnect handshake only. Stateless invariant holds (handle is client-side;
backend stores nothing).

Open implementation edge (not a blocker, for the impl bead): an unintentional
reconnect carries BOTH a handle AND the client's current form-state handshake; if
the handle is stale relative to form state, prefer the fresh handshake as the
source of truth (the handle restores conversational continuity, not form state).
Also decide handle TTL/expiry fallback to vmxx.

This bead is the DECISION (conditional go). The implementation is a separate bead.

## Lessons

- **A correct evaluation can still be too COARSE.** The no-go's facts were all
  right (SDK surface, vmxx status, client-owns form state) but it collapsed two
  different events into one and judged resumption against the wrong alternative.
  The maintainer's cause-based split -- intentional (clear context) vs.
  unintentional (keep context) -- is the axis that resolves it. When a
  recommendation feels like "low value, don't bother," check whether it is actually
  "right tool for the wrong sub-case."

## Doc freshness

- Bumped with content: `docs/components/context-compression.md` (session-resumption
  decision rewritten to the cause-based conditional go).
- The prior wnt journal entry (`2026-06-12-bd-wnt-session-resumption-eval.md`,
  shipped in PR #161) is left intact as the chronological record of the original
  no-go; this entry supersedes its conclusion.

## Files touched

- `docs/components/context-compression.md` -- session-resumption section + stamp.
