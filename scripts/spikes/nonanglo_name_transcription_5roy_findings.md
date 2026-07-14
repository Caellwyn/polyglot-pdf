# Non-Anglo name transcription -- mitigation shipped (bd polyglot-pdf-5roy)

**Date:** 2026-07-14. **Status:** MITIGATION SHIPPED (SI spell-first). The
maintainer chose the mitigation directly (2026-07-14), so no baseline probe was
run -- the fix ships on the maintainer's product call, not on a measured rate.
The Gate-1 audit + Gate-2 estimate below are retained as the record of what was
considered. No live-model API calls were made for this bead.

## Shipped mitigation (maintainer directive, 2026-07-14)

For any PERSON'S NAME field the model now, per the DTI + legacy SIs:

- **asks for the SPELLING as the PRIMARY ask** -- "How do you spell your <name>?"
  instead of "What is your <name>?" (the maintainer's exact direction: spelling
  is safer for uncommon spellings -- Johnson vs Johnsen vs Johanson);
- fills the exact spelling letter for letter;
- **verifies by reading the SPELLING back** ("N-G-U-Y-E-N, Nguyen -- did I get
  that right?"), not just saying the name;
- never fills a guessed spelling -- if the user only says the name, it asks them
  to spell it first.

Pinned by `test_dti_and_legacy_si_ask_names_by_spelling_and_verify_by_spelling`.

A related open question -- what to fill when the name's native script differs
from the form's fill language (e.g. a Latin name on a Mandarin form) -- is a
separate product/legal decision, filed as **bd polyglot-pdf-cfm3**.

---

## (Original scoping, retained) Gate-1 audit + Gate-2 estimate

## The problem

Stress-test E0 (epic 00pt, run costs_i90-full_..._20260714T054615Z): with natural
(unspelled) TTS pronunciation, the live model transcribed the Vietnamese persona's
names as Anglo defaults -- "Nguyen" -> "Smith", "Linh" -> "Lynn", "Thi" -> "T"
(3/10 name fields wrong; 10/10 correct once the script switched to spelling names
out). The invented "Smith" (not a homophone) is the dangerous mode: a
plausible-looking wrong legal name that survives a casual read-back. The user base
of an immigration product skews to exactly the names this fails on.

## Gate 1 -- prior-work audit (VERDICT: probe is necessary, extend don't write)

- No `scripts/spikes/*_findings.md` measures name transcription accuracy. The only
  transcription doc (`diag_input_transcription_fa4x.py`) measures whether
  `input_transcription` FIRES, not whether names are CORRECT.
- No journal entry, no `bd memories` result, no other bead covers name accuracy.
  polyglot-pdf-5roy is the only bead on the topic.
- No existing SI guidance about spelling back / confirming uncommon names. The DTI
  SI read-back is a generic "read the value back, ask 'Is that correct?'" -- a
  casual read-back the invented "Smith" survives.
- The right harness to EXTEND is the stress harness itself
  (`scripts/spikes/full_form_script.py` + `measure_form_session_costs.py`):
  name fields have NO `_SAY_OVERRIDES_EN` today, so they fall through to the
  generic "My {name} is {answer}" natural (unspelled) phrasing -- exactly the
  failing arm. `scenario_events.py` already has a `transcription` failure bucket.
- Post-cutover (all evidence dated 2026-07-13/14), so nothing is stale.

## Candidate mitigations (product decision needed on which)

1. **SI spell-back for name-type fields (cheapest to test).** Add SI guidance: for
   a name field, read the name back LETTER BY LETTER and confirm before filling.
   One-constant change to the DTI SI, cleanly A/B-able against the current casual
   read-back. A DRAFT of this is staged below.
2. **Form-kit flags name-type fields for spell-back.** The kit marks name fields
   so the UI/SI prompts the user to spell them. More targeted but touches the kit
   schema + renderer.
3. **Validator/copy_from name-consistency net.** The validator rail exists but has
   no name-consistency check today; adding one is a larger build.

These trade off UX friction (spelling every name aloud is slower/annoying for
common names) vs accuracy -- a product call, not a technical default.

## Gate 2 -- cost estimate (for the go-ahead)

- Probe = extend the existing live stress harness (Vertex, `2.5` live/native
  audio for the real failing surface; or the `TextAIGemini` text driver if a
  cheaper text-only proxy is acceptable -- to be decided with the arm).
- Sweep: baseline arm (unspelled names) + mitigation arm (SI spell-back), >=10
  trials each over the ~6-8 name fields on the i-90. Roughly 20-30 short
  sessions.
- Anchor: a full i-90 happy session is on the order of $1-3 in tokens (per-turn
  text-input SI dominates the measured cost invariant). A focused name-field
  probe is a fraction of a full session each.
- **Estimated total: ~$20-40.** This clears the experimentation skill's
  per-instance-ask threshold (>~$few or >50 live calls), so it needs an explicit
  maintainer yes before the run.

## Staged mitigation-1 draft (NOT yet applied -- pending the product decision)

Proposed DTI SI addition (to A/B as the mitigation arm):

> NAMES: When filling a person's name field, read it back LETTER BY LETTER
> ("N-G-U-Y-E-N, Nguyen -- is that right?") and confirm the spelling before you
> fill it. Do NOT assume a common Anglo spelling for an unfamiliar name; if you
> are unsure how it is spelled, ask the user to spell it.

Applying this depends on (a) the maintainer choosing mitigation 1, and (b) the
probe confirming it moves the wrong-name rate -- both gated below.

## What is blocked

Both 5roy exit criteria require the live probe: criterion 1 wants the baseline AND
mitigation wrong-name rates recorded; criterion 2 wants the chosen mitigation to
ship or a documented NO-GO. Neither can be satisfied without (a) a maintainer
decision on which mitigation to pursue and (b) approval for the ~$20-40 live-probe
spend.
