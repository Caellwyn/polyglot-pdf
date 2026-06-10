---
date: 2026-06-10
bead: polyglot-pdf-xroy
title: "Voice round-trip surface: orchestrated investigation + hardening bundle (xroy, nlfc, cwsy, kom1; files 95uy, ykvt)"
tags: [postmortem, performance, testing, harness]
---

## Trigger

The 2026-06-10 demo failures (investigated under the now-closed `irck`) kept
widening: Gemini going silent on field 2, a ~49s tool-call round trip, a
resize that killed the mic. The maintainer asked for a high-level
investigation of the whole voice round-trip / tool-call surface -- the app's
highest-priority, costliest failure surface -- with liberal subagent use, plus
fixes for whatever was already actionable.

## How the investigation ran

An orchestrator session fanned out nine subagents: two read-only deep-dives
(frontend status/audio path; backend session lifecycle + latency), a
docs/journal synthesis (full failure-mode catalog), a live voice-harness
reproduction against real Gemini, three fix implementations in isolated
worktrees, a re-run after a base mix-up (below), and a long-timeout
classification run for the new model-silence bug.

## Findings (the short version)

1. **The irck silent-mic gate is real and is now fixed (`xroy`).** All mic
   audio was gated on `status === 'connected'` in
   `frontend/src/shared/connection.ts` with no log, no buffer, no recovery --
   any stranded status (`switching_section`, `reconnecting`, `error`,
   `idle_timeout`) silently discarded the user's voice while Gemini audio kept
   playing. Worse, four arming sites had three different copies of the gate
   (one narrow, two absent). Fix: one shared `sendMicChunkToBackend` callback
   built on a pure `shouldSendMicChunk(status, socketOpen)` policy --
   `connected` always sends; `switching_section` sends while the socket is
   open (safe: the backend sets `drop_audio=True` during manual switches, and
   the AI-initiated switch path tears the old session down); everything else
   drops LOUDLY via a rate-limited warn. Every `setStatus` transition is now
   logged `old->new (reason)` at all 14 call sites, so the next stranded
   status is visible instead of invisible.

2. **Which transition stranded the demo's status is still unproven.** The
   live harness could not test it: harness audio injection bypasses the mic
   callback entirely (filed `ykvt` to add a real-path injection mode). In 3/3
   live runs the status stayed `connected` -- but the demo evidence (backend
   saw ZERO inbound frames for ~4 min) still firmly implicates the frontend
   send path for THAT hang. The new transition logging is the trap that will
   catch it on the next live occurrence.

3. **NEW P1, `95uy`: the native-audio model goes silent at the confirm step,
   3/3 reproducible on dev.** `update_form_fields` lands, Gemini speaks the
   verification question, the injected "yes" is received and transcribed
   (`in_trans=3`)... then NOTHING: no `confirm_field`, no audio, no
   `turn_complete` within 35s. This is a model/adapter-level failure, distinct
   from the frontend gate. Open question (classification run was still in
   flight at writing): terminal stall vs glacial latency -- the demo's 49s
   tool call suggests the model may answer eventually, beyond harness
   timeouts. Results land in the bead.

4. **`cwsy` reframed: restarts-per-field RULED OUT; the 49s is
   unattributable without instrumentation -- so instrumentation shipped.**
   Same-section advances do NOT restart Gemini (only `manual_section_switch`
   or the AI `switch_section` tool do); the demo's 3 sessions were initial
   connect + first-section switch + idle-timeout reconnect. The backend had
   zero timing checkpoints between user activity and tool-response send. Now
   it logs `timing_session_connect_ready`, `timing_sysinstruction_build`,
   `timing_activity_start/end`, `timing_tool_call_received` (with
   `since_activity_end_ms` -- the headline number), `timing_tool_callback_ms`,
   `timing_tool_response_sent`, `timing_coordinator_roundtrip`,
   `timing_section_switch_total`, plus an `audio_frames_dropped` counter in
   the session summary. No behavior change, no PII.

5. **`nlfc` fixed: the desktop<->mobile resize flip killed the mic.** The new
   overlay's `alreadyLive` early-return skipped `handleConnect()`, so
   `startRecording()` never re-armed after the old overlay's teardown. Both
   overlays now call a shared `rearmAudioCapture()` on the manager (double-arm
   guarded, PTT/mute re-synced, no reconnect, no re-disclaimer), with
   component regression tests.

## The wrong-base trap (process scar tissue)

Remote-container agent worktrees (`isolation: worktree`) branch from
**origin/main**, not the session's checked-out branch. origin/main is ~270
commits divergent from dev BOTH WAYS and its HEAD is unbootable (SyntaxError
in `backend/services/form_filling_service.py` ~L223, bad merge of bd `9dq`;
measured detail added to bead `m85` -- dev->main is NOT a fast-forward). Two
fixes and one harness run were silently built on that base before the
divergence was caught (the giveaway: a "pre-existing" 23-test failure
baseline that does not exist on dev). Everything was re-run on dev. Recorded
as a `bd remember` memory: every worktree subagent must first
`git fetch origin dev && git reset --hard origin/dev` and verify
`py_compile` passes.

## What shipped (this PR)

- `55d22af` backend timing checkpoints + audio-queue drop counter [`cwsy`]
- `8cb4027` mic re-arm on alreadyLive overlay remount [`nlfc`]
- `20b8e6a` widened mic send gate + drop logging + status-transition logging [`xroy`]
- `70a914d` all four mic arming sites unified on the shared gated callback [`xroy`]
- `65edd77` harness RUNBOOK/SKILL: 0ux marked fixed [`kom1`]

Verified on the assembled branch: frontend 264/264 vitest, tsc steady at the
22 pre-existing errors (bd `0tgc`), backend 266 passed / 2 skipped.

## Lessons

- The harness's injection bypass means the entire frontend mic send path --
  exactly where the demo died -- has NO automated coverage (`ykvt`). A test
  harness that skips the layer under suspicion produces confident-looking
  NOT-REPRODUCED verdicts that mean nothing for that layer.
- Multiple copies of a safety gate WILL drift; the bug was not the gate's
  policy but its duplication. Pure-function policy + one shared callback is
  the durable shape.
- "Model went silent" had at least three distinct mechanisms on this surface
  (frontend drop, model stall, receive-loop crash families fixed under wpw);
  symptom-level bug reports on this surface need the layer attributed before
  fixes are chosen -- which is what the new timing + transition logging buys.
