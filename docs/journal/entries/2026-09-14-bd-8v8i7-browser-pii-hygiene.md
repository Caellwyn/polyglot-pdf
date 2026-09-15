---
date: 2026-09-14
bead: polyglot-pdf-8v8i7
title: "fix(frontend): E1 browser PII hygiene -- console leaks gone, storage wiped on completion, idle and logout"
tags: [security-audit, frontend, pii, schema-forms]
---

## Trigger

Sprint 23 (the security + data-leak audit, epic `polyglot-pdf-uijam`, plan
`docs/sprint_23_security-audit_plan.md`), workstream E1, threat actor T6
(the browser on a shared law-office device). Two pre-findings: PF-13, raw
field values printed to the browser console at ten-plus sites in the
production bundle, including a demo-era submit handler that dumped the
whole map and told the client to "check console for field values"; and
PF-14, nothing ever cleared a client's answers (`schema_form_state`) or
their magic-link credential (`vff_client_link_token`) automatically, and
the voice app had no logout control. Built by a Sonnet builder in an
isolated worktree over three rounds; the orchestrator ran the review loops
and closeout.

## What shipped

**Console.** Every value-carrying site is deleted (state-manager field
dumps, the connection value preview, the PDF-filler checkbox dump, the
sample dump, the demo submit handler and its alert, the checkbox field).
`send()`'s two error branches log `{type, size}` / `{size}` only. The
WS-close diagnostic staff read on staging is promoted to `console.info`
so it survives the build-time strip: `esbuild: { pure: ['console.log',
'console.debug'] }` in the three production configs (`frontend/vite.config.schema.ts`,
`schema-editor/vite.config.ts`, `admin-console/vite.config.ts`). Two
guards: `consoleGuard.test.ts` extracts the identifiers in every console
call's arguments and fails on `fieldValues`, `current_values`, or anything
containing `token`/`credential` (identifier extraction, not `\b`, so
`link_token` and `linkToken` are caught); `bundleNoConsoleLog.test.ts`, one copy per
app (frontend, schema-editor, admin-console), each building only its own
app in its own CI job and asserting no `console.log(` survives, failing
closed on a missing env file or a failed build.

**Storage lifecycle.** `SchemaFormStateManager.clearAllClientState()`
composes the existing Clear-form path (`clear()` + `clearOnboardingState()`
+ `clearClientLinkToken()`, in that order) and runs on three triggers:

- **Completion** -- after a SUCCESSFUL download or print of a form whose
  `isFormComplete` is true, in a client-link session only: a 60-second
  non-restarting countdown banner with a "Done -- clear now" button, then
  the wipe. Never from the error path, never for staff (they may need both
  actions and have logout plus the Clear-form buttons).
- **Idle** -- the backend's `idle_timeout` is its 120-second no-traffic
  socket watchdog, not proof the person left, and the voice overlays
  answer that same status with a Reconnect button and a save prompt. So
  the wipe arms a 10-minute inactivity grace (`IDLE_WIPE_GRACE_MS`,
  exported, maintainer-tunable) behind a persistent banner with a live
  countdown and a "Keep my answers" button; any pointer, key or touch
  event, the button, a save, or the status leaving idle cancels it; it
  re-arms on a repeat idle; staff sessions get the same treatment. Only a
  full grace with no activity wipes.
- **Logout** -- the new `StaffHeader` (staff sessions only; renders nothing
  for a client link) calls the existing `useAuth().logout()` then the wipe.

All four wipe sites (idle, completion timeout, the "Done -- clear now"
button, and the logout handler's `finally`) end in
`window.location.reload()`, as the existing Start Fresh button does: the
mounted form still holds the answers in React state, and without the
reload the next keystroke would save them straight back. The SET is
pinned by `frontend/src/shared/wipeSitesReload.test.ts`, which scans
`frontend/src` for every `clearAllClientState()` call and fails on one
with no reload within a few code lines. The three new banners and the
header have their own CSS rules, reusing the existing warning palette.

`WebFormConnection.reset()` (dead) is deleted.

## Review record

**Fresh-eyes (sonnet): three rounds.** Round 1 GAPS-FOUND (2): the
completion clear fired the moment the voice session confirmed the last
field, before the client had the PDF -- moved to the download/print
success path with the callback plumbing removed rather than left dead; a
duplicated comment block. Plus nits adopted: the `\b`-based token match
missed snake_case/camelCase identifiers; the idle copy for a client link
now says reopening the link resumes; the "suspicious" branch no longer
logs an always-undefined `type`; the bundle test fails closed. Round 2
GAPS-FOUND (1): the wipe left the mounted form's in-memory values in
place, so the next keystroke re-saved them -- fixed in round 3 by reloading after every automatic wipe, pinned by
reload-once and ordering tests at each site. Round 3 GAPS-FOUND (2): the
fourth wipe site -- the logout handler -- had no reload (safe only
because a SUCCESSFUL sign-out unmounts the tree; a failed one left the
form able to re-save), and the ordering tests did not discriminate. The
third round finding the same shape was the enumerate-the-set tell:
round 4 added the reload there, pinned the whole set with a source scan,
and rewrote the ordering tests so the reload stub captures storage at
call time. Round 4 GAPS-FOUND (1), a doc sentence: the paragraph called the manual
Clear-form buttons' path "two-step" without saying what the missing step
is; reworded to name the gap (they never clear the link token, bd
`polyglot-pdf-ylokf`, which supersedes the narrower `ugn55`). Accepted
and recorded, not fixed: the set-pin scan is line-window based and a
reload in a sibling else-branch would fool it (no site has that shape);
a failed logout reloads without a message; a download landing exactly
as the idle countdown elapses could have its fetch torn off. Round 2 also
filed `polyglot-pdf-ugn55` (the pre-existing "Start Fresh" button never
clears the link token).

**Opus cross-surface review: two rounds.** Round 1 GAPS-FOUND (2), both
blockers and both adopted: the idle wipe fired 5 s after a status that
means "no socket traffic for two minutes" while the overlays were
offering Reconnect and a spoken save prompt -- replaced by the 10-minute
activity-cancellable grace above; and the bundle test built the other two
apps from inside the frontend CI job, which never installs their
dependencies -- split per app. Filed there: `polyglot-pdf-vzvkk` (three
non-PII sessionStorage keys survive the wipe), `polyglot-pdf-y6b48` (a
pre-existing voice-overlay test flake), `polyglot-pdf-b5c1t` (two doc
precision nits, folded in). Fresh-eyes round 5 on that delta: GAPS-FOUND
(0), one stale comment fixed. Round 2 NO-GAPS: every cancel path reaches
`document` unobstructed (no modal stops pointerdown/keydown), Reconnect
cancels the grace twice over, a failed reconnect lands on `error` so it
still cancels, mobile has parity, the per-app bundle tests match CI's
three jobs, and the dev merge reverted nothing. One filed and then fixed
in-PR: the idle banner promised that reopening the link resumes the form,
which only a saved PDF can do (`polyglot-pdf-xv4eb`); the copy now says so.

**Housekeeping reviewed and left:** other sessions' in-progress beads; the
stale-doc flags for files this branch did not touch. The prep script's
full backend suite passed (6052) though this branch touches no backend
file.

## Lessons

- **"Complete" has three different clocks.** The voice session's
  last-field confirmation, the backend's link burn at teardown, and the
  client's download are all "completion" to someone; the one that matters
  for wiping the device is the last one the client can observe. The bead
  said so; the first build picked the wrong clock anyway.
- **A wipe that leaves the page mounted is not a wipe.** Storage is a
  mirror of React state, and the next keystroke re-mirrors it. The
  existing Start Fresh button already knew this (it reloads); read the
  neighbours before designing a sibling.
- **Three rounds, three sites, one shape.** Rounds 2, 3 and 4 each found
  one more wipe site without a reload. The fix that ended it was not the
  fourth reload but the scan that enumerates every site (scar #8).
- **`\b` fails after an underscore, again.** Third time in this repo's
  memory; the fix is identifier extraction, not a cleverer boundary.

## Doc freshness

Bumped: `docs/components/schema-forms.md` (automatic-clearing paragraph +
stamp) and `docs/standards/hipaa-pii-policy.md` (new "Browser console +
sessionStorage" per-surface row + stamp). The maintainer decision this
bead surfaces for workstream G: the voice app's Firebase persistence mode
(`browserSessionPersistence` recommended for the voice app only, local
kept for editor/admin) -- recorded on the bead, not changed here.

## Files touched

- frontend/vite.config.schema.ts, schema-editor/vite.config.ts, admin-console/vite.config.ts -- `pure` strip
- frontend/src/schema-forms/state/schemaFormState.ts -- value dumps gone; `clearAllClientState()`
- frontend/src/shared/connection.ts -- value preview gone
- frontend/src/schema-forms/utils/pdfFiller.ts -- value dumps gone
- frontend/src/schema-forms/components/SchemaForm.tsx -- completion grace, idle clear, StaffHeader mount
- frontend/src/schema-forms/components/StaffHeader.tsx -- new logout control
- frontend/src/schema-forms/SchemaFormDemo.tsx -- submit dump + alert gone
- frontend/src/schema-forms/components/fields/CheckboxField.tsx -- dumps gone
- frontend/src/webFormConnection.ts -- redacted send() branches, info promotion, reset() removed
- frontend/src/schema-forms/styles/schema-form.css -- banner + header rules
- frontend/src/shared/wipeSitesReload.test.ts -- set pin: every wipe site reloads
- schema-editor/src/bundleNoConsoleLog.test.ts, admin-console/src/bundleNoConsoleLog.test.ts -- per-app bundle guards
- tests: consoleGuard.test.ts, bundleNoConsoleLog.test.ts, schemaFormState.clearAllClientState.test.ts, SchemaForm.completionClear.test.tsx, SchemaForm.idleClear.test.tsx, StaffHeader.test.tsx, webFormConnection.pii.test.ts
- docs/components/schema-forms.md, docs/standards/hipaa-pii-policy.md
- docs/journal/entries/2026-09-14-bd-8v8i7-browser-pii-hygiene.md -- this entry
