---
date: 2026-07-06
bead: polyglot-pdf-9jv
title: "Delete dead VAD-config endpoint (9jv) + unreachable ProtectedRoute spinner (31u1)"
tags: [refactor, conventions]
---

## Trigger

Two long-standing dead-code beads the maintainer cleared for deletion (decision
2026-07-06), bundled into one PR because each is individually too small for its
own cycle and they sit on disjoint surfaces (backend vs frontend):

- **9jv** -- the `/ws/vad-config` WebSocket + `backend/vad_config.json` were a
  Gemini-side VAD tuning path that nothing read: the live adapter builds its
  Gemini-VAD settings from `Settings` (`VAD_*` env fields), never from the JSON,
  and `DISABLE_GEMINI_VAD=True` makes those knobs inert regardless. Real
  turn-taking is client-side Silero (`useDemoVAD.ts`). Maintainer: delete.
- **31u1** -- `ProtectedRoute`'s `if (loading)` spinner branch is unreachable in
  production: `AuthProvider` renders `{!loading && children}` (AuthContext.tsx),
  so a `ProtectedRoute` never mounts while auth is loading. The one test covering
  it drove `useAuth` directly to reach the branch in isolation. Maintainer: delete
  (option 1), accepting the loss of the deliberate isolation test rather than
  restructuring AuthProvider (the UX-improving option 2 was a product call the
  maintainer declined here).

## What shipped

**9jv (backend):**
- Deleted `backend/routes/vad_config_routes.py` and `backend/vad_config.json`.
- Removed the import + `@app.websocket("/ws/vad-config")` registration in
  `backend/main.py`; dropped the now-unused `WebSocket` import.
- Deleted `frontend/vad-tuning-lab/` (5 files) -- the standalone vanilla-JS tuning
  UI that was the endpoint's ONLY client. Decided (not asked): it has no HTML entry
  point and is referenced by nothing in `src`/the build (grep-confirmed), so it was
  already orphaned; leaving a client for a deleted endpoint is worse than removing
  both. Trivially in service of the bead, reversible. (The LIVE client-side tuner is
  the separate React `frontend/src/vad-tuning/` dashboard -> localStorage; untouched.)

**31u1 (frontend):**
- Removed the `if (loading)` branch from `ProtectedRoute.tsx` (and the now-unused
  `loading` from the `useAuth` destructure); added a comment explaining the
  auth-init wait is owned upstream by AuthProvider.
- Removed the single `renders the loading spinner...` test from
  `AuthContext.test.tsx` and updated the block's explanatory comment; the other two
  gate tests (Login when no user, children when user) stay.
- Cascade dead-code (decided, not asked): the spinner branch was the only renderer
  of `.auth-loading`/`.auth-spinner`, and `.auth-spinner` was the only user of the
  `@keyframes spin`. Removed all three from `Login.css`. Same reasoning as the
  tuning-lab: keep the deletion coherent.

Verification: backend `928 passed, 2 skipped` (3 external deselected); backend
`main` imports clean with no vad route (loaded-from confirmed under the worktree).
Frontend `754 passed` (38 files) + `tsc --noEmit` exit 0. Nothing filed as
out-of-scope.

## Lessons

Nothing new generalizes. Re-confirmed two known traps: (1) verifying a backend
delete via `import backend.main` needs the loaded module's `__file__` checked --
the first attempt resolved main's copy and still showed the route (scar #3); (2)
frontend tests in a worktree need the `node_modules` junction
(`frontend-tests-in-worktrees-via-junction`).

## Doc freshness

Bumped and content-fixed for the 9jv delete:
- `docs/standards/voice-and-vad.md` -- rewrote the "two VAD configs" caveat block
  to current state (Gemini-side VAD is env-only; the dead JSON/endpoint is removed);
  dropped `vad_config_routes.py` + `vad_config.json` from `**Tracks:**`.
- `docs/technical_guide.md` -- removed `/ws/vad-config` from the direct-on-`app`
  routes prose and its route-table row.
- `docs/standards/risk-rating.md` -- dropped `vad_config_routes.py` from the
  narrower-blast-radius route-handlers row.

Left as-is (verified NOT about the deleted endpoint): `docs/standards/testing.md`'s
"VAD-config 1007 fix" reference is the historical `p1t` testing-pattern example
(the `live_ai_gemini.py` VAD builder helper, still present), not this route.
`docs/archive/*` are archived (freshness-exempt). The other ~20 docs the freshness
checker flags STALE track backend/frontend files this branch did not touch --
pre-existing staleness, left alone.

## Files touched

- `backend/main.py` -- removed vad-config import + route + unused WebSocket import.
- `backend/routes/vad_config_routes.py` -- DELETED.
- `backend/vad_config.json` -- DELETED.
- `frontend/vad-tuning-lab/{handlers,metrics,state,ui}.js`, `styles.css` -- DELETED (orphaned client).
- `frontend/src/components/layout/ProtectedRoute.tsx` -- removed dead loading branch.
- `frontend/src/contexts/AuthContext.test.tsx` -- removed the spinner-branch test + stale comment.
- `frontend/src/components/auth/Login.css` -- removed dead `.auth-loading`/`.auth-spinner` + `@keyframes spin`.
- `docs/standards/voice-and-vad.md`, `docs/technical_guide.md`, `docs/standards/risk-rating.md` -- current-state fixes + stamp bumps.
- `docs/journal/entries/2026-07-06-bd-9jv-31u1-dead-code-deletes.md` -- this entry.
