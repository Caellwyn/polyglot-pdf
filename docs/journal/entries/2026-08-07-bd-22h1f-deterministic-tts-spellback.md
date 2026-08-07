---
date: 2026-08-07
bead: polyglot-pdf-22h1f
title: "Deterministic TTS spell-back: name spelling out of the model's speech path"
sprint: 19
tags: [hotfix, harness, testing]
---

## Trigger

P0, demo/investor risk. The bd 0rpu investigation (2026-08-05/06, ~10 live
harness runs, evidence corpus PR #558) proved the native-audio Live model's
SPEECH path has a sticky-first-spelling attractor: on spelled name read-backs
the audio re-emits the session's FIRST spelled name (audio says J-O-H-N while
the text track and every tool call correctly say JOSHUA or JOSE) on 9.7% of
scoreable spelled generations (control arm, LIVE_TEMPERATURE=0.4). Four
mitigation levers were tested and rejected (re-anchor injection ran away at
$9.93/105s; NATO prompting ignored; comma pacing obeyed but did not fix;
tool-echo thinning a no-op), and the half-cascade tier is permanently barred
for latency. Conclusion: the spelling must leave the model's speech path
entirely.

## What shipped

The `name_spellback` tool (flag `SPELLBACK_TOOL_ENABLED`, default OFF -- lands
dark; cutover is a later deliberate change):

- **Backend**: tool declaration (`SPELLBACK_TOOL_DECLARATION`, appended by
  `_build_tool_declarations` only while the flag is on -- kept out of
  `TOOL_DECLARATIONS` so the default declared contract is byte-identical);
  `CallbackHandler._handle_name_spellback_tool` with three response variants
  (delivered / interrupted / error), every one of which forbids the model from
  spelling itself; `RequestCoordinator.request_spellback` -- the ONE round-trip
  that deliberately holds the Gemini receive loop for the playback duration
  (90s cap; the model is parked on the pending tool response, which is the
  point); `POST /api/tts/spellback` (auth-gated, 503 while the flag is off,
  never logs the value) synthesizing a letter-by-letter en-US Cloud TTS MP3
  via per-character `say-as` SSML with 400ms breaks; `DTI_SPELLBACK_SI_ADDENDUM`
  appended to the DTI SI while the flag is on so the model stops spelling
  aloud (double delivery -- corrupted then correct -- is worse than either).
- **Frontend**: `handleSpellbackRequest` resolves the CURRENT field with the
  pin-aware NEXT-FIELD computation, computeNextField (a client-only
  resolution -- deliberately NOT confirm_field's backend-coerced field_id
  mechanism; fresh-eyes round 1 corrected the docs that claimed parity) (the
  tool takes NO
  arguments -- nothing for the model to hallucinate, bd jnjj.46), reads the
  stored value through the []-alias fallback (bd h7wx: never model memory),
  and delegates to the connection manager: sustained-quiet drain wait on the
  model's playback backlog, TTS fetch with the Firebase bearer token, blocking
  `HTMLAudioElement` playback, ack with status + `playback_ms`/`fetch_ms`.
  `audioManager.setSpellbackHold` gates the mic in EVERY input mode during the
  clip (silence-substitution under native VAD to keep the stream continuous;
  frame-drop in manual modes). A PTT press mid-clip stops playback, releases
  the hold, and resolves the round-trip as `interrupted` -- the model is told
  to listen to what the user says next.

## Key design decisions

- **Letters-only clip; the model frames it.** The clip carries ONLY the
  spelled characters. The model announces the read-back and asks "is that
  correct?" in the session language with its own voice -- prose was never
  observed corrupted, only spelled letter sequences, and this sidesteps
  needing the framing phrase in 17+ languages.
- **Always en-US letters.** English letter names in every session language is
  the SI's NAMES invariant (the letters are what is written on the English
  form); a session-language voice would read letter names in that language or
  transliterate unpredictably.
- **Client resolves everything.** Backend stateless; the wire messages carry
  no field id and no value in either direction.
- **Present-but-empty `parameters` schema** on the declaration: a name-only
  declaration is the wire-verified 2.5 native-audio 1011 hazard (bd daa/h04c).
  No 1011s were observed across the validation runs.

## Validation (W-7 harness, live Vertex 2.5 native audio, temp 0.4)

Run 1 aborted on the STALE bundled form-kits copy (frontend/public/form-kits
served a 59-field w7 while the worktree kit has 53 -- the exact trap in the
memory files); fixed with a junction to the worktree kits. $0.12.

Run 2: **PASS 15/15** fields filled+confirmed, all 6 spelled names correct
(JOHN JOSHUA JOHNSON MARIA JOSE SMITH), zero retries on every name field.
name_spellback: 6 delivered (one per name), 4 premature calls correctly
redirected by the error variant ("fill first"). Cloud STT scoring of the
model's output audio: 32/32 generations scoreable, ZERO spelled-letter runs in
the model's audio -- the defect surface is gone, not just quiet (baseline
control had 3/31 corrupted spelled read-backs). Two UTTERANCE_DESYNC rows are
non-name street/city read-back wording quirks, out of this bead's scope.
Delivered spell-backs held the tool response 4.3-7.1s (median 5.5s) covering
drain-wait + TTS fetch + full letter-by-letter playback; the clip REPLACES the
model's own spoken spelling inside the SAME verification turn (the maintainer's
ride-along question: answered, no extra turn). $1.30 / 79 turns.

Run 3: **PASS 15/15**, zero retries on all six name fields. name_spellback 6/6
delivered (no premature calls this time), round-trip median 5.0s (4.4-7.0).
Cloud STT: 32/32 scoreable, **0 desync**, zero spelled-letter runs in the
model's audio. $1.20 / 75 turns. One instructive wrinkle: the input ASR
misheard the injected J-O-S-E fixture and the model filled `JOSC` -- the
spell-back then faithfully played J-O-S-C (the STORED value, as designed) and
the harness's scripted "yes" confirmed it. That is an INPUT-path mishear, a
different defect class from 0rpu's output substitution -- and it is exactly
the case spelled verification exists to let a real user catch. The tool's
guarantee is "the read-back always matches the stored value", not "the stored
value is always right".

Total live spend for the validation: ~$2.65 (guarded by run_guard, cap $2/run;
TTS+STT costs are fractions of a cent). Exit criteria: (1) spell-back audio
produced outside the Live model's speech path from the stored value only --
shipped; (2) spelled read-backs match the stored value in every scoreable
generation across 2 runs -- met (zero model-spelled generations; clips are
deterministic functions of the stored value; harness values verified per
field); (3) latency/turn cost measured, ride-along achieved (no extra turn) --
this entry + the PR report.

## Fresh-eyes triage (Step 5.5, round 1: GAPS-FOUND (4) -> all adopted)

1. ADOPTED (blocker-adjacent): the SI addendum was appended only in the DTI
   branch while the tool declaration gates only on the flag -- a legacy-SI
   session with the flag on would keep its spell-it-yourself wording alongside
   the live tool (double delivery). Fix: the addendum now rides BOTH SI modes;
   pinned by a new legacy-mode test.
2. ADOPTED: disconnect()/pause() mid-clip left the HTMLAudioElement audibly
   playing and the playback promise pending forever. Fix: `cancelSpellback()`
   on both paths.
3. ADOPTED (docs): the docstrings/doc claimed the client's field resolution was
   "the same as the confirm path" -- it is the pin-aware NEXT-FIELD computation
   (client-only), distinct from confirm_field's backend-coerced field_id.
   Reworded in code, ws-protocol.md, and this entry.
4. ADOPTED (nit): client-side 60-char pre-check before the TTS fetch (mirrors
   the backend cap) so a mis-targeted long value fails fast.
Round 2: GAPS-FOUND (2 + 2 notes) -> all adopted:
1. ADOPTED (blocker-adjacent): playSpellback's module-scoped clip state had no
   reentrancy guard -- a retry after a hung fetch could let the STALE call's
   cleanup release the mic hold mid-clip of the LIVE call (the feature's core
   safety invariant). Fix: extracted the whole state machine to
   `spellbackPlayer.ts` with pre-emption + a per-call generation guard +
   cancellation poisoning + a 20s fetch timeout; the guard is mutation-verified.
2. ADOPTED: `getPlaybackBacklog`'s MEASUREMENT-ONLY comment was made false by
   this very diff (the drain-wait now gates on it) -- re-commented LOAD-BEARING.
3. ADOPTED (coverage): the player now has its own unit suite (delivered / PTT
   interrupt ordering / cancel mid-playback / cancel mid-fetch / reentrancy /
   fail-fast / error mapping).
4. ADOPTED (doc nit): ws-protocol reason-token list completed
   (value_too_long, no_audio_manager, cancelled).
Round 3: GAPS-FOUND (1 + 1 note) -> both adopted:
1. ADOPTED (blocker-adjacent): a PTT press during the PRE-PLAYBACK window
   (drain-wait/fetch, up to ~28s worst case) was silently swallowed --
   interruptForPtt only handled the audible-clip phase, so the hold stayed
   engaged through the press and the clip then played over the user. Fix:
   the press now wins in that window too (hold released immediately, the
   parked call resolves the interrupted variant); mutation-verified test.
2. ADOPTED (note): the mirrored 60-char cap (backend MAX_SPELLBACK_CHARS /
   frontend SPELLBACK_MAX_CHARS) is now pinned to each other by a backend
   static test, so the constants cannot drift silently.
Round 4 verdict: NO-GAPS (two low-confidence notes, non-blocking). Scorer
note: both runs reported `needs_hand_check: []` -- no rows required hand
adjudication.

## Outer (Opus cross-surface) triage -- round 1: GAPS-FOUND (8)

Fixed inline (the filed beads close with this PR):
1. bd 4uytx: texttospeech.googleapis.com was missing from BOTH deploy scripts'
   API-enable lists -- the cutover flag-flip would 502 opaquely. Added (no
   extra IAM role needed; synthesis needs only an authenticated principal).
2. bd fjb2k: the blocking playback await had no timeout -- a stalled <audio>
   (OS audio interruption on mobile) would gate the mic FOREVER, with no PTT
   press available in open-mic mode. Added a value-proportional playback
   watchdog (15-80s), mutation-style pinned by a test.
3. bd dtywl: the name_spellback dispatch arm was not flag-gated -- a
   hallucinated call while dark ran the whole round-trip (mic hold,
   receive-loop block, PII value POSTed to a 503 route). Now refuses in-band
   immediately via an injected-settings getter (same principle as
   _get_use_dti), fail-closed; test added.
4. bd j6fxt: the SI addendum's blanket wording contradicted SPEECH STYLE's
   digit-by-digit number read-back. Re-scoped to LETTERS only, with the digit
   behavior explicitly preserved; pinned by test.
5. (unfiled note) AbortSignal.timeout is unpolyfilled on older mobile Safari
   -- now feature-guarded (degrades to no client-side fetch timeout; the
   backend's 90s cap still bounds).
Deferred as beads (open, future work):
6. bd a43y4: the E2E harness bypasses the mic hold and cannot observe clips
   -- a harness-observability improvement for future measurement runs.
7. bd flnz1: the interrupted variant is PTT-only; open-mic native-VAD users
   cannot barge into a clip (clips are short + now watchdog-capped; whether
   voice barge-in should interrupt a clip is a product/UX call at cutover).
   ws-protocol row now documents the mode-dependence.
Raised to the maintainer (design consequence, not a defect):
8. The 90s tool-response hold blocks the Gemini receive loop, so a GoAway or
   interrupted event arriving mid-clip is processed late (worst case ~its
   duration; typical clips 5-7s, watchdog-capped). Bounding this would
   revisit the maintainer-approved blocking design -- reported in the PR.

## Voice matching (maintainer ask, mid-review 2026-08-07)

The clip now defaults to the SAME persona as the Live model: Cloud TTS's
Chirp 3 HD family carries the Live API's prebuilt voice names, so
LIVE_VOICE_NAME derives en-US-Chirp3-HD-<name> (endpoint-verified accepting
this feature's SSML with Iapetus). SPELLBACK_TTS_VOICE overrides explicitly;
resolution in spellback_tts.resolve_spellback_voice, pinned by test.

## Doc freshness

Bumped: voice-ai.md, tool-call-flow.md, websocket-routing.md, ws-protocol.md,
voice-and-vad.md (spell-back hold), technical_guide.md (Surface contracts).
Reviewed-and-left: testing.md (tracks requirements.txt; the dep add changes no
testing policy), validation-delegation.md (stale only via files this branch did
not touch -- pre-existing).

## Traps for the future

- The FE static form-kits copy is gitignored and goes stale silently; junction
  `frontend/public/form-kits` -> the worktree's `form-kits` before any
  schema-dependent voice test (this repo's third hit on this trap).
- Harness-injected audio bypasses the worklet, so `setSpellbackHold` does NOT
  gate the E2E driver's injections -- fine for the harness (its "yes" lands
  after the tool response), but do not read harness behavior as proof the
  mic-hold works; the unit tests pin that layer.
- The dev-file logger writes unit-test tool calls into the same dated
  `gemini_<date>.jsonl` as live runs -- rotate per run before scoring, or the
  scorer joins against test noise.

## Left open

- Secretary arm for spelling PAST fields: bd polyglot-pdf-m8iov.
- Cutover (flag default flip + SI NAMES wording replacement at the SI-slimming
  session's marker + retiring the addendum): sequenced in bd 22h1f, blocked on
  the SI session landing its marker. ~60 SI-pinning test assertions will need
  the same PR.
- `LIVE_TEMPERATURE` for the demo is a Cloud Run env decision at deploy time.
