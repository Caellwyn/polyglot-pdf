---
date: 2026-06-10
bead: polyglot-pdf-cd0
title: "Mobile reads full disclaimer text + remove dead isFieldConfirmed (cd0, exs)"
tags: [bug, frontend, mobile, cleanup]
---

## Trigger

Third cheap-win cleanup bundle. The first two (PR #139 ASCII, PR #140 backend
nits) drained the locally-verifiable backend/doc nits; this one picks up two
small FRONTEND items, now that browser verification via `dev-local.sh` +
Chrome MCP is on the table (the Claude Preview tool is sandboxed for this
storage-dependent SPA -- see local memory `preview-tool-sandboxed-use-chrome-mcp`).

## What shipped

### cd0 (item 1): mobile reads the FULL disclaimer, not a generic fallback

`VoiceOverlayMobile.tsx` called `connectionManager.readDisclaimer(selectedLanguage)`
at BOTH sites (auto-read on connect ~L506, `handleDisclaimerListenAgain` ~L624),
omitting the `disclaimerText` arg that `ConnectionManager.readDisclaimer(language,
disclaimerText)` expects. Desktop `VoiceOverlay.tsx` passes both. With the text
missing, the backend (`websocket_routes.py`) logged `missing_disclaimer_text` and
read a GENERIC fallback ("Please read the disclaimer.") aloud instead of the full
verbatim translated legal disclaimer -- a real degradation for mobile users of an
immigration/legal intake tool, where reading the actual disclaimer matters.

Fix mirrors desktop exactly: add `DISCLAIMER_TRANSLATIONS` to the existing
`DisclaimerModal` import, derive `disclaimerText =
DISCLAIMER_TRANSLATIONS[selectedLanguage]?.fullText ||
DISCLAIMER_TRANSLATIONS['English'].fullText`, pass both args at both sites.

cd0 item 2 (mobile `handleDisclaimerAgree` calls `sendActivityStart()`
unconditionally; desktop does not) is SPLIT to **polyglot-pdf-zq9l**: the mobile
call looks intentional (its comments describe a deliberate interrupt-Gemini-audio
sequence), so it needs a behavioral decision, not a mechanical delete.

### exs (dead-code): remove isFieldConfirmed

Removed `SchemaFormStateManager.isFieldConfirmed` (`schemaFormState.ts`) -- zero
callers, dead since PR #113 replaced PR #111's confirmed-flag detection with a
value-based gate. The journal already flagged this as dead code in the f5w
merge-artifact-cleanup entry ("isFieldConfirmed is now dead code ... unused after
#113"); this closes that loop. exs items 1+2 (ConnectionCallbacks
onStopCapture/onFormComplete wiring + the sendRecoveryPrompt caller decision) SPLIT
to **polyglot-pdf-0tgc** (larger; item 1 touches the 24-error TS baseline).

## Verification (browser, via dev-local + Chrome MCP)

Brought up the full local stack (`scripts/dev-local.sh both`), drove onboarding
(English -> i-90) in a real Chrome tab, and:

- A `WebSocket.prototype.send` interceptor captured the live `read_disclaimer`
  frame: `disclaimer_text` is the full 1120-char verbatim disclaimer (was the bug's
  empty/undefined). Backend log shows `sending_disclaimer_message` with NO
  `missing_disclaimer_text` warning.
- Fetched the VITE-SERVED `VoiceOverlayMobile.tsx`: both `readDisclaimer` call
  sites are now two-arg and `DISCLAIMER_TRANSLATIONS` is imported -- i.e. the edits
  are what's actually running. (The resize tool could not force innerWidth < 768 to
  render the mobile React path, so the mobile fix is verified by served-module
  inspection + the desktop path's identical wire contract, not a mobile click-through.)
- `await import()` of `schemaFormState.ts`: `isFieldConfirmed` is `undefined` while
  `confirmField`/`load` remain; the i-90 schema state loaded with NO console errors
  -- dead-code removal broke nothing.

Full backend suite still green at prep (266 passed; this change is frontend-only).

## Doc-freshness triage

Several docs flagged STALE, all false positives (mtime heuristic). Most trace to
backend files this branch does NOT touch (earlier-today churn). The one branch-
touched file that appears, `schemaFormState.ts`, is flagged against schema-forms.md
/ stateless-architecture.md / terminology.md -- but the change is a dead-method
REMOVAL with zero callers, and NO tier-1/tier-2 doc references `isFieldConfirmed`
(only journal entries do, which is correct). No doc update warranted.

Closes polyglot-pdf-cd0, polyglot-pdf-exs. Follow-ups: polyglot-pdf-zq9l,
polyglot-pdf-0tgc.
