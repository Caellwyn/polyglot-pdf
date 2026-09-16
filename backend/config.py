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
	# RESOLVED active model (derived below), kept as a field so pricing,
	# and dependencies can read the single source of truth. Set MODEL_NATIVE
	# directly via env to pin an exact model string (overrides the flag).
	# MODEL_LABELING: Model for field labeling/normalization (normalizer currently
	#   deprecated; kept as an env-swappable knob; not surfaced on /health).
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
	# NOTE: there is no VAD mode toggle any more (bd polyglot-pdf-v1m8g).
	# Gemini's automatic activity detection is unconditionally DISABLED and
	# push-to-talk is the only input mode: PTT already KNOWS when the user is
	# speaking (they are holding the button), so a second gate inferring the same
	# thing from the audio could only disagree with it. One turn signal, stated
	# rather than guessed. See docs/standards/voice-and-vad.md.
	GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")

	# Audio settings
	AUDIO_IN_RATE: int = 16000
	AUDIO_OUT_RATE: int = 24000
	MAX_UPLOAD_MB: int = 5
	# Wall-clock cap on the resume-form parse (fitz.open + the structural
	# check) in backend/routes/pdf_fill_routes.py's /api/resume-form (bd
	# polyglot-pdf-6088m, sprint 23 C4; PF-10). That parse runs on
	# attacker-controlled bytes -- a client uploads a PDF straight off their
	# own disk -- and PyMuPDF has no built-in wall-clock guard, so a crafted
	# file that is slow to parse (deeply nested objects, a pathological
	# content stream) could otherwise tie up a worker indefinitely. A few
	# seconds is generous: the shipped kits are ~150KB-2MB and parse in low
	# milliseconds.
	RESUME_FORM_PARSE_TIMEOUT_S: float = float(
		os.getenv("RESUME_FORM_PARSE_TIMEOUT_S", "8.0")
	)
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

	# === VAD ===
	# Gemini's automatic activity detection is unconditionally DISABLED
	# (bd polyglot-pdf-v1m8g), so the sensitivity/padding knobs that used to
	# tune it are GONE rather than left as dead settings -- a knob nothing can
	# turn on is a trap for the next caller (CLAUDE.md scar #7). Turn-taking is
	# push-to-talk only; see docs/standards/voice-and-vad.md.

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
	# lever). "Algieba" (Smooth) is the current pick -- see the DEFAULT CHANGED
	# note below for why it replaced "Iapetus" (Clear). Other calm candidates if
	# this needs tuning: Schedar (Even), Vindemiatrix (Gentle), Achernar (Soft).
	# VERIFY BEFORE DEPLOY -- an unaccepted voice name is a HARD failure, not a
	# degrade: the SDK types voice_name as a bare Optional[str] with NO enum, and
	# Vertex closes the session with `1007 Invalid voice name` at connect, so a
	# bad value breaks EVERY session. A 2026-07-30 probe (bd polyglot-pdf-e1x9)
	# endpoint-verified 11 prebuilt voices ACCEPTED on
	# gemini-live-2.5-flash-native-audio with `NotARealVoiceXYZ` correctly
	# rejected -- but the probe did not record its 11 names and was never
	# committed. VERIFY ANY NEW VOICE LOCALLY FIRST, it takes 30 seconds:
	#   VERTEXAI=true backend/.venv/Scripts/python.exe \
	#       backend/scripts/probe_voice_name.py <VoiceName>
	# Local and demo hit the SAME Vertex Live endpoint, so a name that connects
	# locally connects on the demo -- this is NOT a deploy-time-only risk.
	# Both Algieba (2026-08-11) and Iapetus are connect-verified ACCEPTED on
	# gemini-live-2.5-flash-native-audio by that probe. If a voice ever does
	# 1007, set LIVE_VOICE_NAME="" to fall back to the API default.
	# DEFAULT CHANGED 2026-08-11 (Iapetus -> Algieba): Iapetus was chosen for
	# clarity but shipped with a MISPRONUNCIATION defect the maintainer heard
	# in the live demo -- "not applicable" spoken as "not a pickle" (bd
	# polyglot-pdf-0rpu, second half). Lowering LIVE_TEMPERATURE to 0.4 was the
	# standing hypothesis for that and was DISCONFIRMED in production, which
	# points at the voice model rather than the sampling. Algieba is the
	# maintainer's own pick from their Chirp 3 notebook.
	# NOTE this also changes the SPELL-BACK CLIP's voice AND the INTRO CLIP's
	# voice (resolve_spellback_voice derives {locale}-Chirp3-HD-{this}; the
	# intro route reuses that resolution, bd s1iex.3) -- intended: one speaker
	# across all three surfaces. The SPELL-BACK clip's loudness gain is
	# DERIVED from whichever persona ends up speaking
	# (spellback_tts.spellback_gain_db), because voices differ in base
	# loudness -- Iapetus's +7.0 dB CLIPS on Algieba -- so changing this name
	# cannot leave a stale gain behind. A persona with no recorded measurement
	# takes the conservative (quietest) value and a test fails until it is
	# measured. The INTRO clip does NOT take that gain: it pins 0 dB
	# (intro_tts.INTRO_GAIN_DB), because the per-voice gain is measured on
	# ~4s clips and clips ~90s content.
	LIVE_VOICE_NAME: str = os.getenv("LIVE_VOICE_NAME", "Algieba")
	# Sampling temperature for the Live session (bd polyglot-pdf-0rpu; DEPLOYABLE
	# since 2026-08-10). EMPTY by default = do not send it at all, so a service
	# that does not set it keeps Google's default (1.0) unchanged.
	#
	# Honored WHEREVER it is set -- local dev and deploys alike. It was
	# originally local-dev-only (double-gated on the .env.DEV marker) on the
	# ruling that "a temperature slider is a prototyping tool, not a production
	# knob"; the maintainer reversed that once 0.4 was judged by ear to make the
	# model's speech measurably clearer AND every spell-back validation run
	# (bd 22h1f / 44ywm) was conducted at 0.4 -- shipping the demo at 1.0 would
	# have been an untested configuration. The demo sets 0.4 (deploy-demo.sh).
	#
	# Range: sweep 0.3-0.6. NEVER 0 on native audio -- googleapis/js-genai#1578
	# reports runaway/no-audio output and a 1011 session close at temperature 0.
	# The adapter rejects <=0 and >2 rather than passing them through.
	LIVE_TEMPERATURE: str = os.getenv("LIVE_TEMPERATURE", "")
	# LOCAL-DEV-ONLY transcript capture (bd polyglot-pdf-0rpu). Turning this on
	# makes the adapter request input+output transcription so the dev JSONL log
	# records WHAT WAS SAID, not just the tool calls -- without it, a voice bug
	# can only be diagnosed by inference (three rounds were spent on 0rpu for
	# exactly this reason).
	#
	# PRIVACY (maintainer directive 2026-08-05: "It's important for privacy that
	# they are turned off for deploy"): transcripts are PHI. The adapter gates
	# this on DEV_LOGGING_ENABLED too, so it cannot turn on in a deployed
	# service even if the env var is set. See docs/standards/hipaa-pii-policy.md.
	LIVE_DEV_TRANSCRIPTS: bool = (
		os.getenv("LIVE_DEV_TRANSCRIPTS", "false").lower() == "true"
	)
	# LOCAL-DEV-ONLY per-generation output-audio capture (bd polyglot-pdf-0rpu).
	# Dumps the model's OUTPUT audio, one WAV per generation, to
	# backend/logs/audio_out/ -- the ground-truth artifact for the text/audio
	# desync investigation: if the wrong letters are INSIDE the generated WAV the
	# defect is model-side; if the WAV is correct but the user heard wrong, it is
	# client-side playback. Scored against the text track by
	# scripts/spikes/stt_readback_diff.py.
	#
	# PRIVACY: output audio is the user's form values spoken aloud -- PHI, same
	# class as transcripts. The adapter double-gates this on DEV_LOGGING_ENABLED
	# (the gitignored backend/.env.DEV marker, which cannot exist on Cloud Run),
	# so it cannot turn on in a deployed service even if the env var is set.
	LIVE_DEV_AUDIO_DUMP: bool = (
		os.getenv("LIVE_DEV_AUDIO_DUMP", "false").lower() == "true"
	)

	# --- Gemini Live session resumption (bd polyglot-pdf-2nikx) ---
	# The Live API can hand back a resumption HANDLE (via SessionResumptionUpdate
	# messages on the receive stream) that a later connect can present to resume
	# the SAME server-side session state instead of rebuilding context from
	# scratch (docs/genai_docs/live-api-best-practices.md: "Retain the latest
	# resumption token ... and pass it as the handle when reconnecting").
	#
	# DEFAULT FALSE -- production behavior must stay byte-identical with this
	# off. The repo already WEIGHED and DECLINED resumption for production in
	# June (journal 2026-06-15-bd-l3a.3, bead l3a.3 closed wont-do): the
	# maintainer judged the benefit (invisibly surviving the Live API's ~10-min
	# connection reset mid-session) too marginal against the real cost
	# (handle-plumbing across the stateless backend boundary, frontend
	# storage/handshake carry, live-only testing) -- reconnect already rebuilds
	# context fine from the client-owns-state handshake. That tradeoff is
	# unchanged for production; this flag does NOT reopen l3a.3.
	#
	# This flag exists ONLY for the cost-measurement harness (scripts/spikes/
	# measure_form_session_costs.py, maintainer directive bd polyglot-pdf-2nikx):
	# the naive arm's unhappy-path run has no client-owns-state handshake to
	# rebuild from on a reconnect (it is a single deliberately-naive session with
	# no section machinery), so when the model wedges mid-run the ONLY way to
	# keep going without discarding the whole scripted plan is a literal
	# server-side resume. No new external API surface: this rides the SAME Live
	# API websocket connect config the adapter already sends
	# (google.genai.types.SessionResumptionConfig) -- no new IAM permission, no
	# new endpoint.
	SESSION_RESUMPTION_ENABLED: bool = (
		os.getenv("SESSION_RESUMPTION_ENABLED", "false").lower() == "true"
	)

	# --- Deterministic spell-back tool (bd polyglot-pdf-22h1f / 0rpu) ---
	# Routes name spelling OUT of the Live model's speech path: the model calls
	# the name_spellback tool, the CLIENT plays a Cloud Text-to-Speech clip of
	# the stored value (letter by letter), and the model only frames/asks in
	# prose. Fixes the measured sticky-first-spelling audio defect (the speech
	# head re-emits the session's FIRST spelled name at ~10% of spelled
	# read-backs while text + tool calls stay correct).
	#
	# Default ON since the cutover (bd polyglot-pdf-apkdl). It landed dark and
	# ran on the demo from 2026-08-10 via deploy-demo.sh's BACKEND_EXTRA_ENV,
	# which is the bake the dark launch was for.
	#
	# THE DEFAULT IS WHY THIS CUTOVER HAPPENED. Nothing local set the env var --
	# not scripts/dev-local.ps1, not the run-local or voice-harness skills, not
	# backend/.env.DEV -- so every local session ran WITHOUT the tool declared
	# and without the SI addendum. The model cannot call a tool it was never
	# given, so it fell back to speaking the spelling aloud, and local looked
	# broken against a demo that worked. A default-off feature that only one
	# deploy script turns on is a permanent local-vs-deployed divergence, and it
	# cost a full investigation to rediscover.
	#
	# The env var is KEPT as an emergency rollback (SPELLBACK_TOOL_ENABLED=false)
	# rather than removed, so the four gates it drives stay one switch: the tool
	# declaration (form_filling_service._build_tool_declarations), the
	# DTI_SPELLBACK_SI_ADDENDUM append (ai_context), the dispatch guard
	# (callback_handler's get_spellback_enabled), and the /api/tts/spellback
	# route's 503. Flipping the default flips all four together.
	SPELLBACK_TOOL_ENABLED: bool = (
		os.getenv("SPELLBACK_TOOL_ENABLED", "true").lower() == "true"
	)
	# Cloud TTS voice for the spell-back clip. Empty (the default) = follow the
	# SESSION LANGUAGE with the Live model's persona:
	# {session-locale}-Chirp3-HD-<LIVE_VOICE_NAME> (the Chirp 3 HD family
	# carries the Live API's prebuilt voice names, so the clip sounds like the
	# same speaker in the user's language -- maintainer ruling 2026-08-08:
	# letter names come out the way that language's speakers say them; a
	# Spanish speaker hears 'jota'). Locales with no Chirp3 voice fall back to
	# en-US, availability derived from list_voices at runtime (never a
	# hand-pinned language list). Set explicitly (full voice name) to pin one
	# voice for every session; resolution lives in
	# spellback_tts.resolve_spellback_voice.
	SPELLBACK_TTS_VOICE: str = os.getenv("SPELLBACK_TTS_VOICE", "")

	# Scripted intro+disclaimer clip (sprint 20, bd polyglot-pdf-s1iex.3):
	# gates POST /api/tts/intro (503 while off). The BACKEND half of the
	# epic's two-flag design -- the frontend lifecycle flag is a separate
	# build-time flag, and the two can skew across the two-surface deploy
	# (the skew matrix lives in docs/sprint_20_sol-intro-tts_plan.md; deploy
	# backend first, frontend second). Default OFF: the route lands dark.
	INTRO_TTS_ENABLED: bool = (
		os.getenv("INTRO_TTS_ENABLED", "false").lower() == "true"
	)

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
		# The SAME fail-closed shape for the AUTH bypass (bd polyglot-pdf-knmp).
		# VFF_DISABLE_AUTH=true makes verify_token return a stub user for EVERY
		# caller, and since bd polyglot-pdf-z2is that one bypass gates /ws/fill
		# AND every require_auth route -- including /api/fill-pdf, which renders
		# the client's entered PII into a PDF. The service deploys
		# --allow-unauthenticated, so a stray `--set-env-vars
		# VFF_DISABLE_AUTH=true` would make the whole backend world-open with no
		# startup failure and only a per-request warning log.
		#
		# Deliberately NO override flag, for the same reason the AI Studio guard
		# has none: no legitimate deployed use of a blanket auth bypass exists.
		# Read from the ENV rather than a Settings field because auth.py reads
		# the env directly -- adding a field here would create a second source
		# of truth that could drift from the thing actually enforcing.
		# auth.verify_token carries the matching runtime guard, so the bypass is
		# inert even if a caller constructs Settings differently or not at all.
		if os.getenv("VFF_DISABLE_AUTH", "false").lower() == "true" and os.getenv("K_SERVICE"):
			raise ValueError(
				"VFF_DISABLE_AUTH=true is not permitted on a deployed service. It "
				"disables Firebase token verification for EVERY caller -- the voice "
				"session and every auth-gated HTTP route, including the PDF fill "
				"endpoint that renders client PII. It exists for local development "
				"only (no K_SERVICE); there is no deployed override."
			)
		# The two local-dev dump knobs are inert on a deployed instance whatever
		# the env says: transcripts and audio dumps are field VALUES on disk.
		# Both are already double-gated on the backend/.env.DEV marker, which the
		# image never carries; this is the independent guard for a marker that
		# somehow shipped (bd polyglot-pdf-wfgjz).
		if os.getenv("K_SERVICE"):
			self.LIVE_DEV_TRANSCRIPTS = False
			self.LIVE_DEV_AUDIO_DUMP = False
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
						"description": "How the field was confirmed (verbal: user said yes/correct, manual: user verified it in the UI)"
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
				"NOT currently hold -- 'which field is the mailing city?'; (3) get "
				"the OFFICIAL INSTRUCTION TEXT quoted back when the current field's "
				"reference text does not cover something -- 'what do the "
				"instructions say about exception 3?'. Use (3) to obtain the form's "
				"OWN WORDS, which you may then read to the user. On anything shaped "
				"like 'do I qualify' or 'would my document work', it answers FROM "
				"the official text, flags the conditions that text puts on it, and "
				"defers the applicant's own situation to the firm or professional "
				"reviewing the form -- it never concludes their case. Relay all "
				"three parts: do not trim the conditions to give a cleaner yes, and "
				"do not add a verdict of your own. Ask it what the instructions SAY, "
				"never what the user SHOULD DO. The "
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
							"('what is their mailing zip code?'), which field the "
							"user means for navigation ('which field is the apartment "
							"number?'), or what the official instructions SAY about "
							"something ('what do the instructions say about exception "
							"3?'). Phrase a guidance question as what the text says, "
							"never as what this applicant should do or qualifies for."
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

	# Deterministic spell-back tool declaration (bd polyglot-pdf-22h1f).
	# Deliberately kept OUT of TOOL_DECLARATIONS even though the flag now
	# defaults ON (bd polyglot-pdf-apkdl). The earlier note here said the
	# cutover would move it into the main list; it deliberately does not.
	# _build_tool_declarations appending it under SPELLBACK_TOOL_ENABLED is what
	# makes the flag a real rollback: setting the env var to false has to remove
	# the tool from the declared set, and a constant merged into
	# TOOL_DECLARATIONS could not be removed that way. TOOL_DECLARATIONS stays
	# the unconditional production contract the static tests pin; this is the
	# one conditional member.
	#
	# No parameters ON PURPOSE: the client resolves the CURRENT field itself
	# (same pin-aware resolution the confirm path uses), so the model never
	# supplies a field_id it could hallucinate (bd jnjj.46), and the spelled
	# value can only ever be the stored value of the field under verification
	# (bd h7wx). The `parameters` schema is present-but-empty rather than
	# absent: a name-only declaration (NO parameters key) is the wire-verified
	# 2.5 native-audio 1011 hazard (bd daa/h04c) -- if early-turn 1011s appear
	# with this shape, the documented fallback is one optional ignored param.
	SPELLBACK_TOOL_DECLARATION: dict = {
		"name": "name_spellback",
		"description": (
			"Play the CURRENT field's stored value to the user as a "
			"deterministic audio clip that says the spelling letter by letter, "
			"in the session language, AND asks them whether it is correct. This "
			"is the ONLY way a LETTER spelling is ever read back -- never speak "
			"a letter spelling yourself. (Digit-by-digit read-back of numbers is "
			"unaffected: keep reading numbers back digit by digit yourself.) "
			"After update_form_fields succeeds on a name (or other "
			"letter-spelled) field, call this tool INSTEAD of doing the spoken "
			"read-back yourself, and stop speaking. The audio is generated from "
			"the STORED value, never from conversation memory, and it already "
			"asks the verification question -- so when the tool returns "
			"delivered, say NOTHING and wait silently for the user's answer, "
			"then confirm as usual once they agree."
		),
		"parameters": {
			"type": "object",
			"properties": {}
		}
	}

	# Appended to the SI (BOTH modes) while SPELLBACK_TOOL_ENABLED
	# (ai_context.py). The v4 DTI SI (bd 6a79) already forbids spelling aloud
	# and says voicing a spelling "is handled outside this conversation" --
	# this addendum names the mechanism and replaces the WORKFLOW read-back
	# step for letter-spelled values (bd 44ywm: the clip carries the whole
	# verification question, so the model waits instead of asking). The
	# LEGACY SI still carries its old verify-by-spelling wording, which this
	# addendum also overrides (fresh-eyes round 1 on bd 22h1f).
	#
	# THE ASK IS RESTATED HERE ON PURPOSE (bd polyglot-pdf-ku69b). This block
	# is the LAST text in the assembled SI and the only one whose heading names
	# a mechanism, so it carries disproportionate authority -- and every earlier
	# revision of it was pure PROHIBITION ("do NOT read back", "stop speaking")
	# opening with "For a NAME". Measured on the shipped SI: the DTI names
	# block's "HOW DO THEY SPELL THEIR NAME" lands ~4,600 chars earlier, so the
	# model's final, most-specific naming instruction told it only to stay
	# silent. The maintainer observed the consequence on the live demo -- the
	# model asks for the name and fills what it hears, never asking for the
	# spelling, which makes the clip verify a value that may already be wrong.
	# The scoping line and the closing SO-THE-SHAPE line exist to keep this
	# block from reading as the whole naming policy. Keep BOTH if you edit
	# this; test_spellback_si_addendum pins them.
	DTI_SPELLBACK_SI_ADDENDUM: str = (
		"\n\nSPELL-BACK AUDIO TOOL (this is the mechanism that voices "
		"spellings outside this conversation, and it overrides any earlier "
		"instruction to read a LETTER spelling aloud or to verify by spelling "
		"yourself):\n"
		"This changes only how a spelling is READ BACK. It does NOT change how "
		"you ASK: you still ask every person's name by asking for its SPELLING "
		"up front, every time, exactly as instructed above -- never just the "
		"name.\n"
		"For a NAME or any letter-spelled value: after the fill succeeds, do "
		"NOT read the value back and do NOT ask whether it is correct -- call "
		"the name_spellback tool instead, and stop speaking. A deterministic "
		"clip says the stored spelling to the user, letter by letter in the "
		"session language, and asks them whether it is correct. When the tool "
		"returns delivered, stay SILENT and listen for their answer; once they "
		"agree, confirm as usual. Numbers are unaffected: keep reading "
		"identifier numbers back digit by digit yourself.\n"
		"So the shape of every name field is: ASK for the spelling -> fill the "
		"letters they gave -> call name_spellback -> stay silent."
	)

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
    "CRITICAL: A field is NOT confirmed until the user explicitly says yes. "
    "Never skip confirmation. Never move to next field without calling confirm_field.\n\n"

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
		"ROLE: You are a warm, empathetic assistant filling an English legal form one field at a time, by voice. Most users cannot see the form -- your voice is their only access to it, and forms are stressful, so stay warm and patient.\n"
		"\n"
		"LANGUAGE (absolute):\n"
		"The session language is announced as 'Speak <language>' and is fixed for the whole form. RESPOND IN that language. YOU MUST RESPOND UNMISTAKABLY IN that language -- every turn, every word, including single words, place names and brief acknowledgements; never let a neighbouring language's word slip in. Never switch: not when the user's speech momentarily sounds like another language, and not on request. If they ask to switch, say warmly that changing language means starting over, using the button that clears the form and starts a new session -- describe that button by what it DOES, never by a label (on-screen labels are translated). Only if no language was announced, detect it from their first utterance.\n"
		"Everything you RECEIVE is English -- tool responses, errors, injected guidance. That never changes what you SPEAK. Never echo, quote or answer system text in English. Quoted phrases in these instructions are English illustrations of intent: express them in the session language, never word for word.\n"
		"Anything English you must SAY -- field name, option label, form or section title -- you translate yourself as you say it. Never call a tool to translate. Exact English values are for tool calls only.\n"
		"Field VALUES go in the fill language named in the current field's guidance. One exception: a person's NAME is always stored in Latin characters (see NAMES).\n"
		"\n"
		"DELIVERY (how you sound, every language):\n"
		"Speak SLOWLY and calmly, distinctly slower than natural conversation, as if to someone concentrating on each word -- err on the side of too slow. Many users are non-native speakers filling a stressful legal form. Hold that pace to the last word; never speed up mid-sentence or rush an ending.\n"
		"Articulate each word fully through to its END -- endings are lost first when speech gets sloppy. In a tonal or syllable-timed language, keep every tone and syllable distinct instead. Never slur, mumble, swallow syllables, or use contractions or fillers ('uh', 'um'). Pause briefly between clauses, fully between sentences.\n"
		"Read an IDENTIFIER number digit by digit -- id and case numbers, dates, phone, ZIP, accounts: 'one two three four five', never 'twelve thousand three hundred forty-five'. Go slower still there, with a deliberate pause between digits. A real quantity -- a count, an amount, an age -- is spoken normally.\n"
		"Never spell a word out letter by letter aloud; voicing a spelling is handled outside this conversation.\n"
		"This governs delivery only, not word choice.\n"
		"\n"
		"REGISTER (what you say, every language):\n"
		"Speak like a helpful human, not a form or a textbook: warm, polite, conversational, plain everyday words. Never academic, verbose, stiff or formal; avoid regional idioms and rare synonyms. Ask each question as a full short sentence, never a bare two-word demand, and never pressure the user, even on a required field. Keep this same register in every language -- do not become terse or formal because the language changed.\n"
		"\n"
		"CURRENT FIELD -- READ THIS FIRST:\n"
		"The field you are filling RIGHT NOW -- its exact field_id, spoken name, instructions, format and options -- is ALWAYS in the most recent injected guidance block. Act on the LATEST block and ignore earlier ones. Holding none (e.g. after a reconnect), request form status or ask the user; never guess.\n"
		"COPY the field_id VERBATIM from that block, character for character. NEVER invent, reconstruct, abbreviate or pattern-match one from another field.\n"
		"Ask using the guidance's Spoken name -- already in the session language when a translation exists. Say it in full; never abbreviate it, never say 'field', never read a raw id aloud.\n"
		"You do not hold other fields' ids and do not need them: to jump to a field the user names ('go back to my mailing city'), call switch_to_field with their own words. Do not ask the secretary for the CURRENT field's name or id -- you already have it.\n"
		"\n"
		"WHAT YOU CANNOT SEE:\n"
		"You do not hold the form's state. You never know which fields are filled, empty, skipped or confirmed unless you CHECK -- get_form_status for status, ask_secretary for past answers. Never tell the user a field is filled, empty or missing without checking: not seeing a value does not mean none exists.\n"
		"\n"
		"WORKFLOW (one field at a time):\n"
		"1. ASK for the current field. If it has options, present them as PRESENTING OPTIONS directs: read EVERY option aloud for a list (never one-by-one as yes/no questions), ONE natural question for a TWO-option field the guidance marks that way, ask directly for a standard list.\n"
		"2. FILL that ONE field from the user's answer, using its exact field_id.\n"
		"3. READ BACK the STORED value the fill tool returned ('stored_values' / 'Stored value') -- the authoritative saved value, never your own memory of what was said. Unless a later instruction gives you a different way to verify a name, say a name as a word; read identifier numbers digit by digit. Then ask 'Is that correct?'\n"
		"4. WAIT for explicit agreement (yes / correct / that's right).\n"
		"5. CONFIRM with confirmation_method='verbal'.\n"
		"6. The confirmation returns the NEXT field's guidance: ask for that field, following ITS instructions and copying ITS field_id.\n"
		"If the user says no, ask for the correct value and repeat from 2. A field is NOT confirmed until the user explicitly agrees -- never skip confirmation, never advance without it.\n"
		"\n"
		"TOOL PROTOCOL:\n"
		"Use the tool whose declared purpose matches your intent and pass arguments exactly as declared. Fill exactly ONE field per call. Act on what a tool returns: on a validation error, retry with a corrected value or ask the user to clarify -- never proceed until the field updates successfully. You FILL in the current section only; to fill a field in another section, navigate there first -- but that limit is about WRITING: get_form_status and ask_secretary read across the WHOLE form and are always available.\n"
		"A validation error tells you WHAT was wrong -- SAY THAT, never a bare apology. 'There was an error' is useless to the user and they cannot act on it. Put the reason in your own words in the session language (the error text itself is English system text and is never spoken word for word): name what the field needs, and if it is a FORMAT problem fix it YOURSELF and retry rather than asking the user to re-say the same answer differently -- they already gave you the answer, the shape is your job. Ask them again only when you genuinely need a different ANSWER, not a different format.\n"
		"\n"
		"NEVER INVENT A VALUE -- this outranks every instinct to be helpful. Fill only what the user explicitly gave you in this conversation. Heard nothing, noise or silence? Ask again. Never guess, never reuse an example value, and never supply a value the user has not said.\n"
		"\n"
		"EMPTY vs SKIP (different things):\n"
		"- EMPTY is a real answer: the question does not apply (no middle name), they want the field cleared, or they DECLINE an optional checkbox. Fill \"\" and confirm normally. The stored value is the empty string -- never 'N/A', 'none' or any equivalent in any language. On a declined checkbox never write 'true'/'false': 'true' wrongly checks the box, a wrong answer on a legal form. Write a checked value only when they affirmatively ask for it.\n"
		"- SKIP means no answer yet: the question applies but they cannot answer now. Ask 'Would you like to skip this for now?' and on yes call skip_field -- which records it, so do NOT also confirm. Only skip when they ask; if they simply have not answered, keep asking.\n"
		"\n"
		"NAMES (family, given, middle, interpreter, preparer):\n"
		"The SPELLING is the answer -- never build one from the sound (Nguyen, Johansen, Thi mishear into Anglo defaults). The stored name is ALWAYS Latin characters, never Chinese, Cyrillic, Arabic or any other script.\n"
		"So your FIRST question asks for all of it at once: HOW DO THEY SPELL THEIR NAME IN LATIN CHARACTERS, EXACTLY AS ON THEIR PASSPORT OR GREEN CARD. Ask that in full -- never a bare 'how do you spell it?', never the name first and the spelling after. Fill the exact letters they give.\n"
		"That spelling comes from THEM, never from you: NEVER transliterate or romanize a name yourself. Most names have several plausible romanizations and their document uses exactly one, so a guess is a wrong name on a legal form. If they answer in another script, ask how it is written in Latin characters on their document. If they truly do not know, say the form needs that spelling and offer to skip for now -- leaving it for later is correct; storing a guess, or another script, is not. Ask warmly: the requirement is the form's, never a judgement about their name.\n"
		"Never accept just the spoken name and fill your best guess at its spelling -- if they answer with the name alone, ask for the spelling before you fill anything. Unless a later instruction gives you a different way to verify a name, verify by saying the name back as a word ('Nguyen -- did I get that right?').\n"
		"\n"
		"DATES:\n"
		"Accept a date spoken naturally ('January first two thousand one') and convert it to the required format YOURSELF -- never ask the user to restate a date in a format; the format is for you, not them. If it is ambiguous or incomplete, ask a natural clarifying question (which year?). Read it back naturally, then confirm.\n"
		"\n"
		"ADDRESSES:\n"
		"After filling a state, ZIP, province or country, check it against the address fields already filled, using world knowledge (ZIP-to-state, US state vs foreign province, country vs state). On a conflict, name both fields and ask them to verify -- 'You said West Virginia but that ZIP code is in Iowa; are both correct?' -- then accept their answer.\n"
		"\n"
		"PRESENTING OPTIONS:\n"
		"When the current field has options, read EVERY option aloud as you ask: the complete list, in order, each to the END of its label. Every qualifier, parenthetical and condition is part of the option. Never summarize, trim, merge, skip or stop partway, however long or awkward the list is, and never refer to 'the options shown' -- they cannot see them. Never walk options one at a time as yes/no questions; that hides the full set. Present the whole list, then ask which applies (or which ones, for a multi-select). Translating a label is not licence to shorten it: translate every clause and keep them all.\n"
		"Speak each option's SUBSTANCE. The test is WHAT A CLAUSE DOES, never whether it names a box or line:\n"
		"- OMIT pure NAVIGATION -- a pointer telling a sighted reader where to go, carrying no obligation: '(Proceed to Item 5.a)', 'Skip line 6f', 'see instructions', 'Select Yes'. The app navigates for them.\n"
		"- SPEAK every REQUIREMENT, CONDITION or CONSEQUENCE of choosing that option -- always, even in parentheses, even naming a box. 'You must also check and complete box h' is an OBLIGATION they take on; '(based on days present in the United States)' decides whether the option applies at all. Dropping either lets them agree to something they were never told.\n"
		"- Cannot tell which it is? SPEAK IT. An extra clause costs seconds; a missing requirement is a wrong answer on a legal form.\n"
		"If stripping navigation would leave NOTHING to say (a label that is only 'Line 3a'), that reference IS the option's identity: say it, and lean on the field's question for meaning.\n"
		"Two exceptions, and ONLY when the guidance marks them:\n"
		"- TWO-OPTION field: one natural question carrying both choices IS the complete ask -- plain yes/no when the options amount to yes and no, either/or otherwise ('Is this a new application, or a renewal?'). Do not recite the two labels. But when the guidance says 'read ALL 2 aloud', read both in full.\n"
		"- STANDARD LIST (e.g. every US state): ask the question directly, say you can read the full list, and read all of it the moment they ask or seem unsure.\n"
		"When you fill the field, the value must match the guidance EXACTLY, punctuation included; translate the user's spoken answer to the matching option. Multiple checkboxes: comma-separated exact values.\n"
		"\n"
		# The hedge-and-defer policy below RESTS ON A DEPLOYMENT INVARIANT, and is
		# wrong without it: this app produces a DRAFT, is never used for
		# self-filing, and an outside qualified human reviews the form before it
		# is filed (customer contracts require it). That is what makes "confirm
		# with the firm or professional reviewing your form" point at a real
		# person. Opened to self-filers or sold direct-to-consumer, the deferral
		# points nowhere and a careful hedge becomes a dead end.
		#
		# NOTE THE REGISTER (bd polyglot-pdf-rdsl, updated by bd
		# polyglot-pdf-nsb4y): review is REQUIRED contractually, and the shipped
		# disclaimer now has the applicant UNDERTAKE it -- "you agree to review
		# the completed document yourself and with a certified professional
		# before filing". That is the applicant's commitment, NOT a promise by
		# us that a review will occur. Do not "tighten" this text into
		# guaranteeing that a professional WILL review the form: we do not
		# control whether they do, and the deferral must stay a deferral.
		#
		# This prompt is NOT the record of that invariant -- see
		# docs/standards/confirmation-and-audit.md ("The deployment invariant").
		"ANSWERING QUESTIONS:\n"
		"Ground answers about the current field in its 'Official reference text' from the guidance block -- never read that text aloud wholesale, and never invent legal or document requirements. If it does not clearly answer, or you hold none, call ask_secretary rather than guessing; the secretary quotes the form's official instructions back to you, and also holds the user's past answers and can identify a field you do not hold. Ask it what the instructions SAY, never what the user should do. Relay its answer FAITHFULLY AND WHOLE -- including every condition or exception it flags, and its closing deferral. Never trim the conditions to give a cleaner yes: the qualifier is the part that protects the user. Never add a conclusion of your own on top ('so yours should be fine') -- the guidance speaks, you do not decide their case.\n"
		"PLAIN MEANING is not a determination -- just answer it. If they ask what a word or acronym on the form MEANS -- 'what does ITIN stand for', 'what is a surname' -- say it plainly, in one short sentence, and move on. These have one correct answer, it does not depend on their situation, and refusing makes you useless on the easy questions. Do not hedge, do not attribute, do not defer, and do not call the secretary first. The line is WHAT AN ORDINARY WORD MEANS versus WHAT A RULE SAYS OR WHAT APPLIES TO THEM: 'ITIN stands for Individual Taxpayer Identification Number' is plain meaning; 'are you eligible for an ITIN', 'do you need one', 'should you check box a' are NOT -- those hedge and defer exactly as below, even when the answer feels obvious. A NAMED RULE ON THE FORM IS NEVER PLAIN MEANING, however the question is phrased: 'what does exception 3 mean', 'what counts as an exemption', 'what does it mean that I need a tax return' are asking what a RULE REQUIRES, not what a word means -- hedge and defer on those exactly as below, and use the official text rather than your own words. When genuinely unsure which side a question is on, treat it as a rule question and hedge.\n"
		"ALWAYS HEDGE AND DEFER on anything touching eligibility, requirements, documents, or what a rule means for THIS user -- even when the answer looks obvious, even if they press, and even if you are sure. Say what the official guidance says, attribute it ('according to the instructions for this form ...'), state the conditions it puts on it, and close by telling them to confirm their own situation with the firm or professional reviewing their form. A qualified human is expected to review this form before it is filed; that reviewer makes the determinations, never you. Do not promise the user that a review WILL happen -- the disclaimer has them AGREE to obtain review, which is their commitment, not our guarantee that it occurred.\n"
		"INFORMATION, NEVER ADVICE: you explain what a field expects and what the official instructions say. You never tell the user what to enter, which option to choose, or what applies to their situation -- those decisions are theirs alone. 'The instructions say category a covers X' is information; 'you should check box a' is advice. Never give advice."
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
	# NO GREETING (bd polyglot-pdf-s1iex.6). Sol introduces himself in the
	# scripted intro clip -- by name, in the user's language -- so a second
	# "greet user warmly" here lands seconds after that clip and reads as the
	# assistant forgetting it already said hello. The clip greets on EVERY path
	# the modal is shown, which is why this is unconditional rather than
	# flag-gated. Accepted cost while the frontend flag is OFF, stated in the
	# sprint-20 plan: returning users who skip both modals (accepted, same
	# browser session) lose the Live greeting during the dark period.
	INITIATING_MESSAGE: str = (
		"Speak {spoken_language}. You MUST respond UNMISTAKABLY in {spoken_language}. "
		"State the section name, then immediately ask for {next_field_hint}. "
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
	hot-ish paths read it per call (bd polyglot-pdf-efd), each previously
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



# ============================================================================
# Text-generation pricing (plain generate_content, NOT the Live endpoint)
# ============================================================================
# The Live table above does NOT transfer here: GEMINI_PRICING_BY_FAMILY prices
# the native-audio Live models, and the secretary/validator/translation paths
# call the ordinary generate_content endpoint on different models at different
# rates. Two tables, because they bill as two products.
#
# Verified against https://ai.google.dev/gemini-api/docs/pricing on 2026-09-09
# (bd polyglot-pdf-wio6m; gemini-2.5-pro row added on 2026-09-09 fixing a gap
# found in cross-surface review of bd polyglot-pdf-t86oz), paid-tier rows,
# quoted per 1M tokens:
#   gemini-2.5-flash:       text in 0.30 / cached in 0.03 / out 2.50
#   gemini-2.5-flash-lite:  text in 0.10 / cached in 0.01 / out 0.40
#   gemini-2.5-pro:         text in 1.25 / cached in 0.125 / out 10.00
#     (<=200k-token prompt tier; this app's validator/translation prompts are
#     well under that. The page's >200k tier -- in 2.50 / cached 0.25 / out
#     15.00 -- is NOT carried here; add a second row if a prompt ever needs it.)
# Output rates include thinking tokens. Audio input is priced separately on that
# page (2.5-flash 1.00, 2.5-flash-lite 0.30) and is NOT carried here: these are
# the TEXT paths, which send no audio. Add an "audio_input" column if a text
# model is ever handed audio.
# Updated: 2026-09-09.
TEXT_GENERATION_PRICING: dict[str, dict[str, float]] = {
	"gemini-2.5-flash": {
		"text_input": 0.30 / _PER_1M,
		"cached_input": 0.03 / _PER_1M,
		"text_output": 2.50 / _PER_1M,
	},
	"gemini-2.5-flash-lite": {
		"text_input": 0.10 / _PER_1M,
		"cached_input": 0.01 / _PER_1M,
		"text_output": 0.40 / _PER_1M,
	},
	"gemini-2.5-pro": {
		"text_input": 1.25 / _PER_1M,
		"cached_input": 0.125 / _PER_1M,
		"text_output": 10.00 / _PER_1M,
	},
}


def get_text_generation_pricing(model_name: str | None) -> dict[str, float] | None:
	"""Return the per-token rate row for a text-generation model, or None.

	Matches on the model id with any date/preview suffix stripped (the chain
	ships concrete ids like "gemini-2.5-flash-lite-preview-09-2025", which must
	bill at the base model's rate). Returns None -- not a fallback row -- for an
	unknown model: billing an unknown model at a guessed rate produces a
	confident wrong number, which is worse for a cost dashboard than an
	explicit gap. Callers emit cost_estimate_usd=None in that case.
	"""
	name = (model_name or "").lower()
	if not name:
		return None
	# Longest key first, so "gemini-2.5-flash-lite" wins over "gemini-2.5-flash"
	# for an id that starts with both.
	for key in sorted(TEXT_GENERATION_PRICING, key=len, reverse=True):
		if name.startswith(key):
			return TEXT_GENERATION_PRICING[key]
	return None


# ============================================================================
# Cloud Text-to-Speech pricing (USD per CHARACTER, keyed by voice tier)
# ============================================================================
# TTS bills per character of input text, not per token. Keyed by voice tier
# because the tiers differ by an order of magnitude; this app synthesizes with
# Chirp 3 HD voices only ({locale}-Chirp3-HD-{persona}, see spellback_tts.py),
# so that is the only tier that needs a row today.
#
# Chirp 3 HD: USD 0.00003 per character (USD 30 per 1M characters), SKU
# F977-2280-6F1B, read from https://cloud.google.com/text-to-speech/pricing by
# the maintainer on 2026-09-14 (the page would not load for an automated fetch
# on 2026-09-09). Re-verify against the live page whenever a tier is added; a
# tier with no verified rate stays None so callers emit cost_estimate_usd=None
# rather than a guess, and backend/tests/unit/test_pricing_tables.py refuses
# a None row.
TTS_PRICING_USD_PER_CHAR: dict[str, float | None] = {
	"Chirp3-HD": 0.00003,
}


def tts_voice_tier(voice_name: str | None) -> str | None:
	"""Map a resolved TTS voice name to a TTS_PRICING_USD_PER_CHAR tier key.

	Voice names are "{locale}-{tier}-{persona}", e.g. "en-US-Chirp3-HD-Algieba".
	Returns None for an empty name (the locale-default fallback rung in
	resolve_spellback_voice, which leaves the voice unnamed) or an unrecognized
	tier -- callers then emit cost_estimate_usd=None rather than guessing.
	"""
	name = voice_name or ""
	for tier in TTS_PRICING_USD_PER_CHAR:
		if tier in name:
			return tier
	return None
