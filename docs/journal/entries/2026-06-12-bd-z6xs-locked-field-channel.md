---
date: 2026-06-12
bead: polyglot-pdf-z6xs
title: "Locked-field rejection now reaches Gemini via completion_message"
tags: [bugfix, frontend, webFormConnection]
---

## Trigger

Discovered during wpw.3 (bd polyglot-pdf-wpw.3): when AI tried to fill a
hidden/locked field, `webFormConnection.ts` sent a `dependency_error` WS
message. The backend `websocket_routes.py` has no handler for that type --
it falls through to `unknown_control_message_type` plus an `error` reply.
Gemini never learned why the field didn't fill, so it kept re-attempting.

## What shipped

Replaced the `dependency_error` send with a `completion_message` send,
using the same field spoken_name + reason phrasing but routing it through
the proven in-band channel that `handleAiValueRejected` already uses. The
message text tells Gemini not to re-attempt locked fields until prerequisites
are met. Added a directive: "Do not attempt to fill them again until the
prerequisite fields are completed."

Two regression tests added to `webFormConnection.aivalidation.test.ts`:
one confirms `completion_message` fires when a locked field is targeted,
one confirms it does NOT fire for a normal (unlocked) field update.
