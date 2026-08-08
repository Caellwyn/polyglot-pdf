---
date: 2026-08-08
bead: polyglot-pdf-xzw5
title: "Author-supplied revision marker for forms with no government edition"
sprint: 19
tags: [testing, conventions, audit]
---

## Trigger

Sprint 19 (docs/sprint_19_firm-tier-kit-lifecycle_plan.md), epic
polyglot-pdf-7jmy child 3 of 4, unblocked by bd polyglot-pdf-6dz0.

`resolve_edition_marker` (bd 47r3) had two ranks: the government
`edition_date`, else a `sha256:<12hex>` fingerprint of the form's answerable
shape. The fingerprint is stable and changes when the form changes, which is
the property that matters -- but it is unreadable. A firm's own intake sheet
has no government edition, so every confirmation recorded against one named a
digest no human could act on in the dispute the record exists for.

The function's own docstring anticipated the fix and predicted it would need a
manifest/wire change, because the author version was expected to live in kit
METADATA, which the audit path never receives.

## What shipped

A third rank between the two: `form_metadata.author_version`, supplied by the
author at publish time.

- **Precedence** `edition_date > author_version > fingerprint`. The government
  marker still wins where it exists -- it is the only one an agency recognizes.
- **Required** to publish a kit with no `edition_date`. The refusal detail is
  PREFIXED `AUTHOR_VERSION_REQUIRED:`, a machine-readable contract both
  catalogues `startsWith`-match to open the version dialog.
- **Immutable once live** (maintainer decision): it is what existing records
  name, so changing it would silently re-point them at a revision those clients
  never saw. Scoped to `complete` -- a retired kit republishes freely, and a
  draft carrying a version from a failed publish stays editable.
- **Normalized** once, in one helper per surface: trim, then strip a leading
  `v`/`V` ONLY before a digit, so `v2` -> `2` while `version-3` survives.

The docstring's prediction was wrong twice over: the version arrived, and it
needed no wire change. It lives in `form_metadata` beside `edition_date`,
inside the schema the client already sends whole.

## Scar tissue

**1. The client cannot know which kits need a version -- and should not learn.**
`edition_date` lives in the SCHEMA, and the catalogue listing deliberately does
not read every kit's schema (that is what the readiness stamp exists to avoid).
Deriving the rule client-side would have undone that optimization. The server
emits a token on refusal instead: one rule, server-side, no extra reads.

**2. Verifying a value is COMPUTED is not verifying it ARRIVES.** Three separate
defects on this bead shared that shape, and all three passed every test:

- the normalized version was validated and then thrown away, because this route
  never wrote the schema (the drift sweep does, separately);
- the retirement archive was keyed on a fingerprint while records named the
  version, so the bytes sat on disk under a key nobody holds;
- `scripts/read_kit_revision.py` -- the operator read that closes the loop --
  still resolved through two ranks, so a LIVE versioned kit was unfindable.

The last one is the sharpest: the archive WRITER was fixed and pinned in this
same bead. Only the reader lagged, in a file the diff never touched, which no
inner review round would have opened.

**The fix that generalizes: pin the AGREEMENT, not either side.** The tests now
resolve the marker a confirmation record WOULD carry, then assert that same
marker retrieves the bytes. That shape catches all three; asserting either half
alone caught none of them.

**3. A five-path conditional needs the matrix re-derived, not the path in front
of you re-read.** I introduced a regression in each of two consecutive rounds
while editing the same branch chain: round 2 broke the draft-retry path, round
3 bricked retired kits (all four exits closed, and the error message named an
action the API forbids). Both times the fix was right for the case in hand and
wrong for a neighbour. The durable fix was a test parametrized over all three
statuses -- `unpublished` is the row that fails, and only enumeration finds it.

**4. A mutation run whose restore silently no-ops is worse than no mutation
run.** A string-replacement restore failed to match after a reflow, so a
deletion stood and the next two mutations ran against broken code; all three
verdicts were meaningless. Caught because a "restored" run still failed. Use a
file backup and assert byte-identity afterward -- and do not confirm a restore
by grepping for a phrase that also appears in a comment.

**5. `version` was already taken.** `form_metadata.version` exists and is
auto-extracted display text; real shipped values include `"draft"` and
`"v9_conformant"`. It could never serve as an audit marker, which is why the
new field is separate -- checked against the shipped corpus before building,
not assumed.

## Review record

Four inner rounds (5, 2, 2, 0 gaps) then two outer cross-surface passes (2, 0).
The outer re-ran because behavioral fixes void a clear. Eleven defects total;
overwhelmingly real behavior rather than weak assertions.
