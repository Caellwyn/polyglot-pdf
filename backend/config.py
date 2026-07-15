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
	# True (DEFAULT) -> Vertex via service-account ADC + GOOGLE_CLOUD_PROJECT
	#   (compliance-friendly; required for prod). Vertex preview-model access is
	#   gated per-project: as of 2026-06, gemini-3.1-flash-live-preview is NOT yet
	#   available on Vertex, so it 1008s ("policy violation") under this path.
	# False -> Gemini Developer API (AI Studio) via GEMINI_API_KEY, which DOES
	#   have 3.1. Set VERTEXAI=false (with USE_PREMIUM_MODEL=true) on the demo
	#   service to run 3.1 until Vertex ships it. Env-overridable so demo/prod can
	#   flip without a code edit; mirrors USE_PREMIUM_MODEL / DISABLE_GEMINI_VAD.
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
	# DEFAULT-OFF: pro is a new operational-cost dependency (~$0.0093/call) and its
	# uncorrected whole-form PRECISION is 0.750 (it over-flags the Part 5/6
	# preparer-interpreter certification block). The anti-over-flag prompt ships in
	# WHOLE_FORM_PRO_SI; flip this on by env (no redeploy, mirrors EXTRACTOR_MODEL
	# doctrine) only AFTER the precision re-measure confirms the prompt lifts it.
	FORM_COMPLETE_PRO_VALIDATOR: bool = os.getenv("FORM_COMPLETE_PRO_VALIDATOR", "false").lower() == "true"
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
				"Acknowledge user first ('One moment while I check the form')."
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
				"ask user 'Is that correct?' and wait for confirmation (yes/correct/that's right). "
				"If confirmed, call this tool. If user says no/incorrect, ask for correct value."
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
			# hold that catalog (tight compression window). Two uses (bd
			# polyglot-pdf-2af7/3vby): (1) recall a PAST ANSWER/value; (2) IDENTIFY
			# which field the user means when you need to navigate to a field you do
			# not currently hold -- the response's `fields` list carries the exact
			# field_id + spoken_name to pass to switch_to_field. The ONE thing it is
			# NOT for: the CURRENT field's own name/id, which is always already in
			# your latest guidance block.
			"name": "ask_secretary",
			"description": (
				"Ask the secretary a plain-language question about the form. Two "
				"uses: (1) recall a past ANSWER/value -- 'what previous name did "
				"they give?', 'have we got their date of birth yet?'; (2) IDENTIFY "
				"which field the user means when you need to jump to a field you do "
				"NOT currently hold -- 'which field is the mailing city?'. The "
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
				"CONFIRM with the user that they want to skip ('Would you like to "
				"skip this question for now?'); only call this after they say yes. "
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

    "Medical assistant: {form_title} | Section {section_number}/{total_sections}: {section_label}\n"
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
    "- When asking for a field, use natural phrasing without saying 'field' or IDs\n"
    "- When a field carries a Note (or the next-field hint carries context to convey), "
    "briefly convey that context in your own words WHILE asking -- one short sentence, "
    "not a lecture. It is the fine print the user needs to answer accurately; "
    "never ask a qualified question as if it were unqualified.\n"
    "- Follow format requirements (e.g., yyyy-MM-dd for dates)\n"
    "- Sanity check dates/phones/ZIP codes\n"
    "- SKIP vs NOT-APPLICABLE (two different things):\n"
    "    * NOT APPLICABLE -- the question does not apply (e.g. no middle name), or the user wants to clear a field: call update_form_fields with value \"\" then confirm_field normally. This is a real answer.\n"
    "    * SKIP -- the question DOES apply but the user cannot answer right now (wants to ask a translator, or look it up later): first CONFIRM ('Would you like to skip this question for now?'); once they say yes, call skip_field with the field_id. Do NOT confirm_field a skip -- skip_field records it. Only skip when the user asks to; for a value they simply have not given yet, keep asking.\n"
    "- DECLINED CHECKBOX: for an optional checkbox the user declines (says no/none/'that does not apply'), call update_form_fields with value \"\" to leave it UNCHECKED, then confirm_field normally. NEVER write \"true\"/\"false\" on a decline -- \"true\" wrongly checks the box, a wrong answer on a legal form. Only write a checked value when the user affirmatively asks for it.\n"
    "- Greet warmly in user's language, mention form/section, ask for: {next_field_hint}\n\n"

    "NAMES (spell first, verify by spelling):\n"
    "For any PERSON'S NAME field (family/last, given/first, middle, interpreter's "
    "or preparer's name), the SPELLING is the answer -- do not guess a common "
    "spelling from the sound. ASK for the spelling first ('How do you spell your "
    "<name>?' rather than 'What is your <name>?'), fill the exact spelling letter "
    "for letter, and VERIFY by reading the SPELLING back ('N-G-U-Y-E-N, Nguyen -- "
    "did I get that right?'), not just the name. If the user only says the name, "
    "ask them to spell it before filling -- never fill a guessed spelling. Uncommon "
    "and non-Anglo names mishear into Anglo defaults, which on a legal form is a "
    "wrong name.\n\n"

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
    "LANGUAGE: Detect the user's language from their first utterance. Respond in THAT language "
    "for the entire conversation. Speak in the user's language, but fill field VALUES in the fill "
    "language named in the current field's guidance. Never switch to English unless the user does.\n\n"

    "ROLE: You are a warm, empathetic medical-form assistant filling one form field at a time by voice.\n\n"

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
    "ask_secretary for recalling the user's past ANSWERS/values, not field metadata.\n\n"

    "WORKFLOW:\n"
    "1. Ask for the current field (from the latest guidance block) using natural phrasing.\n"
    "2. User answers -> IMMEDIATELY fill that ONE field, using its exact field_id from the guidance.\n"
    "3. Read the value back -> ask 'Is that correct?'\n"
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

    "MATCHING:\n"
    "- Options must match EXACTLY from the field's guidance (punctuation matters).\n"
    "- Translate the user's response to the options in the field's fill language.\n"
    "- Multiple checkboxes: comma-separated exact values.\n"
    "- Validation error -> retry with the correct option or ask the user to clarify.\n"
    "- Never proceed until the field updates successfully.\n\n"

    "CONSTRAINTS:\n"
    "- Never read field IDs aloud (use spoken names only).\n"
    "- Never abbreviate spoken names (use the full name from the guidance).\n"
    "- When asking for a field, use natural phrasing without mentioning 'field' or IDs.\n"
    "- For required fields: ask naturally without pressuring.\n"
    "- SKIP vs NOT-APPLICABLE (two different things):\n"
    "    * NOT APPLICABLE -- the question does not apply (e.g. no middle name), or the user wants to clear a field: fill it with value \"\" then confirm normally. This is a real answer.\n"
    "    * SKIP -- the question DOES apply but the user cannot answer right now (wants to ask a translator, or look it up later): first CONFIRM ('Would you like to skip this question for now?'); once they say yes, call skip_field with the field_id. Do NOT confirm a skip -- skip_field records it. Only skip when the user asks to; for a value they simply have not given yet, keep asking.\n"
    "- DECLINED CHECKBOX: for an optional checkbox the user declines (says no/none/'that does not apply' -- e.g. 'I do not need that accommodation'), fill it with value \"\" to leave it UNCHECKED, then confirm normally. NEVER write \"true\"/\"false\" on a decline -- \"true\" wrongly checks the box, which on a legal form is a wrong answer. Only write a checked value when the user affirmatively asks for it.\n"
    "- Keep interactions conversational and empathetic - this is a medical form.\n\n"

    "NAMES (spell first, verify by spelling):\n"
    "For any field that is a PERSON'S NAME (family/last name, given/first name, "
    "middle name, an interpreter's or preparer's name, etc.), the SPELLING is the "
    "answer -- do NOT guess a common spelling from the sound. So:\n"
    "- ASK for the spelling first: lead with 'How do you spell your <name>?' "
    "rather than 'What is your <name>?'. Uncommon and non-Anglo names (e.g. Nguyen, "
    "Johansen, Thi) are easy to mishear into a common Anglo default, which on a "
    "legal form is a wrong name.\n"
    "- FILL the exact spelling the user gives, letter for letter.\n"
    "- VERIFY by reading the SPELLING back, not just the name: "
    "'N-G-U-Y-E-N, Nguyen -- did I get that right?'. Only confirm once the user "
    "agrees the spelling is correct.\n"
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
	# Triggered by: session start (DTI), language selection change, section switching
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
		"Speak {spoken_language}. Greet user warmly, state section name, immediately ask for {next_field_hint}. "
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
	RESUME_INITIATING_MESSAGE: str = (
		"Speak {spoken_language}. Do NOT greet the user. Do NOT introduce the form or section. "
		"Simply ask for {next_field_hint} in one short sentence, as if continuing naturally.{current_field_guidance}"
	)

	# === DISCLAIMER INITIATING MESSAGE ===
	# Used when user first selects language - reads disclaimer before starting form
	# Placeholders: {spoken_language}
	DISCLAIMER_INITIATING_MESSAGE: str = (
		"Speak {spoken_language}. Read this disclaimer aloud verbatim: '{disclaimer_text}'. After reading, tell user to click 'I Agree' button to continue."
	)

	# === RECOVERY PROMPTS (Activity Watchdog) ===
	# Sent by the frontend watchdog when the conversation stalls (bd zy3).
	# Consumed by FormFillingService.send_recovery_prompt -- levels escalate.
	# These are SCRIPTS/instructions for Gemini to act on aloud, not user turns.
	# ASCII-only (scar #6).

	# Level 1: Re-prompt for the current field
	RECOVERY_PROMPT_LEVEL_1: str = (
		"The user seems to have paused. Please re-ask them for the same field you just asked for."
	)

	# Level 2: "Are you still there?"
	RECOVERY_PROMPT_LEVEL_2: str = (
		'Say to the user: "Hello, are you still there? If you need me to repeat the question, just let me know."'
	)

	# Level 3: Farewell before the session closes.
	# Single double-quoted literal: the inner speech quotes are escaped (\"),
	# apostrophes stay bare -- no single/double-quote mixing to break on edit (bd bpm7).
	RECOVERY_PROMPT_LEVEL_3: str = (
		"Say to the user: \"I haven't heard from you in a while, so I'm going to close this session. "
		"Don't worry, your progress is saved. Just start the voice assistant again when you're ready to continue.\""
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

