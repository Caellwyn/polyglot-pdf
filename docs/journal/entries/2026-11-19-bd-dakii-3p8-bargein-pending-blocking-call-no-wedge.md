---
date: 2026-11-19
bead: polyglot-pdf-dakii
title: "fix(voice): 3.8 barge-in during a pending BLOCKING call does not wedge -- correct the r3ham.4 probe and pin the recovery"
tags: [testing, postmortem, harness]
---

## Trigger

bd polyglot-pdf-dakii (P1, under the 3.8 validation epic r3ham) said that on
gemini-3.8-live a push-to-talk barge-in while a BLOCKING tool call is still
pending wedges the whole session: no `tool_call_cancellation`, the barge never
transcribed, the late tool response unanswered, and the NEXT turn dead too. It
was 3 of 3, twice, in the r3ham.4 quirk re-tests
(`scripts/spikes/probe_bargein_blocking_3p8.py`). The maintainer held the next
staging deploy on it.

## What shipped

**The wedge was a probe bug, not a 3.8 bug.** google-genai 2.8.0
`AsyncSession.receive()` ends its iterator after EVERY `turn_complete`
(`live.py`: `if ...turn_complete: yield result; break`). The probe iterated it
once. On 3.8 a barge's `interrupted` and `turn_complete` arrive on ONE message,
so the probe stopped reading exactly there, and everything after it was
recorded as "lost" because it was never read. The control arm only ever has
one turn, which is why it looked healthy. The production adapter re-enters
`receive()` in a `while True` loop and never had this blind spot.

- **Probe fixed:** the reader re-enters `receive()` per turn. New `--late` arm
  answers the pending call N seconds after the barge starts, WHILE the barge
  audio is still streaming. That is the production timing, since the adapter
  answers the moment a slow callback returns. Also new: `--no-control` and
  usage events.
- **Re-run on Vertex (under $0.25):** both arms, 3 of 3 each, recovered:
  - the barge is transcribed;
  - a NEW `update_form_fields` call carries the corrected value;
  - the model reads back the corrected value;
  - the follow-up turn is answered with `confirm_field`.

  3.8 sends no `tool_call_cancellation`; the pending call stays open and takes
  its response. Data: `scripts/spikes/data/r3ham/dakii/`.
- **Field state:** the client applies call A's write and then call B's, so
  the last write is the corrected value the model reads back. Consistent.
- **Guard pinned:** `backend/tests/unit/test_bargein_pending_blocking_call.py`
  uses a fake session whose `receive()` reproduces the SDK's per-turn iterator.
  It asserts that the corrected call AND the next turn are dispatched and that
  every id is answered once. Mutation-verified: (1) the loop stops re-entering,
  and (2) the interrupt is treated as terminal (`continue` -> `return`). Each
  turns all 3 cases red; the adapter was restored byte-identical.
- No production code changed: nothing in the adapter needed fixing.

## Lessons

- **Suspect the probe's reader before the model.** `session.receive()` is
  per-TURN, not per-session. Any probe or harness that iterates it once goes
  deaf at the first `turn_complete`, and on 3.8 `interrupted` shares that
  message. The tell was a "dead" session whose only evidence was an absence of
  events after a `turn_complete`.
- A probe whose failure arm is the only arm with a second turn cannot
  distinguish "the model stopped" from "the reader stopped". Give the control
  arm a second turn as well.

## Doc freshness

- `docs/standards/ai-models.md`: the "known cost of BLOCKING: wedges the
  session" sentence was wrong; replaced with the measured 3.8 barge behavior.
- `docs/components/voice-ai.md` Barge-in: added the per-turn re-entry
  invariant and the 3.8 no-cancellation shape.
- `scripts/spikes/3p8_quirk_retest_findings.md`: verdict row and section
  corrected, with the probe-bug explanation.
- Prep flagged pre-existing staleness unrelated to this branch: admin-service,
  auth, config-deployment, jit-schema, pdf-filling and schema-forms docs track
  files this branch did not touch, and seven tier-2 docs carry stacked stamps.
  All were left as found. The stale in-progress bead h06sv (beads GCS cutover)
  is another workstream's.

## Files touched

- `backend/tests/unit/test_bargein_pending_blocking_call.py` (new)
- `scripts/spikes/probe_bargein_blocking_3p8.py`
- `scripts/spikes/data/r3ham/dakii/bargein_fixedpump_original_shape.json` (new)
- `scripts/spikes/data/r3ham/dakii/bargein_fixedpump_late1s.json` (new)
- `scripts/spikes/3p8_quirk_retest_findings.md`
- `docs/standards/ai-models.md`
- `docs/components/voice-ai.md`
