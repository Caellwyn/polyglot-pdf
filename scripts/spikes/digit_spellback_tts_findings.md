# Digit read-back clip: TTS-only live check (bd polyglot-pdf-r3ham.26)

2026-11-21. Script: `scripts/spikes/check_digit_spellback_tts.py`.
**No Live-model (Gemini) spend.** Total spend across every call in this bead,
including two diagnostic STT requests and the name leg: about **$0.062**
(Cloud TTS Chirp 3 HD ~470 characters, Cloud STT v1 8 requests). The original
cap was $0.05; the Mandarin + Russian name clips (~$0.013) were approved past
it, with a hard stop there. Value: the synthetic phone digits
`5035550297`.

## Result: PASS (3 languages + 3 negative cases)

| Language | Locale / voice | Separate digit tokens (waveform) | STT in that language | Digits recovered | English digit words |
|---|---|---|---|---|---|
| Spanish | es-US-Chirp3-HD-Algieba | 10 / 10 | `Usted dijo 503 5 5 0 2 9 7` | 0.9 | none |
| Chinese | cmn-CN-Chirp3-HD-Algieba | 10 / 10 | `您说的是贾035555 0297对吗？` | 0.9 | none |
| Russian | ru-RU-Chirp3-HD-Aoede (rung 2: ru-RU has no Algieba) | 10 / 10 | `Вы сказали, 5035 55029 7 это верно.` | 1.0 | none |

Negative leg (no synthesis, $0): Urdu (ur-PK), Persian (fa-IR) and an unmapped
language each raise `SpellbackLanguageUnavailable` -- no digit clip at all, so
never an English one.

## Name leg (scope addition): frames confirmed, letter names not decidable by STT

Added on request: the existing letter path (`resolve_spellback_voice` +
`build_spellback_text`, unchanged by this bead) for `JOSE` in Spanish.

| Language | Voice | Clip text | STT es-US heard | conf |
|---|---|---|---|---|
| Spanish | es-US-Chirp3-HD-Algieba | `Usted dijo J, O, S, E. ¿Es correcto?` | `Usted dijo J o s e es correcto.` | 0.84 |
| Chinese | cmn-CN-Chirp3-HD-Algieba | `您说的是 J, O, S, E。对吗？` | `你说的是这一番对吗？` | 0.85 |
| Russian | ru-RU-Chirp3-HD-Aoede | `Вы сказали J, O, S, E. Это верно?` | `Вы сказали jo7er.` | 0.78 |

- **Frames: confirmed in all three** -- each recognized in its own language.
- **Spanish letter names (jota/o/ese/e vs jay/oh/ess/ee): NOT determinable.**
  Cloud STT normalizes spoken letter names to bare letters exactly as it
  normalizes digits, so `J o s e` fits either reading. Segment timing did not
  settle it either (es-US J/O/S/E 0.40/0.28/0.44/0.16 s vs en-US
  0.54/0.36/0.40/0.33 s). The production clip is saved for a human listen:
  `r3ham26-es-JOSE-name-clip.mp3` in the r3ham side-session notes folder.
- **Mandarin** (no native Latin-letter names; English-style expected):
  recorded, not judged. STT heard the four letters as Chinese syllables
  (这一番), so the letter style is not readable from the transcript.
- **Russian** (no native Latin-letter names either): STT returned the
  letters as Latin text (`jo7er`), consistent with English-style letter names
  from the Russian voice -- the expected behavior, recorded, not a failure.
- No language with its OWN Latin-letter names was shown to read them in
  English, so no bead was filed for that.

## Why two measurements, not one

**STT cannot tell separate digits from one number.** Cloud STT applies inverse
text normalization: a run of spoken digit words comes back as a numeral
(`cinco, cero, tres` -> `503`), and it merges repeats (`5, 5, 5` -> `5 5` in
the Spanish row). A first-pass verdict that failed any recognized word holding
several digits therefore failed all three languages for a recognizer artifact.

So the token question is answered on the **waveform**: the digit slot exactly
as the clip renders it (`5, 0, 3, ...`) is synthesized as LINEAR16 with the same
voice, and voiced segments are counted (a segment ends after 120 ms of
silence). Every language gave exactly **10 segments of 0.2-0.6 s** -- one
spoken word per digit, none dropped (the Spanish STT's missing `5` is the
recognizer merging a repeat; the waveform has all three). Reproduced on two
separate syntheses.

The **language** question is answered by STT in the session language: an
English voice heard by another language's recognizer comes back as
transliterated English words, not as that language's digits (measured below).

## The finding that shaped the code: voiceless locales speak English

**Which rung.** An Urdu session (LIVE_VOICE_NAME=Algieba) walks
`resolve_spellback_voice` as: rung 1 `ur-PK-Chirp3-HD-Algieba` -> not listed;
rung 2 any ur-PK Chirp3 voice -> none; rung 3 returns `("", "ur-PK")`, the
"locale's default voice". The synthesize call then carries
`language_code=ur-PK` and NO voice name, and **Cloud TTS itself** substitutes
an English voice -- our code never picks en-US on this path. **Names are
affected too** (bd polyglot-pdf-r3ham.27, P1): this bead removes the rung for
DIGIT clips only; an Urdu name clip still sends its Urdu-script frame to that
English voice (inferred from the digit measurement; the framed ur-PK name clip
was not synthesized), a Persian name clip 400s -> 502 every time, and the
intro and notice clips share the resolver.


`list_voices` (2026-11-21) shows **no voice at all** for `ur-PK` and `fa-IR`
(ur-IN carries 34, including Chirp 3 HD). A synthesize request for `ur-PK`
with no voice name does NOT fail -- it returns audio in an **English** voice:
ur-IN STT transcribed it as `فائیو زیرو ...` ("five zero" in Urdu script),
en-US STT as `5 0397`. `fa-IR` returns 400 instead.

That is why the digit gate checks the voice listing, not just the language
map: the old ladder's last rung ("the locale's default voice") is silently
English for a voiceless locale. Digits now refuse that rung.

## Follow-ups (filed as beads)

- Names, the intro clip and the notice clip still take that rung for Urdu and
  Persian (English voice reading Urdu/Persian script, or a 400). Urdu could be
  served by `ur-IN` voices. -> bd polyglot-pdf-r3ham.27
- Phone formats with `(`, `)` or `+` have no punctuation word in the frames
  file, so those characters reach the voice raw. -> bd polyglot-pdf-r3ham.28
- Whether gemini-3.8-live actually calls the tool after a number fill is
  unmeasured (this bead was TTS-only by design). -> bd polyglot-pdf-r3ham.29
