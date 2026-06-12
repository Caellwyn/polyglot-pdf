---
date: 2026-06-12
bead: polyglot-pdf-wnt
title: "Evaluate native Live API session_resumption: no-go (conditional), vmxx covers the user-visible need"
tags: [doctrine]
---

## Trigger

Epic l3a remaining work, after GoAway (c5t) shipped. `wnt` was deferred from the
nv0 design with a "likely no-go" pending a concrete need; the 2026-06-11 demo
report (mid-section reconnect re-greets) re-opened it. This entry is the
evaluation + recommendation -- a decision bead, no runtime code.

## What shipped (the decision)

**Recommendation: do NOT adopt native `session_resumption` now (no-go, with an
explicit re-open condition).** The deferred-decision doc
(`context-compression.md`) was updated to current state, and the parallel GoAway
deferral was marked DONE.

SDK surface, verified against google-genai 2.8.0:
- Config IN: opt in by SETTING `LiveConnectConfig.session_resumption` to a
  `types.SessionResumptionConfig(handle: Optional[str], transparent: Optional[bool])`
  at all (leaving the field None disables the feature). First connect uses
  `handle=None` (a fresh session that still emits update messages); reconnect passes
  the saved handle.
- Receive: `types.LiveServerSessionResumptionUpdate(new_handle, resumable,
  last_consumed_client_message_index)`; retain `new_handle`. The mechanism is real.

The two approaches solve different layers:
- **vmxx (shipped, code in tree, pending live verify)** -- prompt layer: an
  `is_reconnect` RESUME override tells Gemini not to re-greet. Fixes the
  user-visible complaint. Loses CONVERSATIONAL context (fresh session).
- **session_resumption (this bead)** -- protocol layer: resumes the same Gemini
  session, preserving conversational context.

Why no-go: this is a FORM-FILLER. The durable state is the FORM (field values +
confirmations), already lossless across reconnect via the client-owns-state design.
A vmxx reconnect loses only the last few spoken turns, which is low value for a
field-at-a-time flow (the next-field prompt re-establishes the FIELD context, even
if not any mid-utterance conversational state). session_resumption's real win
therefore does not move the needle, while it adds a 2h handle lifecycle to maintain
and a stale-handle failure mode.

The nv0 "adds server-correlated state" objection turned out weaker than assumed:
the handle can live CLIENT-side (sessionStorage) and pass back through the
stateless backend, so the stateless invariant would hold. The no-go rests on
LOW VALUE for this product, not on the stateless tension.

**Re-open condition:** adopt if live verification of vmxx shows suppress-greeting
is insufficient -- e.g. Gemini repeats an answered question, mis-tracks the current
field, or re-asks for confirmation after a reconnect. That is the "concrete need
where client rehydration is insufficient" nv0 named. The client-side-handle design
is the implementation path if so. Tracked against vmxx + the l3a.2 reconnect-policy
bead.

## Lessons

- **Re-evaluate a deferred decision against the SHIPPED state, not the original
  premise.** nv0's "no-go because it adds server state" was dissolved by the
  client-side-handle insight; the real reason to defer is now "low value given
  vmxx + client-owned form state." Same shape as the genai-2.8 re-test lesson:
  the old rationale outlived its facts.
- **A no-go is a deliverable.** Documenting the evaluation + an explicit re-open
  trigger (so the decision is tracked, not silently dropped) is the point of the
  bead -- not writing code.

## Doc freshness

- Bumped with content: `docs/components/context-compression.md` (the "Session
  resumption + GoAway" section: GoAway DONE, resumption evaluated -> no-go).
- Pre-existing staleness left untouched (PR #156-era; this docs-only branch did not
  change what they track).

## Files touched

- `docs/components/context-compression.md` -- session-resumption/GoAway section +
  stamp.
