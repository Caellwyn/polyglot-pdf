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

### Legal-element traceability matrix (v4 clauses) -- SUPERSEDED

**This round-1 table maps the pre-amendment 15-element set onto v4, which was
never frozen. The authoritative matrix for the FROZEN master (v5) is in the
"FROZEN" section below.** Kept for the round-1 record only.

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

## Round 2 (2026-08-13, after maintainer edit + "robotic voice" report)

**The maintainer edited the candidate** (clarity pass; now
`data/intro_en_v5.txt`, verbatim -- the measured v4 text is restored in
`data/intro_en_v4.txt` as the round-1 audit artifact) and reported the round-1
MP3 sounded ROBOTIC for an HD voice, asking whether it was resampled.

### Voice-quality investigation (measured, not guessed)

- The audio WAS genuine `en-US-Chirp3-HD-Algieba` at its native **24,000 Hz**
  mono -- no downsampling anywhere.
- **Cloud TTS v1's default MP3 encode is 32.0 kbps** (measured from the
  artifact) -- bitrate-starved for a 24 kHz HD voice. This is also the encode
  the shipped spell-back clips use.
- **`MP3_64_KBPS` (v1beta1) is REJECTED by Chirp3-HD voices** (measured 400:
  "This voice currently only supports LINEAR16, MP3, OGG_OPUS, MULAW, ALAW").
- **OGG_OPUS also lands at ~33 kbps** -- there is NO higher-bitrate
  compressed output from Cloud TTS for this voice. The only high-fidelity
  output is LINEAR16 (384 kbps WAV, ~4.4 MB for this clip).
- **The shipped +4.0 dB Algieba gain CLIPS on long-form content**: the +4 dB
  WAV peaked at 1.000 (hard clip) and the +4 dB MP3 at 0.998, while a 0 dB
  WAV draw peaked 0.784. The +4 dB figure was measured on SHORT spell-back
  clips (peak 0.975, bd 9oejl) and does not transfer to ~90 s of speech --
  clipping distortion plausibly contributes to the "robotic" impression.
  The intro clip plays standalone (not mid-conversation), so it does not
  need the conversation-loudness match anyway: **bead .3 should pick its own
  gain (0 dB or server-side peak normalization), not inherit +4.**
- Chirp3 generates fresh audio per request, so peaks/durations differ
  slightly across draws; cross-arm ear comparisons should tolerate small
  draw-to-draw differences.

Ear-test files (same maintainer text, all at 0 dB): `intro_en_v5_gain0.wav`
(uncompressed reference), `intro_en_v5_gain0.mp3` (32 kbps, the shipped
encode), `intro_en_v5_gain0.ogg` (Opus ~33 kbps). Verdict tree: if the WAV
still sounds robotic, the VOICE is the ceiling (try another Chirp3 persona);
if only the MP3 does, the encode is the culprit -- ship options then are
(a) server-side transcode of LINEAR16 to a higher-bitrate format (new
encoder dependency), (b) serve WAV (~4.4 MB, cached + ETag), (c) OGG_OPUS
only if playback verifies on a real iOS Safari (historically no Ogg support
in HTMLAudioElement).

### Maintainer-edit measurements

| Candidate | Words | Measured duration (s) | Verdict vs 60-90 s |
|---|---|---|---|
| v5 (maintainer edit, verbatim) | 278 | 94.3 (+4 dB), 92.6, 92.6, 93.1 (0 dB arms) | **over, consistently** |
| v6 (v5 + elements 10 and 14 restored, "outloud" fixed) | 307 | 104.5 | **well over** |

### Matrix audit of the maintainer edit (v5)

- **Element 10 DROPPED** (USCIS may require certified review + signature).
- **Element 14 DROPPED** (user is responsible for every answer) -- partially
  replaced by the new agree-clause's "you agree to review", which is a
  different commitment.
- **NEW element added** (tracked as #16): an affirmative release -- "you
  agree to absolve PolyGlot Forms and their staff of all responsibility" --
  converting disclosure into agreement terms. Counsel-grade addition.
- Element 1 lost "not a person" but keeps "a computer program" -- intact.
- All other elements present. Nits staged in v6 only: "outloud" -> "out
  loud", "PolyGlot forms" -> "PolyGlot Forms". The 'talk' button reference is
  accurate for the default mode (PTT defaults ON; the desktop label is
  "Hold to Talk (or Spacebar)"; in the optional continuous mode there is no
  button).

Round-2 spend: 6 billed synthesis calls (~9 KB) = ~USD 0.27; cumulative
~USD 0.63.

### FROZEN (2026-08-13): maintainer sign-off received

Maintainer verdicts: **MP3 sounded better than the WAV** in the ear test --
the 32 kbps shipped encode stays (the codec is not the quality ceiling);
**"95 seconds is fine"** -- the window is 60-95 s and v5's measured
92.6-94.3 s passes; **elements 10 and 14 stay dropped, element 16 (the
release clause) stays added** -- a counsel pass is still pending and reviews
that delta. The frozen master (v5 + the two typographical fixes, placeholders
restored) is [`data/intro_en_master.txt`](data/intro_en_master.txt); its
frozen element set is 1-9, 11-13, 15, 16 (14 elements). Gain decision for the
intro route: 0 dB (the +4 dB spell-back gain clips long-form content, and the
standalone intro clip does not need the mid-conversation loudness match).
Decision log also in `docs/sprint_20_sol-intro-tts_plan.md` post-filing
section and on beads polyglot-pdf-s1iex / s1iex.1.

#### Authoritative traceability matrix -- the FROZEN element set on the frozen master

This is the counsel-review deliverable: 14 live elements (1-9, 11-13, 15, 16)
mapped to the frozen master's clauses, with the two maintainer-dropped
elements shown explicitly so counsel reviews the delta, not just the text.

| # | Element | Frozen-master clause |
|---|---|---|
| 1 | Is an AI tool | "I'm an artificial intelligence -- a computer program." |
| 2 | Language + form data entry only | "I'll be helping you fill out your [FORM NUMBER] today" + "I'll enter your response on the form" |
| 3 | Not a lawyer | "I'm not a lawyer" |
| 4 | Not a certified translator | "...or a certified translator." |
| 5 | No legal / immigration / professional advice | "I can't give you legal or immigration advice" |
| 6 | Does not tell you how to answer | "But I can't give you advice on what to enter or what to do." |
| 7 | No lawyer-client relationship | "working with me doesn't make me or PolyGlot Forms your lawyer" |
| 8 | Output is a DRAFT | "What we make together is a first draft of this document." |
| 9 | Not a certified/official/sworn translation | shared with #4 (the speaker is not a certified translator), per the plan's original mapping |
| 10 | **DROPPED** (USCIS may require certified review + signature) | removed by maintainer decision 2026-08-13; counsel pass pending reviews this drop |
| 11 | Advise professional check before submitting | "review it with a certified interpreter or legal professional before you file or submit" |
| 12 | AI makes mistakes | "I do make mistakes -- I can mishear a word, translate incorrectly, or just encounter an error." |
| 13 | Must check every answer on the English form | "Check every answer on the English form" |
| 14 | **DROPPED** (user responsible for every answer) | removed by maintainer decision 2026-08-13; partially succeeded by element 16's agree-to-review commitment; counsel pass pending reviews this drop |
| 15 | Company not responsible for AI errors | "PolyGlot Forms cannot be responsible for my mistakes." |
| 16 | **NEW** -- affirmative release as agreement terms | "By clicking \"[AGREE LABEL]\", you agree to review the completed document yourself and with a certified professional before filing, and you agree to absolve PolyGlot Forms and their staff of all responsibility for any mistakes or omissions." |

Every translation carries the same 14 live elements (verified by the
independent second-pass review, STATUS 0-ISSUES, recorded on bd s1iex.2).

#### Evidence audio for the frozen master

`data/intro_en_master.mp3` -- synthesized from the frozen master text itself
(placeholders instantiated as `Form I-90` / `I Agree`, i.e. the typo-fixed
text, byte-consistent with `intro_en_master.txt`), at the intro-route ship
config (0 dB, MP3). **Measured: 94.3 s, IN the amended 60-95 s window; peak
0.725 (no clipping at 0 dB on this draw -- consistent with the 0 dB gain
decision).** The earlier `intro_en_v5.mp3` (+4 dB, pre-typo-fix text) stays
as the round-2 historical artifact. This evidence run: 1 synthesis call,
~USD 0.05; cumulative ~USD 0.86.

## Round 3 (2026-08-13): 18-language store + non-English spot-checks

The frozen master + 17 translations landed in
`backend/services/intro_script.json` (bd s1iex.2), pinned by
`backend/tests/unit/test_intro_script.py` (language set DERIVED from
SPOKEN_LANGUAGE_BCP47; byte cap; placeholder/brand counts; 8-paragraph
structure; no-fullText shape). All six assertion families mutation-verified
red-then-green against six different languages.

Duration spot-checks through the real path at 0 dB (the intro-route gain),
placeholders instantiated (Form I-90 + the language's agree label):

| Language | Voice resolved (rung 1) | Bytes | Measured duration |
|---|---|---|---|
| German | `de-DE-Chirp3-HD-Algieba` | 1942 | **120.2 s** (+29% vs EN ~93s) |
| Hindi | `hi-IN-Chirp3-HD-Algieba` | 4068 | **113.5 s** (+22%) |

Both inside the plan's recorded +/-50% working assumption -- now MEASURED
for the two expected worst offenders, not assumed. German runs a full two
minutes; the maintainer accepted the assumption knowingly (no per-language
copy tuning planned). Hindi instantiated lands at 4068 of 5000 bytes --
the byte-cap margin is real but not generous; the derived test is what
keeps language growth honest. MP3-decoded peaks slightly above 1.0
(1.063) appear on these draws at 0 dB -- lossy-decode overshoot on hot
draws (the 0 dB RAW waveform measured 0.784 peak on English); distinct
from the +4 dB case where the raw waveform itself hit full scale.

Round-3 spend: 2 synthesis calls (~6 KB) = ~USD 0.18; cumulative ~USD 0.81.

## Reproduce

    backend/.venv/Scripts/python.exe scripts/spikes/measure_intro_duration.py \
        scripts/spikes/data/intro_en_v4.txt

(from repo root; the venv lives in the MAIN checkout, the script resolves its
own repo root so it runs correctly from a worktree.)
