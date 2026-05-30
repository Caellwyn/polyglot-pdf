---
date: 2026-05-30
bead: polyglot-pdf-j2l
title: "Re-orientation brief after the ~4-month gap"
tags: [conventions, review]
---

## Trigger

`bd polyglot-pdf-j2l` (the sole child of the re-orientation epic
`polyglot-pdf-4ta`). After a ~4-month gap, capture the current, *verified* state
of polyglot-pdf — architecture, the claude-swarm-kit workflow now layered on top,
and the three drift areas the decomposition has to clean up — so the doc-reorg
(`polyglot-pdf-gfb`) and model-refresh (`polyglot-pdf-9nl`) epics build on facts,
not memory. Read-only: every claim below was checked against the code on
2026-05-30, not restated from the bead text or old notes.

## Architecture (verified, current state)

**One sentence:** a browser SPA streams the user's voice to a stateless FastAPI
backend, which proxies a Gemini Live session that drives form-filling via tool
calls; all field state lives on the client, and PDF rendering is a separate HTTP
call.

```
Frontend (React/Vite SPA)
  │  WebSocket: wss://…run.app/ws/fill  (handshake = schema + current_values + fill_language)
  ▼
FastAPI  /ws/fill  ──►  FormFillingService  ──►  LiveAIGemini
  │                                                  │  google.genai …aio.live.connect()
  │  ◄──────────────── audio / tool calls / transcript ◄──┘
  ▼
Frontend updates sessionStorage + DOM
  …
  │  HTTP POST /api/fill-pdf  (separate path, not the WS)
  ▼
PyMuPDF fills the kit's PDF, returns bytes → browser downloads
```

**Frontend** — React + TypeScript (Vite), built to `frontend/dist`. WS endpoint
configured at `frontend/src/shared/config.ts` (prod points at the Cloud Run
service; tries `ws://localhost:8000/ws/fill` first in dev). **Stateless from the
backend's view:** field values, confirmations, and section state live in
`sessionStorage` via `SchemaFormStateManager`
(`frontend/src/schema-forms/state/schemaFormState.ts`); the WS client lives in
`frontend/src/shared/connection.ts`. On reconnect the backend rebuilds context
purely from the handshake.

**Backend** — FastAPI, entry `backend/main.py`. The `/ws/fill` route
(`backend/routes/websocket_routes.py`) accepts the handshake, then
`_handle_fill_session()` multiplexes the socket: PCM16/16 kHz audio frames →
`stream_audio()`, and JSON control messages (`activity_start`/`activity_end` VAD
signals, `change_spoken_language`, `next_field_hint`, `ping`/`stats`). An idle
watchdog closes the socket after `WS_IDLE_TIMEOUT_SEC` (default 120 s).

**Gemini Live** — wrapped by `LiveAIGemini` (`backend/adapters/live_ai_gemini.py`)
around `google.genai …aio.live.connect()`. The model exposes tools declared in
`backend/config.py` (`update_form_fields`, `confirm_field`, `get_form_status`,
`get_field_value`, `switch_section`). Two system-instruction modes: full-schema
and **JIT** (manifest + current-field only, behind `USE_JIT_SCHEMA`, default off)
to cut tokens on large forms. **Manual VAD:** `DISABLE_GEMINI_VAD = True` — the
frontend sends explicit `activity_start/end` rather than letting Gemini segment.

**PDF filling** — separate HTTP path: `POST /api/fill-pdf`
(`backend/routes/pdf_fill_routes.py`) loads the kit's PDF, maps `field_id →
pdf_field_name` from the schema, fills via PyMuPDF (AcroForm/XFA), returns bytes.
Form kits live in `backend/services/form_kits.py` (local FS or GCS).

**Deployment** — Firebase Hosting (frontend) + Cloud Run (backend), confirmed by
the architecture memory and the `deploy-demo.sh` / `deploy-production.sh` scripts
(→ `deploy-all.sh`). Deploy is **local/manual by decision** (see the
`architecture-decision-2026-05-30-final-keep-classic` bd memory: Cloud Run is
co-located with Gemini = lowest latency + scale-to-zero; no App Hosting, no
Railway). `firebase.json` rewrites `/api/**` to Cloud Run but the **WS URL is
hardcoded** to the Cloud Run host — hosting rewrites don't carry WebSockets.

## The claude-swarm-kit workflow (now in force)

The repo runs the swarm-kit's process layer on top of the product:

- **Beads is the system of record for "what next."** Resume via `bd ready` /
  `bd show`, pull-before-read, push-after-write. The `bd prime` hook reloads
  context after compaction. Persistent decisions live as `bd remember` memories.
- **3-tier progressive-discovery docs.** Tier-1 (`CLAUDE.md` + `docs/INDEX.md`)
  auto-loads; tier-2 (`docs/components/*`, `docs/standards/*`) loads per surface;
  tier-3 (`docs/journal/entries/`, frontmatter-tagged) is the chronological "why."
  Tier-1/2 are **current-state only** — no `Previously:` chains or history
  sections, mechanically enforced by `scripts/check_doc_freshness.py`.
- **Review flow:** feature branch → fresh-eyes review (parallel with Copilot) →
  normal PR → maintainer merges. No draft PRs.
- **Promotion:** feature → `dev` (staging) → `main` (prod). Note the open
  caveat in the deploy memory: the `main` ruleset still carries an *inert*
  `required_deployments → staging` gate; status checks + Copilot review can be
  enforced, but staging/prod **deploys stay manual**.
- **`/closeout`** at the end of each bead encodes the housekeeping checklist
  (beads, doc-freshness, journal entry, tests, PR + dual review, loop-to-clean).
- **Worktree discipline:** the shell cwd resets between tool calls — run git via
  `git -C <worktree-path>` (this brief was written from a worktree).

## The three drift areas

1. **Doc disorganization — scaffolded, not yet populated.** Tier-1
   (`INDEX.md`, `doc-architecture.md`, `technical_guide.md`) is live, but the
   tier-2 dirs `docs/components/` and `docs/standards/` are **empty stubs** —
   `check_doc_freshness.py` literally reports "No docs to check." The doc-reorg
   epic `polyglot-pdf-gfb` exists to fill them; `polyglot-pdf-cg7` (lean
   CLAUDE.md + INDEX skeleton) is the keystone that unblocks ~14 downstream
   component/standards docs. Older `docs/releases/*` notes are not maintained.
   *Terminology to canonize there:* **sections vs parts** (the schema and JIT
   manifest both speak "sections"; "parts" leaks in from older forms) and
   **form-session vs session** (a WS form-fill session vs. browser session) —
   resolve these in `docs/standards/terminology.md` (`polyglot-pdf-m3f`).

2. **AI model / pricing drift — largely fixed, docs pending.** The
   `polyglot-pdf-9nl` epic is **3/4 done**: the undefined-`MODEL_LIVE/LABELING`
   `/health` crash is fixed and models are env-swappable (`9dq`); pricing is now
   family-keyed (`2.5` vs `3.1`) with fail-open cost calc (`lky`, rates verified
   against Google's docs); the deprecated `2.5-pro` ref is gone (`252`). The
   **current live defaults** are `MODEL_NATIVE=gemini-live-2.5-flash-native-audio`,
   `MODEL_LIVE=gemini-live-2.5-flash-preview`, `MODEL_LABELING=gemini-2.5-flash`
   — the `gemini-3.1-flash-live-preview` / `-preview-12-2025` names in the `lky`
   entry are A/B candidates and pricing-test inputs, **not** the running defaults.
   What remains: `polyglot-pdf-2hy` (model + pricing docs), now unblocked. *Watch
   item:* `polyglot-pdf-daa` — a Google forum report of `code=1011` mid-turn at
   ~80% on `gemini-2.5-flash-native-audio-preview-12-2025` since 2026-05-27. Note
   this dated preview ID is a *different* model from our running default
   `gemini-live-2.5-flash-native-audio` (the stable alias), which is not
   confirmed affected.

3. **Stale TODO.md.** `planning_documents/TODO.md` is stamped **Nov 20, 2025**
   (~6 months stale) and is built around a "Week of Nov 25, 2025 ESC Pilot" that
   has long passed; its "Critical Path" still has unchecked end-to-end-testing /
   hardware items that are no longer the live priority. Beads is now the tracker —
   `polyglot-pdf-9np` (triage TODO.md and file downstream beads) is the home for
   reconciling it; until then, treat TODO.md as historical, not a to-do list.

## Lessons

- **Verify config against the code, not the journal.** The `lky` entry's
  `3.1` / `-preview-12-2025` model names are real, but they're A/B and test
  inputs — the *running* defaults are still the 2.5 `gemini-live-*` IDs in
  `config.py`. A journal entry records what a bead touched, not necessarily the
  current default; when a brief asserts "the current model," read `config.py`.
- **The drift areas aren't all rot — two are scaffolding.** Empty tier-2 dirs
  and a 3/4-done model epic are *in-progress*, not neglected; only TODO.md is
  genuinely stale. Naming which is which keeps the reorg from "fixing" things
  that are working as designed.

## Doc freshness

`check_doc_freshness.py`: "No docs to check" — `docs/components/` and
`docs/standards/` are the empty starter skeleton (drift area #1). No tier-1/2
docs were edited by this read-only bead. Populating tier-2 is owned by the
`polyglot-pdf-gfb` doc-reorg epic, starting with `polyglot-pdf-cg7`.

## Files touched

- `docs/journal/entries/2026-05-30-bd-j2l-reorientation-brief.md` — this entry
  (read-only bead; no code changed).
