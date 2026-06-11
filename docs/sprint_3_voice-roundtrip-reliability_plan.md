# Sprint 3 plan: voice round-trip reliability (SDK cutover first)

**Epic roots:** `polyglot-pdf-1cnn` (google-genai SDK cutover, phase 1) +
`polyglot-pdf-4sv7` / `polyglot-pdf-vmxx` (turn reliability + reconnect UX,
phases 2-3). Supersedes nothing; consolidates the open voice-reliability
beads under one ordered plan.

**Maintainer authorization (2026-06-11):** the maintainer pre-authorized this
plan and its autonomous execution in the kickoff message ("consolidate the
beads related to this epic, create a spear plan, and orchestrate trials,
fixes, investigations, upgrades, and whatever else is necessary"; "be as
autonomous as you can"). Codex review is unavailable (quota exhausted);
all assessments run through the internal adversarial fresh-eyes loop.

---

## Why (L1)

The demo's core voice loop is unreliable: short answers ("yes") frequently
fail to register, two successful turns in a row are rare (1-4 retries between
successes), and mid-section disconnects re-greet the user. This blocks
demo-readiness (possible VC demo). The maintainer's first move: upgrade
`google-genai` from the pinned 1.38.0 to current 2.8.0 -- being ~40 releases
behind risks both bugs and lock-out from features/models -- then fix whatever
remains (model choice, VAD tuning, WS contracts, mic/audio quality).

## How -- challenge registered (L2)

The SDK bump alone likely fixes none of the observed drops directly: the
code-confirmed suspects are the 2.5 native-audio model itself (bd `daa`:
first-turn 1011 on the audio path while 3.1 billed cleanly) and Gemini-side
VAD tuning (START/END_SENSITIVITY=LOW + 500 ms silence window). The frontend's
450 ms min-utterance gate was ruled OUT for the live demo (native-VAD mode
streams continuously; Silero and the gate are bypassed -- see 4sv7 comment
2026-06-11). The bump is still the right FIRST move (avoids rework, unlocks
matured session_resumption / VAD / transcription surfaces), but phase 1's
verification probes double as the model/VAD experiments so the reliability
answers arrive with the cutover, not after it.

## Ground truth established at planning time (2026-06-11)

- Container has `GEMINI_API_KEY`; live probe on 1.38.0 returned a full audio
  turn from 2.5 native-audio (endpoint reachable; experiments can run here).
- Test baseline on 1.38.0: `pytest backend/tests -m "not external"` ->
  270 passed, 2 skipped.
- The 1cnn SDK-coupling audit was re-verified clean against current code; no
  missed `google.genai` touchpoints.
- Demo config: native Gemini VAD ON, continuous client streaming, model
  `gemini-2.5-flash-native-audio-preview-12-2025`.
- The 95uy harness fix (continuous trailing silence under native VAD) has NOT
  landed in `tests/e2e/voice-harness/harness.js` (still fixed 500 ms).
- SDK 1.38.0 -> 2.8.0 breaking-change diff: see "SDK diff findings" below.

## Exit rubric (epic-level)

| # | Criterion | Verify |
|---|-----------|--------|
| 1 | Backend runs `google-genai==2.8.0`: pin updated, full non-external test suite green (no skips added to dodge failures). | `grep google-genai backend/requirements.txt`; run `pytest backend/tests -m "not external"` -- pass count >= the 1.38.0 baseline (270). |
| 2 | A live multi-turn AUDIO round-trip with a tool call completes on 2.8.0 against BOTH models (2.5 native-audio and 3.1 live-preview) using the adapter's real config shape; results recorded. | Run the post-cutover probe script(s); read the probe artifacts/output showing >= 1 clean audio turn + >= 1 tool call per model. |
| 3 | Turn-reliability evidence: a measured N-turn comparison (2.5 vs 3.1, plus a VAD-sensitivity variant) on the audio path, with the chosen model + VAD recommendation documented in `docs/standards/voice-and-vad.md` and a single packaged demo-flip ask for the maintainer. | Read `docs/standards/voice-and-vad.md` (recommendation section dated 2026-06-11+) and the probe artifacts; the maintainer ping contains the one-ask deploy recommendation. |
| 4 | A mid-section reconnect resumes silently: no greeting, no section re-intro; fresh first connect still greets. Resume vs fresh signaled explicitly in the handshake. | Run the new unit/spec tests for the resume flag; observe behavior on the local stack (fresh connect greets, simulated reconnect does not). |
| 5 | An end-to-end fill -> confirm -> advance cycle against real Gemini passes on 2.8.0 (voice harness `runCycle` >= 2/3 PASS on the local stack if the container can drive Chrome; otherwise the external tool-contract test as fallback). | Harness report JSON (or `pytest -m external backend/tests/contract/test_tool_contracts.py` output) captured in the closing PR. |

Rubric changes are logged on `polyglot-pdf-1cnn`.

## Phases + bead tree

**Phase 1 -- SDK cutover (epic 1cnn; blocks phases 2-3 where noted):**

- `1cnn` child A -- SDK bump + code migration (requirements pin, client
  construction, Live config shape, types/pattern-match, receive loop) +
  unit-test/mock updates. Surfaces: `backend/requirements.txt`,
  `backend/adapters/live_ai_gemini.py`, `backend/tests/unit/test_live_ai_gemini.py`.
  Inherits criteria 1.
- `1cnn` child B -- post-cutover live verification: re-run/extend the headless
  probes on 2.8.0 against both models with the adapter's REAL config builder;
  absorbs bd `a7k` (rework the integration smoke test to drive the real
  adapter config + default model). Surfaces:
  `backend/tests/contract/test_live_ai_gemini_integration.py`,
  `backend/scripts/probe_*.py`, `scripts/spikes/diag_*.py` (new variants only).
  Inherits criteria 2.
- `1cnn` child C -- vendored-docs refresh: update `docs/genai_docs/` to the
  2.x surface (verified against the live endpoint, per the repo's
  endpoint-probe rule). Surfaces: `docs/genai_docs/`. Inherits criterion 2
  (documentation half).

**Phase 2 -- reliability experiments (existing bead `4sv7`, runs on 2.8.0):**

- `4sv7` -- N-turn audio-path reliability A/B (2.5 vs 3.1) + Gemini-VAD
  sensitivity variants, headless, reusing `diag_native_audio_1011.py`
  lineage; closes the bd `daa` open question (model viability) and the bd
  `9jv` decision (vad_config.json wiring: recommend remove-or-wire as part of
  the doc update); recommendation lands in `docs/standards/voice-and-vad.md`
  + a single maintainer deploy ask. Surfaces: `scripts/spikes/`,
  `docs/standards/voice-and-vad.md`. Inherits criterion 3.

**Phase 3 -- reconnect UX (existing bead `vmxx`, SDK-agnostic, parallelizable
with phase 1):**

- `vmxx` -- resume/is_reconnect flag through the WS handshake; backend sends a
  RESUME initiating message (no greeting/re-intro) on reconnect; bundles bd
  `wq9y` (add `type:'handshake'` to the legacy handshake payload -- same
  surface, few lines). Surfaces: `backend/config.py` (INITIATING_MESSAGE
  variants), `backend/services/form_filling_service.py`,
  `backend/routes/websocket_routes.py`, `frontend/src/webFormConnection.ts`,
  `frontend/src/schema-forms/state/schemaFormState.ts`. Inherits criterion 4.

**Phase 4 -- end-to-end verification (existing bead `95uy` completes here):**

- `95uy` -- land the harness continuous-silence fix in
  `tests/e2e/voice-harness/harness.js` (+ a Playwright driver if the container
  can drive Chrome), then run the E2E cycle on 2.8.0. Surfaces:
  `tests/e2e/voice-harness/`. Inherits criterion 5.

**MECE check:** no two children share a write surface; every criterion has
>= 1 owner (1->A, 2->B+C, 3->4sv7, 4->vmxx, 5->95uy); no "etc." items; vmxx
is flagged parallelizable with phase 1 (disjoint surfaces, no ordering edge).

**PR shaping (planned):** PR1 = phase 1 (children A+B+C + a7k, one cutover
PR); PR2 = vmxx + wq9y; PR3 = 4sv7 (docs + probe artifacts) + 95uy harness
fix if small, else its own PR.

## Consolidation actions (tracker hygiene)

- `daa` -- stays open as the evidence record; closes WITH 4sv7's model
  decision (its acceptance criteria are exactly 4sv7's first experiment).
- `a7k` -- absorbed into 1cnn child B; closes with the cutover PR.
- `9jv` -- decision folded into 4sv7's doc update; closes with it.
- `wq9y` -- bundled into the vmxx PR.
- `wpw` -- remains open; its two remaining children (`xvu`, `v3jd`) are
  post-demo P3s, untouched by this sprint.

## Out of scope (explicitly)

- `jf6w` (connection-timeout modal epic) -- investigation-only, later.
- `xvu` (TEXT-cost reduction), `v3jd` (cost/architecture spikes) -- post-demo.
- `s3zv` (audio-send indicator), `ykvt` (harness mic-path realism),
  `ppf1` (disclaimer fall-through), `d0k` (tokenless standalone overlays) --
  open, not in this sprint's critical path.
- `wnt` (native session_resumption) -- re-evaluate AFTER the cutover lands
  (2.x matured it); not committed this sprint.
- Any demo deploy -- maintainer-gated per instance; this sprint only packages
  the recommendation.

## SDK diff findings (filled at planning time, 2026-06-11)

Empirical install-and-diff of 1.38.0 vs 2.8.0 (full record in the
`polyglot-pdf-1cnn` comment of 2026-06-11):

- **Cutover is SMALL; jump straight to 2.8.0** (no 1.75 stepping stone).
- NO break in: client construction (`vertexai=` kwarg retained; the v2.6
  "rename to enterprise" was docs-only), raw-dict Live config (same coercion,
  same `extra='forbid'`, our exact dict validates in both), all three send
  methods, all `types.*` we use, the `ModalityTokenCount` pattern-match,
  receive-event field reads, and tool-response wire encoding. The 2.0.0
  breaking changes are Interactions-API-only.
- **The ONE required code change:** `live_ai_gemini.py:2088` -- 2.8 converts
  WS closures in the receive path to `google.genai.errors.APIError`, so the
  graceful-close handler must catch it alongside `ConnectionClosed` (send
  methods still raise raw `ConnectionClosed`).
- Additive 2.8.0 surface relevant to later phases: explicit VAD signal
  (`voice_activity_detection_signal`), transcription `language_codes`,
  `thinking_config`, `session_id`, `setup_complete`.
- Dependency constraints all compatible with the repo's pins.
