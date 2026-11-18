# gemini-3.8-live spelling read-back with the TTS clip OFF (bd polyglot-pdf-r3ham.3)

**Date:** 2026-11-17/18 (UTC).

**Model:** `gemini-3.8-live` on Vertex us-central1. The model id was checked in the raw dev log of all 12 runs.

**Question:** can the Cloud TTS `name_spellback` clip (bd 22h1f) be retired on 3.8? That would mean the model reads a spelled name back by itself, without the 2.5 defect where the audio repeats the session's first spelled name ("sticky first spelling", baseline 9.7% on 2.5, bd 0rpu).

**Decision rule, set in the epic plan:** recommend retiring the clip only if there are 0 errors with n>=24 scoreable read-backs per temperature arm, extended to n>=60. Retiring it is the maintainer's call.

**Spend for this phase:** $12.50 across 12 browser runs.

## Recommendation: do NOT retire the TTS clip

- **At the deployed temperature (0.4), the decision rule fails.** 2 of 15 scoreable spelled read-backs were the 2.5 sticky defect, now reproduced on 3.8. The text track said "J-O-H-N-S-O-N, Johnson" while the audio said "J-O-H-N, John". Both were full-length clips, so the driver did not cut them off.
- **At temperature 1.0, read-backs were clean (0 errors in 21), but the stored values were worse.** n=21 is below the n>=24 bar, so this is not a pass. In one 1.0 run the model stored `JOHNSN` for a spelled "J. O. H. N.", `JOHNSN` for "J. O. H. N. S. O. N." and `N/A` for "M. A. R. I. A.". Another 1.0 run stalled at the birth first name. Phase 2 stopped here (prune rule): at the deployed temperature the answer is already no, and moving to 1.0 is a separate maintainer decision that would bring worse input errors.
- **The clip protects against stored-value errors as well as read-back errors.** It speaks the STORED value letter by letter, so when the model writes the wrong letters (JOHNSN, JOSHUA for JOSE), the user hears exactly what went into the form and can say no.

## What "TTS off" means on today's system instruction

With `SPELLBACK_TOOL_ENABLED=false`, the shipped instruction says "Never spell a word out letter by letter aloud", and to verify a name "by saying the name back as a word ('Nguyen -- did I get that right?')". The model follows this exactly: in two runs it said "John, did I get that right?" and "Jose, did I get that right?".

That arm can therefore never show a spelling error. It also means the TTS-off rollback cannot let a user hear the difference between "Ana" and "Anna", or "Jon" and "John".

To answer the real question, a **local-only labelled arm** (`R3HAM_SPELL_ALOUD_ARM=true`, never committed) swapped three sentences of the shipped instruction for the spell-it-back wording used before bd 6a79:
1. "Never spell a word out letter by letter aloud; voicing a spelling is handled outside this conversation." became "When you read back a NAME or any letter-spelled value, spell the STORED value aloud letter by letter."
2. "Unless a later instruction gives you a different way to verify a name, say a name as a word;" became "Read a name back by SPELLING it letter by letter, then saying it;".
3. "...verify by saying the name back as a word ('Nguyen -- did I get that right?')." became "VERIFY by reading the SPELLING back, letter by letter ('N-G-U-Y-E-N, Nguyen -- did I get that right?')."

Everything else was the production config: v4 DTI SI, production tool declarations, compression on, push-to-talk, `SPELLBACK_TOOL_ENABLED=false`.

## Results

Source: `scripts/spikes/data/r3ham/spelling/readbacks_20261117.json`. It has one row per spelled step, with the stored value, the Cloud STT text of the read-back audio, and a hand classification (legend inside the file).

| Arm | Temp | Runs | Scoreable read-backs | Sticky | Added / dropped letters (read-back vs stored) | Stored-value errors |
|---|---|---|---|---|---|---|
| Shipped SI, TTS off | 0.4 | 2 | 0 (names said as words) | -- | -- | 1 of 12 (JOSE -> JOSHUA) |
| Spell-aloud arm, TTS off | **0.4** | 4 (1 stalled) | **15** | **2** (13%) | 0 | 2 of 18 (JOSE -> JOSHUA x2) |
| Spell-aloud arm, TTS off | 1.0 | 6 (1 stalled) | 21 | 0 | 0 | 5 of 33 (JOSE -> JOSHUA x2, JOHN -> JOHNSN, JOHNSON -> JOHNSN, MARIA -> N/A) |

**Rates with Wilson 95% intervals:**

| Rate | k / n | Rate | 95% interval |
|---|---|---|---|
| Sticky read-back, 3.8 at 0.4 | 2 / 15 | 13% | 3.7-37.9% |
| Sticky read-back, 3.8 at 1.0 | 0 / 21 | 0% | 0-15.5% |
| Sticky read-back, both 3.8 arms pooled | 2 / 36 | 5.6% | 1.5-18.1% |
| Read-back letter errors (added or dropped), all 3.8 arms | 0 / 36 | 0% | 0-9.6% |
| Stored-value errors, spell-aloud arm at 0.4 | 2 / 18 | 11% | 3.1-32.8% |
| Stored-value errors, spell-aloud arm at 1.0 | 5 / 33 | 15% | 6.7-30.9% |
| Stored-value errors, every 3.8 spelled fill (bd r3ham.15) | 8 / 63 | 13% | 6.6-23.1% |

- **The 2.5 baseline** for the sticky defect is 9.7%, from the bd 0rpu control arm with corrected pairing (`0rpu_desync_attribution_findings.md`).
- Every 3.8 sticky-read-back interval above overlaps it. At this n, the evidence is that 3.8 has NOT removed the defect, not that it is worse.
- The decision rule needs 0 errors, and the 0.4 arm already has 2.

- **Scoreable** means the read-back audio carried the whole spelling, and the class is OK or STICKY. Read-backs the scripted "yes" cut off are excluded; see "Instrument limits" below.
- **Sticky** means the audio spells an earlier name of the session while the text track is correct. This is the same signature as 2.5, and both cases spoke JOHN for JOHNSON.
- **No added or dropped letters were found in the read-back audio.** Every OK read-back spelled what was stored. The letter errors developers report on 3.8 showed up in the stored values instead: `JOHNSN` for JOHN and for JOHNSON.
- **JOSE -> JOSHUA has a fixture caveat.** Cloud STT on `spell_jose.wav` returns "josc" (0.53) ahead of "j o s e" (0.42), so the clip is weak, though nothing suggests it sounds like JOSHUA. The JOHN, JOHNSON and MARIA clips recognize cleanly. In every JOSE -> JOSHUA case the model then read JOSHUA back faithfully, so a real user would have heard the error.
- **Stalls.** In pilot 3 (0.4), the model asked the user to spell "your first name, Johnson" (the previous field's surname) and never filled JOHN. In run 6 (1.0), it never filled the birth first name.

## Instrument limits (read before re-running)

- **Pacing.** 3.8 calls `update_form_fields` FIRST and speaks the read-back AFTER. Fixed-sleep pacing therefore says "yes" over every read-back: in pilot 1, all 16 dumped clips were question prompts. The driver's new `VFF_PACING=readback` waits for the model to start speaking. It then waits for a turn_complete that arrives after that. That is still imperfect: 3.8 sends turn_complete for the tool-call turn early, and the slow, paused spelling drains the playback backlog. As a result, 14 of the 53 spelled steps in the spell-aloud runs were still cut off by the scripted "yes" and are excluded. Another 3 had nothing to spell (never filled, or `N/A`), which leaves 36 scoreable. The driver change is committed in this PR; a turn-aware fix is the next step if this arm is re-run.
- **Pairing.** `stt_readback_diff2.py` compares the model's audio to its own transcript. On 3.8 the transcript arrives bundled with audio and its seq window straddles generations, so it mislabels clean read-backs. `spell_readback_truth_score.py` (new) instead pairs each spelled step with the clip dumped between fill and "yes", and compares that to the scripted truth and the stored value. Its automatic letter extraction misses Cloud STT's run-together renderings ("J Oshua"), so the final classes are by hand.
- **The scripted user always says yes.** The harness therefore cannot measure whether a user would catch a wrong read-back.

## Related

- **"Anna" in the Phase 1 smoke test was a fixture defect** (bd r3ham.14). gTTS pronounced "A N A" as the word Ana/Anna. The W-7 script now says "spelled A - N - A", and W-7 has a strict answer key.
- **Defects filed or updated from this phase:**
  - r3ham.3 itself: the decision recorded here.
  - j9jpk: harness-timing caveat on cut-offs.
  - bd r3ham.15: 3.8 stored-value letter errors, 8 of 63 spelled fills.
