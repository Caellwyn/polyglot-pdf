# Voice & VAD (turn-taking modes)

**Tracks:** backend/config.py backend/adapters/live_ai_gemini.py backend/routes/websocket_routes.py backend/main.py frontend/src/shared/connection.ts frontend/src/shared/audioManager.ts frontend/src/webFormConnection.ts frontend/src/demo/useDemoVAD.ts frontend/src/demo/VoiceOverlay.tsx frontend/src/vad-tuning

*Last updated: 2026-09-02 (bd polyglot-pdf-wurj8: the Pause button is replaced by a sticky manual/voice mode toggle -- manual suppresses the model's proactive speech at the ADAPTER while the session stays live and the mic stays usable; a PTT press unmutes at both ends; the mode is client-owned and re-asserted on every reconnect.)*

The cross-cutting rules for voice turn-taking: who decides when the user is
speaking, how barge-in works, and the language distinction. The Gemini Live
adapter internals are in [voice-ai.md](../components/voice-ai.md); model selection
is in [ai-models.md](ai-models.md).

## One turn signal: push-to-talk

**Push-to-talk owns activation. There is no VAD mode toggle** (bd
polyglot-pdf-v1m8g). Gemini's `automatic_activity_detection` is unconditionally
`{'disabled': True}` -- `_build_vad_settings` in `live_ai_gemini.py` returns that
constant -- and the client brackets every turn with explicit `activity_start` /
`activity_end`.

The reason is not cost, it is ambiguity. PTT *knows* when the user is speaking:
they are holding the button. Gemini's VAD *infers* it from the audio. Running
both meant a signal we can state exactly was second-guessed by one that can only
estimate, and the two could disagree -- so the redundant gate is gone.

What this replaced, for anyone reading old code or journal entries:

- a **NATIVE** mode where Gemini's own VAD drove turns on a continuous ungated
  stream (silence included), with the client's manual signals SUPPRESSED and a
  set of `VAD_*` sensitivity/padding knobs tuning the detector;
- a **MANUAL** mode where the client's own Silero VAD drove turns instead;
- the `DISABLE_GEMINI_VAD` flag that chose between them, the `native_vad` field
  that mirrored it into the `session_ready` handshake, and the backend guard that
  dropped stray manual signals in native mode.

All of it is removed rather than defaulted off: a knob nothing can safely turn on
is a trap for the next caller (CLAUDE.md scar #7). Two consequences worth knowing:

- **Gap-fill is dead.** It manufactured a continuous stream so Gemini's VAD was
  not starved of trailing audio. Under PTT, audio is expected ONLY inside an
  activity bracket, so injecting silence between turns would send un-bracketed
  audio and desync the turn state. `_gapfill_enabled` is pinned `False`; removing
  the plumbing it threads through is bd polyglot-pdf-ggdpn.
- **The client Silero VAD no longer gates audio.** The hook still exists and the
  thresholds below are still its tuning surface, but `shouldRunVAD` requires
  `!pushToTalkMode`, which no longer happens in practice.

## The client VAD thresholds (Silero)

The frontend VAD is **Silero** (ONNX), not a hand-rolled energy gate. Its tuned
defaults are `DEFAULT_VAD_CONFIG` in `frontend/src/demo/useDemoVAD.ts`:

| Param | Value | Meaning |
|-------|------:|---------|
| `positiveSpeechThreshold` | 0.85 | model confidence to *start* speech |
| `negativeSpeechThreshold` | 0.65 | hysteresis threshold to *end* speech |
| `minSpeechMs` | 250 | minimum speech duration to count |
| `redemptionMs` | 400 | grace before declaring speech ended |

These can be overridden per-session via `VADOptions.sensitivity`; the
`frontend/src/vad-tuning/` dashboard tunes them live and persists overrides in the
browser (`localStorage`), exporting a snapshot file for sharing. The post-barge-in
tool-call rejection window is a **separate** hardcoded constant —
`BARGE_IN_GRACE_PERIOD_MS = 150` in `frontend/src/shared/metrics.ts`. Barge-in /
latency metrics are collected in metrics.ts (local-only — see
[hipaa-pii-policy.md](hipaa-pii-policy.md)).

> **There are no Gemini-side VAD knobs.** The `VAD_*` env fields that used to
> tune the detector are gone with it (bd polyglot-pdf-v1m8g) -- Gemini's automatic
> detection is always disabled, so nothing would read them. (A dead
> `backend/vad_config.json` + `/ws/vad-config` WebSocket predated even that and
> was removed in bd `polyglot-pdf-9jv`.) The thresholds above tune the client
> Silero hook, which is retained but no longer gates audio under push-to-talk.

## Barge-in

When the user starts talking while Gemini is speaking, the frontend
(`connection.ts` `onVADSpeechStart`) immediately flushes its local audio queue
(`audioManager.flushAudioQueue()`) for instant UX. The backend separately watches
Gemini's own `server_content.interrupted` flag and **forwards it to the client
as a `{"type": "interrupted"}` WS message** (bd polyglot-pdf-s7uf; adapter
`_on_interrupted` -> `callback_handler.on_interrupted`, same detect-and-forward
discipline as `go_away`). The client reacts by clearing BOTH its audio holds:
`webFormConnection` empties the staging `audioQueue`, then
`audioManager.resetPlaybackClock()` stops the scheduled sources and resets the
playback clock **without setting `playbackBlocked`** (the model speaks a NEW
generation on the same connection, so an unpaired block would kill it -- the
nm7z trap; `flushAudioQueue` keeps the blocking behavior for the
pause/section-switch paths and delegates the drain).
See [voice-ai.md](../components/voice-ai.md#barge-in).
**Push-to-talk** (`setPushToTalkMode(true)`) is the ONLY mode -- there is no
alternative to be the default against (bd polyglot-pdf-v1m8g) -- and it disables
the energy-based barge-in path entirely (`onVADSpeechStart`/`End` early-return).

> **The instant client-side flush does not run.** It lived on the Silero
> `onVADSpeechStart` path, which PTT mode early-returns from — and PTT is the only
> input mode (bd polyglot-pdf-v1m8g). Interruption is Gemini's own
> `server_content.interrupted`, and the forwarded `interrupted` message (above) is
> what drains the client, so barge-in latency is that round-trip rather than
> instant. Measured on the RUDE harness arm, the drain cut stale playback backlog
> at field updates from mean 1.10s to 0.14s (bd s7uf; the wire-order fix is part
> of that bundle). **The PTT button is now the only barge-in gesture**; whether
> typing should also barge in is deferred (bd polyglot-pdf-6fau6).

There's a barge-in **grace period**: tool calls arriving within
`BARGE_IN_GRACE_PERIOD_MS` (150ms, a constant in
`frontend/src/shared/metrics.ts`) of a barge-in are treated as hallucinations from
the interrupted generation and rejected (`metrics.recordToolCall` → `reject`; see
`connection.ts onFieldUpdate`).

## Manual / voice mode (the sticky control)

The voice UI is exactly TWO controls, and that limit is a design constraint
rather than an aesthetic one: many users touch this app once, so anything needing
explanation has to fit in about a sentence of the spoken introduction.

| Control | Sticky? | What it does |
|---|---|---|
| **Push-to-talk** | No | Press to talk. Also the only barge-in gesture. |
| **Manual / voice mode** | Yes | Whether the model speaks on its own. |

**Manual mode suppresses the model's PROACTIVE speech; it does not suspend the
session.** The WebSocket stays up, the Gemini session stays warm, the mic stays
usable, and field/focus tracking keeps running underneath -- so the assistant is
correctly oriented the instant the user wants it. This is the operating mode for
the "mostly manual" profile: present but quiet.

**The gate is at the backend adapter, and that placement is the whole design.**
Every text turn this app sends carries `turn_complete=True` -- it ASKS the model
to respond. So muting the speaker client-side would leave the model talking into
a discarded buffer: billed, unheard, and then waiting on an answer to a question
the user never received. `LiveAIGemini.set_voice_muted(True)` instead drops the
turn before it reaches Gemini, across both elicitation paths
(`send_text_message`, the queued hints; and `send_client_content`, the direct
"speak now"). A held `send_client_content` returns **False** -- not-delivered --
which callers already handle; the validator steer in particular must not HOLD a
section on speech nobody heard.

**Context is held, not lost.** The newest suppressed turn is kept and replayed
onto the ordinary text queue on unmute, so the model resumes oriented. Only the
newest: these messages restate whole current state ("the next unfilled field is
X"), so an older one is a stale contradiction rather than extra information, and
replaying a backlog would bill for every one.

The held turn is **cleared only once it has actually reached a live queue.** A
section switch tears the session down (`_text_queue = None`) and the next connect
builds a new one; an unmute landing between the two would otherwise drop the
context silently, since a put on an orphaned queue raises nothing and nobody
drains it. Deferring instead means the next turn on the fresh session carries it,
and a newer turn still wins -- an unmute during that gap degrades to "replay a
moment later" rather than losing the re-orientation.

For that to hold, **both** elicitation paths check the mute flag BEFORE their
queue/session guards. A hint arriving while muted and mid-teardown must still be
recorded, or the deferred replay voices an OLDER hint as if it were current --
the model naming the wrong field confidently, which is worse than saying
nothing.

**A PTT press leaves manual mode**, at both ends: the client flips its own toggle
in `sendActivityStart`, and the backend unmutes on `vad_activity_start` before
forwarding it. Pressing to talk is an unambiguous request for the assistant, so
it must not require finding the toggle first.

**The mode is client-owned and re-asserted on every (re)connect.** The backend is
stateless and each new Gemini session defaults to speaking, so `onSessionReady` /
`onSessionRestarted` re-send it -- otherwise a GoAway or auto-drop would silently
put a user back into a talking session. Wire format: `voice_mode` /
`voice_mode_ack` (see `docs/standards/ws-protocol.md`); an unrecognised `mode` is
rejected rather than coerced, because the failure mode of a wrongly-silenced
session is a user who concludes the app is broken.

> **`pause()` / `resume()` are DEAD PATH.** They suspended the session -- mic torn
> down (the user went mute, not merely deaf), Gemini's in-flight question
> discarded client-side, and a paid 1.5s debounced `recovery_prompt` re-ask
> (bd polyglot-pdf-yo5t) needed just to come back. The mode toggle replaced the
> only UI caller (bd polyglot-pdf-wurj8), so nothing now sets status `'paused'`;
> removing the machinery is bd polyglot-pdf-oaidu. `recovery_prompt` has no
> remaining production caller.

## Mic send gate (audio-up path)

Every mic-arming site shares ONE send callback in
`frontend/src/shared/connection.ts`, gated by the pure function
`shouldSendMicChunk(status, socketOpen)` (bd polyglot-pdf-xroy). A single
`rehydrateAudio(reason)` routine (bd polyglot-pdf-z9bc) owns arming for every
reconnect / session-restart path: `resume`, `startSection`, `switchToSection`,
`rearmAudioCapture`, and the `onSessionReady` / `onSessionRestarted` callbacks
(the latter is how the automatic/internal reconnects -- GoAway pre-emptive resume
and auto-drop -- re-sync). Because `session_ready` also fires on the FIRST
connect, `rehydrateAudio` runs on initial connect too -- it races the overlay's
connect-poll `startRecording`, which the in-flight `arming` guard in
`audioManager.startRecording` makes safe (the second caller awaits the first
instead of double-arming). `rehydrateAudio` is idempotent: a no-op under the test
harness and while paused; it skips the arm when already recording (the mic
worklet + playback `AudioContext` survive a socket swap, so on GoAway/auto-drop
audio self-heals -- a pure PTT-mode re-sync); it re-applies the PTT gate MODE
always, but only (re)sets mute/unmute when it ARMED A FRESH mic. That fresh-arm
mute decision reads the CURRENT push-to-talk hold state (bd polyglot-pdf-qt7w):
`pushToTalkMode && !held -> mute, else unmute`, read AFTER the arm await. The
overlays drive that hold state via `connectionManager.setPushToTalkHeld(true/false)`
from their PTT press / release / force-release / unmount handlers. Reading it
last means a press that lands DURING the arm await leaves the fresh mic unmuted
(the user's in-progress utterance is not truncated), and a press that lands after
still wins via its own `unmuteInput()`. Combined with the already-recording skip
above (a reconnect that finds the mic still live never touches mute at all), no
reconnect can re-mute an active hold. The shared send callback is then gated by:

- `connected` → always send.
- `switching_section` **with the WebSocket open** → send. Safe because the
  backend discards switch-window audio server-side on BOTH switch paths: the
  `drop_audio` flag in `websocket_routes.py` (manual switch), and
  `FormFillingService.stream_audio`'s `_switch_lock.locked()` backstop, which
  also covers the AI-initiated `switch_section` swap.
- Anything else (or socket closed) → **drop, never silently**: a rate-limited
  (~1/s) `console.warn` reports the status + socket state. Silent mic loss is
  what made the 2026-06-10 demo hang invisible.

The demo's mic-energy meter (visual level indicator, bd polyglot-pdf-s3zv) only
**reads** this same send gate to decide whether to animate -- it does not alter
`shouldSendMicChunk` or introduce a second gating path.

Every `WebFormConnection.status` transition is logged `old->new (reason)` so a
stranded status is visible in the console.

**Spell-back hold** (bd polyglot-pdf-22h1f, flag-gated `SPELLBACK_TOOL_ENABLED`):
while the deterministic spell-back TTS clip plays, `audioManager.
setSpellbackHold(true)` hard-gates the mic: the frame is DROPPED, so the clip
cannot leak back in as user speech. (It used to branch -- substituting zeroed
frames under native VAD, to keep the continuous stream that detector needed alive
-- but with native VAD gone there is nothing requiring a continuous stream, so
the drop is unconditional; bd polyglot-pdf-v1m8g.) The tool response is held open for the whole
clip, but that does NOT park the model (bd polyglot-pdf-kvrfq, wire-verified
2026-08-26): under user barge-in pressure it keeps emitting further
`name_spellback` calls, which queue behind the backend's blocked receive loop
and arrive as stale duplicates once the round-trip settles. A PTT
press mid-clip releases the hold FIRST (the user's barge-in audio flows), stops
the clip, and resolves the round-trip as `interrupted`; a request that ARRIVES
while PTT is held, within the post-interrupt cooldown, or duplicating a
just-delivered value is refused up front by `spellbackPlayer.play()` -- no
playback, no mic hold (details in
[voice-ai.md](../components/voice-ai.md)'s `name_spellback` bullet).
NOTE: the E2E harness's
injected audio bypasses the worklet and therefore this hold -- the hold is
pinned by unit tests (`audioSpellbackHold.test.ts`), not by harness behavior.

## fill-language vs spoken-language

Two independent language axes — don't conflate them:

- **fill-language** — the language values are written into the form in. Changed via
  `change_fill_language` (`service.change_fill_language`); defaults to `English`.
- **spoken-language** — the language Gemini *converses* in. **PINNED for the whole
  form.** See the rule below; the two axes differ here, and that asymmetry is
  deliberate: fill-language is data, spoken-language is session config.

### SPEC: the spoken language is pinned per session (maintainer policy)

**Mid-conversation language switching is NOT supported.** The spoken language is
chosen once, before the form starts, and held for every turn of that session:

- The **system instruction** tells the model the language is fixed for the whole
  form, and to answer a user who asks to switch by explaining they would need to
  start over via the control that clears the form. **The SI describes that
  control by what it DOES and must never name it** -- the on-screen label is
  translated per session language (`frontend/src/demo/overlayTranslations.ts`;
  Spanish shows "Borrar formulario"), so an English label in the SI would have
  the model name a button the user cannot see. That is the bd polyglot-pdf-s863
  defect, which the disclaimer path solves differently -- by threading the
  client's TRANSLATED label through `{agree_button_label}`. There is no such
  placeholder here (this clause is static SI, not a per-turn template), hence the
  describe-don't-name rule.
  (The SI previously said the opposite of the whole policy -- "only the user's
  explicit request to switch changes the session language" -- which told the
  model to honor a switch the app cannot service; bd polyglot-pdf-87a9.)
- The user picks it in `LanguageSelectionModal` — a one-time entry gate, bound only
  to `handleInitialLanguageSelect` in both overlays.
- It is pinned into the per-connect Gemini config (the ASR `language_codes` bias,
  `backend/utils/language_codes.py`) and into the system instruction, at session
  start. The model is expected to hold it for the entire form.
- **The only way to change it is a NEW session:** "clear form", then choose again
  in the modal.

So a session's spoken language never changes after it starts. Code that assumes
otherwise is wrong, not merely unused.

**`change_spoken_language` is a misnomer for what it now does.** The WS message
survives, but its ONLY live sender is `webFormConnection`'s reconnect opener
(`webFormConnection.ts`, the `session_ready` path), which **re-asserts the SAME
pinned language** after a socket teardown — a section switch or a reconnect drops
the Gemini session, and the opener re-establishes the language and the current
field. It is a re-assertion, not a switch. The backend handler
(`websocket_routes.py`) correspondingly re-sends the initiating message.

The UI paths that once switched language on a live session
(`handleLanguageChange` in both overlays, `connectionManager.changeSpokenLanguage`)
were **removed** in bd polyglot-pdf-87a9: they were wired to nothing, but their
presence implied a supported flow that does not exist.

## Hallucination reduction

Two standing mitigations:
- **Single-field updates only.** `update_form_fields` takes ONE field per call;
  multi-field updates raised hallucination rates. (Marked HALLUCINATION_REDUCTION
  in config.py.)
- **No proactive audio.** Gemini's `proactive_audio` connect option is never set:
  enabling it made Gemini ignore dirty/choppy audio but also stop calling tools,
  so the adapter must not turn it on. (The old `PROACTIVE_AUDIO` config flag was
  removed as dead code — it was hardwired `False`.)
