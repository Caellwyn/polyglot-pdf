---
date: 2026-05-30
bead: polyglot-pdf-9dq
title: "Fix undefined MODEL_LIVE/MODEL_LABELING crash; make models env-swappable"
tags: [hotfix, refactor]
---

## Trigger

`bd polyglot-pdf-9dq` (child of the AI model + pricing refresh epic
`polyglot-pdf-9nl`, plan Phase 3). `backend/config.py` `Settings` defined only
`MODEL_NATIVE`, but `backend/main.py:59-61` (`/health`) and
`backend/dependencies.py:17` both referenced `settings.MODEL_LIVE` /
`settings.MODEL_LABELING` -- a latent `AttributeError` that would 500 `/health`
and break the cascade (non-native-audio) path in `get_live_ai`. No deps; meant
to land early so the family-keyed pricing bead (`polyglot-pdf-lky`) can build on it.

## What shipped

Added `MODEL_LIVE` and `MODEL_LABELING` to `Settings`, all three model fields
now `os.getenv`-backed (mirroring the existing `USE_JIT_SCHEMA` / `FORM_KITS_*`
pattern), so a family can be A/B'd live with no redeploy
(e.g. `MODEL_NATIVE=gemini-3.1-flash-live-preview`). Defaults:

- `MODEL_NATIVE` = `gemini-live-2.5-flash-native-audio` (unchanged)
- `MODEL_LIVE` = `gemini-live-2.5-flash-preview` (cascade path)
- `MODEL_LABELING` = `gemini-2.5-flash`

**Decision on the `/health` `labeling` key:** kept it. The LLM normalizer is
deprecated (commented out in config) and no labeling adapter currently consumes
`MODEL_LABELING`, but the acceptance criterion lists it as a model name to
populate, and keeping it as an env-swappable knob surfaced on `/health` is
zero-risk and leaves the door open to re-wiring normalization later. Dropping
the key would have been a behavior change with no upside this sprint.

Verified: `Settings()` loads all three fields; `/health` returns 200 with all
model names populated (via `TestClient`, app imports clean = uvicorn boots
clean); env override of `MODEL_NATIVE` confirmed.

Nothing deferred.

## Lessons

The `backend/.venv` lives in the **main repo**, not in worktrees -- worktrees
have no venv. Run Python from a worktree with
`PYTHONPATH=. /c/.../polyglot-pdf/backend/.venv/Scripts/python.exe`. The
closeout skill hard-codes `venv/Scripts/python.exe`; that path does not exist
here. (Saved to beads memory.)

## Doc freshness

`check_doc_freshness.py`: "No docs to check" -- `docs/components/` and
`docs/standards/` are the empty starter skeleton, so nothing to bump. No
CLAUDE.md change needed.

## Files touched

- `backend/config.py` -- added `MODEL_LIVE` + `MODEL_LABELING`, made all three model fields `os.getenv`-backed, added a model-selection comment block.
- `docs/journal/entries/2026-05-30-bd-9dq-fix-undefined-model-live-model-labeling-crash.md` -- this entry.
