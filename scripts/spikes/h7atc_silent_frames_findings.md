# h7atc -- can we stop sending silent frames once auto-VAD is off?

**Status:** exit criterion 1 ANSWERED without spend. The premise the bead was
built on is **already false**: no silent frames are sent, from either side.
Criterion 2's "stop sending them" work is therefore **already done** (shipped by
bd `polyglot-pdf-v1m8g`), and what remains is a narrower, unmeasured question.

**Date:** 2026-09-03. **Spend so far: $0.00** -- no live API call was made.

---

## 1. The premise, and why it no longer holds

The bead states (quoting its own trace):

> PTT today already gates which bytes reach Gemini
> (`frontend/src/demo/VoiceOverlay.tsx:995` mutes input), but the comment at :997
> says "only silence is sent until button is pressed" -- i.e. **MUTED INPUT STILL
> SENDS FRAMES**, and silence is bytes.

That was true when the bead was written (2026-08-31). It stopped being true when
`polyglot-pdf-v1m8g` merged (PR #716, commit `538d6a91`), which removed BOTH
silence producers. The cited comment no longer exists.

### Client side -- withholds, does not substitute

`frontend/src/shared/audioManager.ts::shouldSendAudioChunk` collapsed from three
arms to one. Its own header records the change:

> ONE mode now: push-to-talk. Send only while the button is held. The two other
> arms are gone with the detectors they served -- **a native-VAD arm that always
> returned true (Gemini's own VAD needed a continuous stream, so a muted PTT sent
> silence rather than nothing)** and a client-Silero arm gated on `vadActive`.

The call site (`audioManager.ts:492`) `return`s early when the gate is false, so
an unheld PTT emits **nothing** -- not a silent frame.

### Backend side -- gap-fill is pinned off and unreachable

`backend/adapters/live_ai_gemini.py:1035` pins `_gapfill_enabled = False` as a
literal, deliberately not reading `AUDIO_GAPFILL_ENABLED`, "so the setting cannot
resurrect a path that is now always wrong". Both senders (`_run_paced_sender`,
`_run_legacy_sender`) gate their silence emission on that flag.

### Runtime confirmation (no network)

Drove `_audio_sender_loop` directly with a fake session: one real chunk, then a
**350 ms gap** (14x the 25 ms gap-fill interval), then the shutdown sentinel.

| Sender | frames sent | real | silent |
|---|---|---|---|
| paced (`AUDIO_PACING_ENABLED=true`, production) | 1 | 1 | **0** |
| legacy (pacing off) | 1 | 1 | **0** |

Adapter's own rollup agreed: `silence_frames_sent=0, total_chunks_sent=1`.

**Conclusion for criterion 1:** we already send no audio between turns. There is
no silent-token burn left to remove, so there is no saving to measure. The
hypothesis was right about the direction and wrong about the current state.

---

## 2. What the vendored SDK docs do and do not settle

Per CLAUDE.md, `docs/genai_docs/` is authoritative for this SDK (web search and
Context7 are unreliable for `google-genai`).

- `genai.live-docs.md:164-176` documents `send_realtime_input(...)` including
  `audio`, `audio_stream_end`, `activity_start`, `activity_end`. It describes
  what the parameters ARE. It does **not** state whether a session tolerates gaps
  in the audio stream.
- `live-api-best-practices.md:132-135` confirms our configuration is the
  supported one: "our path -- automatic activity detection DISABLED, with
  push-to-talk bracketing every turn in `activity_start`/`activity_end` (bd
  polyglot-pdf-v1m8g) -- remains **the only endpoint-verified approach**."

So the docs endorse the ARCHITECTURE but are silent on idle tolerance. That
silence is not evidence either way, and per this repo's hard-won rule
(`docs/genai_docs/README.md`) absence of a documented prohibition is not
permission.

---

## 3. The question that actually remains (and it is not the bead's)

The bead framed this as "can we stop sending silence, and what does that save?"
Both halves are settled: we already stopped, and the saving is already banked in
whatever v1m8g's config costs.

The real open question is the RISK side, and it is live TODAY on `dev`:

> **Does a Gemini Live session tolerate an arbitrarily long gap with no audio
> frames at all?**

We ship that behaviour now. If the answer is no, the failure mode is a session
that dies between turns -- exactly the 1011 class this repo has chased before.

### Why this is not merely theoretical

Historical gap-fill existed *because* a starved stream was believed to trigger
1011s (bd `polyglot-pdf-7f7m`). v1m8g removed it on the sound reasoning that the
starvation risk belonged to Gemini's own VAD, which is now disabled. That
reasoning was reviewed and is probably right -- but **it is reasoning, not
measurement**, and no live session has exercised it: `v1m8g` is merged to `dev`
and **has not been deployed** (`deploy-staging.sh` / `deploy-demo.sh` are manual
and were not run for it).

### What is NOT at risk (checked, so it need not be re-derived)

- **The WebSocket idle watchdog does not close on audio silence.** `last_rx`
  (`backend/routes/websocket_routes.py:38,64`) is bumped by CONTROL messages, and
  PTT brackets arrive as control messages. Verified during v1m8g's review.
- **Session duration** is bounded by context-window compression and GoAway
  handling, neither of which depends on the audio cadence.

So the residual risk is narrow: whether the GEMINI side objects to a silent
input stream, independent of our own liveness plumbing.

---

## 4. Recommendation: verify by DEPLOY, not by probe

A dedicated live probe would cost roughly:

| Item | Estimate |
|---|---|
| 1 session, ~5 min idle-with-gaps, native-audio Vertex | ~$0.05-0.15 |
| 3 arms (short gap / long gap / very long gap) x 2 runs | ~$0.30-0.90 |

Cheap -- but it would measure a **synthetic** idle pattern, and this repo has
been burned by probes whose config diverged from the deploy
(`live-probes-must-mirror-deploy-config`). A real staging session exercises the
exact shipped path for free, and v1m8g needs a staging deploy before the demo
regardless.

**Proposed:** fold this verification into v1m8g's staging deploy rather than
spending on a separate probe. Hold a PTT turn, wait out a deliberate 60-90 s
silence, then take another turn; confirm the second turn is answered and the
session did not drop. If it survives, criterion 2's risk is discharged by the
strongest available evidence -- the real thing. If it dies, we have a concrete
1011 to diagnose with the deploy logs to hand.

**Deploys are maintainer-gated** (explicit per-instance permission, CLAUDE.md
"Deployment / promotion"), so this is the maintainer's call, not an autonomous
step.

---

## 5. Answers to the bead's exit criteria

1. **"A documented, sourced answer on whether an idle (frame-free) stream is
   permitted with automatic activity detection disabled."**
   PARTIAL, and the question is narrower than it looked. The vendored SDK docs
   confirm our activity-bracketing path is the only endpoint-verified approach
   but do not address idle tolerance. **What is settled and sourced: we already
   send a frame-free idle stream in the shipped code** (section 1, with a runtime
   probe). Whether the endpoint tolerates it long-term is unproven, and is best
   answered by v1m8g's pending staging deploy rather than a synthetic probe.

2. **"If permitted: silent frames are no longer sent while PTT is unheld,
   sessions survive the gap, and the saving is measured."**
   First clause: **already true**, shipped by v1m8g -- no work needed, no saving
   to measure because the frames were removed as part of that change rather than
   as a separate optimisation. Second clause (sessions survive the gap) is the
   live check above and remains open.

**No API spend was incurred reaching these conclusions.**
