---
date: 2026-07-15
bead: polyglot-pdf-taw3
title: "fix(voice): form stalls after first field -- isFormComplete required-only short-circuit (PR #437 regression)"
pr: "PENDING"
tags: [hotfix, testing, postmortem]
---

## Trigger

A shipped regression: on the deployed app, after the user confirmed the FIRST
field the voice model announced "all fields have been confirmed" and would not
advance to the next question. Reported by the maintainer testing the live demo.

Root cause traced to PR #437 (bd polyglot-pdf-a1ql, merged 2026-07-14), which
migrated the I-90 form kit to the canonical `validation.required` shape and marked
the A-Number field required. That made the A-Number the ONLY required field on the
132-field I-90 form. The frontend's `isFormComplete` had a required-vs-optional
short-circuit: when a form had ANY required field, completion was defined as "all
REQUIRED fields confirmed" and every optional field was ignored. So the instant
the A-Number (the first field asked) was confirmed, `isFormComplete` returned
true, the post-confirm next-field hint round-trip came back null, and the backend
told the model "All fields confirmed." Before #437 no field carried
`validation.required`, so the gate always took its "all fields" branch and the bug
was latent.

## What shipped

Made `isFormComplete` (frontend/src/navigation.ts) **required-agnostic**, per the
maintainer's product correction: this product does not distinguish required from
optional -- the voice model asks for every currently-shown field and the user may
skip or NA any of them. The completion rule is now a single uniform pass: the form
is complete when EVERY currently-shown field is confirmed. Hidden fields
(`field.hidden` or an unmet `show_if`, via `shouldShowField`) are excluded; a
skipped/NA'd field already stores `confirmed: true` (SchemaFormStateManager.
markFieldSkipped sets an empty value + `confirmed: true`), so "confirmed"
transparently covers answered, NA'd, and skipped-for-review fields. The
`hasRequiredFields` branch is removed entirely. `computeNextField` already iterated
all shown fields regardless of required-ness, so this one gate change fixes the
whole confirm -> next-hint -> complete flow; the backend just relays the hint the
client computes.

Two maintainer decisions settled the semantics before the edit: (1) a skipped/NA'd
field counts as done, so the form can complete with fields still flagged for
follow-up; (2) hidden fields are excluded from the completion check.

Tests updated (no new dependencies):
- switch-to-field-pin.test.ts: the pin-integration fixtures keyed off the old
  "all required confirmed -> complete" baseline. Reframed so the baseline/stale-pin
  cases confirm ALL shown fields (the pinned field left unconfirmed only in the
  live-pin case), keeping each test focused on the pin logic, not the deleted
  required short-circuit.
- webFormConnection.proactivecomplete.test.ts: two tests explicitly asserted
  form_complete firing while an optional field was still empty (the old semantics).
  Reframed to reach completion via a SKIPPED last field (the new required-agnostic
  path) -- one through the manual-edit flow, one through the voice skip_field flow --
  each still proving its original property (buildValidatorFields' non-empty payload
  filter; maybeEmitFormComplete firing on the voice path).

Full frontend suite green: 65 files / 979 tests. A throwaway repro test against the
exact shipped scenario (1 required field confirmed, rest empty) confirmed the form
no longer reports complete after field 1 and offers the next field.

Related bead noted, not closed: polyglot-pdf-tg0s ("Mark the genuinely-mandatory
I-90 fields required") was filed as a fast-follow to mark more I-90 fields
required. With completion now required-agnostic, required-ness no longer affects
form completion, so tg0s is no longer needed to fix THIS bug -- but it may still
matter for the section-validity gate / PDF review (a product call), so it was left
open.

Assess: exit-criteria rubric scored PASS/PASS (see PR body scorecard). Fresh-eyes
inner loop + Opus outer review breakdown recorded in the merge ping.

## Lessons

A latent completion bug hid behind a data-only change. `isFormComplete`'s
required-only short-circuit was harmless for as long as NO field on any live form
was marked `validation.required`; the moment a kit migration set the flag on one
field (a change that looked purely like data/metadata), the logic branch it fed
went live and broke progression. Lesson: a completion/gating predicate that
branches on a field-level flag is coupled to the data even when the code doesn't
change -- a kit/schema edit can flip its behavior. When the product does not
actually use a distinction (required vs optional here), a predicate that branches
on it is latent risk, not harmless generality.

## Doc freshness

check_doc_freshness reported no stale docs for this change. The only tier-2 doc
near this area, docs/components/schema-forms.md, tracks the `schema-forms/` subtree
(schemaFormState.ts, validation.ts, etc.), NOT the top-level
frontend/src/navigation.ts that this change touches, so nothing was in scope to
bump. Reviewed and left as-is.

## Files touched

- frontend/src/navigation.ts -- removed the required-vs-optional short-circuit from
  isFormComplete; completion is now "every currently-shown field confirmed"
  (hidden excluded; skipped/NA counts as confirmed). Rewrote the doc comment.
- frontend/src/__tests__/switch-to-field-pin.test.ts -- reframed the pin-integration
  fixtures off the deleted required-only baseline.
- frontend/src/webFormConnection.proactivecomplete.test.ts -- reframed two
  required-only-completion tests to skip-driven completion.
- docs/journal/entries/2026-07-15-bd-taw3-form-complete-required-agnostic.md -- this
  entry.
