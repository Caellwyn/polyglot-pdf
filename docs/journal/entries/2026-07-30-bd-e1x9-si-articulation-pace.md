---
date: 2026-07-30
bead: polyglot-pdf-e1x9
title: "Slurred, rushed speech is an SI gap: articulation was never instructed, only pace"
tags: [conventions, testing]
---

## Trigger

The maintainer reported the voice model "slurs or mispronounces words too
often" and brought research (from Gemini) proposing four fixes: audio-delivery
rules, filler/slang suppression, TTS-style performance tags, and an explicit
voice + `language_code` binding.

Three of the four turned out to be already-done, inapplicable, or deferred. The
one real gap was narrow and unglamorous: **the SI told the model how FAST to
speak but never how CLEARLY to speak.**

## What was already there

`DTI_SYSTEM_INSTRUCTION` (the production path -- `USE_DTI=true` by default)
already carried a `SPEECH STYLE` block covering:

- pace ("Speak SLOWLY and calmly in every language"), and
- per-character read-back of digits and spelled names ("N ... G ... U ... Y ...").

It said nothing about articulation -- consonants, word endings, slurring,
swallowed syllables, or clause pauses. The legacy `SYSTEM_INSTRUCTION` had
neither pace nor articulation in its `REGISTER` block.

So the fix EXTENDS `SPEECH STYLE` rather than adding a competing
`AUDIO DELIVERY RULES` section. A second block restating pace would have put two
pace instructions in one prompt -- the failure mode the existing block already
covered.

## What the four proposals actually resolved to

| Proposal | Verdict |
|---|---|
| Audio-delivery / articulation rules | **The real gap.** Shipped, both SIs. |
| Suppress fillers + casual contractions | Shipped, folded into ARTICULATION -- simulating casual disfluency is a plausible slurring trigger. |
| TTS `[measured, clear]` performance tags | **Rejected.** That `### PERFORMANCE` / `### TRANSCRIPT` pattern belongs to the TTS API, which has a TEXT stage to tag. Native-audio Live has no such stage; the model would most likely speak the bracketed words aloud. |
| Explicit voice + `language_code` | `speech_config.language_code` already shipped (bd m1lg). Voice selection deferred -- see below. |

## Probe results (free, $0 -- no inference tokens billed)

Two questions were settled by connect/registry probes before any code was
written. Both used a **negative control**, which is what makes them trustworthy.

**1. Prebuilt voices ARE available on the production model.** All 11 tested
voices (incl. `Erinome`, `Rasalgethi`) returned ACCEPTED at connect on
`gemini-live-2.5-flash-native-audio` (Vertex), while the control
`NotARealVoiceXYZ` was REJECTED with `1007 Invalid voice name` -- proving the
endpoint genuinely validates the field rather than ignoring it.

**No voice is configured today**, so Google assigns its default. This remains
the strongest untried lever on diction. It is deferred only because the
maintainer can currently audition voices solely on AI Studio 3.1 (2.5 is no
longer offered in that quick-test environment) -- a tooling constraint, not a
technical one.

**2. `gemini-3.1-flash-live-preview` on Vertex: registered but NOT usable.**
Gemini claimed 3.1 was now on Vertex via the `global` endpoint. Measured:

- `models.list()` -- 3.1 absent at BOTH `global` and `us-central1`.
- `models.get()` -- **FOUND at `us-central1`**, NOT_FOUND at `global`
  (the opposite of the claimed `global`-endpoint caveat).
- Every serving path -- Live connect (3 api_versions, both modalities) and
  plain `generate_content` -- fails: *"was not found **or your project does not
  have access to it**."*

Registry-resolvable but unusable on every serving path is the signature of an
**access/allowlist gate**, not absence. The maintainer's read is that it is
simply not available yet. Either way the repo's documented
"3.1 is AI-Studio-only" position stands for now, so no doc was changed.

**Methodology scar:** `models.list()` alone was misleading -- it omits preview
models that `models.get()` resolves. An early conclusion of "3.1 is not on
Vertex" was drawn from the listing plus a **truncated** `1008` close-reason
(the WebSocket close field caps the message, hiding the decisive "or your
project does not have access" clause). Use `models.get()`, and read the full
error from a REST/`generate_content` path, before concluding a model is absent.

## Pace was tuned by ear, not by theory

First pass shipped articulation only. The maintainer test-drove the local stack
(`gemini-live-2.5-flash-native-audio`, Vertex) and reported she was still
"rushing a bit" -- asking for ~10% slower.

Two changes, deliberately separable so either can be tuned alone:

1. **A concrete relative target** -- "about ten percent slower again than the
   measured pace you would otherwise choose; err on the side of too slow."
   Preferred over stacking intensifiers (`VERY`/`EXTREMELY` slowly), which
   saturate and stop changing behavior.
2. **An anti-acceleration clause** -- hold the pace "from the FIRST word to the
   LAST", do not speed up mid-sentence, never rush a sentence ending. The
   observed "rushing" was mid-sentence DRIFT, a distinct failure from baseline
   speed.

The legacy SI got a matching `PACE` rule so both paths behave the same.

Confirmed good by ear in a second live session.

## Cost

~200 tokens/turn of added SI text. Non-trivial against the measured invariant
that per-turn SI text is 95-98% of session cost (and against the active
SI-reduction epic `polyglot-pdf-jnjj`), but small in absolute terms and bought a
maintainer-verified quality win.

## What pre-PR review caught

The fresh-eyes reviewer returned GAPS-FOUND on prompt-quality grounds, and two
findings were worth acting on:

1. **"word ENDINGS" was English-shaped.** The rule's central example is an
   inflectional-morphology concept: meaningless in Chinese, Vietnamese, Thai, or
   Japanese, whose sloppy-speech failure mode is lost tones or uneven mora
   timing. The `gonna` example had been hedged ("say the equivalent of"); this
   one had not. Reworded to "full value through to the END of the word" and it
   now names BOTH failure modes explicitly.
2. **REGISTER vs ARTICULATION read as competing.** "Polite, warm,
   conversational" sits near "no casual contractions / do not imitate casual
   speech"; a model could plausibly resolve that by dropping the warm register.
   Added an explicit scope clause: these rules govern DELIVERY only, not word
   choice.

A third finding (no ordering pin on the legacy SI) became two tests -- an
ordering assertion and a "exactly one ARTICULATION block per SI" count -- which
would have caught the wrong-constant mis-edit described below.

**Process note:** the first implementation pass put BOTH articulation blocks
into `DTI_SYSTEM_INSTRUCTION`, because the two SIs have near-identical REGISTER
text and the edit anchored on the shared wording. The tell was a test failure
naming `SYSTEM_INSTRUCTION`. When editing one of two near-duplicate constants,
anchor on text UNIQUE to the target (here: the following NAMES block, which is
worded differently in each) and verify with a count assertion afterwards.

## Scar tissue

- **Instruct articulation and pace SEPARATELY.** "Speak slowly" does not imply
  "speak clearly" -- the model can hit an unhurried pace while still slurring
  word endings. They are independent controls.
- **"Rushing" is usually acceleration, not baseline speed.** Pin the sustain
  ("first word to the last") as its own rule, or a pace target alone will not
  fix it.
- **A voice-quality change is only verified by LISTENING.** Tests pin that the
  SI *says* the right thing; they cannot show the model *does* it. This shipped
  on maintainer ear-verification, and that is the only evidence that counts here.
- **Prompt-level fixes are a soft lever.** SI wording nudges; it does not
  guarantee. If diction regresses over long sessions, the voice knob (verified
  available above) is the harder lever.
