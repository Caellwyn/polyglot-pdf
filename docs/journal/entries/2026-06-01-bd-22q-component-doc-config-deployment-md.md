---
date: 2026-06-01
bead: polyglot-pdf-22q
title: "Component doc: config-deployment.md"
tags: [conventions]
---

## Trigger

`bd polyglot-pdf-22q`, a child of the docs-reorg epic `polyglot-pdf-gfb` (3-tier
progressive discovery). Write the tier-2 component doc for the config + deployment
surface and absorb the legacy `backend/ENV_VARIABLES.md`. Dep `cg7` (tier-1
skeleton) was already closed, so this was unblocked.

## What shipped

`docs/components/config-deployment.md` — covers `backend/config.py` `Settings`,
the manual deploy path, and how `.env` reaches the backend. INDEX row de-`(planned)`-ed
to a live link. Key facts, all **verified against code** rather than the bead text:

- **`.env` IS auto-loaded.** `backend/main.py:7` calls `load_dotenv()` before
  importing config — so I documented that, and flagged that the `get_settings`
  docstring (".env in later phases") is stale.
- **Env-overridable vs code-constant split.** Only fields that call `os.getenv`
  can be set by env (models, JIT, form-kits); the WS/audio/VAD knobs,
  `DISABLE_GEMINI_VAD`, `PROACTIVE_AUDIO`, etc. are plain field defaults and need a
  code edit. The doc lists which is which so nobody tries to set `WS_IDLE_TIMEOUT_SEC`
  via env.
- **Dev-logging mechanism corrected.** `DEV_LOGGING_ENABLED` is driven by the
  **`backend/.env.DEV` marker file** (`dev_file_logger.py`), NOT by `VFF_DEV_LOGGING`.
  `VFF_DEV_LOGGING` only gates the separate field-value `_dev_log` path in
  `callback_handler.py`. The legacy `ENV_VARIABLES.md` conflated these; noted it as
  superseded.
- **Deploy ground truth** (from the deploy scripts / firebase.json / .firebaserc):
  demo project `polyglot-demo-aa709`, prod `polyglot-forms-919f2`, both a
  `polyglot-backend` Cloud Run service in `us-central1`; `deploy-all.sh` sets
  `FORM_KITS_MODE=gcs` + bucket via `--set-env-vars`; `/api/**` rewrites to Cloud
  Run while WS uses a hardcoded direct `wss://...run.app/ws/fill` (Hosting can't
  proxy WS).
- **Scope boundaries respected:** model-selection canon points at
  `standards/ai-models.md` (not duplicated); VAD flags point at `voice-and-vad.md`;
  auth env vars (`VFF_DISABLE_AUTH`) get a one-line mention pointing at the planned
  `auth.md` (`bd polyglot-pdf-y3l`). The **physical** archival of `ENV_VARIABLES.md`
  is left to `bd polyglot-pdf-4p0` (which 22q blocks), so I only added a superseded
  pointer rather than deleting the file.

### Review triage (PR #<TBD>)

_To be filled after round-1 triage._

## Lessons

The doc-freshness checker (`scripts/check_doc_freshness.py`) resolves all paths
against `REPO_ROOT = Path(__file__).parent.parent`, i.e. **its own checkout** — so
running the main-repo copy never sees a worktree branch's new docs (it reported
"docs/ empty"). To validate a doc on a branch, run the **worktree's own copy** of
the script (`"$PY" "$WT/scripts/check_doc_freshness.py"`). With that, the new doc
reports OK.

## Doc freshness

- `docs/components/config-deployment.md` — created, stamped `2026-06-01`, passes the
  checker.
- `docs/INDEX.md` — config-deployment row de-`(planned)`-ed.
- Pre-existing STALE (left as-is, track files this branch did NOT touch): `voice-ai.md`,
  `ai-models.md`, `logging-and-cost.md`, `voice-and-vad.md` (all track
  `live_ai_gemini.py`, made stale by the merged p1t fix), and `technical_guide.md`
  (tracks `config.py`/`main.py`; owned by the in-progress `bd polyglot-pdf-gfb.2`).
- Four pre-existing stale `in_progress` beads (`gfb.2`, `m3f`, `pki`, `hjo`) surfaced
  by housekeeping — all others' in-flight work, none orphaned, untouched.

## Files touched

- `docs/components/config-deployment.md` — new tier-2 component doc.
- `docs/INDEX.md` — linked the config-deployment row.
- `docs/journal/entries/2026-06-01-bd-22q-component-doc-config-deployment-md.md` — this entry.
