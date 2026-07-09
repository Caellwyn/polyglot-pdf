---
date: 2026-07-09
bead: polyglot-pdf-v3jd
title: "WS-G cost/architecture spikes: go/no-go synthesis -- all four resolved by shipped work"
tags: [voice-ai, cost, session-management, wpw]
---

## Trigger

Bead audit (2026-07-09). v3jd (WS-G) is the last open child of epic wpw (Harden
the core voice round-trip loop), which sat at 12/13 after the audit's other
closes. v3jd is an INVESTIGATE-ONLY bead: four cost/architecture spikes, each
"spike-first, go/no-go each; NOT committed deliverables ... each spike ends in a
go/no-go memo for the maintainer; no code PRs from this bead." This entry IS that
memo -- it synthesizes what shipped work (mostly under epic l3a and the
continuous-session cutover) already answers for each spike, so the bead closes on
its actual deliverable.

## The four spikes and their verdicts

All four questions the bead raised have been answered by work that shipped AFTER
v3jd was filed (2026-06-09). Verified against code on `dev` 2026-07-09.

### 1. Session resumption (avoid re-billing SI on reconnect) -- RESOLVED (no separate spike needed)

- Native `session_resumption` was evaluated under bd wnt and got a conditional
  no-go for our native-audio model family; the decision was documented, not coded
  as a `SessionResumptionConfig` handle (see the l3a.3 tracker note from this same
  audit -- the delivered reconnect behavior is handshake-rebuild + GoAway + vmxx
  silent-resume, not a native handle).
- The SI-rebill-on-reconnect COST concern is separately defused: `is_reconnect` /
  `RESUME_INITIATING_MESSAGE` suppress the re-greeting on resume (vmxx, shipped),
  and continuous-session mode removes per-section reconnects entirely (see #2).
- Verdict: NO-GO on a native-handle spike (model family does not support it
  usefully); the cost goal is met by other shipped levers.

### 2. Single-session section swap (no full restart) -- SHIPPED (spike overtaken by delivery)

- This is exactly what continuous-session mode delivered (bd x8rt): the whole form
  runs as ONE Gemini session, and `switch_section` is dropped from the tool set in
  continuous mode. Code: `backend/services/form_filling_service.py:199`
  (`declarations = [d for d in declarations if d.get("name") != "switch_section"]`)
  gated on continuous mode; `config.py:300-303` forces `USE_DTI` on when
  `CONTINUOUS_SESSION` is set. Live in the demo deploy
  (`deploy-demo.sh`: `USE_DTI=true,CONTINUOUS_SESSION=true`).
- Verdict: DONE. The "no full restart per section" architecture is the production
  default; no spike remains.

### 3. Mid-section context reset (cadence / acceptable re-ask rate) -- MOOTED

- Predicated on per-section session resets, which continuous-session removed. With
  one session for the whole form there is no mid-section reset cadence to tune.
- Verdict: MOOT under the shipped continuous-session architecture.

### 4. Proactive-audio idle-billing audit -- SHIPPED (defense landed)

- The walk-away cost hole (native-VAD streams continuous silence, so the WS idle
  watchdog never fired and a mic-open abandonment burned audio-input tokens until
  Gemini's 15-min cap) was fixed by bd l3a.4. The idle watchdog is now keyed to
  REAL user turns: the adapter surfaces `input_transcription` as an
  `on_user_activity` callback (text-less, PHI-safe) that only fires on a detected
  utterance, and the route watchdog bumps liveness on THAT, not on inbound audio
  frames. Code: `live_ai_gemini.py:2000-2004` (fire on non-empty
  `input_transcription`), `:636` (callback wired), `:1420-1430` (registration).
- The cost-vs-hallucination "proactive audio" flip is subsumed: idle sessions now
  close via the existing `idle_timeout` -> ConnectionTimeoutModal path instead of
  listening (and mis-hearing) indefinitely.
- Verdict: DONE. The idle-billing defense is in production.

### Bonus: the absorbed receive-loop DECOUPLE spike -- NO-GO (invariant-preserving)

v3jd also absorbed the receive-loop decouple spike (moved out of WS-B/0c1). The
bead's own note flagged the blocker: decoupling the serial `_bg_task` pump into a
per-event worker would break the invariant that `switch_section` can never
interleave with an in-flight synchronous confirm (WS-E2, shipped via wpw.2). With
the demo-critical loop now stable on the serial pump (WS-B/0c1, WS-E1/bxw keyed
slots, WS-E2 sync confirm all shipped) and continuous-session removing the
switch_section interleave case in production anyway, there is no live pressure to
take on that risk. Verdict: NO-GO for now; revisit only if a concrete
throughput/latency problem forces it (none observed).

## Outcome

All four WS-G spikes are resolved by shipped work; the receive-loop decouple is a
deliberate NO-GO. No code PR comes from v3jd (as chartered). Closing v3jd on this
memo completes epic wpw (all 13 children resolved).

## Scar tissue

- A "spike / investigate-only" bead's deliverable is the go/no-go memo, not code.
  When later work ships that answers the spike's questions, the honest close is to
  write the synthesis and cite the shipping beads -- not to leave the spike open
  forever waiting for a code PR it was chartered never to produce.
- Continuous-session mode (x8rt) is a load-bearing simplifier: it retired an entire
  cluster of session-management questions (per-section reconnect latency, restart
  cadence, mid-section reset, single-session swap) by making the whole form one
  session. Cross-ref the same-audit closes of jnjj.18-.21 (C-pillar).
