# Spellback status + correction re-store probe (bd r3ham.23, r3ham.24)

**Date:** 2026-11-21. **Model:** `gemini-3.8-live` on Vertex, production config
(`--arm dti --continuous --compression --derive-compression --text-ai
--pro-pass`, `LIVE_TEMPERATURE=0.4`, `SPELLBACK_TOOL_ENABLED=true`).
**Harness:** sim user (Haiku 5.5 actor, gTTS, `--ears transcript`), persona
`w7_ana_selfcorrect` (every answer first slipped, then corrected),
`--max-user-turns 24`. **Cost:** $0.62 in all ($0.47 Gemini, $0.14 Cloud
STT, $0.003 actor).

**Data:** `scripts/spikes/data/sim_user/r3ham_probe/`, stamp
`20261121T193430Z`. Everything in it is a synthetic applicant.

## Why one short run

The maintainer asked for frugal validation. A W-7 asks the three name fields
first, and every spellback clip in the 2026-11-20 benchmark landed in a run's
first ~18 user turns. So 24 turns of the self-correcting persona cover:
- all the clips;
- the first numeric corrections (street number, ZIP);

at about a fifth of a full run's cost. It stopped by its turn cap (exit 5),
with 8 of 22 fields confirmed.

## Results

- **Spellback (r3ham.23): no regression from the bare-status `delivered`
  response.** There were 4 deliveries. Every spellback generation was silent
  (no audio, no other tool call), and the next generation went straight to the
  next question. There was no re-ask and no spoken tool text. 0 of 21 voiced
  generations diverged from their transcript (Cloud STT).
  - **Limit:** 4 deliveries cannot show the old 1-in-45 leak rate is now
    zero. The fix removes the speakable text by construction; this run
    checks only that nothing else broke.
- **Corrections (r3ham.24): 7 of 7 re-stored correctly**, 3 of them
  numeric:
  - street 480 -> 418;
  - ZIP 97747 -> 97477;
  - foreign street 20 -> 12.

  For every confirmed field, the value sent to `update_form_fields`, the value
  stored and the read-back audio agree. The new per-write log
  (`generations[].field_writes`) recorded each write.
- **The open case is long-session.** The I-90 phone-number failure of
  2026-11-20 came about 2000 s into the session, where the read-back audio
  repeated an earlier number. Checking it is deferred, with no dedicated spend,
  to the field-write log of the next I-90 run made for other reasons (follow-up
  bead under epic `polyglot-pdf-r3ham`).
