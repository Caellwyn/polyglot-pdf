---
date: 2026-08-04
bead: polyglot-pdf-47r3
title: "The audit trail names the kit and the edition, with a fallback for custom forms"
tags: [security, conventions, testing]
---

## Trigger

The maintainer read the bd `polyglot-pdf-n0em` summary (PR #540, "the audit
trail now names the form") and asked the right follow-up:

> "so this will ensure that forms with the same name will be identified by their
> metadata identifier? will this differentiate by release version of the form?
> Government updates forms regularly, we want them pinned by version."

Both answers were **no**. `n0em` recorded a form NUMBER (`"W-7"`), which
identifies neither:

- **which KIT** -- `form_number` is not unique. Two kits can carry the same one
  (a standard W-7 and a firm-specific variant, which the firm-tier epic
  `polyglot-pdf-02ye` anticipates via per-firm proprietary forms).
- **which EDITION** -- agencies revise forms and enforce edition dates. A W-7
  filled against the 12/2024 edition and one filled after a later revision read
  identically in the trail, so a disputed filing could not answer "which edition
  did the client confirm these answers against?".

## What shipped

**Three identity fields on every confirmation event**: `form_id` (the number,
from `n0em`), plus `kit_id` and `edition_date`. The client sends `kit_id` from
`onboardingStorage` (the kit the user actually picked) and `edition_date` from
`form_metadata`; the route threads `edition_date` into the minimal JIT schema's
`form_metadata` like `form_number`, while `kit_id` is read at the SHARED
handshake scope and passed as its own argument -- it names the kit, not the
form, so it is not a `form_metadata` key and both transports need it.

**`edition_date`, never `version`.** Measured across the shipped kits first:

    w7:    form_number="W-7"   version="December 2024"  edition_date="12/2024"
    i-90:  form_number="I-90"  version="v9_conformant"  edition_date="01/20/25"
    f1040: form_number="1040"  version="draft"          edition_date="2025"

`version` is a schema-AUTHORING field -- `v9_conformant` is an extraction output
format, `draft` is kit status. It LOOKS like a version and means something
different per kit; recording it would have put a version-shaped field with
per-kit semantics into a legal record. `edition_date` is the government's own
marker and is present on every kit.

**A fallback, not a gate** (maintainer correction mid-implementation). The first
cut made a missing `edition_date` an ERROR blocking Mark-complete. The
maintainer: *"Some custom forms for future clients may not have that metadata.
Rather than a gate, we need a fallback."* A firm's proprietary intake sheet has
no government edition, and blocking publish would make the product unusable for
exactly the firm-tier customers it exists to serve. So:

- schema-lint emits `audit-identity-no-edition` as a **WARNING** (advisory,
  never blocks), with a label AND a remedy sentence in the editor panel;
- `resolve_edition_marker` falls back to a fingerprint of the kit's
  **answerable shape** (field ids + types + option values), `sha256:<12 hex>`.
  Deliberately excludes labels and guidance prose: a copy edit must not read as
  a new revision, while adding/removing/retyping a field or changing an option
  value must. Verified all four properties by direct execution.

**`metadata.published_at` stamped on promotion.** The maintainer proposed the
marked-complete date as a better fallback than a digest -- correct, and it is
now recorded on every publish (preserved across a revert to draft; moved on
re-publish, which is the revision signal). SURFACING it into the audit record is
deferred: kit metadata is not reachable where the record is written (an uncached
GCS read per call, the client never sees it, the manifest does not carry it), so
it needs a wire change. That plus author-supplied versions is epic
`polyglot-pdf-7jmy`.

## Scope corrections made during the work

**The "edition drift" this bead was filed to fix did not exist.** The bead (and
the PR-#540 review finding behind it) claimed `form-kits/w7` and
`frontend/public/form-kits/w7` disagreed (`12/2024` vs `December 2024`) and
needed normalizing. `frontend/public/form-kits/` is **gitignored build output**:
`generate-form-manifest.ts` does an `fs.cp` from `form-kits/` on every build.
Proven by running the prepare script -- the bundle copy rewrote itself from
`December 2024` to `12/2024` in one pass. There is one source of truth; the
stale value was a local artifact. The lint rule checks that source instead.

**Two catalogue-hygiene requirements surfaced and were split out.** The
maintainer flagged the real constraint behind versioning -- *"I don't want a
client's form manifest to be cluttered with 50 slightly different versions of
the same form"* -- plus a need for authors to unpublish or delete obsolete kits.
Filed as epic `polyglot-pdf-7jmy` with two design decisions settled: superseded
revisions stay in storage but leave the manifest (so an old confirmation record
still points at a schema that EXISTS), and hard delete is refused when
confirmation records exist for that kit (offer unpublish instead).

**Fresh-eyes round 1 (Sonnet): GAPS-FOUND (2 rubric FAILs + 2 notes), all
adopted.** The reviewer reproduced a real bug empirically rather than arguing
it:

`_switch_to_section_locked` re-enters `start_session` with the NEW SECTION's
schema and no `kit_id` / `full_schema`. My assignments were UNCONDITIONAL, so on
every section switch `kit_id` reset to `None` and the fingerprint was recomputed
from a single-field section schema. For any multi-section form -- the normal
case -- every confirmation after section 1 lost its kit, and the "pinned"
revision marker CHANGED mid-session. Both exit criteria therefore failed.

The sting: the correct pattern sat three lines above my code
(`if full_schema is not None: self._full_schema = full_schema`), added for
exactly this trap, and an existing test
(`test_switch_to_section_preserves_form_session_id_in_callback_handler`, bd
`rwjy`) guards the identical failure for `form_session_id`. I copied the
*intent* -- my own comment said the values were "stored so
`_switch_to_section_locked` can thread them" -- without the *mechanism* that
intent requires, which made the comment false.

Fixed: preserve `kit_id` when the caller supplies none; recompute the edition
marker ONLY when `full_schema` is present (a client (re)connect). Guarding on
`edition_date is not None` alone was NOT enough -- the section schema still
yields a wrong fingerprint from its own fields. The CallbackHandler now receives
`self._kit_id` / `self._edition_date`, not the local args. Two regression tests
mirror the `rwjy` precedent; both fail under a reverting mutation.

Also adopted: the docs asserted a stronger guarantee than the code delivered
(now true, and the session-spanning behavior is stated explicitly). Not adopted
as a change: `full_schema or schema` truthiness (the reviewer's low-confidence
nit) -- switched to `is not None` anyway while fixing the same lines, since it
is the consistent idiom.

## Lessons

- **A `-k`-filtered run is iteration, never evidence.** I reported "21 passing"
  from keyword-filtered runs; the full suite then failed two tests those filters
  had never selected. One was a bug in MY OWN new test (it asserted a legacy
  client records `edition_date: None`, when the fallback correctly produces a
  fingerprint -- the assertion contradicted the feature's entire point). The
  other was `test_lint_rule_parity.py`, which I did not know existed. A filter
  cannot catch a test it does not select. The repo memory already said this;
  I did not follow it.
- **A new lint rule is a CROSS-SURFACE change.** Two parity guards enforce that
  every backend rule has both a human-readable label and a remedy sentence in
  `schema-editor/src/components/ValidationPanel.tsx` -- otherwise a contractor
  sees a raw internal id with no idea what to do. Excellent guard design: one
  test for "is it named", a second for "does it say what to DO".
- **Check whether the artifact is generated before "fixing" it.** Two of us
  (me and a reviewer) treated build output as a second source of truth and
  planned a normalization that a single build would have undone.
- **A severity choice is a product decision.** ERROR vs WARNING on a lint rule
  looks like a style call; here it decided whether firms with proprietary forms
  could publish at all. The 23 failing fixtures were the signal that the rule
  was mis-scoped, not that the fixtures needed editing.
- **When adding a field beside one that is deliberately PRESERVED, copy the
  preservation, not just the placement.** `start_session` is re-entered by the
  internal section-switch restart with partial arguments, so anything assigned
  unconditionally there silently resets mid-session. `_full_schema` and
  `_form_session_id` both carry guards for this; I put my fields next to them
  and assigned unconditionally. The tell was available in my own comment, which
  claimed a persistence the code did not implement -- a comment describing
  behavior the lines below do not produce is worth re-reading as a bug report.

## Doc freshness

Bumped with substance: `docs/standards/ws-protocol.md` (the two new handshake
keys + the fallback note; the existing contract test demands documentation for
any key the route reads) and `docs/standards/confirmation-and-audit.md` (the
three-field event shape, why three not one, and a new section on kits with no
government edition). Both stamps updated.

## Files touched

- frontend/src/schema-forms/state/schemaFormState.ts -- send kit_id + edition_date
- backend/routes/websocket_routes.py -- read both; kit_id at shared scope for both transports
- backend/services/form_filling_service.py -- resolve the marker, thread to CallbackHandler
- backend/services/callback_handler.py -- carry kit_id/edition_date into the log call
- backend/utils/confirmation_logger.py -- resolve_edition_marker + the two new event keys
- backend/services/schema_lint.py -- audit-identity-no-edition (WARNING)
- backend/routes/editor_kit_routes.py -- stamp metadata.published_at on promotion
- schema-editor/src/components/ValidationPanel.tsx -- rule label + remedy
- backend/tests/unit/test_jit_handshake_form_id.py -- 5 new route-level tests
- backend/tests/unit/test_confirmation_firestore_sink.py -- allowlist + 6 fallback tests
- backend/tests/unit/test_editor_kit_routes.py -- 3 publish-date tests, 2 fixtures given an edition
- backend/tests/test_schema_lint.py -- 4 lint-rule tests + the audit-identity filter
- frontend/src/schema-forms/state/schemaFormState.test.ts -- 2 handshake tests
- docs/standards/ws-protocol.md, docs/standards/confirmation-and-audit.md
