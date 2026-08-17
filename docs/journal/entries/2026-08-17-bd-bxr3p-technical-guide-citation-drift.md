---
date: 2026-08-17
bead: polyglot-pdf-bxr3p
title: "docs(technical_guide): fix remaining citation drift in sections 5-6"
tags: [conventions, testing]
---

## Trigger

While fixing bd x82ii (widespread citation drift in `ws-protocol.md` and the
WS-handshake block of `technical_guide.md`, PR #597), spot-checked the
remaining sections of `technical_guide.md` for the same drift class and found
it continued into sections 5 ("Fill round-trip") and 6 ("Confirmation audit
trail"). Those sections are a different topic (PDF filling, confirmation
audit logging) and x82ii's own comment scoped its widening to the
WS-handshake block specifically, so filed this as a separate bead rather than
expanding x82ii further.

## What shipped

Every `(line N)` / `:N` citation in sections 5-6 re-verified against live
source with the same small verification script used for x82ii, and every
mismatch fixed:

- **Section 5.** `SchemaForm.tsx`'s download/print handler ranges,
  `FilledPreviewModal.tsx`'s unwrap loop, `unwrapFieldValue`'s real def line,
  `pdfFiller.ts`'s request-payload assembly, the two-pass `[]`-alias
  resolution range, the field-type dispatch loop bounds, the skip-empty
  block, the `xref_set_key` radio-write lines. The `_load_kit_dump` citation
  was the most substantively wrong -- it named one arbitrary call site among
  7, not the actual mark-complete promotion gate (which is inside
  `set_editor_kit_status`), so a reader following it to understand "how does
  promotion see the AcroForm dump" would land in the wrong function entirely.
- **Section 6.** The whole `confirm_field` audit chain --
  `request_coordinator.py`'s `request_confirm_field`, `webFormConnection.ts`'s
  `handleConfirmFieldRequest` + `sendConfirmFieldResponse`,
  `callback_handler.py`'s `recorded` guard + `log_field_confirmation` call,
  `confirmation_logger.py`'s event-dict construction + all three sinks
  (structured log, JSONL file, Firestore), and the
  `kit_id`/`form_number`/`edition_date` origin citations (previously a single
  generic line range in the wrong file -- `schemaFormState.ts` at a line that
  wasn't any of the three actual assignment sites).

Both review layers cleared: Haiku fresh-eyes (diff-size-routed, since the
diff was small) spot-checked 35+ citations, NO-GAPS; the Haiku
`docs-reviewer` (docs-only diff) then reviewed prose + cross-doc consistency
against `ws-protocol.md` and `voice-ai.md` (both touched by the same-day
PR #597), NO-GAPS.

## Lessons

- **A citation naming the wrong call site among several is a different, worse
  failure than a citation naming the right function at a stale line number.**
  `_load_kit_dump` has 7 call sites; the doc's original citation happened to
  land on one that has nothing to do with the promotion gate it was meant to
  illustrate. A drift-fix pass that only re-derives line numbers for the SAME
  named symbol would have preserved this error -- it required reading what
  the sentence actually claims ("called from... the mark-complete promotion
  gate") and finding THAT specific call site, not just re-locating
  `_load_kit_dump`'s definition.
- **Splitting a large citation-drift bead by topic (not just by file) kept
  each PR reviewable.** x82ii and bxr3p together touch every citation in one
  file, but shipped as two PRs on the same day because they're different
  subsystems (WS protocol vs. PDF-fill/audit). Neither reviewer had to hold
  the whole file's citation set in mind at once.

## Doc freshness

- **Bumped:** `docs/technical_guide.md` -- re-stamped to today with a prose
  summary naming every citation class fixed; `check_doc_freshness.py`
  confirms OK.

## Files touched

- `docs/technical_guide.md`
