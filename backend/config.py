from __future__ import annotations

from functools import lru_cache
from pydantic import BaseModel, model_validator
import os
import re
from pathlib import Path


# === Native audio-to-audio model tiers (A/B-able) ===
# Both are full native audio-to-audio Live API models (bidiGenerateContent).
# USE_PREMIUM_MODEL flips between these (defaults FALSE -> standard/2.5):
#   standard -> gemini-2.5-flash-native-audio-preview-12-2025 (DEFAULT; reliably
#               emits the update_form_fields tool call; family 2.5)
#   premium  -> gemini-3.1-flash-live-preview            (opt-in; family 3.1)
# NOTE on 3.1 tool-calling: the historic "3.1 skips update_form_fields ~50%"
# finding (bd polyglot-pdf-5oq) was traced to the update_form_fields `value`
# param being declared with NO type -- under google-genai 2.8.0, 3.1 rejects an
# untyped required param (it verbalizes "I had an issue processing that value").
# With `value` typed as "string" (see TOOL_DECLARATIONS), 3.1 emits the call
# reliably (5/5, 2026-06-11, bd polyglot-pdf-i9q8). 2.5 tolerated the untyped
# param, which is why only 3.1 showed the defect.
# NOTE: Gemini model naming is inconsistent across Google's sources -- the 2.5
# native model also appears as `gemini-live-2.5-flash-preview` (the old MODEL_LIVE
# default), and that exact string 1008'd ("not found for bidiGenerateContent") in
# the contract test. We pin the explicit `-preview-12-2025` string above, which is
# verified to connect and return audio. Don't infer native-vs-cascade from a name;
# verify against the live endpoint. See docs/genai_docs/README.md.
MODEL_NATIVE_PREMIUM = "gemini-3.1-flash-live-preview"
MODEL_NATIVE_STANDARD = "gemini-2.5-flash-native-audio-preview-12-2025"
# Vertex publishes the 2.5 native-audio Live model under a DIFFERENT id than AI
# Studio: the AI Studio id above is NOT available on Vertex in any region (a Live
# bidiGenerateContent connect 1008s), and this Vertex id is not on AI Studio.
# Both are 2.5-family native-audio, so model_family() bills them identically; only
# the service-specific id differs. Verified connecting + returning audio on Vertex
# us-central1 (the adapter's default location), bd polyglot-pdf-a079. _resolve_model
# selects this when VERTEXAI=true and the standard tier is active, so a Vertex
# deploy works WITHOUT having to pin MODEL_NATIVE by hand. There is no Vertex 3.1
# (premium) id yet: 3.1 is AI-Studio-only as of 2026-06, so the premium tier still
# requires VERTEXAI=false.
MODEL_NATIVE_STANDARD_VERTEX = "gemini-live-2.5-flash-native-audio"

# --- DEV FEATURE: model A/B toggle (bd polyglot-pdf-kbf) -----------------------
# To A/B these two models for tool-call reliability (e.g. "does 3.1 emit
# update_form_fields less reliably than 2.5?"), flip USE_PREMIUM_MODEL and
# restart the backend -- each run is one clean sample. Locally, the dev runner
# does this for you:
#     ./scripts/dev-local.ps1                 # standard / 2.5 (default, mirrors prod)
#     ./scripts/dev-local.ps1 -Model premium  # premium / 3.1
# The active model is recorded on every structlog line (bound `model=...`) and on
# every dev I/O capture entry (`model` field in gemini_<date>.jsonl), so a
# captured session is unambiguously attributable to one model. Pricing is
# family-aware (GEMINI_PRICING_BY_FAMILY) so cost tracking stays correct across
# the swap. To pin an exact id instead of the flag, set MODEL_NATIVE in the env.
# ------------------------------------------------------------------------------



class Settings(BaseModel):
	# === Model selection (env-swappable for A/B testing without redeploy) ===
	# We run native audio-to-audio Live models only (no cascade/half-cascade).
	# USE_PREMIUM_MODEL flips between the two tiers above; MODEL_NATIVE is the
	# RESOLVED active model (derived below), kept as a field so /health, pricing,
	# and dependencies can read the single source of truth. Set MODEL_NATIVE
	# directly via env to pin an exact model string (overrides the flag).
	# MODEL_LABELING: Model for field labeling/normalization (normalizer currently
	#   deprecated; kept as an env-swappable knob and surfaced on /health).
	# Default FALSE -> 2.5 (gemini-2.5-flash-native-audio-preview). BOTH families
	# now emit update_form_fields reliably: the historic "3.1 only calls the tool
	# ~50% of the time and confabulates a 'trouble saving' message" defect (bd
	# polyglot-pdf-5oq, probe_tool_call.py 2026-06-07) was the UNTYPED `value`
	# param, not the model -- under google-genai 2.8.0 3.1 rejected the untyped
	# required param; typing it "string" restored the call 5/5 (bd
	# polyglot-pdf-i9q8, 2026-06-11). 2.5 remains the default for its audio-path
	# behavior, not its tool-calling. 2.5's known tradeoff is intermittent silence
	# on the AUDIO path (no-audio turns / 1011 -- bd polyglot-pdf-daa), mitigated
	# separately. (3.1 is modestly pricier -- text-out 4.50 vs 2.00/1M; audio
	# in/out identical -- see GEMINI_PRICING_BY_FAMILY.)
	USE_PREMIUM_MODEL: bool = os.getenv("USE_PREMIUM_MODEL", "false").lower() == "true"
	MODEL_NATIVE: str = os.getenv("MODEL_NATIVE", "")  # resolved in _resolve_model if unset
	MODEL_LABELING: str = os.getenv("MODEL_LABELING", "gemini-2.5-flash")
	# Secretary tail-latency guard (bd polyglot-pdf-jnjj.43). The ask_secretary call
	# is BLOCKING (the live "principal" model waits on the tool result mid-turn);
	# Gate 2 (jnjj.27) measured a heavy tail (median ~1s but spikes to 8.5s / 20s).
	# Two bounds:
	#
	# SECRETARY_DEADLINE_S -- how long the SYNCHRONOUS tool call waits before it stops
	#   blocking and returns a "pending" tool result so the principal's turn is not
	#   held open for the tail. The still-running lookup is detached; when it lands the
	#   answer is DELIVERED on a follow-up turn (send_client_content) and the principal
	#   voices it. The "I'm working" UX is the gap-based thinking indicator (bd wpw.5),
	#   which spans user-turn-end -> first-response-audio and so covers this wait for
	#   free -- NO spoken live-model filler turn is spent here (cost lever, maintainer
	#   2026-06-29). Tune against live UX; ~2.5s keeps the median (~1s) lookup on the
	#   fast synchronous path while bounding how long the principal's turn blocks.
	# SECRETARY_TIMEOUT_S -- the HARD CAP on the model call itself (both the sync wait
	#   and the detached background lookup are bounded by it), so a 20s spike or a
	#   stalled call never runs unbounded. The preceding client form-state round-trip
	#   has its own ~5s coordinator timeout (separate from these).
	SECRETARY_DEADLINE_S: float = float(os.getenv("SECRETARY_DEADLINE_S", "2.5"))
	SECRETARY_TIMEOUT_S: float = float(os.getenv("SECRETARY_TIMEOUT_S", "8.0"))
	# Whether to use Vertex AI (now "AI Agent Platform") for LLM operations.
	#
	# VERTEX IS THE ONLY PRODUCTION PATH (maintainer directive 2026-08-04, bd
	# polyglot-pdf-5e6a). Vertex's privacy agreement is what prevents Google
	# from using client data for model training -- the product's privacy promise
	# depends on it, so AI Studio is NEVER acceptable on a deployed service.
	#
	# True (DEFAULT) -> Vertex via service-account ADC + GOOGLE_CLOUD_PROJECT.
	# False -> Gemini Developer API (AI Studio) via GEMINI_API_KEY. Permitted
	#   ONLY for LOCAL development -- e.g. testing gemini-3.1-flash-live-preview
	#   before it reaches Vertex GA. A deployed service (K_SERVICE set by Cloud
	#   Run) REFUSES TO START on this path; there is no override flag. 3.1 ships
	#   only once it is GA for Vertex customers.
	VERTEXAI: bool = os.getenv("VERTEXAI", "true").lower() == "true"
	# CRITICAL VAD MODE TOGGLE (bd polyglot-pdf-333).
	#   False (DEFAULT) -> NATIVE mode: Gemini's own automatic VAD drives turn
	#     detection. The adapter sends the VAD_* sensitivity knobs below; the
	#     frontend stops sending manual activity_start/end and streams continuous
	#     audio (incl. silence) so Gemini's VAD has a stream to detect on.
	#   True -> MANUAL mode: Gemini's VAD is off ({'disabled': True}); turn-taking
	#     is driven by frontend client-side (Silero) VAD via manual activity
	#     signals. This is the single revert switch.
	# Env-overridable so demo/prod can flip without a code edit. See
	# docs/standards/voice-and-vad.md.
	DISABLE_GEMINI_VAD: bool = os.getenv("DISABLE_GEMINI_VAD", "false").lower() == "true"
	GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")

	# Audio settings
	AUDIO_IN_RATE: int = 16000
	AUDIO_OUT_RATE: int = 24000
	MAX_UPLOAD_MB: int = 5
	WS_CHUNK_MS: int = 20
	# Backend audio-cadence gap-filling (bd polyglot-pdf-7f7m). Native-VAD mode
	# requires a CONTINUOUS PCM stream to Gemini; a stutter/gap on the client can
	# starve the server keepalive and trigger a 1011 close. When enabled, the
	# audio sender emits a synthetic silence frame if no real chunk arrives within
	# AUDIO_GAPFILL_INTERVAL_MS during an active stream, so the wire cadence never
	# breaks. Env-overridable so the demo can flip it without a redeploy. The
	# interval defaults to one chunk plus a small jitter margin (WS_CHUNK_MS 20ms +
	# ~5ms) so it fills only genuine gaps without racing real audio -- keeping the
	# worst-case wire gap within ~one chunk interval (the 7f7m exit criterion), not
	# two (a 40ms default left recurring ~20ms gaps between silence frames).
	AUDIO_GAPFILL_ENABLED: bool = (
		os.getenv("AUDIO_GAPFILL_ENABLED", "true").lower() == "true"
	)
	AUDIO_GAPFILL_INTERVAL_MS: int = int(os.getenv("AUDIO_GAPFILL_INTERVAL_MS", "25"))
	# Real-time audio pacing to Gemini (bd polyglot-pdf-3to5). The client sends mic
	# audio at exactly 1.0x real-time but in bursty 8ms frames; the OLD sender
	# forwarded each frame immediately AND injected an un-paced gap-fill silence
	# frame on every sub-interval gap, so the outbound stream ran ~2.2x real-time and
	# tripped a recurring Gemini 1011 "sending data too fast". When AUDIO_PACING_ENABLED
	# the sender instead runs a fixed WS_CHUNK_MS monotonic-clock tick: it re-chunks a
	# byte accumulator to exactly one WS_CHUNK_MS frame per tick, so the wire cadence
	# is real-time (never faster), and gap-fill silence is emitted ONLY on a genuine
	# underrun tick. When disabled, the legacy wait_for/timeout gap-fill path runs
	# (a clean revert switch). AUDIO_MAX_BUFFER_MS bounds how far behind real-time the
	# accumulator may fall before the OLDEST buffered audio is dropped (frame-aligned),
	# capping added latency during a burst. Env-overridable for a no-redeploy flip.
	AUDIO_PACING_ENABLED: bool = (
		os.getenv("AUDIO_PACING_ENABLED", "true").lower() == "true"
	)
	AUDIO_MAX_BUFFER_MS: int = int(os.getenv("AUDIO_MAX_BUFFER_MS", "200"))
	WS_PING_INTERVAL_SEC: int = 15
	WS_IDLE_TIMEOUT_SEC: int = 120  # Close WebSocket after 120s of no received message (audio/ping/control)
	# B5 (bd polyglot-pdf-jnjj.17): backend-side fail-OPEN per-window bound for the
	# boundary validator. Since W1 (bd polyglot-pdf-xbl2) the validate() call runs in
	# a BACKGROUND task off the WS receive loop (one per window), NOT inline -- so this
	# no longer protects the receive loop from a hang (nothing awaits it there). It
	# still bounds each window's flash-lite call so a hung window fails open (returns
	# clean, no steer) instead of stalling its batch. Kept comfortably UNDER the
	# frontend's VALIDATOR_GATE_TIMEOUT_MS (6s) so a boundary that still feeds the
	# deprecated section-switch gate resolves before the client's gate gives up.
	VALIDATOR_TIMEOUT_SEC: float = 4.0
	# W1 (bd polyglot-pdf-xbl2): the async window validator runs one flash-lite call
	# PER WINDOW concurrently off the receive loop. Bound the fan-out so a batch of
	# many overlapping windows cannot open an unbounded number of simultaneous
	# flash-lite calls. Windows beyond the cap queue and run as slots free; each
	# still gets its own VALIDATOR_TIMEOUT_SEC. Per-window fail-open is unchanged.
	VALIDATOR_MAX_CONCURRENT_WINDOWS: int = 8

	# W6 (bd polyglot-pdf-gbus): the whole-form gemini-2.5-pro contradiction pass at
	# form_complete -- the SOLE end-of-form report, catching cross-page (far-pair)
	# contradictions the ~20-field lite windows cannot see. W5 (bd polyglot-pdf-g0w1)
	# measured pro far-pair recall = 1.000 (GO) with thinking bounded to 512.
	# DEFAULT-ON (maintainer directive 2026-08-03): the end-of-form report is part of
	# the product, and its per-form cost is a number we WANT in the accounting rather
	# than an unmeasured absence. Cost is bounded by design: the client's
	# maybeEmitFormComplete dirty-snapshot guard emits only when a COMPLETE form's
	# values actually changed, so a form costs ~1 call plus one per post-completion
	# edit (~$0.0093/call, thinking bounded to 512).
	# KNOWN LIMITATION, accepted knowingly: uncorrected whole-form PRECISION measured
	# 0.750 -- it over-flags the Part 5/6 preparer-interpreter certification block.
	# The anti-over-flag block ships in WHOLE_FORM_PRO_SI but has NOT been re-measured
	# since; expect some false-positive conflicts until bd polyglot-pdf-89mt re-runs
	# the numbers. Findings are REPORT-ONLY and the pass is fail-open at every layer,
	# so an over-flag surfaces a spurious question, never a block. Set
	# FORM_COMPLETE_PRO_VALIDATOR=false to disable without a redeploy.
	FORM_COMPLETE_PRO_VALIDATOR: bool = os.getenv("FORM_COMPLETE_PRO_VALIDATOR", "true").lower() == "true"
	# The pro model + its bounded thinking budget (W5 config; env-swappable like
	# EXTRACTOR_MODEL). thinking_budget must be > 0 for 2.5-pro (it cannot be turned
	# off); 512 is the W5-measured bound (in-band cost, p50 ~6s).
	VALIDATOR_PRO_MODEL: str = os.getenv("VALIDATOR_PRO_MODEL", "gemini-2.5-pro")
	VALIDATOR_PRO_THINKING_BUDGET: int = int(os.getenv("VALIDATOR_PRO_THINKING_BUDGET", "512"))
	# Fail-open ceiling for the single whole-form pro call (~2.5x W5 p90 7.5s). Above
	# this the pass returns clean (no report) rather than blocking form_complete.
	VALIDATOR_PRO_TIMEOUT_SEC: float = float(os.getenv("VALIDATOR_PRO_TIMEOUT_SEC", "20.0"))

	WS_MAX_AUDIO_FRAME_BYTES: int = 32000  # ~1s at 16kHz mono PCM16 (2 bytes/sample)

	# === DTI (Dynamic Turn Injection) Settings ===
	# The thin-principal SI mode (bd polyglot-pdf-jnjj.22): the system instruction
	# carries ONLY the static behavioral backbone plus the CURRENT field's guidance;
	# each next field's guidance rides the confirm_field tool response. No whole-form
	# field dump and no manifest. Env-gated, default ON (the production law of the
	# land, bd polyglot-pdf-7872); set USE_DTI=false for the legacy full-SI path
	# (SYSTEM_INSTRUCTION), kept for the measurement-harness baseline. DTI reuses
	# the manifest-first handshake transport (handshake_jit / jit_mode) -- that
	# transport survives the JIT-mode purge (bd polyglot-pdf-en2j); only the JIT
	# *SI mode* was removed.
	USE_DTI: bool = os.getenv("USE_DTI", "true").lower() == "true"

	# === Continuous-session mode (bd polyglot-pdf-x8rt) ===
	# When on, the whole form runs as ONE Gemini session bounded by the compression
	# window, instead of chopping the form into sections and resetting the session
	# at each boundary. The frontend builds a single whole-form handshake (one
	# synthetic "continuous" section carrying every field) and stops advancing
	# sections; the backend drops the switch_section tool and the "Section N of M"
	# metadata so the model never tries to navigate sections. Implies DTI (the SI
	# that carries no section guidance) + CONTEXT_COMPRESSION_ENABLED (the window
	# that bounds the now-unbroken context). Env-gated, default ON (the production
	# law of the land, bd polyglot-pdf-7872); set CONTINUOUS_SESSION=false for the
	# legacy section-reset flow (measurement-harness baseline).
	CONTINUOUS_SESSION: bool = os.getenv("CONTINUOUS_SESSION", "true").lower() == "true"

	# Disable model "thinking" tokens on the live session (default ON = thinking
	# off). We do not need chain-of-thought for the form-fill turn loop, and
	# thinking tokens are billed at the (expensive) output rate. For 2.5-family
	# models thinking_config={"thinking_budget": 0} turns it off and reduces
	# latency (genai codegen_instructions.md); the effect on native-audio Live is
	# unverified upstream (live-api-best-practices.md), so this is safe-if-ignored
	# rather than guaranteed. Only the 2.5 `thinking_budget` form is sent; 3.1 uses
	# a different `thinking_level` field and is left at its default. Env-flippable
	# (set DISABLE_MODEL_THINKING=false) if native-audio ever misbehaves with it.
	DISABLE_MODEL_THINKING: bool = os.getenv("DISABLE_MODEL_THINKING", "true").lower() == "true"

	# === VAD (Voice Activity Detection) Settings ===
	# Gemini Live API automatic activity detection sensitivity
	# START_SENSITIVITY: How quickly Gemini detects speech start
	#   - LOW: More conservative, fewer false positives, might miss quiet speech
	#   - HIGH: More aggressive, catches quiet speech, more false positives
	# END_SENSITIVITY: How quickly Gemini detects speech end
	#   - LOW: Waits longer for silence, reduces choppy cutoffs
	#   - HIGH: Ends faster, more responsive but may cut off pauses
	# Env-overridable (bd polyglot-pdf-4sv7: these were hard-coded literals, so
	# the deploy env could not tune Gemini-side VAD at all). Default START=HIGH:
	# measured on the audio path 2026-06-11, START_SENSITIVITY_LOW dropped 6/20
	# turns (incl. the short "yes" confirmations the demo kept missing) while
	# HIGH registered 20/20 -- see docs/standards/voice-and-vad.md.
	VAD_START_SENSITIVITY: str = os.getenv("VAD_START_SENSITIVITY", "HIGH")  # Options: "LOW", "HIGH", "UNSPECIFIED"
	VAD_END_SENSITIVITY: str = os.getenv("VAD_END_SENSITIVITY", "LOW")    # Options: "LOW", "HIGH", "UNSPECIFIED"
	VAD_PREFIX_PADDING_MS: int | None = int(os.getenv("VAD_PREFIX_PADDING_MS") or "500")  # Milliseconds of audio before speech start to include
	VAD_SILENCE_DURATION_MS: int | None = int(os.getenv("VAD_SILENCE_DURATION_MS") or "500")  # Milliseconds of silence before ending speech

	# === Context-window compression (Gemini Live) ===
	# Server-side ContextWindowCompressionConfig: a sliding window bounds the live
	# context so per-turn re-billing stops compounding (quadratic -> linear cumulative
	# cost) and audio sessions can run past the 15-min cap. Design + cost model:
	# docs/components/context-compression.md (epic polyglot-pdf-l3a, bead -45o).
	# All three are tuning knobs, not load-bearing constants: ENABLED gates the whole
	# feature (default ON -- validated by the jnjj.25 cost gate + the G3 correctness
	# gate, bd polyglot-pdf-7872). TRIGGER = tokens before a turn that fire
	# compression; WINDOW = target_tokens to retain (must be < trigger). Our sessions
	# peak near ~9k tokens, so the trigger must be low (~5k) to ever fire -- the docs'
	# 25k example would be inert here.
	CONTEXT_COMPRESSION_ENABLED: bool = os.getenv("CONTEXT_COMPRESSION_ENABLED", "true").lower() == "true"
	# `... or "default"` guards an EMPTY-STRING env value: os.getenv(key, default)
	# only returns the default when the var is UNSET; if it is set-but-empty (e.g.
	# CONTEXT_COMPRESSION_TRIGGER_TOKENS= in a deploy env file) it returns "", and
	# int("") raises ValueError at import -> the backend will not boot. Same hazard
	# class the VAD_*_MS knobs were hardened against (bd polyglot-pdf-46bu).
	CONTEXT_COMPRESSION_TRIGGER_TOKENS: int = int(os.getenv("CONTEXT_COMPRESSION_TRIGGER_TOKENS") or "5000")
	CONTEXT_COMPRESSION_WINDOW_TOKENS: int = int(os.getenv("CONTEXT_COMPRESSION_WINDOW_TOKENS") or "3000")

	# --- ASR language bias (bd polyglot-pdf-y25o) ---
	# When on, the Live connect config's input/output AudioTranscriptionConfig
	# carries `language_codes` derived from the user's app-start language choice
	# (backend/utils/language_codes.py), biasing the ASR listener toward the
	# session language. SI text steers only the LLM's output language; without
	# this bias a mumbled session-language word can be TRANSCRIBED as a
	# neighboring language and drag the model's auto-detect with it (live es->pt
	# slip: "distrito quintal"). Endpoint-verified ACCEPTED on the default tier
	# (Vertex 2.5 native audio, 2026-07-16 -- see
	# scripts/spikes/transcription_lang_codes_findings.md); the premium tier
	# (AI Studio 3.1) is unverified, so this kill-switch reverts to unbiased
	# multilingual ASR if a model tier rejects it (1007 at connect).
	# API-level speech language on the Live connect config (bd polyglot-pdf-m1lg):
	# speech_config.language_code from the session's spoken-language bias code.
	# Google's Live docs recommend it for the CASCADED gemini-live-2.5-flash
	# tier (docs/genai_docs/live-api-best-practices.md:56); on this repo's
	# native-audio tier it is endpoint-VERIFIED accepted rather than
	# doc-recommended. Default ON with this env kill-switch,
	# mirroring the transcription-hint flag below -- including its caveat: NOT
	# verified on the premium AI-Studio 3.1 tier; set this false for a
	# USE_PREMIUM_MODEL deploy unless verified there first.
	SPEECH_LANGUAGE_CODE_ENABLED: bool = (
		os.getenv("SPEECH_LANGUAGE_CODE_ENABLED", "true").lower() == "true"
	)
	TRANSCRIPTION_LANGUAGE_HINT_ENABLED: bool = (
		os.getenv("TRANSCRIPTION_LANGUAGE_HINT_ENABLED", "true").lower() == "true"
	)
	# Prebuilt voice for the Live session's audio output
	# (speech_config.voice_config.prebuilt_voice_config.voice_name).
	# Native-audio Live models accept ANY of the 30 TTS prebuilt voices
	# (ai.google.dev/gemini-api/docs/live-guide: "Native audio output models
	# support any of the voices available for our Text-to-Speech (TTS) models").
	# Google's default when UNSET is "Puck" (Upbeat) -- wrong register for a
	# stressful legal intake, and the SI's slow/deliberate PACE + ARTICULATION
	# prose does not reliably override delivery on native audio (the Live docs
	# document NO pace/prosody/style parameter, so voice choice is the only real
	# lever). "Iapetus" (Clear) is the maintainer's pick (2026-08-03) for
	# non-native speakers concentrating on each word. Other calm candidates if
	# this needs tuning: Schedar (Even), Vindemiatrix (Gentle), Achernar (Soft),
	# Algieba (Smooth).
	# VERIFY BEFORE DEPLOY -- an unaccepted voice name is a HARD failure, not a
	# degrade: the SDK types voice_name as a bare Optional[str] with NO enum, and
	# Vertex closes the session with `1007 Invalid voice name` at connect, so a
	# bad value breaks EVERY session. A 2026-07-30 probe (bd polyglot-pdf-e1x9)
	# endpoint-verified 11 prebuilt voices ACCEPTED on
	# gemini-live-2.5-flash-native-audio with `NotARealVoiceXYZ` correctly
	# rejected -- but the probe did not record its 11 names, so "Iapetus" is
	# documented-valid (it is one of Google's 30 TTS voices, and native-audio
	# accepts the TTS set) yet NOT endpoint-verified on this tier. First deploy
	# must confirm the session connects; set LIVE_VOICE_NAME="" to fall back to
	# the API default if it 1007s.
	LIVE_VOICE_NAME: str = os.getenv("LIVE_VOICE_NAME", "Iapetus")

	# Runtime option-label translation (bd polyglot-pdf-ow1e): at session start
	# the secretary (lite text model) translates the form's option labels into
	# the session language (one batched call per form+language per process,
	# cached); guidance renders then carry translated labels so the voice model
	# stops translating aloud on the fly (the tester-observed misfires). Kill
	# switch now; once extraction-time kit translations exist (bd
	# polyglot-pdf-2h9j) the kit-precedence step makes the secretary call a
	# natural no-op. Fail-open: any failure leaves English labels + the SI's
	# translate-on-the-fly rule.
	RUNTIME_OPTION_TRANSLATION_ENABLED: bool = (
		os.getenv("RUNTIME_OPTION_TRANSLATION_ENABLED", "true").lower() == "true"
	)

	# --- Per-form window derivation (bd polyglot-pdf-jnjj.35 / A6) ---
	# The jnjj.25 cost measurement proved DTI + CALIBRATED eviction is the win
	# (-21% on the unhappy path), and the calibration is LOAD-BEARING and
	# FORM-SPECIFIC: the sliding window must sit JUST ABOVE the unevictable SI+tools
	# floor. Too loose -> Gemini barely evicts (l3a) -> no win; too tight (<= floor)
	# -> compression fires turn 1 and evicts ALL conversation. A FIXED constant (the
	# TRIGGER/WINDOW above) is therefore wrong for any form whose floor differs from
	# the one it was tuned for. When this flag is on (the default), the adapter
	# DERIVES the window/trigger per-form from the rendered DTI SI floor:
	#   window  = floor_tokens + WINDOW_HEADROOM_TOKENS   (room for a couple fields'
	#                                                       guidance to accumulate)
	#   trigger = window       + TRIGGER_MARGIN_TOKENS    (pile-up before eviction)
	# The static TRIGGER/WINDOW above stay as the explicit OVERRIDE used when this is
	# off (or when the floor is unknown -- e.g. a non-DTI SI). Findings:
	# scripts/spikes/jnjj_25_dti_cost_findings.md (the production-wiring note).
	#
	# CALIBRATING THE HEADROOM (the load-bearing number). The floor estimator is a
	# coarse chars/4 of the SI+tools TEXT, which UNDERSHOOTS the floor Gemini
	# actually bills: on the measured I-90 DTI run the rendered SI is 3786 chars
	# (-> ~946 est. tok) + ~655 tok tools = ~1601 ESTIMATED floor, but the live
	# eviction landing zone was ~1978-2034 tokens (the meta.json eviction_drops) --
	# a ~377-tok undershoot, because Gemini's tokenizer + conversation framing bill
	# more than chars/4 of the raw text. So the headroom must clear the REAL billed
	# floor, not the estimate: 599 lifts the ~1601 estimate to the validated ~2200
	# window (which sits just above the ~1978 real floor). (Anchored to the one
	# form with measured eviction data; the estimator's undershoot scales loosely
	# with content, so re-measure the headroom when a second form's eviction floor
	# is known. Strictly safer than the old 222, which derived a 1823 window --
	# BELOW the 1978 real floor -> turn-1 eviction.)
	#
	# MARGIN default 1500 (the ctu8-validated production value, bd polyglot-pdf-7872):
	# on Vertex the derived trigger (~window + margin) sits under the API minimum
	# 5000 and gets clamped UP; the adapter then re-tunes the window to
	# trigger - margin, so the margin IS the window selector post-clamp. 1500 lands
	# the validated 3500 window (5000 - 1500); the old 600 default derived an
	# UNTESTED 4400 window (measured 2026-07-05: 5000/3500 stayed coherent across
	# 7 evictions; see the retune comment in live_ai_gemini.py).
	CONTEXT_COMPRESSION_DERIVE_FROM_SI_FLOOR: bool = (
		os.getenv("CONTEXT_COMPRESSION_DERIVE_FROM_SI_FLOOR", "true").lower() == "true"
	)
	CONTEXT_COMPRESSION_WINDOW_HEADROOM_TOKENS: int = int(
		os.getenv("CONTEXT_COMPRESSION_WINDOW_HEADROOM_TOKENS") or "599"
	)
	CONTEXT_COMPRESSION_TRIGGER_MARGIN_TOKENS: int = int(
		os.getenv("CONTEXT_COMPRESSION_TRIGGER_MARGIN_TOKENS") or "1500"
	)

	@model_validator(mode="after")
	def _resolve_model(self) -> "Settings":
		# Fail-closed guard (bd polyglot-pdf-z2is, HARDENED under bd
		# polyglot-pdf-5e6a): a DEPLOYED service (K_SERVICE is set by Cloud Run)
		# may NEVER run the AI Studio path. There is deliberately NO override
		# flag -- the earlier ALLOW_AI_STUDIO acknowledgment was removed because
		# no legitimate deployed AI Studio use exists: only Vertex's privacy
		# agreement prevents Google from using client data for model training,
		# and the product's privacy promise rests on it (maintainer directive
		# 2026-08-04). Local dev, the voice harness, and probes have no
		# K_SERVICE and remain free to use AI Studio for pre-GA 3.1 testing.
		if not self.VERTEXAI and os.getenv("K_SERVICE"):
			raise ValueError(
				"VERTEXAI=false is not permitted on a deployed service. Vertex is "
				"the ONLY production path: its privacy agreement is what keeps "
				"client data out of Google's model training, and AI Studio's "
				"consumer terms do not. Use AI Studio locally (no K_SERVICE) for "
				"pre-GA model testing; deploy 3.1 only once it is GA on Vertex."
			)
		# Resolve the active native-audio model from USE_PREMIUM_MODEL unless an
		# explicit MODEL_NATIVE was pinned via env (non-empty wins). The standard
		# (2.5) tier is BACKEND-AWARE: the native-audio Live model has a different id
		# on Vertex than on AI Studio (see MODEL_NATIVE_STANDARD_VERTEX), and the
		# AI Studio id 1008s on Vertex. So when VERTEXAI=true and no explicit pin is
		# set, resolve to the Vertex id -- this makes ANY Vertex deploy work without
		# hand-pinning MODEL_NATIVE (bd polyglot-pdf-a079). The premium (3.1) tier is
		# AI-Studio-only as of 2026-06, so it is unaffected; USE_PREMIUM_MODEL=true on
		# the Vertex path will 1008 until Vertex ships 3.1 (an explicit, documented
		# limitation, not this resolver's concern).
		if not self.MODEL_NATIVE:
			if self.USE_PREMIUM_MODEL:
				self.MODEL_NATIVE = MODEL_NATIVE_PREMIUM
			elif self.VERTEXAI:
				self.MODEL_NATIVE = MODEL_NATIVE_STANDARD_VERTEX
			else:
				self.MODEL_NATIVE = MODEL_NATIVE_STANDARD
		# The Live API requires target_tokens (window) < trigger_tokens. If a misconfig
		# inverts them, clamp the window below the trigger rather than send a config the
		# API rejects. Only clamp when compression is ENABLED: otherwise the values are
		# inert and silently rewriting them would surprise an operator pre-staging values
		# before flipping the flag. (fresh-eyes PR #76.)
		if (self.CONTEXT_COMPRESSION_ENABLED
				and self.CONTEXT_COMPRESSION_WINDOW_TOKENS >= self.CONTEXT_COMPRESSION_TRIGGER_TOKENS):
			self.CONTEXT_COMPRESSION_WINDOW_TOKENS = max(1, self.CONTEXT_COMPRESSION_TRIGGER_TOKENS // 2)
		# Continuous-session mode (bd polyglot-pdf-x8rt) IMPLIES DTI: the whole-form
		# handshake + section-advance suppression only cohere with the DTI SI (which
		# carries no section guidance) and the per-field drip. CONTINUOUS_SESSION
		# without USE_DTI is a broken hybrid -- the frontend would section-chop the
		# handshake (jitModeEnabled is off) while the client suppresses advancing. So
		# force USE_DTI on and log loudly, rather than serve that inconsistent state.
		if self.CONTINUOUS_SESSION and not self.USE_DTI:
			print("[config] WARNING: CONTINUOUS_SESSION requires USE_DTI; forcing "
				  "USE_DTI=true (continuous mode needs the DTI SI + per-field drip).")
			self.USE_DTI = True
		return self

	# Tool declarations for web forms (stateless, client-managed)
	# Note: get_next_field is NOT included - client handles field navigation
	TOOL_DECLARATIONS: list[dict] = [
		# HALLUCINATION_REDUCTION (Oct 30, 2025): Changed to single-field updates only
		# Multi-field updates caused higher hallucination rates
		{
			"name": "update_form_fields",
			"description": (
				"Update ONE field with user's provided value. Call immediately when user answers. "
				"Translate values to English. Use exact field_id from schema (with brackets if present). "
				"For radio/select fields: Use the 'value' from the option object shown in schema "
				"(e.g., if option shows '\"Yes\" (use value: P1_checkbox4[0])', send value: \"P1_checkbox4[0]\"'). "
				"For checkboxes: boolean (true/false). For text fields: string. Current section only."
			),
			"parameters": {
				"type": "object",
				"properties": {
					"field_id": {
						"type": "string",
						"description": 'Exact field "id" from schema (e.g., "firstName", "p1_checkbox4")'
					},
					"value": {
						# Declared "string" deliberately: under google-genai 2.8.0 a
						# REQUIRED param with no type makes gemini-3.1 reject the call
						# (it verbalizes "I had an issue processing that value" and never
						# fills) -- 2.5 tolerated the untyped param, 3.1 does not (bd
						# polyglot-pdf-i9q8). The model already sends radio/select and
						# checkbox values as the option-value STRING shown in the schema
						# (e.g. "P1_checkbox4[0]"), and the frontend owns boolean coercion,
						# so a string type matches real usage without losing information.
						"type": "string",
						"description": 'For radio/select: exact "value" from option object. For checkbox: the option value (or "true"/"false"). For text: string.'
					}
				},
				"required": ["field_id", "value"]
			}
		},
		{
			"name": "get_form_status",
			"description": (
				"Check which fields are filled and their values. "
				"Acknowledge the user briefly first, in the user's language."
			),
			"parameters": {
				"type": "object",
				"properties": {
					"field_ids": {
						"type": "array",
						"description": "Field IDs to check",
						"items": {"type": "string"}
					}
				},
				"required": ["field_ids"]
			}
		},
		{
			# DEPRECATED (bd polyglot-pdf-55jg):
			# section-reset production path; continuous-DTI is the live flow. Kept as
			# a fallback, not deleted. Do not extend.
			"name": "switch_section",
			"description": "Navigate to a different section/part. Use the section NUMBER only (e.g., '2' for Section 2).",
			"parameters": {
				"type": "object",
				"properties": {
					"section_identifier": {
						"type": "string",
						"description": "Section number as a string (e.g., '1', '2', '3'). ALWAYS use numbers, not labels."
					}
				},
				"required": ["section_identifier"]
			}
		},
		# REMOVED: complete_section tool (optimization - frontend auto-detects completion)
		# Section completion is now triggered automatically when all fields are confirmed
		{
			"name": "confirm_field",
			"description": (
				"Confirm that a field value is correct after user verification. "
				"MUST be called before moving to next field. After filling a field with update_form_fields, "
				"ask the user, in the session language, whether the value is correct, and wait for their "
				"confirmation. If confirmed, call this tool. If the user says it is wrong, ask for the correct value."
			),
			"parameters": {
				"type": "object",
				"properties": {
					"field_id": {
						"type": "string",
						"description": "ID of the field being confirmed"
					},
					"confirmation_method": {
						"type": "string",
						"enum": ["verbal", "manual"],
						"description": "How the field was confirmed (verbal: user said yes/correct, manual: user edited field)"
					}
				},
				"required": ["field_id", "confirmation_method"]
			}
		},
		{
			# The secretary (bd polyglot-pdf-jnjj.45): a cheap text-model helper
			# that holds the WHOLE form catalog + the applicant's current answers
			# and answers prose questions about them -- the principal does NOT
			# hold that catalog (tight compression window). Three uses (bd
			# polyglot-pdf-2af7/3vby + wsao.8's official-guidance lookups from
			# the booklet floor): (1) recall a PAST ANSWER/value; (2) IDENTIFY
			# which field the user means when you need to navigate to a field you do
			# not currently hold -- the response's `fields` list carries the exact
			# field_id + spoken_name to pass to switch_to_field. The ONE thing it is
			# NOT for: the CURRENT field's own name/id, which is always already in
			# your latest guidance block.
			"name": "ask_secretary",
			"description": (
				"Ask the secretary a plain-language question about the form. Three "
				"uses: (1) recall a past ANSWER/value -- 'what previous name did "
				"they give?', 'have we got their date of birth yet?'; (2) IDENTIFY "
				"which field the user means when you need to jump to a field you do "
				"NOT currently hold -- 'which field is the mailing city?'; (3) look "
				"up OFFICIAL GUIDANCE the secretary holds (the form's full official "
				"instructions text) when the current field's reference text does "
				"not clearly answer a requirements question -- 'what documents does "
				"exception 3 require?'. The "
				"secretary holds the whole form catalog + the applicant's answers "
				"and replies in prose; when it identifies fields, the response also "
				"carries a `fields` list of exact {field_id, spoken_name} you can "
				"pass straight to switch_to_field. Do NOT ask it for the CURRENT "
				"field's own name or id -- that is always in your latest guidance "
				"block already."
			),
			"parameters": {
				"type": "object",
				"properties": {
					"query": {
						"type": "string",
						"description": (
							"The plain-language question: a past answer/value "
							"('what is their mailing zip code?'), or which field the "
							"user means for navigation ('which field is the apartment "
							"number?')."
						)
					}
				},
				"required": ["query"]
			}
		},
		{
			# SKIP a required field the user cannot answer right now (bd
			# polyglot-pdf-7yra). DISTINCT from "not applicable": N/A is a real
			# answer (fill "" via update_form_fields), whereas skip_field defers a
			# question that DOES apply but has no answer yet (ask a translator, look
			# it up later). It marks the field skipped -- the form stays submittable
			# and the field shows as "needs follow-up", printing blank. Use ONLY
			# after the user confirms they want to skip. Do NOT use for a value the
			# user simply hasn't given -- keep asking for that.
			"name": "skip_field",
			"description": (
				"Skip a REQUIRED field the user cannot answer right now (they want "
				"to ask a translator or look it up later). This is NOT 'not "
				"applicable' -- for a question that does not apply (e.g. no middle "
				"name), use update_form_fields with an empty value instead. First "
				"CONFIRM with the user, in the session language, that they want to "
				"skip this question for now; only call this after they say yes. "
				"The question stays flagged for follow-up and the form can still be "
				"completed. Use the exact field_id from the schema."
			),
			"parameters": {
				"type": "object",
				"properties": {
					"field_id": {
						"type": "string",
						"description": 'Exact field "id" from schema (e.g., "firstName", "p1_checkbox4")'
					}
				},
				"required": ["field_id"]
			}
		},
		{
			# Field-level navigation (bd polyglot-pdf-jnjj.36): jump the form's
			# focus to ONE SPECIFIC field -- the correction/revisit path
			# ("actually, my zip code was wrong"; "go back to my mailing city").
			# The target identifier comes from the user's own words, from a field
			# this tool's candidate list named on a miss, or from ask_secretary's
			# `fields` list when the model asked it "which field is X?" to identify
			# a field it does not hold (bd polyglot-pdf-3vby). DISTINCT from
			# switch_section, which navigates whole sections and (in section mode)
			# restarts the session; this stays in the current session and just
			# changes which field is current.
			"name": "switch_to_field",
			"description": (
				"Jump to ONE SPECIFIC field so it becomes the current field -- "
				"use it when the user wants to change or revisit an earlier answer "
				"(e.g. 'go back to my mailing city'). Just pass what the USER "
				"called the field, in their own words -- an exact field_id if you "
				"have one in a recent guidance block, otherwise the field's spoken "
				"name OR even a rough description ('that government id with 12 "
				"digits', 'the box where they sign'). The tool figures out which "
				"field that is for you -- do NOT reconstruct or guess a field_id "
				"from memory. If it cannot tell which field you mean, the response "
				"says so and may list options to pick from -- ask the user which, "
				"then call again with that field. On success the response carries "
				"that field's guidance -- ask the user about THAT field next. This "
				"does NOT navigate sections; for a whole different section use "
				"switch_section."
			),
			"parameters": {
				"type": "object",
				"properties": {
					"field": {
						"type": "string",
						"description": (
							"The target field, in whatever form you have: an exact "
							"field_id from a recent guidance block, the field's "
							"spoken name, or a plain-language description of it (the "
							"tool resolves a description to the field). Do not invent "
							"a field_id."
						)
					}
				},
				"required": ["field"]
			}
		}
	]

	# Hosted schema-editor access (bd polyglot-pdf-92qe.1). Two shared-secret
	# tiers checked by the /api/editor/* routes: EDITOR (polish provided kits:
	# list/read drafts, save schemas, flip status) and AUTHOR (editor + onboard
	# PDFs + run hosted extraction). Unset -> the editor surface is disabled
	# (routes fail closed with 503). On Cloud Run these arrive via Secret
	# Manager (--set-secrets), never plaintext env.
	SCHEMA_EDITOR_TOKEN: str | None = os.getenv("SCHEMA_EDITOR_TOKEN")
	SCHEMA_AUTHOR_TOKEN: str | None = os.getenv("SCHEMA_AUTHOR_TOKEN")
	# Extra CORS origins (comma-separated), e.g. the hosted schema-editor site.
	# The editor calls Cloud Run directly (not via the Hosting /api rewrite,
	# whose 60s cap would kill minutes-long extraction), so its origin must be
	# allowed here.
	CORS_EXTRA_ORIGINS: str = os.getenv("CORS_EXTRA_ORIGINS", "")
	# Hosted PDF->schema extraction (bd polyglot-pdf-92qe.3, author tier).
	# EXTRACTOR_MODEL must be a gemini-* model on Cloud Run: the extraction
	# script's default (the local `claude` CLI) does not exist in the container.
	# gemini-2.5-pro over flash on purpose: authoring is a ONE-OFF per form, so
	# quality beats per-call cost (the runtime token economy does not apply --
	# bd 7a9 doctrine). Swap by env without a redeploy of code.
	EXTRACTOR_MODEL: str = os.getenv("EXTRACTOR_MODEL", "gemini-2.5-pro")
	# Wall-clock cap for one extraction subprocess. Well under Cloud Run's
	# --timeout=3600 so the HTTP request outlives the subprocess kill.
	EXTRACTOR_TIMEOUT_SEC: float = float(os.getenv("EXTRACTOR_TIMEOUT_SEC", "1500"))
	# Upload cap for the onboarding PDF (MB). Government form PDFs run 1-15 MB.
	EXTRACTOR_MAX_PDF_MB: float = float(os.getenv("EXTRACTOR_MAX_PDF_MB", "25"))
	# Authoring-time option-label translation (bd polyglot-pdf-2h9j): the model
	# that bakes FieldOption.label_translations into kit JSON. Pro over lite on
	# the same one-off-per-form rationale as EXTRACTOR_MODEL -- these are legal-
	# form answer labels shipped as permanent artifacts. The RUNTIME secretary
	# path (option_translation.build_translation_overrides) stays lite-tier and
	# is untouched; it is only the fallback for unbaked strings.
	OPTION_TRANSLATION_MODEL: str = os.getenv(
		"OPTION_TRANSLATION_MODEL", "gemini-2.5-pro")
	# Which LLM serves the EDITOR's authoring-time text work (translation sweep,
	# guidance regeneration) -- bd polyglot-pdf-cpiw. This is the ONE sanctioned
	# difference between local and hosted mode: everything else (lint rules,
	# gates, UI affordances) must behave identically in both.
	#   "gemini"     -- metered Vertex tokens. The hosted/Cloud Run default.
	#   "claude-cli" -- the local `claude` CLI on the maintainer's Claude Code
	#                   subscription, effectively free in-environment. The
	#                   local-dev default (scripts/run-schema-editor.sh sets it
	#                   when the CLI is on PATH), and the same seam
	#                   scripts/bakeoff/llm_providers.py uses for extraction.
	# Deliberately NOT auto-detected from "is the CLI on PATH": a developer with
	# the CLI installed must still get Gemini when running a hosted-parity check,
	# and Cloud Run must never silently pick a provider it cannot run.
	EDITOR_TEXT_PROVIDER: str = os.getenv("EDITOR_TEXT_PROVIDER", "gemini")
	# Model id handed to the claude-cli provider ("sonnet", "opus", "haiku", or
	# a full model id). Ignored unless EDITOR_TEXT_PROVIDER=claude-cli.
	EDITOR_CLAUDE_MODEL: str = os.getenv("EDITOR_CLAUDE_MODEL", "sonnet")
	# Model for the editor's GUIDANCE regeneration (re-authoring help.instructions
	# / help.details from the form's instruction booklet). Empty means "follow
	# EDITOR_TEXT_PROVIDER": claude-cli -> EDITOR_CLAUDE_MODEL, gemini ->
	# EXTRACTOR_MODEL. The enrichment path dispatches on the MODEL NAME
	# (scripts/bakeoff/llm_providers.resolve_json_runner), so a non-gemini name
	# routes itself to the local CLI.
	EDITOR_GUIDANCE_MODEL: str = os.getenv("EDITOR_GUIDANCE_MODEL", "")
	# Translation quality gate (epic polyglot-pdf-sekc, V3): the verify/rectify
	# loop that runs inside bake_label_translations on freshly baked strings.
	# DEFAULT-ON, opt-out (maintainer decision 2026-07-23). The distinction it
	# once drew against the pro pass no longer applies (FORM_COMPLETE_PRO_VALIDATOR
	# also defaults on since 2026-08-03), but the cost SHAPES still differ: the pro
	# pass is a RUNTIME per-session spend, while this gate runs at AUTHORING time
	# only (a deliberate per-bake spend of ~cents). Fail-open:
	# a verify outage leaves the baked kit byte-untouched.
	TRANSLATION_VERIFY_ENABLED: bool = (
		os.getenv("TRANSLATION_VERIFY_ENABLED", "true").lower() == "true"
	)
	# The independent back-translation leg runs on the LITE tier (deliberate:
	# independence from the pro forward/judge path; V1 measured its noise as
	# the main FP driver and the judge prompt guards against anchoring on it).
	TRANSLATION_VERIFY_BT_MODEL: str = os.getenv(
		"TRANSLATION_VERIFY_BT_MODEL", "gemini-2.5-flash-lite")

	# Form kit storage (schema/PDF pairs)
	FORM_KITS_MODE: str = os.getenv("FORM_KITS_MODE", "local")
	FORM_KITS_LOCAL_ROOT: str = os.getenv(
		"FORM_KITS_LOCAL_ROOT",
		str(Path(__file__).resolve().parents[1] / "form-kits")
	)
	FORM_KITS_GCS_BUCKET: str | None = os.getenv("FORM_KITS_GCS_BUCKET")
	FORM_KITS_REMOTE_PREFIX: str = os.getenv("FORM_KITS_REMOTE_PREFIX", "form-kits")

	# === SYSTEM INSTRUCTION TEMPLATE ===
	# Main instruction set that controls AI behavior for form filling
	# Placeholders: {form_title}, {section_number}, {total_sections}, {section_label},
	#               {filled_count}, {total_fields}, {unfilled_count}, {fields_json},
	#               {fill_language}, {previous_spoken_names}, {confirmation_policy}, {section_list}
	# Note: {fields_json} is pipe-separated text format to avoid JSON quote confusion with field IDs

	SYSTEM_INSTRUCTION: str = (
    "LANGUAGE: Detect user's language from first utterance. Respond in THAT language for entire conversation. "
    "Field VALUES in {fill_language}, but YOUR SPEECH in user's language. Never switch to English unless user does.\n\n"

    "Form assistant: {form_title} | Section {section_number}/{total_sections}: {section_label}\n"
    "Progress: {filled_count}/{total_fields} | Previous: {previous_spoken_names}\n\n"

    # DEPRECATED (bd polyglot-pdf-55jg):
    # section-reset production path; continuous-DTI is the live flow. Kept as
    # a fallback, not deleted. Do not extend. (AVAILABLE SECTIONS block below.)
    "AVAILABLE SECTIONS:\n{section_list}\n\n"

    "FIELDS:\n{fields_json}\n\n"

    "WORKFLOW:\n"
    "1. Ask for ONE field (skip Filled=True)\n"
    "2. User answers -> IMMEDIATELY call update_form_fields with ONE field\n"
    "3. Always read back user provided value and ask 'Is that correct?'\n"
    "4. Wait for verbal confirmation (yes/correct/that's right)\n"
    "5. Call confirm_field tool with confirmation_method='verbal'\n"
    "6. Move to next field (hint provided in confirm_field response)\n"
    "If user says no/incorrect: ask for correct value and repeat from step 2\n"
    "CRITICAL: Fields filled by you (AI) are NOT confirmed until user explicitly says yes. "
    "Never skip confirmation. Never move to next field without calling confirm_field. "
    "Only manual edits by user are auto-confirmed.\n\n"

    "TOOLS:\n"
    "- update_form_fields: Fill ONE field. Returns success or validation error.\n"
    "- confirm_field: REQUIRED after filling field. Params: field_id, confirmation_method='verbal'. Returns next_field_hint.\n"
    "- get_form_status: Returns 'field_id:value:confirmed|field_id:value:unconfirmed'. Only filled fields included. Omitted = empty. Use when user asks 'what have I filled?'\n"
    # DEPRECATED (bd polyglot-pdf-55jg):
    # section-reset production path; continuous-DTI is the live flow. Kept as
    # a fallback, not deleted. Do not extend.
    "- switch_section: Navigate to different section using ORDER number from AVAILABLE SECTIONS\n"
    "- Current section only - for previous sections tell user to switch first\n\n"

    "MATCHING:\n"
    "- Options must match EXACTLY from schema (punctuation matters)\n"
    "- Translate user response to {fill_language} options\n"
    "- Multiple checkboxes: comma-separated exact values\n"
    "- Validation error -> retry with correct option or ask user to clarify\n"
    "- Never proceed until field updates successfully\n\n"

    "CONSTRAINTS:\n"
    "- Never read field IDs aloud (use spoken names only)\n"
    "- Never read an ENGLISH field name or label aloud in a non-English session -- the guidance's spoken name is already in the session language when a translation exists; say THAT, and translate yourself when it is not\n"
    "- When asking for a field, use natural phrasing without saying 'field' or IDs\n"
    "- When a field carries a Note (or the next-field hint carries context to convey), "
    "briefly convey that context in your own words WHILE asking -- one short sentence, "
    "not a lecture. It is the fine print the user needs to answer accurately; "
    "never ask a qualified question as if it were unqualified.\n"
    "- Follow format requirements (e.g., yyyy-MM-dd for dates)\n"
    "- Sanity check dates/phones/ZIP codes\n"
    "- SKIP vs NOT-APPLICABLE (two different things):\n"
    "    * NOT APPLICABLE -- the question does not apply (e.g. no middle name), or the user wants to clear a field: call update_form_fields with value \"\" then confirm_field normally. This is a real answer. The stored value is the EMPTY string \"\" -- NEVER the literal text \"N/A\", \"none\", or any equivalent in any language; this rule is the same in every session language.\n"
    "    * SKIP -- the question DOES apply but the user cannot answer right now (wants to ask a translator, or look it up later): first CONFIRM ('Would you like to skip this question for now?'); once they say yes, call skip_field with the field_id. Do NOT confirm_field a skip -- skip_field records it. Only skip when the user asks to; for a value they simply have not given yet, keep asking.\n"
    "- DECLINED CHECKBOX: for an optional checkbox the user declines (says no/none/'that does not apply'), call update_form_fields with value \"\" to leave it UNCHECKED, then confirm_field normally. NEVER write \"true\"/\"false\" on a decline -- \"true\" wrongly checks the box, a wrong answer on a legal form. Only write a checked value when the user affirmatively asks for it.\n"
    "- Greet warmly in user's language, mention form/section, ask for: {next_field_hint}\n\n"

    "REGISTER (how you speak, in EVERY language):\n"
    "Speak like a helpful human assistant, not a form or a textbook: polite, warm, "
    "conversational, common everyday vocabulary, clear, simple, concise. NOT academic, "
    "complex, verbose, or obscure. Ask each question as a full short sentence, never a "
    "bare two-word demand. Keep this same register in every session language -- do not "
    "become terse or formal just because the language changed. When you say the form's "
    "or a section's TITLE, translate it into the session language -- never read an "
    "English title aloud in a non-English session.\n"
    "PACE: Speak SLOWLY and calmly -- distinctly slower than a natural conversational "
    "pace, about ten percent slower again than the measured pace you would otherwise "
    "choose; err on the side of too slow, never too fast. Hold that pace from the FIRST "
    "word to the LAST -- do not start slowly and then speed up as the sentence goes on, "
    "and never rush the end of a sentence or trail off quickly once the point is made.\n"
    "ARTICULATION (say every word clearly): pronounce each word fully and distinctly, "
    "giving each sound its full value through to the END of the word -- the end of a "
    "word is the first thing lost when speech gets sloppy. In a language where word "
    "endings carry meaning (verb and case endings), never clip them; in a language "
    "built on tones or on evenly-timed syllables, keep every tone and syllable "
    "distinct and fully voiced instead. Do NOT slur words together, swallow syllables, "
    "drop sounds, mumble, or rush through a sentence. Leave a brief, deliberate pause "
    "between clauses and a full stop between sentences, so each phrase lands separately "
    "instead of blurring into the next. Speak the full, standard form of every word: no "
    "casual contractions or clipped forms (say the equivalent of 'going to', not "
    "'gonna'), and no filler or hesitation sounds ('uh', 'um', 'hmm'). Do not imitate "
    "casual or hurried human speech -- clear, even, fully-formed pronunciation matters "
    "more than sounding relaxed. These rules govern DELIVERY only, not word choice: stay "
    "warm and conversational in the words you pick, and say those words crisply -- being "
    "clearly understood is never the same as being formal or stiff. This applies in "
    "EVERY session language.\n\n"

    "NAMES (spell first, verify by spelling):\n"
    "For any PERSON'S NAME field (family/last, given/first, middle, interpreter's "
    "or preparer's name), the SPELLING is the answer -- do not guess a common "
    "spelling from the sound. ASK for the spelling FIRST, as your very first "
    "question ('How do you spell your <name>?'); do NOT first ask 'What is your "
    "<name>?' and then ask them to spell it -- go straight to the spelling. Fill "
    "the exact spelling letter "
    "for letter, and VERIFY by reading the SPELLING back ('N-G-U-Y-E-N, Nguyen -- "
    "did I get that right?'), not just the name. If the user only says the name, "
    "ask them to spell it before filling -- never fill a guessed spelling. Uncommon "
    "and non-Anglo names mishear into Anglo defaults, which on a legal form is a "
    "wrong name. Read Latin letters back by their ENGLISH letter names in EVERY "
    "session language -- the letters are exactly what is written on the English "
    "form; never translate a spelling into another alphabet's letter names (e.g. "
    "never read N-G-U-Y-E-N back as Cyrillic or Devanagari letter names -- that "
    "verifies nothing about what the form will say).\n\n"

    "ADDRESS CONSISTENCY:\n"
    "After filling any address-cluster field (state, zip, province, country), "
    "check coherence with other address fields already filled using world knowledge "
    "(zip-to-state, US state vs. foreign province, country vs. state/province). "
    "If a conflict exists, name both fields and ask the user to verify: e.g. "
    "'You said West Virginia but that zip code is in Iowa -- are both correct?' "
    "Accept the user's answer if they confirm.\n\n"

    "CONFIRMATION:\n{confirmation_policy}"
)

	# DTI_SYSTEM_INSTRUCTION (bd polyglot-pdf-1ac3, epic polyglot-pdf-13w7): the
	# FULLY STATIC thin-principal backbone -- zero placeholders. It carries NO
	# form/session state and NO field guidance. Every field's guidance (incl.
	# field 1) reaches the model via the dynamic injection: the initiating message
	# at session/section start, then next_field_guidance after each confirm. The
	# model acts on the LATEST injected guidance block and copies its field_id
	# verbatim. The tool prose is protocol-only (no per-tool catalog), so adding a
	# tool needs no SI edit -- tool names/params/returns live in the tool
	# declarations the SDK sends. Form/section metadata moves onto the injection in
	# a later epic child; the constant itself stays state-free.
	DTI_SYSTEM_INSTRUCTION: str = (
    "LANGUAGE: The session language is CHOSEN BY THE USER at app start and announced to you in "
    "system messages as 'Speak <language>' -- that choice is authoritative. Speak THAT language "
    "for the entire conversation, whichever of the supported languages it is. YOU MUST RESPOND "
    "UNMISTAKABLY IN the session language -- every turn, every word, including single words and "
    "place names: never let a neighboring language's word slip in. Do NOT switch "
    "languages because the user's speech momentarily sounds like another language -- and NOT "
    "because the user asks you to: the session language is fixed for the whole form, so if they "
    "ask to switch, tell them warmly that they would need to start over -- the button that clears "
    "the form and starts a new session lets them choose a different language. Describe that "
    "button by what it DOES; never invent a label for it, and never say an English one (the "
    "on-screen label is translated, so an English name would not match what they see). "
    "Only if NO session language "
    "has been announced, detect it from the user's first utterance. Fill field VALUES in the fill "
    "language named in the current field's guidance. System text you receive -- tool responses, "
    "error messages, injected instructions -- is written in English; that NEVER changes your "
    "spoken language. Never echo, quote, or answer system text in English: every word you speak, "
    "including brief acknowledgements ('one moment') and error explanations, stays in the session "
    "language. Any quoted phrase in these instructions ('Is that correct?', example questions, "
    "sample read-backs) is an English ILLUSTRATION of intent -- always express it in the session "
    "language, never speak the English wording verbatim.\n\n"

    "SPEECH STYLE: Speak SLOWLY and calmly in every language -- distinctly slower than a natural "
    "conversational pace, as if speaking to someone who is concentrating hard on each word. Aim "
    "for about ten percent slower again than the measured pace you would otherwise choose: err on "
    "the side of too slow, never too fast. Hold that unhurried pace from the FIRST word to the "
    "LAST -- do not start slowly and then speed up as the sentence goes on, and never rush the end "
    "of a sentence or trail off quickly once the point is made. Many "
    "users are non-native speakers or filling a stressful legal form, so an unhurried pace matters "
    "more than sounding brisk. When reading back numbers (dates, phone numbers, ZIP codes, "
    "government id numbers) or a SPELLED-OUT name, go MUCH slower still: pronounce each digit or "
    "letter INDIVIDUALLY with a distinct, deliberate pause between characters (e.g. 'N ... G ... "
    "U ... Y ... E ... N'), never run them together, so the user can follow and verify one "
    "character at a time. Use plain, widely understood everyday words -- polite but conversational, "
    "never stiff or formal. Avoid regional idioms, rare synonyms, and archaic or ultra-formal "
    "forms; when a concept has several names in a language, use the one most speakers know.\n"
    "ARTICULATION (say every word clearly): pronounce each word fully and distinctly, giving "
    "each sound its full value through to the END of the word -- the end of a word is the first "
    "thing lost when speech gets sloppy. In a language where word endings carry meaning (verb and "
    "case endings), never clip them; in a language built on tones or on evenly-timed syllables, "
    "keep every tone and syllable distinct and fully voiced instead. "
    "Do NOT slur words together, swallow syllables, drop sounds, mumble, or "
    "rush through a sentence. Leave a brief, deliberate pause between clauses and a full stop "
    "between sentences, so each phrase lands separately instead of blurring into the next. Speak "
    "the full, standard form of every word: no casual contractions or clipped forms (say the "
    "equivalent of 'going to', not 'gonna'), and no filler or hesitation sounds ('uh', 'um', "
    "'hmm'). Do not imitate casual or hurried human speech -- clear, even, fully-formed "
    "pronunciation matters more than sounding relaxed. These rules govern DELIVERY only, not "
    "word choice: stay warm and conversational in the words you pick, and say those words "
    "crisply -- being clearly understood is never the same as being formal or stiff. "
    "This applies in EVERY session language.\n\n"

    "ROLE: You are a warm, empathetic form-filling assistant filling one form field at a time by voice.\n\n"

    "CURRENT FIELD -- READ THIS FIRST:\n"
    "The field you are filling RIGHT NOW -- including its EXACT field_id, spoken name, instructions, "
    "format, and options -- is ALWAYS provided in the most recent injected guidance block: the "
    "initiating message at the start of a session or section, and the next-field guidance returned "
    "after each confirmation. ALWAYS act on the LATEST guidance block and ignore guidance from "
    "earlier blocks. When you fill or confirm a field, COPY its field_id VERBATIM from that latest "
    "guidance block -- character for character. NEVER invent, reconstruct, guess, abbreviate, or "
    "pattern-match a field_id from another field's id. If you have no current guidance block (e.g. "
    "after a reconnect), request the current form status or ask the user, rather than guessing.\n"
    "Do NOT call ask_secretary for the CURRENT field's own spoken name or id -- that is always in "
    "this guidance block already. You DO NOT hold OTHER fields' ids, but you do not need them: to jump "
    "to a DIFFERENT field the user names ('go back to my mailing city', 'that 12-digit government id'), "
    "just call switch_to_field with the user's own words -- it resolves the field for you. Reserve "
    "ask_secretary for recalling the user's past ANSWERS/values, not field metadata.\n"
    "FIELD NAMES ALOUD: the guidance block's Spoken: name is already in the session language "
    "whenever a translation exists -- say THAT name when asking. Never read a raw field id aloud, "
    "and never read an ENGLISH field name or label aloud in a non-English session: if the guidance "
    "text is English and the session is not, translate it yourself as you speak. Never call a tool "
    "to translate or fetch a field name.\n\n"

    "WHAT YOU CANNOT SEE:\n"
    "You do not hold the form's state. You never know which fields are filled, empty, skipped, or "
    "confirmed unless you CHECK: get_form_status for fill/confirm status, ask_secretary for past "
    "answers. NEVER tell the user a field is filled, empty, or missing without checking first -- "
    "not seeing a value does NOT mean it does not exist. When in doubt, check, then answer.\n\n"

    # Deep-question grounding + no-advice rules (bd wsao.1 + wsao.8, sprint-16
    # plan; maintainer directive 2026-07-26). Terse on purpose -- the SI is
    # per-turn cost (docs/standards/logging-and-cost.md).
    "DEEP QUESTIONS: answer questions about the current field's requirements from its "
    "'Official reference text' in the latest guidance block -- ground every claim there; never "
    "read it aloud wholesale, and NEVER invent legal or document requirements. If the reference "
    "text does not clearly answer -- or you hold none -- CALL ask_secretary (it holds the full "
    "official instructions) instead of guessing.\n\n"

    "INFORMATION, NEVER ADVICE: you explain what a field expects and what the official "
    "instructions say -- you NEVER tell the user what to enter, which option to choose, or what "
    "applies to their situation. Those decisions are the user's alone. 'The instructions say "
    "category a covers X' is information; 'you should check box a' is advice -- never say it.\n\n"

    "WORKFLOW:\n"
    "1. Ask for the current field (from the latest guidance block) using natural phrasing. If the "
    "field has options, present them as PRESENTING OPTIONS directs: read EVERY option aloud for a "
    "list (never one-by-one as yes/no questions), ONE natural question for a TWO-option field the "
    "guidance marks that way, ask directly for a standard list.\n"
    "2. User answers -> IMMEDIATELY fill that ONE field, using its exact field_id from the guidance.\n"
    "3. Read the value back -> ask 'Is that correct?'. Read back the STORED value the fill tool "
    "returned ('stored_values' / 'Stored value' in its response) -- that is the authoritative "
    "saved value; NEVER read a value back from your own memory of the conversation. For names "
    "and for numbers (ids, dates, phone, ZIP), read the stored value character by character.\n"
    "4. Wait for verbal confirmation (yes/correct/that's right).\n"
    "5. Confirm the field with confirmation_method='verbal'.\n"
    "6. The confirmation returns the NEXT field's guidance. Ask for THAT field next, following its "
    "instructions/format/options, and copy ITS field_id verbatim when you fill it.\n"
    "If the user says no/incorrect: ask for the correct value and repeat from step 2.\n"
    "CRITICAL: Fields you (the AI) fill are NOT confirmed until the user explicitly says yes. "
    "Never skip confirmation. Never move to the next field without confirming the current one. "
    "Only manual edits by the user are auto-confirmed.\n\n"

    "TOOL PROTOCOL:\n"
    "- Use the tools provided to you; their names, parameters, and return shapes are defined in the "
    "tool declarations. Use the tool whose declared purpose matches your intent.\n"
    "- Fill exactly ONE field per fill call. Always confirm a filled field before advancing.\n"
    "- Pass arguments exactly as declared; use the field_id verbatim from the latest guidance.\n"
    "- Act on what each tool returns: a validation error means retry with a corrected value or ask "
    "the user to clarify; never proceed until the field updates successfully.\n"
    "- You operate on the current section only. To reach a field in another section, navigate to "
    "that section first (or, for a read-only lookup, use the appropriate retrieval tool).\n\n"

    "PRESENTING OPTIONS:\n"
    "Most users CANNOT read the form -- your voice is their ONLY access to the choices. When the "
    "current field has options, read EVERY option aloud when you ask the question: the complete "
    "list, one after another, in the order given, at the unhurried pace above. Never summarize "
    "the list, never skip or merge options, never stop partway, and NEVER refer to 'the options "
    "shown' or 'the choices listed on the form' -- the user cannot see them. Do NOT walk the "
    "options one at a time as separate yes/no questions ('Is it X?' ... 'Is it Y?') -- that hides "
    "the full set of choices; present the WHOLE list first, then ask which one applies (or which "
    "ones, for a multi-select). Reading a long list takes a while -- that is expected and correct; "
    "never shorten it to save time.\n"
    "SPEAK THE SUBSTANCE of each option, not its screen or print wording: NEVER read aloud a "
    "label's printed-form NAVIGATION -- item, line, or box numbers the reader is steered to, "
    "'(Proceed to Item 5.a)', 'Skip line 6f', 'see instructions' -- and never screen wording "
    "like 'Select Yes'; the app moves through the form automatically, so spoken aloud those "
    "directions mean nothing and only confuse. But a cross-reference that carries a REAL "
    "requirement or consequence of choosing that option (e.g. 'you must also check box h and "
    "provide the treaty details') is SUBSTANCE -- keep its meaning when you speak the option. "
    "This navigation carve-out is the ONE exception to saying a label as written -- everything "
    "else in the label is substance and is spoken. If stripping the navigation would leave an "
    "option with NOTHING to say -- its label is only a line or box reference, e.g. '1 Line 3a' "
    "vs '2 Line 3b' -- then the reference IS that option's only identity: say it as written and "
    "lean on the field's own question for the meaning, because an option the user cannot tell "
    "apart is worse than one naming a line they cannot see.\n"
    "TWO-option fields, WHEN THE GUIDANCE MARKS THEM SO: ONE natural question that makes both "
    "choices clear IS the complete ask -- a plain yes/no question when the options amount to yes "
    "and no ('Have you ever ...?'), an either/or question otherwise ('Is this a new application, "
    "or a renewal?'). Do not recite the two labels as a list, and do not ask 'which one applies'. "
    "This applies ONLY when the guidance carries that two-option marker: a two-option field the "
    "guidance marks 'read ALL 2 aloud' has labels too long, or a multi-select where both may be "
    "chosen, so the rules above stand and you read both options in full.\n"
    "A list the guidance marks as a standard list (a dropdown of standard values, e.g. every US "
    "state, or an oversized list): ask the question directly, tell the user you can read the "
    "full list, and read ALL of it the moment they ask or seem unsure.\n\n"

    "MATCHING:\n"
    "- Options must match EXACTLY from the field's guidance (punctuation matters).\n"
    "- Translate the user's response to the options in the field's fill language.\n"
    "- Option labels in the guidance are normally already written in the session language -- "
    "when you SPEAK options to the user, say them as written (minus any printed-form navigation "
    "or screen wording -- see PRESENTING OPTIONS). If a label appears in ENGLISH in a "
    "non-English session (its translation was unavailable), say it translated into the session "
    "language; NEVER read an English label aloud verbatim in a non-English session. The "
    "exact English value is only for the tool call.\n"
    "- Multiple checkboxes: comma-separated exact values.\n"
    "- Validation error -> retry with the correct option or ask the user to clarify.\n"
    "- Never proceed until the field updates successfully.\n\n"

    "DATES:\n"
    "Accept a date spoken naturally in the session language ('January first two thousand one', "
    "'primero de enero de dos mil uno'). Convert it to the field's required format YOURSELF -- "
    "NEVER ask the user to restate a date in a format like 'year, month, day'; the format "
    "requirement is for YOU, not for them. If a spoken date is ambiguous or incomplete, ask a "
    "natural clarifying question (e.g. which year), not a format request. Read the date back "
    "naturally in the session language, then confirm the stored value.\n\n"

    "CONSTRAINTS:\n"
    "- Never read field IDs aloud (use spoken names only).\n"
    "- Never read an ENGLISH field name or label aloud in a non-English session -- the guidance's spoken name is already in the session language when a translation exists; say THAT, and translate yourself when it is not.\n"
    "- Never abbreviate spoken names (use the full name from the guidance).\n"
    "- When asking for a field, use natural phrasing without mentioning 'field' or IDs.\n"
    "- For required fields: ask naturally without pressuring.\n"
    "- NEVER fill a field with a value the user has not explicitly given in this conversation. "
    "If you heard nothing, or only noise or silence, ask the question (again) -- never invent, "
    "guess, or reuse an example value as an answer.\n"
    "- SKIP vs NOT-APPLICABLE (two different things):\n"
    "    * NOT APPLICABLE -- the question does not apply (e.g. no middle name), or the user wants to clear a field: fill it with value \"\" then confirm normally. This is a real answer. The stored value is the EMPTY string \"\" -- NEVER the literal text \"N/A\", \"none\", or any equivalent in any language; this rule is the same in every session language.\n"
    "    * SKIP -- the question DOES apply but the user cannot answer right now (wants to ask a translator, or look it up later): first CONFIRM ('Would you like to skip this question for now?'); once they say yes, call skip_field with the field_id. Do NOT confirm a skip -- skip_field records it. Only skip when the user asks to; for a value they simply have not given yet, keep asking.\n"
    "- DECLINED CHECKBOX: for an optional checkbox the user declines (says no/none/'that does not apply' -- e.g. 'I do not need that accommodation'), fill it with value \"\" to leave it UNCHECKED, then confirm normally. NEVER write \"true\"/\"false\" on a decline -- \"true\" wrongly checks the box, which on a legal form is a wrong answer. Only write a checked value when the user affirmatively asks for it.\n"
    "- Keep interactions conversational and empathetic - forms can be stressful to fill out.\n\n"

    "REGISTER (how you speak, in EVERY language):\n"
    "Speak like a helpful human assistant, not a form or a textbook: polite, warm, "
    "conversational, common everyday vocabulary, clear, simple, concise. NOT academic, "
    "complex, verbose, or obscure. Ask each question as a full short sentence, never a "
    "bare two-word demand. Keep this same register in every session language -- do not "
    "become terse or formal just because the language changed. When you say the form's "
    "or a section's TITLE, translate it into the session language -- never read an "
    "English title aloud in a non-English session.\n\n"

    "NAMES (spell first, verify by spelling):\n"
    "For any field that is a PERSON'S NAME (family/last name, given/first name, "
    "middle name, an interpreter's or preparer's name, etc.), the SPELLING is the "
    "answer -- do NOT guess a common spelling from the sound. So:\n"
    "- ASK for the spelling FIRST -- as your VERY FIRST question for a name field. "
    "Your opening question MUST be 'How do you spell your <name>?'. Do NOT first ask "
    "'What is your <name>?' and then ask them to spell it -- that is two questions "
    "where one suffices and wastes the user's time. Go straight to asking for the "
    "spelling on the first turn. Uncommon and non-Anglo names (e.g. Nguyen, "
    "Johansen, Thi) are easy to mishear into a common Anglo default, which on a "
    "legal form is a wrong name.\n"
    "- FILL the exact spelling the user gives, letter for letter.\n"
    "- VERIFY by reading the SPELLING back, not just the name: "
    "'N-G-U-Y-E-N, Nguyen -- did I get that right?'. Only confirm once the user "
    "agrees the spelling is correct. Read Latin letters back by their ENGLISH "
    "letter names in EVERY session language -- the letters are exactly what is "
    "written on the English form; never translate a spelling into another "
    "alphabet's letter names.\n"
    "- If the user just says the name without spelling it, ask them to spell it "
    "before you fill -- never fill a guessed spelling.\n\n"

    "ADDRESS CONSISTENCY:\n"
    "After filling any address-cluster field (state, zip, province, country), "
    "check coherence with other address fields already filled using world knowledge "
    "(zip-to-state, US state vs. foreign province, country vs. state/province). "
    "If a conflict exists, name both fields and ask the user to verify: e.g. "
    "'You said West Virginia but that zip code is in Iowa -- are both correct?' "
    "Accept the user's answer if they confirm."
)

	# === INITIATING MESSAGE TEMPLATE ===
	# Used to prompt Gemini to initiate conversation in a specific language
	# Triggered by: session start (DTI), reconnect, section switching. (NOT a
	# language change -- the spoken language is pinned per session; the reconnect
	# opener re-asserts it. bd polyglot-pdf-87a9.)
	# Placeholders: {spoken_language}, {next_field_hint}, {current_field_guidance}
	# {current_field_guidance} is the DTI injection channel for field 1 (epic
	# polyglot-pdf-13w7, bd polyglot-pdf-j748): the static SI carries no field
	# data, so field 1's exact field_id + guidance ride here, rendered by the
	# same render_field_guidance() that delivers fields 2..N in the confirm_field
	# response. The caller passes "" in non-DTI mode (legacy/JIT still carry field
	# data in the SI), so this suffix is a no-op there.
	# The re-verify carve-out names ALREADY-CONFIRMED fields specifically, and the
	# first field is explicitly pinned to the normal per-field workflow: the old
	# "DO NOT verify previous fields - move directly to asking for the next field"
	# wording let the model read field 1 (no previous fields exist) as exempt from
	# the read-back + 'Is that correct?' step, so it auto-confirmed field 1 without
	# re-asking (bd polyglot-pdf-choa).
	INITIATING_MESSAGE: str = (
		"Speak {spoken_language}. You MUST respond UNMISTAKABLY in {spoken_language}. "
		"Greet user warmly, state section name, immediately ask for {next_field_hint}. "
		"If the field has options, read EVERY option aloud as you ask -- the user cannot see the form -- "
		"unless the guidance marks the list as a standard list (then ask directly and offer to read "
		"the full list) or the guidance marks the field as having TWO options (then ask ONE natural "
		"question that makes both choices clear). "
		"Do NOT re-verify fields that were already confirmed earlier - start by asking for this field. "
		"This field follows the normal workflow like every other: after the user answers, fill it, "
		"read the value back, ask 'Is that correct?', and confirm only after the user says yes.{current_field_guidance}"
	)

	# === RESUME INITIATING MESSAGE TEMPLATE ===
	# Used instead of INITIATING_MESSAGE when the handshake carries resume:true.
	# The user is already mid-section; skip greeting and section re-introduction.
	# Placeholders: {spoken_language}, {next_field_hint}, {current_field_guidance}
	# ({current_field_guidance} as in INITIATING_MESSAGE: the DTI field-1 channel,
	# "" in non-DTI mode.)
	# "One short sentence" is scoped to fields WITHOUT options (bd polyglot-pdf-6bq8):
	# unqualified, it overrode the SI's PRESENTING OPTIONS rule -- a live resume on a
	# choice field compressed 8 options into a yes/no about the first one.
	RESUME_INITIATING_MESSAGE: str = (
		"Speak {spoken_language}. You MUST respond UNMISTAKABLY in {spoken_language}. "
		"Do NOT greet the user. Do NOT introduce the form or section. "
		"Simply ask for {next_field_hint} as if continuing naturally -- in one short sentence "
		"if the field has no options; if it has options, read EVERY option aloud as you ask, "
		"because the user cannot see the form -- unless the guidance marks the list as a "
		"standard list (then ask directly and offer to read the full list) or the guidance marks "
		"the field as having TWO options (then ask ONE natural question that makes both choices "
		"clear).{current_field_guidance}"
	)

	# === DISCLAIMER INITIATING MESSAGE ===
	# Used when user first selects language - reads disclaimer before starting form
	# Placeholders: {spoken_language}, {disclaimer_text}, {agree_button_label}
	# agree_button_label is the TRANSLATED on-screen label the client sends with
	# read_disclaimer (bd polyglot-pdf-s863): the old hardcoded 'I Agree' made the
	# model name the button in English mid-Spanish ("Estoy de Acuerdo" on screen,
	# "I agree" spoken). Falls back to 'I Agree' when the client omits it.
	DISCLAIMER_INITIATING_MESSAGE: str = (
		"Speak {spoken_language}. Read this disclaimer aloud verbatim: '{disclaimer_text}'. "
		"After reading, tell the user, in {spoken_language}, to click the button labeled "
		"'{agree_button_label}' to continue -- say that label exactly as written."
	)

	# === RECOVERY PROMPTS (Activity Watchdog) ===
	# Sent by the frontend watchdog when the conversation stalls (bd zy3).
	# Consumed by FormFillingService.send_recovery_prompt -- levels escalate.
	# These are SCRIPTS/instructions for Gemini to act on aloud, not user turns.
	# ASCII-only (scar #6).

	# Level 1: Re-prompt for the current field
	# All three levels are INSTRUCTIONS, never quoted scripts: a quoted English
	# script gets read aloud verbatim in English regardless of the session
	# language (observed live in a Spanish session, bd polyglot-pdf-ghv4).
	RECOVERY_PROMPT_LEVEL_1: str = (
		"The user seems to have paused. Re-ask them, in the session language, for the same field "
		"you just asked for. Do not fill or change any field until the user answers."
	)

	# Level 2: "Are you still there?"
	RECOVERY_PROMPT_LEVEL_2: str = (
		"Ask the user, in the session language, whether they are still there, and offer to repeat "
		"the question if they need it."
	)

	# Level 3: Farewell before the session closes.
	RECOVERY_PROMPT_LEVEL_3: str = (
		"Tell the user, in the session language: you have not heard from them in a while, so you "
		"are closing this session; their progress is saved, and they can start the voice assistant "
		"again whenever they are ready to continue."
	)

@lru_cache(maxsize=1)
def get_settings() -> Settings:
	"""Load and return validated settings.

	Cached: Settings is static process-config built from os.environ, and several
	hot-ish paths read it per call (e.g. the native-VAD guard fires get_settings()
	per manual activity signal -- bd polyglot-pdf-efd), each previously
	constructing a fresh Settings model. lru_cache returns one shared instance.
	Tests that need a different config monkeypatch the module attribute
	(monkeypatch.setattr(config, "get_settings", lambda: ...)), which replaces the
	function and so bypasses the cache; a test that mutates os.environ and expects
	a fresh read should call get_settings.cache_clear() first.

	In later phases we can load .env via python-dotenv and add validation.
	"""
	return Settings()


def parse_extra_origins(raw: str | None) -> list[str]:
	"""Split CORS_EXTRA_ORIGINS ("https://a.web.app, https://a.firebaseapp.com")
	into a clean origin list. Empty/None -> [] (no extra origins). Used by
	main.py to extend the hardcoded localhost CORS list with the hosted
	schema-editor's origin(s) without a code change per deploy
	(bd polyglot-pdf-92qe.1).

	Accepts SEMICOLONS as well as commas (bd 92qe.4): the value reaches Cloud
	Run inside `gcloud run deploy --set-env-vars=A=1,B=2,...`, where commas are
	the PAIR separator -- a multi-origin value must therefore use semicolons in
	the deploy scripts ("https://a.web.app;https://a.firebaseapp.com")."""
	return [o.strip() for o in re.split(r"[,;]", raw or "") if o.strip()]


# ============================================================================
# Gemini Pricing for Token Tracking (per-token rates, keyed by model family)
# ============================================================================
# Rates are per-1M list prices from https://ai.google.dev/gemini-api/docs/pricing,
# divided to per-token here. Output rates include thinking tokens. Keyed by model
# FAMILY so the active model (MODEL_NATIVE, set by USE_PREMIUM_MODEL) selects the
# right row -- this is what makes a 2.5 -> 3.1 A/B comparable on cost.
# Verified against ai.google.dev/gemini-api/docs/pricing on 2026-06-12 (bd
# polyglot-pdf-4loz): BOTH rows match the published page exactly (no drift) --
# 2.5 native-audio, and 3.1 flash-live at the page's
# #gemini-3.1-flash-live-preview anchor (text in 0.75 / audio in 3.00 / text
# out 4.50 / audio out 12.00, output incl. thinking tokens).
# Updated: 2026-06-12.
#
# Columns: text_input / audio_input / text_output / audio_output (USD per 1M).
#   2.5 (native-audio):  0.50 / 3.00 / 2.00 / 12.00
#   3.1 (live preview):  0.75 / 3.00 / 4.50 / 12.00
# Note: a bare "gemini-3-flash-*" (no ".1") is NOT a Live/native-audio model per
# Google's docs, so it won't reach this adapter; model_family() bills it at the
# 2.5 default if it ever does. Add a "3" row here if that changes.
_PER_1M = 1_000_000

GEMINI_PRICING_BY_FAMILY: dict[str, dict[str, float]] = {
	"2.5": {
		"text_input": 0.50 / _PER_1M,
		"audio_input": 3.00 / _PER_1M,
		"text_output": 2.00 / _PER_1M,
		"audio_output": 12.00 / _PER_1M,
	},
	"3.1": {
		"text_input": 0.75 / _PER_1M,
		"audio_input": 3.00 / _PER_1M,
		"text_output": 4.50 / _PER_1M,
		"audio_output": 12.00 / _PER_1M,
	},
}

# Family used when a model name doesn't match any known family -- a safe
# fall-back for unrecognized/unspecified model strings (bills at the cheaper
# 2.5 rate). NOTE: this is the pricing fallback for UNKNOWN names. It happens to
# coincide with the runtime default model family (2.5, USE_PREMIUM_MODEL=false --
# bd polyglot-pdf-5oq), but the two are independent knobs.
DEFAULT_PRICING_FAMILY = "2.5"


def model_family(model_name: str | None) -> str:
	"""Map a Gemini model name to a pricing family key in GEMINI_PRICING_BY_FAMILY.

	Matches the version number as a whole token, NOT a bare substring, so
	'gemini-3.10-flash' does not match family '3.1' and 'gemini-12.5-...' does
	not match '2.5'. The version must be bounded by a non-version character (or
	the start/end of the string) on each side -- i.e. not preceded by a digit/dot
	and not followed by a digit/dot. Falls back to DEFAULT_PRICING_FAMILY for
	empty/unrecognized names so cost tracking never crashes on a new preview
	model -- it just bills at the default until a row is added here.
	"""
	name = (model_name or "").lower()
	for family in GEMINI_PRICING_BY_FAMILY:
		# (?<![\d.]) / (?![\d.]) reject a digit or dot abutting the version,
		# so '3.1' matches in 'gemini-3.1-flash' but not in 'gemini-3.10-flash'.
		if re.search(r"(?<![\d.])" + re.escape(family) + r"(?![\d.])", name):
			return family
	return DEFAULT_PRICING_FAMILY


def get_pricing_for_model(model_name: str | None) -> dict[str, float]:
	"""Return the per-token rate row for the given model's family."""
	return GEMINI_PRICING_BY_FAMILY[model_family(model_name)]


# Backward-compatible alias: the old flat dict was the 2.5 rates. Anything still
# importing GEMINI_PRICING keeps working (it gets the default family's rates).
# A COPY, not the live inner dict -- a stray mutation of GEMINI_PRICING must not
# corrupt GEMINI_PRICING_BY_FAMILY for everyone else in the process.
GEMINI_PRICING = dict(GEMINI_PRICING_BY_FAMILY[DEFAULT_PRICING_FAMILY])

