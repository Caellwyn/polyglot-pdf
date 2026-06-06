---
date: 2026-06-06
bead: polyglot-pdf-dem
title: "Remove per-event PTT keyboard console logging (held-key spam)"
tags: [refactor]
---

## Trigger

`bd polyglot-pdf-dem`. During a demo, holding Spacebar flooded the console with
`[PTT Keyboard] Space down, repeat: true ...` / `Not calling press - repeat: true`
on every OS key-repeat event for the whole duration of the hold. The maintainer
confirmed PTT itself **works correctly** -- the only ask was to remove the
console spam.

## What shipped

Removed the per-event debug `console.log` calls from the Spacebar PTT keydown/keyup
handlers in `frontend/src/demo/VoiceOverlay.tsx`:

- `Space down, repeat: ...` -- fired on every keydown, including the continuous
  auto-repeat stream while a key is held (the actual flood).
- `Not calling press - repeat: ...` -- the else-branch that fired on every ignored
  repeat (the other half of the flood).
- `Calling handlePushToTalkPress()` / `Calling handlePushToTalkRelease()` /
  `Space up` / `Not calling release` / `Ignoring - typing in form field` -- the
  remaining per-keystroke debug lines in the same two handlers, removed for
  consistency (same noise class, all bring-up debug).

The control flow is unchanged: the repeat-guard (`if (!e.repeat && isConnected)`)
and the input-focus guard still work exactly as before; only the logging was
removed. The two now-empty `else` branches (which existed solely to log) were
collapsed. A short comment was left on the repeat-guard explaining WHY it ignores
repeats (held-key auto-repeat), since that is the non-obvious behavior the logs
used to document.

**Deliberately left in place** (out of scope, not spam): the `[PTT Safety]`
force-release warnings (they fire rarely, on genuine edge cases, and are useful
diagnostics), the once-per-mount lifecycle logs (attach/remove listeners), and
the `[PTT]` press/release-handler logs (those fire once per push, not
continuously -- trimming them would be scope creep beyond this bead).
`VoiceOverlayMobile.tsx` has no Spacebar/keyboard PTT logging (mobile is
touch-only), so no change there.

## Lessons

None novel. (Standard bring-up debug logging outliving its usefulness.)

## Doc freshness

No tier-1/2 doc tracks this logging detail; nothing to bump. Pre-existing stale
docs from earlier 2026-06-04 backend work remain stale independent of this change.

## Files touched

- `frontend/src/demo/VoiceOverlay.tsx` -- removed per-event PTT keyboard logs
  (-13/+2).
