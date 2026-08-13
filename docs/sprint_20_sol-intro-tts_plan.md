# Sprint 20 -- Sol introduces himself: scripted TTS intro + first-person disclaimer

Epic: polyglot-pdf-s1iex. Maintainer-approved 2026-08-13:
the plan below was delivered whole by the maintainer (including the decision
table) with the instruction to file and begin work; it is recorded verbatim as
the plan of record. Filing-time annotations (stale references found while
filing) are at the end of this file.

---

## Context

**The problem.** A first-time user's very first experience of the voice is a
stranger reciting a liability waiver at them. Today: pick a language, then the
Gemini Live model reads **58 seconds** (measured, English) of third-person legal
text aloud ("This is an Important Notice about the limits of this AI tool..."),
then tells them to click a button. Nothing in it is friendly, nothing is first
person, and the speaker never says who he is. Only *after* Agree does any warmth
appear -- `INITIATING_MESSAGE` says
"Greet user warmly, state section name, immediately ask for [field 1]", so the
greeting is anonymous, arrives after the wall of legalese, and does nothing but
name a section before demanding a passport spelling.

Meanwhile the app already has a character. `frontend/src/shared/Sol.tsx` is a
seven-state avatar, described in its own header as "the voice assistant's avatar
and status indicator in one"; on mobile Sol IS the entire status UI. The voice has
never once said "I'm Sol." The identity shipped; it is simply mute.

**The intended outcome.** Replace the model-read disclaimer with a single scripted
intro-plus-disclaimer, rendered by Cloud TTS in the same voice persona
(`Algieba`) and the user's own locale, spoken by Sol in the first person. The user
meets someone, learns how the next twenty minutes will go, and is told the limits
honestly -- in that order.

**Three things fall out, and they are the real reasons to do it:**

1. **Determinism.** Today the disclaimer is read by a probabilistic model *asked*
   to read verbatim. It can drop a clause or soften a liability sentence and
   nothing catches it, because nobody transcribes what it said. On an immigration
   form that is a compliance gap. A synthesized clip is identical every session,
   in every language, and matches the on-screen text by construction.
2. **The session restart disappears.** If the audio is a clip, no Gemini Live
   session is needed until the user agrees. That deletes the teardown/re-handshake
   (`switchToFirstSection`), the `activity_start` interrupt, and the audio-queue
   flush -- the seam that produced beads `zq9l` and `ppf1`.
3. **Accent quality.** `resolve_spellback_voice` already resolves
   `{session-locale}-Chirp3-HD-{LIVE_VOICE_NAME}`, so a Spanish session gets
   `es-US-Chirp3-HD-Algieba` -- same speaker, right accent.

**Not a cost saving.** Per `docs/standards/logging-and-cost.md`, per-turn
system-instruction text is 95-98% of session cost and audio is negligible. Do this
for the three reasons above.

**Prior art.** The deterministic spell-back clip (bd `22h1f` / `44ywm`) established
the whole pattern: Cloud TTS, same voice persona, locale-aware, client-played, mic
held during playback. This epic is its second application.

## Maintainer decisions

| Decision | Choice |
|---|---|
| Sol's gender | **Male**, consistently, in all languages |
| Epic scope | **Full** -- delete the pre-Agree Live session and the restart |
| Agree-button gating | **Immediate** -- clicking Agree stops the clip (preserves bd `zq9l`) |
| Returning users | **Same full clip every time** -- one script per language, no variant |
| Script vs. instruct-the-model | **Fixed script**, translated once, synthesized by Chirp 3 HD |
| Disclaimer voice | **First person wherever it can be**; company voice only where liability requires it |
| Modal text vs. spoken text | **Identical.** What is written is what is synthesized |
| Length budget | **60-90 seconds** spoken. Today's English notice is ~60s, so the new clip does strictly more in about the same time |
| How length is checked | **By measuring real synthesized audio, never by word count.** See "Measured duration" below |
| Language switching | **Fixed for the whole form-session.** No mid-modal or mid-flow switch |
| Modal frequency | **Once per browser session** (`sessionStorage`). Reconnects never re-prompt; a later visit does |

## Sol is male -- and that is a per-language translation instruction

Gendering Sol male removes the need for neutral phrasing, which means the English
master can read naturally. But it does **not** make the problem disappear at
translation time -- it converts it from "avoid" into "choose consistently," and
that choice has to be made explicitly, because **verbs inflect for subject gender
in four of the eighteen languages**:

- **Russian / Ukrainian** -- past tense (`я ошибся` vs `ошиблась`).
- **Hindi / Urdu** -- present habitual and future (`मैं करता हूँ` vs `करती हूँ`).
- **Arabic** -- first-person verbs are gender-neutral, but predicate nouns and
  adjectives are not.
- **Spanish / French / Italian / Portuguese** -- predicate nouns and adjectives
  ("no soy abogado").

So bead 2 ships **explicit per-language translator instructions**: *Sol is male;
render every gender-inflecting form masculine.* The review checkpoint must check
**verb morphology**, not just nouns and adjectives -- that is the part a reviewer
skimming for "abogado/abogada" will miss.

**Verification item:** confirm the `Algieba` voice does not read as feminine in
the languages where it resolves. A masculine-grammar Sol in a clearly feminine
voice is worse than either alone. `Sol.tsx:39` already refers to Sol as "he", so
masculine is consistent with the shipped code.

## Measured duration, not word count -- the stage-1 gate

**Maintainer directive: no guessing.** Word-count-to-duration extrapolation is
what produced the wrong "2.5 minutes" estimate for a notice that actually runs
~60 seconds. Every length claim in this epic comes from a measured audio file.

**Method.** Stage 1 runs a synthesize-and-measure loop before any copy is frozen:
draft the English master -> synthesize it through the real Cloud TTS path at the
real voice and rate (`en-US-Chirp3-HD-Algieba`, the `spellback_gain_db` encode) ->
measure the returned MP3's actual duration -> revise and repeat until it lands in
**60-90 seconds**. The measured number, and the audio file that produced it, are
the deliverable that closes the copy bead.

**Scope of measurement.** English is the reference language and the only one
measured during copy work. Working assumption, made deliberately: no other
language runs more than **50% longer or shorter** than English. That bounds the
worst case at ~135 seconds, which is acceptable without per-language copy tuning.
The assumption is recorded here so that if a translation lands wildly outside it,
the surprise is a known risk rather than a new discovery.

**This is cheap and in-idiom.** The measurement loop uses the same Cloud TTS path
the feature ships on, so it doubles as an early end-to-end proof that the voice,
locale and gain resolve correctly -- before any route, player or lifecycle work
exists. Per the `experimentation` skill, this is a live-API measurement: it needs
the prior-work audit and a pre-spend estimate first, both trivial here (a handful
of single-sentence synthesis calls, cents at most).

## Draft master script (English) -- starting point, not final copy

**Not final, and not yet measured.** This is the input to the loop above, not its
output. It must be tightened for warmth and first person, then measured and
revised until it lands in the 60-90 second window. It carries all 15 legal
elements and is written first-person wherever first person is honest -- the shift
to the company voice happens only where liability requires it ("we at PolyGlot
Forms cannot be responsible"), which is also the moment the change in voice does
useful work for the listener.

> Hello. I'm Sol, and I'll be helping you fill out your **[FORM NUMBER]** today.
>
> Here's how we'll work. I'll ask you one question at a time. You answer out
> loud, in your own words, and I'll write your answer on the form and read it
> back so you can check it. If I get something wrong, just tell me and we'll fix
> it together -- or change it yourself, and I'll keep what you wrote.
>
> If a question doesn't make sense, ask me. I can tell you more about what the
> form is asking for and what the official instructions say. I can't tell you
> what to enter -- those answers are yours.
>
> Now, some things you should know before we begin.
>
> I'm an artificial intelligence -- a computer program, not a person. I'm not a
> lawyer and I'm not a certified translator, so I can't give you legal or
> immigration advice, and working with me doesn't make PolyGlot Forms your
> lawyer. I'll do my very best for you, but I do make mistakes -- I can mishear a
> word, translate something wrongly, or miss something completely -- and we at
> PolyGlot Forms cannot be responsible for the mistakes I make.
>
> What we make together is a draft. An office like USCIS may require a certified
> professional to review and sign your final form. So please read every answer on
> the English form carefully, and review it with a certified interpreter or legal
> professional before you submit. The finished form is yours, and you are
> responsible for what it says.
>
> Whenever you're ready, choose **[AGREE LABEL]**, and we'll begin.

### Legal-element traceability matrix

Rewriting legal copy means the "enumerate the set before changing any of it" rule
(CLAUDE.md scar #7) applies to the *clauses*. This table is a **required
deliverable** for counsel review and for auditing all 18 translations.

| # | Current disclaimer element | Where it lives now |
|---|---|---|
| 1 | Is an Artificial Intelligence tool | "I'm an artificial intelligence -- a computer program, not a person" |
| 2 | Helps with language + form data entry only | "I'll be helping you fill out..." + "I can't tell you what to enter" |
| 3 | Not a lawyer | "I'm not a lawyer" |
| 4 | Not a certified translator | "I'm not a certified translator" |
| 5 | No legal / immigration / professional advice | "I can't give you legal or immigration advice" |
| 6 | Does not tell you how to answer | "those answers are yours" |
| 7 | No lawyer-client relationship | "doesn't make PolyGlot Forms your lawyer" |
| 8 | Output is a DRAFT | "What we make together is a draft" |
| 9 | Not a certified/official/sworn translation | element 4 (shared) |
| 10 | USCIS may require certified review + signature | "may require a certified professional to review and sign" |
| 11 | Advise professional check before submitting | "review it with a certified interpreter or legal professional" |
| 12 | AI makes mistakes | "I do make mistakes -- I can mishear a word..." |
| 13 | Must check every answer on the English form | "read every answer on the English form carefully" |
| 14 | User is responsible for every answer | "you are responsible for what it says" |
| 15 | We are not responsible for AI errors | "we at PolyGlot Forms cannot be responsible" |

**Gate:** the English master is frozen only after maintainer (and counsel) sign-off
on this table. Nothing downstream starts before then -- every other artifact
derives from it.

## HARD INVARIANT: the modal text IS the TTS input

**Maintainer directive.** Whatever is written in the modal is exactly what is sent
to TTS. No gap.

This fixes a latent bug on the way in. `DISCLAIMER_TRANSLATIONS` currently keeps
`p1`, `p2`, `p3` **and** a separate `fullText` per language
(`DisclaimerModal.tsx:45-172`) -- the modal paints the paragraphs, `fullText` is
what gets spoken, and nothing keeps them in sync. In 18 languages nobody would
catch the drift.

**Shape:** one canonical `paragraphs: string[]` per language. The modal renders the
array; the TTS input is `paragraphs.join(' ')`. `fullText` stops being stored.

**Exact derivation -- stated explicitly, since the invariant demands it:**
- **In:** `paragraphs[]`, joined. That is the whole spoken text.
- **Out:** the modal `<h2>` title ("Important Notice") is a heading, not script --
  it is not spoken. State this in the test so it cannot drift into ambiguity.
- The "choose [AGREE LABEL]" closing line **is** script, so it appears in the
  modal too -- an improvement, since it tells readers what to do, not just
  listeners. It also satisfies bd `s863` (name the *translated* button)
  automatically, because label and script come from the same per-language table.

`DisclaimerModal.test.tsx:168-194` currently asserts the modal renders p1/p2/p3 and
does *not* paint `fullText` verbatim. That assertion inverts.

Backend and frontend must read the **same** data. Preferred: one JSON file both
consume, following `backend/services/spellback_frames.json`. If the Vite build
cannot cleanly import it, duplicate and add a byte-equality test -- the in-idiom
choice for this repo.

## Resolving [FORM NUMBER] -- the keyed-route contract

The route is meant to take a key, never caller text. A per-session form-name
placeholder breaks that: at clip time there is **no WebSocket and no handshake**,
and translated kit content only reaches the backend via the handshake
`full_schema` from the frontend bundle. `form_title` comes off `self._schema`
(`form_filling_service.py:893`), which does not exist yet.

**Decision: speak the form NUMBER, not the title.** The client sends
`{ language, form_number }`; the backend resolves the script from its own table
and interpolates the number. "Form I-90" is:
- short, and what users actually call it;
- **identical in every language**, so it needs no translated-title store and
  cannot be mistranslated;
- a bounded, validatable key -- the backend rejects anything not in its known
  form set, so caller text still never enters synthesis.

The alternative -- `{language, form_kit_id}` with the backend resolving a
translated title from its kit store -- is richer but requires verifying that
translated titles exist server-side per language, which per the recorded project
lesson they may not. Not worth blocking on.

**Consequence:** the cache key is `(language, form_number, script_hash)`, not 18
entries wide. Still small (18 x a handful of forms), but state it correctly.
`[AGREE LABEL]` is fine as-is -- a server-side per-language table.

## Two flags, not one -- and the skew matrix

**The chicken-and-egg:** backend flags reach the client only inside `session_ready`
over the WebSocket (`webFormConnection.ts:864-923`, how `jit_mode_enabled`
arrives). But this flag decides **whether the client connects before Agree at
all** -- a decision made before any connection exists. So "mirror
`SPELLBACK_TOOL_ENABLED`" cannot work as stated.

It is two flags: a **frontend build-time flag** driving the lifecycle, and the
**backend route flag** gating `/api/tts/intro`. They can skew across the
two-surface deploy, so the plan must specify behavior in each quadrant:

| Frontend | Backend | Behavior |
|---|---|---|
| OFF | OFF | Today's behavior exactly |
| OFF | ON | Today's behavior; the route sits unused |
| **ON** | **OFF** | **Modal shows text, intro route 503s, no audio. Agree still connects and the form works. It must NOT fall back to `read_disclaimer`** -- that path is gone on the frontend |
| ON | ON | New behavior |

Deploy backend first, frontend second. The ON/OFF quadrant must be explicitly
tested, not merely reasoned about.

## The double-greeting trap

`hasConnectedOnce` is set `true` on the disclaimer-phase connect
(`webFormConnection.ts:640`). The post-Agree `startSection` handshake passes it as
`resume` (`:4456-4460`), so today `resume=true` and the backend picks
**`RESUME_INITIATING_MESSAGE`** -- "Do NOT greet the user"
(`form_filling_service.py:919-924`).

Remove the pre-Agree connect and `hasConnectedOnce` is `false`, so the backend
picks **`INITIATING_MESSAGE`** -- "Greet user warmly, state section name". Gemini
would greet a second time, seconds after Sol's introduction. Nothing asserts this
either way today.

**Fix: strip "Greet user warmly" from `INITIATING_MESSAGE`** and update
`test_resume_reconnect.py:27-112`, which asserts it retains "greet" -- that test
encodes the old product truth. Sol now greets in the clip in *every* path, so a
greeting in the Live opener is redundant everywhere.

**Two caveats the flag does not cover:**

1. **This edit is a config constant and is NOT flag-conditional.** So "flag OFF is
   exactly today's behavior" is not quite true. The affected population is
   returning users (accepted, same browser session) who skip both modals
   (`VoiceOverlay.tsx:624-632`) and connect at mount with `resume=false` -- today
   they are the only people who actually hear the greeting. Losing it during the
   dark period is acceptable, but say so rather than let the implementer discover
   it.
2. **Stage 4 must preserve the mount-time connect for the already-accepted
   branch.** "Agree becomes the first and only connect" is true only for users who
   see the modal. A reload user never sees Agree; if the mount connect is removed
   wholesale, they never connect at all.

## Technical design

### Reuse, and what NOT to reuse

Reused from `backend/services/spellback_tts.py`: `resolve_spellback_locale:140`
(-> `bcp47_codes_for_spoken_language`, same 18 languages); the
`{locale}-Chirp3-HD-{persona}` construction and its **three-rung fallback**
(`:243-292` -- exact voice, any Chirp3 in locale, locale default); `spellback_gain_db:98`
(loudness leveled **in the encode**; `Algieba` measured `+4.0 dB`);
`_known_voices:200` / `_voice_exists:219` (the `list_voices` cache, **fails
open**); and the `asyncio.to_thread:332` discipline.

**`POST /api/tts/spellback` must NOT be reused.** It is capped at 60 chars
(`MAX_SPELLBACK_CHARS:51`, mirrored in `spellbackPlayer.ts` and pinned by
`test_spellback_tool.py:714`) and takes arbitrary text. Widening it would turn an
authenticated endpoint into a general-purpose TTS synthesizer -- there is **no
rate limiting anywhere** in `backend/main.py`.

### New route

`POST /api/tts/intro { language, form_number } -> audio/mpeg`. Keeps
`require_auth`, the `502`-logging-error-type-only behavior, and graceful handling
of an older client. Adds: in-process cache keyed by `(language, form_number,
script_hash)`; `Cache-Control: private` (**private**, not public -- the route is
auth-gated) plus `ETag`.

### The 5000-byte synthesis cap

This cap is on the **input text** of one `synthesizeSpeech` request -- the UTF-8
byte length of the words sent -- not on audio duration or file size.

A 60-90 second English script is roughly 1-1.4 KB, comfortably clear. But
Devanagari and Arabic script run ~3 bytes/char in UTF-8, so Hindi, Urdu or Arabic
at the same spoken length plausibly lands in the **3.5-4.5 KB** range. That is
under the cap but not by much, and the failure mode is a **permanent 502 for that
language only**, invisible in all English testing.

Add a test deriving the language set from `SPOKEN_LANGUAGES` (not a hand-list --
repo lesson) asserting `utf8len(paragraphs.join(' ')) < 5000` for every language.
This also hands the translation step a hard budget **before** it starts, which is
the cheap time to learn it.

### Sol must animate during the clip

A clip played via a bare `HTMLAudioElement` (`spellbackPlayer.ts:124`, `:324`)
leaves Sol **idle**. Three independent gates: `getOutputEnergy` short-circuits
unless `geminiIsSpeaking`, set only in `playAudio` (`audioManager.ts:233-243`,
`:610`); the AnalyserNode is on the playback `AudioContext`, which an
`HTMLAudioElement` bypasses (`:215-226`); and `useGeminiSpeaking` reads only
`window.vffOnAudioPlaybackStart/End`, fired from the PCM path
(`useGeminiSpeaking.ts:46-88`). `deriveSolState` falls through to `'idle'`.
Nothing tests this -- `SolStateTriggering.test.tsx` does not list the clip.

**Fix:** route the clip through the audioManager's playback context via
`createMediaElementSource` into the existing `getOutputAnalyser` node, and fire the
two `vff*` globals. One energy source, so `deriveSolState` learns nothing new.

**Three traps in that fix:**
- **Play from the fetched blob, never from the cross-origin Cloud Run URL.** A
  CORS-tainted media element silently outputs **zeros** through the graph --
  killing both the audio and the animation, with no error. You need `fetch`
  anyway for the auth header, so use the blob.
- `createMediaElementSource` can be called **once per element**. Reuse the node or
  the element deliberately.
- The audioManager's `AudioContext` lifecycle is presumably tied to connect
  today. With no connection during the clip, the player must create/resume it --
  resume it **synchronously inside the language-pick handler**, where the user
  gesture is live.

### Autoplay -- narrower than the general worry, but not zero

The maintainer is right that the normal flow is fine: mic permission is granted at
page load (`SchemaForm.tsx:214-263`) and the language-pick tap is a real gesture.
Two narrow paths remain: a **reload with the disclaimer unaccepted** reopens the
modal with no gesture at all, and transient activation can expire during a
multi-second cold-cache synthesis fetch. Design a visible **"tap to play"** state
for when `play()` rejects, rather than failing silently. Verify on a real iOS
device, not just a narrow viewport.

### Playback timing model

`spellbackPlayer.ts` budgets `PLAYBACK_TIMEOUT_PER_CHAR_MS (1500) x length`
inside an 80 s total that must beat the backend's 90 s round-trip cap. That is
sized for a <=60-char name and does not transfer. The intro clip is not inside a
Gemini tool round-trip -- no model is waiting -- so it needs only a generous fetch
timeout and an `onended`/`onerror` watchdog. Reuse the *structure* (monotonic
`generation` counter, `cancelledUpTo` poison marks, injectable deps), not the
constants.

### Lifecycle change

**Today.** The mount effect (`VoiceOverlay.tsx:168-234`,
`VoiceOverlayMobile.tsx:120-187`) awaits `handleConnect()` -- opening the WebSocket
*and* the Gemini session -- then shows the modal, so modal and audio race by
design. On Agree, `handleDisclaimerAgree` (`VoiceOverlay.tsx:1155-1275` /
`VoiceOverlayMobile.tsx:658-772`, step-for-step identical) runs: mark accepted ->
hide modal -> `sendActivityStart` -> `flushAudioQueue` -> `POST
/api/disclaimer-acceptance` -> staleness re-check (bd `ppf1`) -> `resumePlayback`
-> `sendActivityEnd` (skipped when reconnected, bd `ala0`) ->
`switchToFirstSection`, which **fully disconnects the WebSocket**
(`webFormConnection.ts:4403-4407`), sleeps 100 ms, reconnects and re-handshakes.

**After.** The modal opens immediately and the clip plays against no Live session.
Agree stops the clip and makes the first and only connect. One handshake, no
interrupt sequence, no teardown.

### Two client paths: one rewired, one DELETED

- **"Listen Again"** (`connection.ts:1105-1130`, hard-gated on
  `getStatus() === 'connected'`) does nothing with no session. **Replay the cached
  blob client-side** -- instant, no network, provably identical to what they just
  heard.
- **Language change while the modal is open** (`VoiceOverlay.tsx:644`, `:1150`;
  mobile `:569`, `:650`) re-sends `read_disclaimer` today. **Maintainer decision:
  language is fixed for the whole form-session, so this path is DELETED, not
  rewired** -- in both hand-duplicated overlays.

  This is a simplification, and it removes work rather than adding it. It also
  aligns the code with doctrine that already shipped: the system instruction
  already tells Sol never to switch language ("if they ask to switch, say warmly
  that changing language means starting over"), and the pinned-language policy
  (bd `87a9`) already treats the onboarding pick as the single source of truth.
  The mid-modal switch was a leftover from the era when Gemini read the
  disclaimer live. **Rationale to preserve in the bead:** a fixed language means
  the acceptance record can state unambiguously which form and which translated
  script the user actually agreed to -- which is the point of recording it.

  **Check during implementation:** confirm nothing else depends on those call
  sites, and that the language picker is genuinely unreachable once the modal is
  open. If the picker remains visible but inert, that is a worse experience than
  either option -- it must be gone, not disabled-looking.

### Modal frequency -- already correct, with one factual caveat

**Requirement:** the modal appears once per session; reconnects and timeouts never
re-prompt; a user who returns later agrees again.

**Verified: the shipped code already satisfies this**, and this epic must not
regress it. `disclaimerAccepted` lives in `sessionStorage`
(`schemaFormState.ts:64`, written at `:1664`), so it dies with the browser
session, and auto-reconnect never remounts the overlay. No new mechanism is
needed.

**One caveat worth stating plainly:** there is **no `localStorage` resume path in
the frontend today.** `localStorage` is used only for dev/E2E harness flags
(`shared/config.ts`) and VAD tuning. A user who closes the tab and comes back does
not resume a partly-filled form and re-agree -- they start over completely,
disclaimer included. The requirement holds, but via "everything resets," not via
"state resumes, agreement does not." If cross-session resume is ever added, the
re-agreement behavior becomes a real design question rather than a free
consequence of the storage choice; that is out of scope here and worth its own
bead if it is ever wanted.

### Contract deletions and the set-pinned tests

Removing the Gemini read deletes two wire types (`read_disclaimer`,
`disclaimer_read_initiated`) and `DISCLAIMER_INITIATING_MESSAGE`. Three tests pin
*sets* and fail until updated together:

- `backend/tests/contract/test_websocket_protocol.py:515-528` -- **set equality**
  on documented-inbound-types-with-no-frontend-sender.
- `frontend/src/__tests__/pinned-language-policy.test.ts:165-249` -- the
  **complete list** of `selectedLanguage` write sites. `readDisclaimer`
  (`connection.ts:1107-1110`) is the *only* production caller of
  `setSelectedLanguage`; deleting it orphans that setter. Behavior stays safe (the
  pin is seeded from onboarding, `schemaFormState.ts:146-152`); the test is not.
- `backend/tests/unit/test_disclaimer_flow.py` -- obsolete wholesale, but
  **preserve the requirement it encodes** (bd `s863`).

### Strengthen the legal-evidence chain

`POST /api/disclaimer-acceptance` and its PII-allowlist test
(`test_disclaimer_acceptance_route.py:37-57`) are the legal record. The
determinism win only *becomes* evidence if the record says which exact text the
user heard, so **add `script_version` (the hash) and `language`** to the logged
allowlist -- both non-PII, added deliberately, with the allowlist test updated to
match. Without this the audit log still cannot answer "what were they told?"

### E2E harness ordering

All five drivers (`tests/e2e/voice-harness/driver_*.mjs`) wait for
`__VFF_TEST_INJECT` then click "I Agree". The hook appears during the
disclaimer-phase connect today; with no pre-Agree session it will not exist until
after Agree, so **the wait and the click must swap order** in every driver, plus
`RUNBOOK.md`.

## Epic exit criteria

1. A first-time user in **any** supported language hears one continuous scripted
   intro+disclaimer in the `Algieba` persona at their locale, and the spoken words
   match the on-screen modal text word for word.
2. Sol animates in the `speaking` state for the clip's full duration, desktop and
   mobile.
3. No Gemini Live session is created before Agree, and Agree produces exactly
   **one** WebSocket handshake -- no teardown and re-handshake.
4. The user is greeted exactly **once** per form-session: the Live model does not
   greet after the clip.
5. All 15 legal elements are present in every one of the 18 scripts; every script
   is under 5000 UTF-8 bytes; and the **measured** English clip runs **60-90
   seconds** (measured from real synthesized audio, not estimated from word
   count).
6. Language is fixed for the whole form-session: the mid-modal switch path is
   gone from both overlays, and the acceptance record states the language and
   script version the user agreed to.

## Implementation sequence

**Stage 1 -- Copy (measure-driven; the only "code" is a throwaway synthesis
script).** Draft the English master against the 15-element traceability matrix,
then run the **synthesize-and-measure loop**: synthesize through the real Cloud
TTS path, measure the actual MP3 duration, revise, repeat until it lands in 60-90
seconds. Deliver the frozen text, the matrix, the measured duration and the audio
file together; maintainer/counsel sign off on that package. **Only then**
translate into the other 17 languages using a high-quality translation model, with
the *Sol is male* instruction and per-language verb-morphology guidance, and have
each translation **checked for accuracy** by a second pass before it ships.
Everything downstream derives from this.

**Stage 2 -- Backend (behind the route flag).** Canonical script store,
`/api/tts/intro`, cache, `Cache-Control: private`, byte-cap test.

**Stage 3 -- Sol animation (UNFLAGGED).** Route clip playback through the
playback `AudioContext` and fire the `vff*` globals. **Explicitly not behind the
flag** -- it fixes the *existing* spell-back clip, which leaves Sol idle in
shipped behavior. This stage stands alone and could ship first.

**Stage 4 -- Clip player + modal (behind the frontend flag).** Fetch/play/cancel,
Agree stops the clip, Listen Again replays the blob, **deletion** of the mid-modal
language switch, "tap to play" fallback, modal renders the same `paragraphs[]`.

**Stage 5 -- Lifecycle (behind the frontend flag).** Stop connecting before Agree;
delete the interrupt sequence and the teardown; preserve the mount connect for the
already-accepted branch; apply the greeting fix (config edit, unflagged).

**Stage 6 -- Contracts, tests, docs, cutover.** Wire-type deletion, the three
set-pinned tests, `script_version` in the acceptance log, five e2e drivers +
RUNBOOK, `ws-protocol.md` / `websocket-routing.md`, flag flip, dead-path deletion.

## Bead decomposition

One bead = exactly one PR; small beads may bundle. The rightmost column is
**epic exit-criteria numbers**, not bead dependencies. Real bead dependencies:
6 needs 4 and 5; wire them with `bd dep add` (`--deps` silently drops edges).

| Bead | Scope | Exit criteria (binary) | Criteria met |
|---|---|---|---|
| **1. English master + matrix + measured duration** | Draft; 15-element matrix; synthesize-and-measure loop to 60-90s | Matrix covers all 15; the **measured** English clip is 60-90s, with the audio file attached as evidence; maintainer signed off | 5 |
| **2. Seventeen translations** | Translate via a high-quality translation model with *Sol is male* + verb-morphology instructions; second-pass accuracy check; collapse to `paragraphs[]` | Every language has a complete `paragraphs[]`, each under 5000 UTF-8 bytes, verified by a `SPOKEN_LANGUAGES`-derived test; every translation has a recorded accuracy check | 1, 5 |
| **3. Backend intro route** | Script store, `/api/tts/intro`, cache, flag | Returns `audio/mpeg` for every language and 503 when off; a repeat request serves from cache with no second synthesis RPC | 1 |
| **4. Sol animates during clips** | Blob playback through the playback context; `vff*` globals. **Unflagged** | `deriveSolState` returns `speaking` for the clip's whole duration; a test pins it | 2 |
| **5. Clip player + modal wiring** | Fetch/play/cancel; Agree stops; Listen Again replays the blob; **delete** the mid-modal language switch in both overlays; tap-to-play | Rendered and synthesized text provably share one source; Agree during playback stops audio immediately; no language-switch path remains while the modal is open | 1, 6 |
| **6. Delete pre-Agree session + restart** | Both overlays; greeting fix; preserve the reload branch | Exactly one handshake per form-session start; the Live model does not greet after the clip | 3, 4 |
| **7. Contracts, evidence, e2e, cutover** | Wire deletion, three set-pinned tests, `script_version` + `language` in acceptance log, drivers, docs, flag flip | Full suites green; voice-harness passes in English and one non-Latin-script language | 1-6 |

Beads 1+2 are copy-only and can bundle. Bead 4 is genuinely independent.

## Risk register

- **Translation quality is now permanent.** A mistranslation repeats identically
  forever instead of being smoothed over by a model. Mitigation: translate with a
  high-quality translation model, then run a **second-pass accuracy check** on
  every language before it ships -- and treat that check as a gate, not a
  formality. It is legal copy; the check is the only thing standing between a
  translation error and every user who speaks that language.
- **Non-English duration is assumed, not measured.** Only English is measured
  during copy work; other languages are assumed within +/-50% of it. Worst case is
  ~135 seconds. If a language lands outside that, it is a known-risk surprise
  rather than a discovery -- but nothing in the plan detects it automatically, so
  spot-check duration in at least one long-running language (German or Hindi are
  the usual offenders) during manual verification.
- **Verb-gender is unavoidable at translation time** in Russian, Ukrainian, Hindi
  and Urdu -- it needs a planned per-language answer, not reviewer vigilance.
- **Language expansion now carries a legal cost.** The set is expected to grow
  toward ~90 (bead `ryu6` context). After this epic, adding a language requires a
  counsel-grade script translation before it can ship, and the derived-set test
  enforces it. Probably the right gate -- but a standing cost to accept knowingly.
- **RTL languages** (Arabic, Urdu, Persian) -- modal rendering and paragraph
  splitting must not corrupt direction.
- **Locales with no Chirp3 voice** fall to the locale default, so the clip will
  *not* sound like Algieba there, and the measured `+4.0 dB` gain will be wrong for
  whatever voice speaks. Verify which of the 18 resolve rung 1.
- **Local dev fails before production does**: TTS uses ADC while Gemini uses an API
  key when `VERTEXAI=false`. Cloud Text-to-Speech must be separately enabled.
- **The two overlays are hand-duplicated** (`Sol.tsx:48` names this a standing
  hazard). Every lifecycle change lands in both; one-sided is the likeliest
  regression.
- **`LIVE_VOICE_NAME` now does quadruple duty** -- Live voice, spell-back persona,
  spell-back gain, intro clip.

## Verification plan

**Automated.** Backend pytest + frontend vitest green, with the three set-pinned
tests updated rather than deleted. Voice-harness in English **and** Russian
(driver exists). The `SPOKEN_LANGUAGES`-derived byte-cap test.

**Manual, by listening -- cannot be automated.** Via `/run-local`:
1. English end to end: clip plays, Sol animates throughout, Agree mid-clip stops
   audio immediately, the Live model asks field 1 **without greeting**.
2. **Spanish**: same speaker with a Spanish accent (`es-US-Chirp3-HD-Algieba`),
   masculine forms throughout, spoken words match the modal exactly.
3. **Hindi or Urdu**: masculine verb forms correct, and the clip is under the byte
   cap in practice.
4. **Arabic**: RTL rendering; check which voice resolved.
5. Listen Again replays instantly with no network round trip.
6. **No** language switch is reachable once the modal is open -- the control is
   gone, not merely inert.
7. **Timed playback**: the English clip measures 60-90 seconds in the running app,
   confirming the stage-1 measurement survived the real playback path.
8. Mobile overlay: Sol animates on the collapsed FAB, where Sol is the only status
   indicator there is.
9. **A real iOS device**, including a reload with the disclaimer unaccepted.

**Skew.** Explicitly test frontend-ON / backend-OFF: modal renders, no audio,
Agree still connects, no fallback to `read_disclaimer`.

**Instrumented.** Confirm exactly one WebSocket handshake per form-session start
(today: two), and that the `client_diagnostic` opener path no longer reports the
"legitimate silent skip" the first connect produces today.

**Demo deploy** is gated per CLAUDE.md: local behavioral test, explicit
per-instance maintainer permission, then a post-deploy test-drive.

## Related open beads

- `polyglot-pdf-ppf1` (P3 bug) -- `handleDisclaimerAgree` falls through to
  `switchToFirstSection` after a silent reconnect timeout. Lives inside the code
  path this epic deletes; likely **fixed by deletion**. Confirm and close as part
  of the epic.
- `polyglot-pdf-uov.6` (P2) -- spec-audit `DisclaimerModal.test.tsx`. Overlaps this
  epic's test rewrite; sequence after, or fold in.

---

## Filing-time annotations (2026-08-13, orchestrator)

Recorded while filing the epic; the plan text above is kept verbatim.

**Both "Related open beads" are already CLOSED.** `polyglot-pdf-ppf1` closed by
PR #160 (2026-06-12) -- the fall-through it describes was fixed then, not left
open; the epic still deletes the whole path. `polyglot-pdf-uov.6` closed at
PR #186 (2026-06-13) -- it added ~76 tests to `DisclaimerModal.test.tsx`,
including an `it.each` over all 18 languages and a "fullText is a superset of
p1/p2/p3" data-integrity invariant. Those are exactly the assertions bead 5
inverts/deletes when `fullText` stops being stored. `polyglot-pdf-s863` is also
closed (PR #448); its requirement (speak the *translated* agree label) is
preserved by construction here (label and script share one per-language table).

**Path corrections (the tree moved since the plan's citations):**

| Plan cites | Actual path |
|---|---|
| `VoiceOverlay.tsx` / `VoiceOverlayMobile.tsx` | `frontend/src/demo/` |
| `DisclaimerModal.tsx` | `frontend/src/schema-forms/components/` |
| `webFormConnection.ts` | `frontend/src/webFormConnection.ts` |
| `connection.ts` | `frontend/src/shared/connection.ts` |
| spell-back route | `backend/routes/tts_routes.py` |
| `schemaFormState.ts` | `frontend/src/schema-forms/state/schemaFormState.ts` |

Line-number citations in the plan were taken against the maintainer's reading
and may drift; treat the named symbols, not the line numbers, as the anchors.

## Post-filing maintainer decisions (2026-08-13, during bead s1iex.1)

Recorded per the rubric-change rule (changes logged, never silent). Full
measurement record: `scripts/spikes/intro_duration_findings.md`.

1. **The English master is FROZEN as the maintainer's own edit** (v5, plus
   two typographical fixes: "outloud" -> "out loud", "PolyGlot forms" ->
   "PolyGlot Forms"). Canonical master with placeholders:
   `scripts/spikes/data/intro_en_master.txt`.
2. **Length window widened to ~95 s** ("95 seconds is fine"). The frozen
   master measures 92.6-94.3 s across four synthesis draws. Epic exit
   criterion 5's "60-90 seconds" reads as "60-95 seconds" from here on.
3. **Element set changed by maintainer decision**: element 10 (USCIS may
   require certified review + signature) and element 14 (user responsible
   for every answer) are DROPPED; a NEW element 16 is added (affirmative
   release: "you agree to absolve PolyGlot Forms and their staff of all
   responsibility for any mistakes or omissions"). The frozen set is
   therefore 14 elements: 1-9, 11-13, 15, 16. A LEGAL PASS IS STILL PENDING
   (maintainer: "this is going to need a legal pass anyway") -- counsel may
   reverse these drops; the traceability matrix records them explicitly so
   counsel reviews the delta, not just the text.
4. **Encode: the shipped 32 kbps MP3 stays.** In the maintainer's ear test
   (same text, 0 dB, WAV vs MP3 vs Opus) the MP3 sounded BETTER than the
   uncompressed WAV -- the encode is not the quality ceiling. No transcode
   dependency, no WAV serving, no Opus/iOS question. Bead .3 keeps
   AudioEncoding.MP3.
5. **Gain (orchestrator technical call, from measurement): the intro route
   uses 0 dB**, not the spell-back +4.0 dB -- the +4 dB gain measurably
   CLIPS ~90 s content (WAV peak 1.000), and the intro clip plays standalone
   so the mid-conversation loudness match that motivated +4 dB does not
   apply.
