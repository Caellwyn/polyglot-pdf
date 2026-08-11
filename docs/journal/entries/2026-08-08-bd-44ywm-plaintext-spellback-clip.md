---
date: 2026-08-08
bead: polyglot-pdf-44ywm
title: "Plain-text Chirp3 spell-back clip: the user's language, the whole question, no SSML"
sprint: 19
tags: [hotfix, harness, testing]
---

## Trigger

bd polyglot-pdf-22h1f (PR #563) shipped the deterministic spell-back mechanism
and proved it removes the bd 0rpu sticky-first-spelling defect. But the clip
itself sounded ROBOTIC with unevenly spaced letters, and it cost an extra
model turn: the clip said only the letters, so the model still had to ask "is
that correct?".

The maintainer then edited Google's Chirp 3 HD quickstart notebook
(`pitch/ignored_pitch/get_started_with_chirp_3_hd_voices.py`) and got a
markedly better result with a one-line prompt:
`"I heard you say J, O, S, E, is that correct?"` -- PLAIN TEXT, letters
comma-separated, question inline.

## The finding

**Chirp 3 HD voices are LLM-based: they generate prosody from natural text,
and SSML markup renders mechanically.** Our shipped builder emitted per-letter
`<say-as interpret-as="characters">` tags separated by explicit 400ms
`<break>`s -- the old-school TTS control style -- so the voice dutifully
performed each tagged fragment instead of speaking a sentence. That is the
robotic tone and the uneven gaps.

Measured A/B, same voice (en-US-Chirp3-HD-Iapetus), JOHNSON:

| approach | clip | synthesis |
|---|---|---|
| SSML, letters only (shipped) | 10.2s | 2.3s |
| plain text, letters + the whole question | **4.9s** | **0.9s** |

Strictly better on every axis, and the question rides along free -- which
answers the maintainer's earlier cost question in the opposite direction from
the original design: the model no longer needs a post-clip turn at all.

## What shipped

- **`build_spellback_text(value, locale)`** replaces `build_spellback_ssml`:
  a natural sentence per locale, letters comma-joined and upper-cased,
  punctuation voiced as that language's word. No markup anywhere.
- **The clip carries the verification question**, so the tool's `delivered`
  response now tells the model to STAY SILENT and listen -- it no longer asks.
- **Session-language clips (maintainer ruling)**: frame + voice follow the
  session's spoken language through the same name->BCP-47 map as the ASR bias.
  Letter names come out the way that language's speakers say them (a Spanish
  speaker hears "jota"); languages with no native Latin-letter names (Chinese)
  naturally get English-style names from their own regional voice. Frames +
  punctuation words are DATA (`backend/services/spellback_frames.json`, UTF-8;
  the source files stay ASCII per scar #6), covering all 18 supported
  languages with an enumeration test so a new language cannot be silently
  missed.
- **Language-first voice ladder** (`resolve_spellback_voice`):
  `{locale}-Chirp3-HD-{LIVE_VOICE_NAME}` -> any Chirp3 voice in that locale ->
  the locale's default voice -> en-US only when the language itself is
  unknown. Availability is derived from `list_voices` at runtime, never a
  hand-pinned language list.
- **The language rides the wire**: `POST /api/tts/spellback` takes an optional
  `language`; the client passes the session's spoken-language name.

## The live run earned its keep twice

**1. It caught a design bug unit tests could not.** The first live pass showed
Russian falling back to an ENGLISH clip. Cause: ru-RU carries only 8 of the 30
Chirp3 personas and no Iapetus, and my first ladder dropped straight to en-US
on a persona miss -- speaking the wrong LANGUAGE to preserve our voice. The
ladder is now language-first (above). Also learned from the same probe:
fil-PH / ur-PK / fa-IR / af-ZA carry no Chirp3 voices at all, so they take the
locale-default rung.

**2. It exposed a pre-existing blocker.** The harness failed 0/15 twice, with
the client spraying `send() called but WebSocket not open (readyState:0)`. Per
the run-the-baseline-arm rule I re-ran with all changes STASHED against the
same server: it reproduced identically, so the spell-back work was exonerated
and the real bug got its own bead (polyglot-pdf-4hnyq) -- see below.

## bd 4hnyq: the /ws/fill handshake took ~9.4s

Every handshake blocked ~9.4s before `accept()`, just past the frontend's 10s
connect timeout, so local voice testing lost a coin-flip on every connection.
Cause: the route's `Depends` chain builds three Gemini adapters, each
resolving ADC/endpoint discovery synchronously (~3s apiece, SERIALLY) before
the socket is accepted.

The fix landed in two steps, and the first was WRONG in an instructive way:
making the dependency `async` + `asyncio.to_thread` moved the work off the
loop but barely helped (9.4 -> 8.6s), because the handshake still awaits the
whole chain. Timing each adapter separately revealed the real shape (3 x ~3s,
serial), which pointed at `asyncio.gather` -- and then process-caching the two
STATELESS text clients (the live adapter must stay per-connection for callback
isolation) took warm connections the rest of the way:

| | handshake |
|---|---|
| baseline | ~9.4s |
| async + to_thread (wrong hypothesis) | ~8.6s |
| + concurrent gather | ~4.6s |
| + cached text clients | **~3.2s warm** |

`lru_cache` could not be used for the cache -- `Settings` is unhashable -- so
it is a bounded dict keyed on the CONFIG VALUES the client is built from. It
was id-keyed at first; fresh-eyes round 1 flagged that as an aliasing footgun
(CPython reuses addresses, so a GC'd short-lived Settings could alias a new
one and hand back a client built for different config), and value-keying makes
a differing Settings miss by construction.

## Validation (W-7 harness, live Vertex 2.5 native audio, temp 0.4)

Two clean runs after the handshake fix, both **PASS 15/15**:

| | run 3 | run 4 |
|---|---|---|
| spell-back clips | 6 delivered, 0 errors | 6 delivered, 1 premature (recovered) |
| **model speech after a clip** | **silent, all 6** | **silent, all 6** |
| model audio (Cloud STT) | (dir deleted mid-run, see traps) | 32/32 scoreable, 0 spelled-letter runs |
| cost | $1.15 / 74 turns | $1.11 / 76 turns |

The silence result is the one that mattered: it is NEW behavior this redesign
introduced (22h1f validated the ask-after variant), and no unit test can prove
a live model will actually stay quiet. It did, across 12 clips. The single
premature call was correctly redirected by the error variant -- the model
refilled and immediately re-called, which is the designed recovery.

The one STT-flagged row was a DATE read-back ("You entered 1990101?"), not a
spelling -- out of this tool's scope and pre-existing.

## Traps for the future

- **Do not delete `backend/logs/audio_out/<date>/` while the server is
  running**: the dump path is resolved at startup, so WAVs keep landing in the
  original (now-recreated) directory while transcripts write to today's. Run 3
  lost its audio to this; nothing else was affected because the TRANSCRIPT
  record answers the silence question directly. Rotate the dir BEFORE starting
  the backend, or point the scorer at the path the `audio_dump` records name.
- **A test that persists state into the shared sessionStorage mock must clear
  it.** The new language spec wrote `selectedLanguage` and left it, leaking a
  Spanish session into a later suite FILE and failing an unrelated
  PDF-preview test. The tell was subtle and nearly mislabeled: the failing
  test passed in ISOLATION both with and without the change, which reads like
  an ordering flake -- but the stashed FULL-SUITE baseline was green, which
  proves the diff caused it. Isolation-passes is not evidence of innocence
  when the suite composition changed; run the stashed full suite.

## Left open

- Cutover (flip `SPELLBACK_TOOL_ENABLED` + `LIVE_TEMPERATURE=0.4` on Cloud
  Run) is a demo deploy and needs the maintainer's per-instance go-ahead.
- Frame translations are initial authored strings; a native review pass per
  language would be worthwhile before a non-English demo.
- bd m8iov (secretary arm for a PAST field), a43y4 (harness clip capture),
  flnz1 (open-mic voice barge-in during a clip -- a product call), 3o2uz
  (dangling token-race timer).
