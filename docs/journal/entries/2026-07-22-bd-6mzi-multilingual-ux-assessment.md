---
date: 2026-07-22
bead: polyglot-pdf-6mzi
title: "feat(spikes): multilingual voice UX assessment -- es/zh/fr/hi/ru in-language sessions, 8 defect beads filed"
tags: [harness, testing]
---

## Trigger

Maintainer ask (2026-07-22, in-chat): assess the app's voice performance across
Spanish, Mandarin, French, Hindi, and Russian using the output-transcript
readout -- register (formal/academic/conversational), slips into other
languages, nonsense words, bad or inappropriate translations, and anything else
that would degrade UX for low-literacy, low-English-proficiency native
speakers. Gate-1 audit: the y25o language-hint probe explicitly deferred
behavioral quality ("that is a behavioral question for the voice-harness /
live testers"); the E6 Spanish stress arm tested Spanish USER audio against an
English-SPEAKING model (the harness hardcoded `send_initiating_message
("English", ...)`), so no prior work had ever run a fully in-language session.

## What shipped

- `measure_form_session_costs.py` gains `--spoken-language`: seeds
  `service._spoken_language` PRE-connect exactly as the production handshake
  does (so the y25o ASR bias and the ow1e option-label translation both fire),
  and passes it to `send_initiating_message`. Default stays English so the
  historical arms (incl. E6) measure unchanged. gTTS code mapping added
  (`zh -> zh-CN`); `meta` records `spoken_language`; the `--debug` artifact now
  also captures `greeting_model_said`/`greeting_model_heard` (the greeting is
  the richest register sample and previously fell outside every question
  window).
- `full_form_script.py` gains `_phrase_generic`: data-driven per-language
  persona phrasing loaded from the NEW UTF-8 fixture
  `scripts/spikes/fixtures/multilang_phrases.json` (zh/fr/hi/ru; native-script
  strings live in the JSON data file so the .py source stays ASCII-only per
  scar #6). Mirrors the E6 value-forward scheme; `_wrong_generic` always
  produces a real mutation (the plan builder aborts on degenerate wrong==say).
- Five live 14-question I-90 runs (Vertex, `gemini-live-2.5-flash-native-audio`,
  DTI continuous, text sidecar wired), ~$3.20 total, data committed under
  `scripts/spikes/data/costs_i90-full_2.5_dti_cont_happy_20260722T17*`.
- Findings doc: `scripts/spikes/multilingual_ux_findings.md` -- per-language
  register verdicts (fr excellent, es good, hi good, zh adequate, ru terse) and
  seven defect classes + one harness gap, each filed as a bead:
  polyglot-pdf-37le (English field labels leak into non-English speech +
  per-field secretary spam), r5m7 (zh name-block desync, 9/14 fill), djnk (hi
  invented field id + value, propagated over the user's real answer), s39z
  (Cyrillic spell-back defeats the 5roy name check), ww9y (short numerics:
  "apartamento 12" filled as "2"), nb2c (zh writes literal "N/A" where other
  languages leave empty), h1me (register + form-title localization
  uncontrolled), lo37 (harness: confirm fixtures are English in every
  language).
- Also observed: fill-language separation held in all five languages
  (休斯顿/ह्यूस्टन/Хьюстон all wrote "Houston"); no inappropriate output
  anywhere; Russian (deliberately unsupported -- not in SPOKEN_LANGUAGES)
  still converses fluently but with unbiased-ASR transcription chaos,
  empirically validating the ow1e code-backed-languages decision ahead of the
  ~90-language expansion (bd ryu6).

## Lessons

- The production spoken-language path has THREE coupled hooks (SI initiating
  message, ASR bias, option-label translation) all keyed off
  `service._spoken_language` seeded pre-connect -- a harness that sets any one
  of them without the others is not deploy-faithful.
- Cost-estimate anchor: a 14q DTI continuous slice is ~$0.52-0.73/run --
  ~2.5x the old E6 10q pilot arm the Gate-2 estimate was anchored on. Anchor
  on the same ARM, not just the same question count.
- The native-audio model fills from AUDIO, not from the input transcription --
  the ru run filled mostly correctly through garbage transcriptions. Input
  transcript chaos is still a defect signal (spelled names DID break), but
  transcription text is not the model's ground truth.

## Doc freshness

No tier-1/tier-2 docs track `scripts/spikes/*` (spike findings docs are the
record for experiments). No doc bumps required beyond the new findings doc.
The closeout freshness checker flagged ~15 stale docs (auth, context-
compression, hipaa-pii-policy, risk-rating, section-reset-deprecation, etc.),
all tracking backend/frontend files LAST TOUCHED 2026-07-12..17 by earlier
branches -- none of them files this branch changed. Left as-is per the
"stale before you, not yours to bump" rule; noting here as the record.

## Files touched

- `scripts/spikes/measure_form_session_costs.py` (spoken-language wire-up,
  gTTS map, greeting capture)
- `scripts/spikes/full_form_script.py` (`_phrase_generic` + fixture loader)
- `scripts/spikes/fixtures/multilang_phrases.json` (NEW)
- `scripts/spikes/fixtures/audio_cache/*.pcm` (new per-language utterances)
- `scripts/spikes/data/costs_i90-full_2.5_dti_cont_happy_20260722T17*` (5 runs)
- `scripts/spikes/multilingual_ux_findings.md` (NEW)
- `docs/journal/entries/2026-07-22-bd-6mzi-multilingual-ux-assessment.md`
  (this entry)
