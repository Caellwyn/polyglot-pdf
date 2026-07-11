---
date: 2026-07-11
bead: polyglot-pdf-944q
title: "Continuous-mode overlay header shows the form title; two jnjj.36 review nits (empty-group has_value guard, alias-read precedence)"
tags: [hotfix, testing]
---

Bundled cleanup PR: bd polyglot-pdf-944q + bd polyglot-pdf-luju (small,
self-contained, collision-free with the active 6cfu epic).

## 944q -- continuous-mode overlay header label

In continuous-session mode the VoiceOverlay header showed the FIRST section's
label (`getCurrentSectionLabel` off the pinned `currentSectionId`) while the AI
fills the whole form. Cosmetic, no functional impact. Fix: `getCurrentSectionLabel`
returns `schema.form_metadata.title` in continuous mode. The field COUNTER was
already whole-form (`schema.fields.length`), so only the label needed changing.
New `VoiceOverlay.continuousheader.test.tsx` mounts the overlay in continuous
mode and pins the `.vff-section-label` to the form title (fails if the continuous
branch is removed).

## luju -- two deferred jnjj.36 review nits

**Nit 1 -- empty checkbox group in the switch_field ack.**
`handleSwitchFieldRequest` computed `has_value` with `!== ''` but no empty-array
guard, so switching to an unconfirmed EMPTY checkbox group acked `has_value:true`
and rode `value:[]` -- telling the model it "already holds an unconfirmed value"
when it holds nothing (the model reads back nothing). Mirrored the skip path's
guard (`!(Array.isArray(v) && v.length === 0)`), so an empty group now acks
`has_value:false` with no `value`. Pinned in `switch-to-field-pin.test.ts`.

**Nit 2 -- alias-read precedence for hollow entries.**
`readFieldEntryWithAlias` used `??`, which returns the exact-key ENTRY object even
when it is HOLLOW (`{value:null, confirmed:false}`), shadowing a real confirmed
answer under the `[]`-alias key. Decision (the bead asked to decide): a hollow
exact-key entry SHOULD fall through to the alias -- otherwise a genuinely
answered field reads as unanswered. Reworked to: meaningful exact-key wins ->
meaningful alias wins -> exact-key (else alias) as the all-hollow fallback.
`entryHasValue` treats null/undefined/''/[] as no-answer. Both callers
(`navigation.ts` pin-confirmed check, `webFormConnection.ts` switch ack) get the
real answer instead of the shadow. Precedence pinned with unit tests including the
hollow-shadow case.

## Verification

- Full frontend suite green (57 files / 909 tests, default forks pool); `tsc`
  clean.
- All three new test groups proven to fail on a revert of their respective fix.
