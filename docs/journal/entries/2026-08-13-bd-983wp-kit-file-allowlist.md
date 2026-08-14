---
date: 2026-08-13
bead: polyglot-pdf-983wp
title: "A published kit was serving its superseded schemas -- and the fix's own allowlist admitted a leak"
sprint: 19
tags: [testing, conventions, review, security]
---

## Trigger

Found while closing bd polyglot-pdf-fqexm. That bead gated WHICH KITS reach the
public bundle; this one gates WHICH FILES within a published kit, which turned
out to be a separate leak with a worse payload.

## What was wrong

Every file in a published kit's directory was copied to Firebase Hosting and
served at a guessable path. On the real tree:

    i-90/schema_archived.json        superseded revision
    i-90/i-90_schema_backup.json     superseded revision
    i-90/migration_report.json       authoring artifact
    i-90/i-90-annotated.pdf          authoring artifact
    w7/schema_archived.json          superseded revision
    w7/migration_report.json         authoring artifact
    w7/w7-instructions.pdf           editor-side input (booklet extraction)

The superseded schemas are the real problem: those are the bytes the revision
archive (bd polyglot-pdf-w3zw / xzw5) exists to keep behind authenticated
access. bd w3zw already excluded `_`-prefixed names at every level -- which
catches `_archive` and `_translation` -- and these slipped through because they
carry ORDINARY names.

## What shipped

An ALLOWLIST, not a denylist: a file ships only if the client fetches it. A
denylist is one new filename away from leaking again, which is exactly how these
survived w3zw.

The allowlist is PER KIT, built from that kit's own metadata, because a kit may
declare its own schema/pdf filenames. And the declared names are coerced through
`safeKitFilename`, mirroring the backend's `safe_filename` -- same regex, same
degrade-to-default behaviour.

A published kit now ships exactly two files: its schema and its PDF.

## The finding that matters most: my own allowlist admitted a leak

Round 5 caught `metadata.json` still shipping. I had allowlisted it and
justified it in the docstring as "carrying the label the catalogue renders."
Both halves of that were wrong: `index.json` already embeds label and
description, and nothing in `frontend/src` fetches `metadata.json` from the
bundle at all.

Worse, the file had grown since I wrote that justification. The editor now
writes a `readiness` block (review counts, error totals, `schema_sha1`, who
stamped it) and an `editing_lock` naming the role holding the kit. So a
published form was serving internal review state to anonymous clients at a
guessable path -- the exact class this bead exists to close, admitted by the
allowlist doing the closing.

The general lesson: **an allowlist entry is a claim about a consumer, and that
claim rots.** Mine was written when the file was three keys; it was still there
when the file became a review-state record.

## Six rounds, twelve findings, and the same mistake four times

The gate was right early. Almost every finding was about whether the TESTS could
detect it being wrong:

- A kit declaring a NESTED schema (`sub/schema.json`) was indexed and published
  with no schema -- listed in the catalogue, 404 on open. A silent per-form
  outage, and a regression against `origin/dev`.
- My per-kit test passed under a GLOBAL UNION allowlist, because the two fixture
  kits had disjoint filenames. The Set -> Map change is the structural heart of
  the diff and was entirely unpinned.
- My allowlist made the pre-existing underscore guard's tests VACUOUS: deleting
  that guard left 29/29 green, because the allowlist blocks the same paths for a
  different reason. Adding a second reason a thing is excluded can hide the first.
- The pdf half of the coercion, the depth check, and the coercion warning were
  each deletable with every test green.

**And four times a fixture was excluded by the WRONG RULE:**

1. A file under `<kit>/_archive` -- excluded by the depth check, not the
   underscore guard it was written for.
2. `_archive_secret.json` -- excluded by the underscore guard, not the charset
   rule it was named for. My comment asserted the opposite.
3. `form.pdf.d/` -- not an allowlisted basename, so the depth mutation it
   targeted survived anyway.

Each time the test looked correct, passed, and proved nothing. **The rule: a test
for a rule must be refused BY that rule and no other -- and green tells you
nothing about which rule did the work.** Only mutating the specific rule and
watching the specific test does.

The corollary I kept relearning: when a mutation survives, the first suspect is
the fixture, not the code.

## Cross-surface result

The outer review traced every changed contract into untouched consumers and
found the blast radius clean. It rebuilt the real bundle on both branches and
diffed: `origin/dev` emits 14 files, this branch emits four.

It found one thing worth recording: this diff **invalidates the stated premise
of a security decision in an untouched file.** `GET /api/form-kits/{id}/pdf` is
deliberately unauthenticated, and its docstring justifies that with "the same
blank-template bytes ship publicly in the frontend bundle regardless." That was
true when the bundle was a blanket recursive copy. It is not now -- the
anonymously-reachable Hosting set is strictly smaller than what that route
serves. Nothing regresses today, but a security decision resting on an argument
its own mechanism no longer supports is how the next person "confirms" it is
safe without re-deriving it. Filed as bd polyglot-pdf-5t377.

The GCS bucket still receives every file in a kit. That divergence is
deliberate: the bucket is the authenticated store that the revision-retrieval
tool and the booklet-extraction route must read from, while Hosting is an
anonymous CDN. Confirmed intentional rather than accidental.

## Follow-ups

- bd polyglot-pdf-5t377 -- the stale unauthenticated-route rationale.
- bd polyglot-pdf-v3suc -- the underscore rule applies to the COPY but not the
  INDEX, so an underscore-named kit is listed and unshipped. Pre-existing; the
  same index/copy split fqexm fixed for status.
- bd polyglot-pdf-cfl28 -- the `SchemaForm.previewEdit` flake, which has now cost
  debugging time in three separate beads.
