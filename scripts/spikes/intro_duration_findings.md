# Intro+disclaimer script: measured TTS duration (sprint 20, bd polyglot-pdf-s1iex.1)

Date: 2026-08-13. Voice: `en-US-Chirp3-HD-Algieba`, `volume_gain_db=+4.0`
(the shipped spell-back encode), MP3, synthesized via
`backend.services.spellback_tts._synthesize_sync` -- the exact path the intro
route (bd `polyglot-pdf-s1iex.3`) will reuse. Script:
[`measure_intro_duration.py`](measure_intro_duration.py). Cloud TTS is not the
`google-genai` SDK, so the 2026-06-11 SDK-cutover staleness rule does not
apply to these numbers.

## Gates (experimentation skill)

**Prior-work audit:** no prior duration measurement of long-form TTS through
this path exists. Prior art reused rather than re-derived:
`measure_spellback_loudness.py` (synth + `soundfile` decode plumbing; proved
local ADC + Cloud TTS works on this machine, runs of 2026-08-10/11) and
`spellback_tts.py` (voice resolution three-rung ladder; Algieba gain +4.0 dB
measured, bd `9oejl`). The "~58-60s current English notice" baseline is the
maintainer's own measurement quoted in the sprint-20 plan; not re-measured.

**Cost estimate (pre-spend):** Chirp 3 HD ~USD 30 per 1M characters, no LLM
calls, no thinking-token exposure. Planned loop <=10 candidates x ~1.4KB =
~USD 0.42 ceiling. **Actual spend: ~11.9K chars across 9 synthesis calls =
~USD 0.36.** Under the few-dollars / ~50-call ask threshold; the sprint plan
itself pre-scoped this loop as "cents at most".

## Method

Candidate copy in `data/intro_en_v*.txt` (UTF-8 data files; placeholders
instantiated as `Form I-90` / `I Agree` for measurement -- the canonical
master keeps `[FORM NUMBER]` / `[AGREE LABEL]`). Each candidate synthesized
through the real path; duration measured from the decoded MP3
(`soundfile.read`, samples/rate). Per the maintainer directive, NO
word-count-to-duration extrapolation anywhere -- word counts below are
context, never the claim.

## Measurements

| Candidate | Words | UTF-8 bytes | Measured duration (s) | Verdict |
|---|---|---|---|---|
| v1 (maintainer draft, verbatim) | 269 | 1463 | 89.9 | in window by 0.1s -- NOT freezable |
| v2 (light trim) | 264 | 1430 | 84.9 | in window, high |
| v3 (deeper trim) | 252 | 1370 | **81.6, 81.6, 88.6** | in window; see variance |
| **v4 (freeze candidate)** | 243 | 1336 | **81.3, 78.8, 81.8** | **in window, all runs** |

Byte budget: English at this length is ~1.3KB of the 5000-byte
`synthesizeSpeech` input cap -- consistent with the plan's estimate that
3-byte/char scripts (Devanagari, Arabic) land ~3.5-4.5KB. Bead `.2`'s derived
byte-cap test remains necessary.

## Finding: run-to-run duration variance is ~9%, not "a few percent"

Chirp 3 HD is generative; `spellback_tts.py`'s loudness comment says output
"varies a few percent run to run". Measured at ~80s clip length, the swing is
bigger: identical v3 text measured 81.6, 81.6, then **88.6s** -- **+8.6%**
run to run. Two consequences, both acted on here:

1. **A single measurement at the window edge is meaningless.** v1's one 89.9s
   reading says nothing about its distribution; a re-synthesis plausibly
   crosses 90s. This is why the freeze candidate was re-centered rather than
   shipped at the edge.
2. **The freeze candidate carries margin for the draw.** v4 centers ~80.6s
   with worst observed 81.8s; even a +8.6% outlier draw (~85-89s) stays
   inside 60-90s. The runtime clip is synthesized once per
   `(language, form_number, script_hash)` cache key, so production ships ONE
   draw from this distribution -- the margin is what makes that draw safe.

## Freeze candidate (v4) -- pending maintainer/counsel sign-off

File: [`data/intro_en_v4.txt`](data/intro_en_v4.txt) (canonical master:
replace `Form I-90` -> `[FORM NUMBER]`, `I Agree` -> `[AGREE LABEL]`).
Evidence audio: [`data/intro_en_v4.mp3`](data/intro_en_v4.mp3) (81.3s run).

### Legal-element traceability matrix (v4 clauses)

| # | Element | v4 clause |
|---|---|---|
| 1 | Is an AI tool | "I'm an artificial intelligence -- a computer program, not a person." |
| 2 | Language + form data entry only | "I'll be helping you fill out your [FORM NUMBER] today" + "I can't tell you what to enter" |
| 3 | Not a lawyer | "I'm not a lawyer" |
| 4 | Not a certified translator | "I'm not a certified translator" |
| 5 | No legal / immigration / professional advice | "I can't give you legal or immigration advice" |
| 6 | Does not tell you how to answer | "But I can't tell you what to enter. Those answers are yours." |
| 7 | No lawyer-client relationship | "working with me doesn't make PolyGlot Forms your lawyer" |
| 8 | Output is a DRAFT | "What we make together is a draft." |
| 9 | Not a certified/official/sworn translation | shared with #4, per the plan's own matrix mapping |
| 10 | USCIS may require certified review + signature | "An office like USCIS may require a certified professional to review and sign your final form." |
| 11 | Advise professional check before submitting | "review it with a certified interpreter or legal professional before you submit" |
| 12 | AI makes mistakes | "I do make mistakes -- I can mishear a word, translate something wrongly, or miss something entirely" |
| 13 | Must check every answer on the English form | "Please check every answer on the English form" |
| 14 | User responsible for every answer | "It's your form, and you are responsible for what it says." |
| 15 | Company not responsible for AI errors | "we at PolyGlot Forms cannot be responsible for my mistakes" |

**Two items flagged for the sign-off ear/eye (not decidable by measurement):**

- **Element 9 rides on element 4** (the speaker is not a certified
  translator) exactly as the plan's draft matrix chose; the OLD text also
  said of the *document* "It is not a certified, official, or sworn
  translation." Counsel may want that stated of the output, not only the
  speaker -- one clause (~2s) if so.
- **Does Algieba read as male?** The plan's verification item (a
  masculine-grammar Sol in a feminine-reading voice is worse than either
  alone) needs a human ear on the attached MP3.

## Reproduce

    backend/.venv/Scripts/python.exe scripts/spikes/measure_intro_duration.py \
        scripts/spikes/data/intro_en_v4.txt

(from repo root; the venv lives in the MAIN checkout, the script resolves its
own repo root so it runs correctly from a worktree.)
