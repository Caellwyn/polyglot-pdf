---
date: 2026-07-12
bead: polyglot-pdf-4l7p
title: "UI sweep: mobile overlay dead section machinery deleted; disclaimer trigger verified correct"
sprint: 11
tags: [refactor, testing]
---

## Trigger

Sprint-11 epic polyglot-pdf-fc7t child C6. Planning research flagged
VoiceOverlayMobile as "not gated at all" for continuous mode while desktop got
the continuousSession gates. PR #405 (bd 944q, parallel session) had already
fixed the desktop header, leaving this bead: mobile parity + the disclaimer
switchToFirstSection start-trigger's continuous semantics + tests.

## What shipped

Scouting overturned the premise in two ways. (1) Mobile never RENDERS section
state: getCurrentSectionLabel/getCurrentSectionOrder/getSectionIdFromOrder,
currentSectionId/completedSections/sectionFieldCount, and the 1s poll were all
declared but no JSX consumed them -- the compact panel shows only whole-form
counts computed straight from the schema prop. So instead of gating dead
machinery, DELETED it (less legacy for the 55jg deletion bead); the
load-bearing SchemaFormStateManager.init side effect in the mount hook stays.
(2) The disclaimer trigger is ALREADY correct in continuous mode:
switchToFirstSection routes through startSection, whose continuous guard sends
the whole-form handshake -- no behavior change needed in either overlay.
Documented at the connection.ts method; the "FirstSection" rename is
deliberately deferred to 55jg (it should go with the legacy path it names).

New VoiceOverlayMobile.continuous.test.tsx pins: in continuous mode the mobile
overlay renders NO section label/nav and shows the whole-form counts.

Live drive (the bead's stated verification, local stack on Vertex -- dev-local
forces AI Studio whose credits are dead, so the backend ran manually with
VERTEXAI=true): real I-90, real Gemini session. Desktop: header shows the FORM
TITLE (the #405 fix live), disclaimer accept -> "Continuous-session mode
enabled by backend" -> startSection -> session ready (console-verified), DTI
SI sent (backend log, 4622 chars). Mobile width (innerWidth-driven classifier;
the OS refused a real window resize, so the classifier was driven by spoofing
innerWidth + a resize event -- the app's own code path end to end): FAB +
panel render, NO section UX, "132 fields" whole-form count, and the live
session SURVIVED the desktop->mobile breakpoint cross (status stayed
connected). Pagination: the "Section N of 28" display divisions render;
manual Prev/Next is deliberately absent in continuous mode by pre-existing
design (bd x8rt: a manual section jump would desync the visible section from
the voice session; only Submit shows) -- unchanged by this diff.

Chrome-MCP gotcha re-confirmed (existing memory): computer-tool ref clicks
did not register on this SPA; el.click() via javascript_tool works.

## Lessons

- "Ungated for continuous mode" can mean dead code, not visible damage --
  check what actually RENDERS before porting a gate. Deleting beat gating.
- When the OS window will not resize, driving the app's own innerWidth
  classifier (defineProperty + resize event) exercises the real breakpoint
  code path -- including the overlay swap and session survival across it.

## Doc freshness

None to bump: overlay internals have no tier-2 doc section stating the mobile
section machinery; the continuous-mode framing sweep remains C8 (ft47).

## Files touched

- frontend/src/demo/VoiceOverlayMobile.tsx (dead machinery deleted)
- frontend/src/shared/connection.ts (switchToFirstSection continuous comment)
- frontend/src/demo/VoiceOverlayMobile.continuous.test.tsx (new pin)
- docs/journal/entries/2026-07-12-bd-4l7p-mobile-overlay-parity.md (this)
