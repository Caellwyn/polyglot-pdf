# CLAUDE.md -- polyglot-pdf

**Project-specific instructions for AI assistants. Read this before making any changes.**

> This file is the tier-1, always-loaded doc. Keep it lean: it should point at
> the on-demand docs (tier 2 + 3), not duplicate them. See
> [`docs/INDEX.md`](docs/INDEX.md) for the canonical doc map and
> [`docs/doc-architecture.md`](docs/doc-architecture.md) for the progressive-
> discovery system this file sits at the top of.

---

## What this is

**polyglot-pdf** is a voice-driven, multilingual form-filler for complex PDFs
(immigration/legal intake). A browser SPA streams the user's voice over a
WebSocket to a stateless FastAPI backend, which proxies a **Gemini Live** session
that drives form-filling through tool calls; all field state lives on the client
(`sessionStorage`), and PDF rendering is a separate HTTP call (PyMuPDF). Stack:
React + TypeScript (Vite) frontend on **Firebase Hosting**; Python/FastAPI backend
on **Cloud Run** (co-located with Gemini). Entry points: backend `backend/main.py`
(WebSocket route `backend/routes/websocket_routes.py`, Gemini adapter
`backend/adapters/live_ai_gemini.py`); frontend `frontend/src/` (WS config
`frontend/src/shared/config.ts`). Deploy is **local/manual**
(`deploy-demo.sh` / `deploy-production.sh`). For the full verified architecture,
read the re-orientation brief
([`docs/journal/entries/2026-05-30-bd-j2l-reorientation-brief.md`](docs/journal/entries/2026-05-30-bd-j2l-reorientation-brief.md)).

---

## Doc map (read these on demand)

This file (CLAUDE.md) is auto-loaded every session. Everything else is on-demand.
**Always start by reading [`docs/INDEX.md`](docs/INDEX.md)** -- it's the canonical map.

| Tier | Where | Load when |
|------|-------|-----------|
| **1 -- Always loaded** | This file + [`docs/INDEX.md`](docs/INDEX.md) | Auto |
| **2 -- Easily reached** | [`docs/components/<surface>.md`](docs/components/) (per surface) + [`docs/standards/*.md`](docs/standards/) (cross-cutting rules) + [`docs/technical_guide.md`](docs/technical_guide.md) | When that surface or concern is in scope |
| **3 -- Indexed / on-demand** | [`docs/journal/entries/`](docs/journal/entries/) (per-file, frontmatter-tagged) + [`docs/journal/TAGS.md`](docs/journal/TAGS.md) | When investigating "why was this built this way?" |

**Trigger reads:** Before changing code in a surface, read the matching
`docs/components/<surface>.md`. If the doc is wrong, fix the doc first as a
separate commit. The tier-2 docs below are being populated under the docs-reorg
epic (`polyglot-pdf-gfb`); until each lands, fall back to the cited code path.

| Before changing... | Read |
|--------------------|------|
| WebSocket session routing / handshake (`backend/routes/websocket_routes.py`) | `docs/components/websocket-routing.md` |
| Gemini Live adapter, tools, models (`backend/adapters/live_ai_gemini.py`, `backend/config.py`) | `docs/components/voice-ai.md` + `docs/standards/ai-models.md` |
| Schema forms / client state (`frontend/src/schema-forms/`, `frontend/src/shared/`) | `docs/components/schema-forms.md` |
| PDF filling (`backend/routes/pdf_fill_routes.py`, `backend/services/form_kits.py`) | `docs/components/pdf-filling.md` |
| Anything logging PII/PHI or audit trails | `docs/standards/hipaa-pii-policy.md` + `docs/standards/confirmation-and-audit.md` |
| VAD / activity signals (`DISABLE_GEMINI_VAD`, `activity_start/end`) | `docs/standards/voice-and-vad.md` |

---

## Top scar tissue (always-relevant lessons)

1. **Beads is the system of record for "what to do next."** Resume work via
   `bd ready` / `bd show <id>`, not by reading a plan file. Pull before reads,
   push after every write. See [`docs/doctrine/workflow.md`](docs/doctrine/workflow.md).
2. **Every PR goes feature-branch -> fresh-eyes review (parallel with Copilot)
   -> normal PR -> maintainer merges.** No draft PRs. See
   [`docs/doctrine/review-flow.md`](docs/doctrine/review-flow.md).
3. **In a worktree, run every git command via `git -C <worktree-path>`** --
   the shell cwd resets between tool calls; a chained `cd <main-repo> && git ...`
   silently operates on the main checkout. The same trap hits file writes: an
   absolute path into the main repo writes there, not the worktree.
4. **The backend is stateless by design; the client owns all field state.**
   Field values, confirmations, and section state live in the browser's
   `sessionStorage` -- the backend rebuilds context from the WS handshake on
   every (re)connect. Never add server-side per-session field persistence, and
   never log field values/PII/PHI server-side. See the re-orientation brief.
5. **"Sections" is the canonical term; "parts" is legacy drift.** The schema and
   JIT manifest speak *sections*; older code still carries `current_part_id` /
   `part_id` (e.g. `backend/adapters/live_ai_gemini.py`). Don't propagate
   "parts" in new code. Canon + cleanup tracked in `polyglot-pdf-m3f`.

---

## Critical rules

The rules that override default behavior. Product-specific invariants live in
"Top scar tissue" above; the cross-cutting workflow rules follow.

### Task tracking
- Beads (`bd`) is the canonical tracker. Pull-before-read, push-after-write.
  Full cadence: [`docs/doctrine/workflow.md`](docs/doctrine/workflow.md).

### Deployment / promotion
- feature branch -> `dev` (staging) -> `main` (prod). Details:
  [`docs/doctrine/promotion-tiers.md`](docs/doctrine/promotion-tiers.md).

### Doc maintenance
- Tier-1 and tier-2 docs are CURRENT STATE ONLY -- no `Previously:` chains, no
  history sections. The journal is the chronological record. Mechanically
  enforced by `scripts/check_doc_freshness.py`. Full rules:
  [`docs/doc-architecture.md`](docs/doc-architecture.md).

---

## Sprint closeout

Run the `/closeout` skill at the end of every bead. It encodes the checklist:
beads housekeeping, doc-freshness, journal entry, tests, then a normal PR with
parallel Copilot + fresh-eyes review, looped to clean, then ping to merge. See
[`.claude/skills/closeout/SKILL.md`](.claude/skills/closeout/SKILL.md).
