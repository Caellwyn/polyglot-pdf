---
date: 2026-07-12
bead: polyglot-pdf-55jg
title: "Deprecate (not delete) the section-reset production path -- marked for later deletion"
sprint: 11
tags: [conventions, doctrine]
---

## Trigger

Sprint-11 epic polyglot-pdf-fc7t child C7. Originally scoped as the LEGACY
DELETION (gated on a demo test-drive). Maintainer changed the direction
mid-session (2026-07-12): DEPRECATE in place, do NOT delete -- keep section-reset
as a fallback in case continuous-DTI hits an unsolvable issue down the road, and
mark it clearly so a later deletion is mechanical.

## What shipped

17 greppable `DEPRECATED (bd polyglot-pdf-55jg):` markers on the production-only
section-reset sites (inverted from the 7872 RETIREMENT-CANDIDATES inventory):
switch_section tool decl + legacy-SI text (config.py), its dispatch +
_handle_switch_section_tool (callback_handler.py), handle_switch_section +
_complete_section_switch (form_filling_service.py), request_section_info /
the prepare_section_switch request (request_coordinator.py), and the FE
section-switch machinery (handlePrepareSectionSwitchRequest, proceedSectionSwitch,
resolve/cancelPendingSectionSwitch, the non-continuous else-branch in
startSection, connection-level switchToSection, completeSection in
webFormConnection.ts; markSectionComplete + state-manager switchToSection in
schemaFormState.ts). Comments only -- zero behavior change.

The KEEP list stays UNMARKED and live (verified by diff + grep): the shared
switch_to_section / _switch_to_section_locked restart primitive (continuous
GoAway/1011 reconnect + the harness baseline arm both drive it), the legacy
full-SI renderer (harness --arm section-reset instrument), the jit transport,
the ai_context rollback route, switch_to_field, the continuous-mode guards
themselves (only the section-reset BODY they route away from is marked), and
every section-reset test (they now guard the deprecated-but-live fallback).

Source of truth: docs/standards/section-reset-deprecation.md (marked-site
inventory + KEEP list with reasons + flag routing + a to-delete-later
pointer); INDEX standards row added.

Because nothing is removed from the running path, this needs NO demo deploy
(the original C7 gate) -- the flags already route around it. Verification: both
suites green (comments-only); the deprecated fallback still imports/constructs
(handle_switch_section + the shared switch_to_section both present, section-reset
Settings(USE_DTI=False, CONTINUOUS_SESSION=False) constructs); the harness
--arm section-reset path parses.

Implementation delegated to a Sonnet subagent with the exact inventory + hard
KEEP boundaries; orchestrator-reviewed every marker against the KEEP list (the
load-bearing check: switch_to_section stays unmarked -- confirmed).

## Lessons

- "Deprecate, don't delete" inverts a deletion inventory but does NOT invert the
  KEEP/delete split: the shared + harness-consumed code that a deletion would
  preserve is ALSO what a deprecation must leave unmarked -- marking it
  deprecated would be a lie about live code. The KEEP list is boundary-critical
  either way.
- A deprecation pass removes the deploy gate a deletion carried: nothing leaves
  the running path, so there is no live-behavior risk to test-drive -- only the
  "did I mismark a live symbol" review, which is a diff read, not a deploy.

## Doc freshness

New: docs/standards/section-reset-deprecation.md + INDEX row. The epic's own
docs-alignment bead (ft47) now describes continuous-DTI as the law AND
section-reset as a deprecated fallback (not gone) -- scope adjusted for the
deprecate-not-delete decision; noted for when ft47 is picked up.

## Files touched

- backend/config.py, backend/services/callback_handler.py,
  backend/services/form_filling_service.py,
  backend/services/request_coordinator.py (markers)
- frontend/src/webFormConnection.ts,
  frontend/src/schema-forms/state/schemaFormState.ts (markers)
- docs/standards/section-reset-deprecation.md (new), docs/INDEX.md (row)
- docs/journal/entries/2026-07-12-bd-55jg-deprecate-section-reset.md (this)
