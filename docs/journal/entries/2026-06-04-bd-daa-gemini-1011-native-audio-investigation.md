---
date: 2026-06-04
bead: polyglot-pdf-daa
title: "Gemini Live 1011 mid-turn failures: are we affected, and the standing mitigation"
tags: [postmortem]
---

## Trigger

`bd polyglot-pdf-daa` (P1 bug, filed 2026-05-30). A Google AI Developers Forum
report flagged that `gemini-2.5-flash-native-audio-preview-12-2025` returns
`code=1011` mid-turn at roughly an 80% rate starting 2026-05-27. The bead is a
**watch/investigate** item: determine whether polyglot-pdf is affected and, if
so, confirm a mitigation is applied and documented. This entry records the
investigation conclusion so the next reader does not have to re-derive it.

This is read-only investigation: every claim below was checked against the code
on 2026-06-04, not restated from the bead text.

## Conclusion (short version)

**By default we are NOT affected.** The bead was filed against an older config in
which `MODEL_NATIVE` resolved to the 2.5 native-audio stable alias. That is no
longer the default. As of `bd polyglot-pdf-4p0` / `4cm`, `backend/config.py`
defines two env-swappable tiers and **defaults to the 3.1 family**, which is the
reliable path:

| Tier | Model id | Default? |
|------|----------|----------|
| premium | `gemini-3.1-flash-live-preview` | **yes** (`USE_PREMIUM_MODEL=true`) |
| standard (cheaper opt-in) | `gemini-2.5-flash-native-audio-preview-12-2025` | no |

The standard tier is pinned to **exactly the model named in the forum report**.
So the residual exposure is narrow and entirely opt-in: a deployment is exposed
to the 1011 failures only if it sets `USE_PREMIUM_MODEL=false` (or pins
`MODEL_NATIVE` to the 2.5 preview string). The production default never touches
the broken model.

## Why this is already mitigated (and where the mitigation lives)

The bead's acceptance is "determined whether affected; if so, a mitigation (model
pin or cascade fallback) is applied and documented." All three are satisfied by
work that already landed:

1. **Applied.** The default is the reliable 3.1 model
   (`MODEL_NATIVE_PREMIUM`), so no redeploy or code change is needed to stay off
   the broken preview. Selection is env-swappable
   (`USE_PREMIUM_MODEL`, or an explicit `MODEL_NATIVE` pin that overrides the
   flag in `Settings._resolve_model`), so if 3.1 ever regressed, an operator
   could pin a known-good model with a single env change and a restart -- no
   image rebuild (`bd polyglot-pdf-9dq`).
2. **Documented.** The trade-off is captured in two current-state places:
   `backend/config.py` (the tier comments name the 1011 symptom and reference
   this bead) and `docs/standards/ai-models.md` ("Why 3.1 is the default").

So polyglot-pdf already carries the model-pin mitigation the bead asked for; the
gap this bead leaves open was the *documented determination*, which is this
entry.

## What the adapter does on a 1011 drop (and what it does not)

`backend/adapters/live_ai_gemini.py` catches `ConnectionClosed` (which a 1011
close surfaces as) in the receive loop, logs
`gemini_session_connection_closed`, and breaks. The outer session loop has
retry-with-backoff for transient name-resolution / socket errors, but
**intentional** shutdown suppresses retry. There is **no model-level fallback**:
nothing automatically switches a 1011-flapping 2.5 session over to 3.1 mid-flight.
That is acceptable given the default already avoids the broken model, but it
means a deployment that *opts into* the 2.5 tier and then hits the 1011 storm
gets a dropped session rather than a graceful degrade. Captured as a follow-up
(below), not built here, because it is hardening beyond this bead's "investigate
and document" scope and the default-3.1 mitigation already covers the common
case.

## Residual risk and follow-ups

- **Opt-in 2.5 exposure.** Anyone running `USE_PREMIUM_MODEL=false` for the
  cheaper text-out price is currently exposed to the 1011 failures. The price
  delta is small (text-out 4.50 vs 2.00 / 1M; audio in/out identical), so the
  cheaper tier is rarely worth that reliability cost while the preview is
  degraded. Filed: a follow-up to consider an optional automatic model fallback
  (2.5 -> 3.1) on repeated mid-turn 1011s.
- **This is a Google-side preview defect.** If Google fixes the 2.5 preview, the
  standard tier becomes usable again with no change on our side; if 3.1 ever
  regresses, the same env-swap mitigation pins a known-good model. Either way the
  selection knob, not code, is the lever.

## Outcome

Determination recorded: not affected by default; the 2.5 standard tier is the
named-broken model but is opt-in only; the model-pin mitigation is in place and
documented. `bd polyglot-pdf-daa` is resolved by this entry (no code change was
required -- the mitigation landed earlier under `4p0` / `4cm`). Hardening and
cleanup spun out as separate beads rather than folded in.
