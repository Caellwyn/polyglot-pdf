---
date: 2026-06-15
beads: [polyglot-pdf-snpi, polyglot-pdf-979r]
pr: TBD
tags: [testing, refactor]
---

# snpi + 979r: custom kit schema filename in deploy + field-count pluralization

Two small, unrelated bugfixes bundled into one PR (each too tiny for its own
review cycle; different surfaces -- a deploy script and a schema-editor display
string -- so they do not interact).

## snpi -- deploy-all.sh ignored a kit's custom schema filename

`deploy-all.sh` has two loops over `form-kits/*/`: an UPLOAD loop and a MANIFEST
loop. Both hardcoded `schema.json` as the kit's schema file -- the presence check
(`[ ! -f "$kit_dir/schema.json" ]`), the title extraction, and the manifest's
`schemaFile`/`schemaPath` entries. But a kit's `metadata.json` may declare a
custom schema filename via the `schema` field (`KitMetadata.schema`, resolved on
the editor side in `formKitDirectory.ts` as `meta?.schema || 'schema.json'`). A
kit with `metadata.json {"schema":"custom.json","status":"complete"}` therefore
PASSED `kit_is_complete` but was then silently skipped by the schema-file check
with a misleading "no schema.json found" warning -- never uploaded, never in the
manifest the voice app reads.

Fix: a new `kit_schema_file()` helper next to `kit_is_complete()`, same
discipline (whitespace-tolerant `grep -Eo`, no jq dependency), mirroring the TS
resolution -- it echoes the custom filename when `metadata.json` carries a
`schema` field, else defaults to `schema.json` (also the default when
`metadata.json` is absent). The resolved filename now threads through the
presence check, the title extraction, and the manifest entry in BOTH loops.

### Verification (snpi)

`bash -n deploy-all.sh` parses clean. The helper was unit-exercised by hand
against four cases -- custom filename, metadata-without-`schema`-field,
no-metadata, and a whitespace-padded `"schema" : "..."` -- all resolving as
expected. A proper bats/functional harness for these deploy gates is the SEPARATE
open bead `polyglot-pdf-45x5` (a bats runner does not exist in the repo yet and
`bats` is not installed); writing one here would pre-empt that bead's scope, so
the functional check stayed hand-run.

## 979r -- "1 fields" grammar (green-but-wrong test)

The schema-editor's `PDFViewer` toolbar rendered the positioned-field count as
`{count} fields` unconditionally, so a single positioned field showed the
grammatically-wrong "1 fields". This is a clean instance of the green-but-wrong
pattern the uov.16 re-audit targets: the existing test ASSERTED `'1 fields'`, so
it encoded the bug as expected output -- a future singular fix would have broken
the test instead of the bug being caught.

Fix: render `count === 1 ? '1 field' : `${count} fields``. The single-field test
now asserts the singular `'1 field'` (and that `'1 fields'` is absent), and a NEW
test gives a second field a `pdf_position` to pin the plural branch ("2 fields").

### Verification (979r)

`schema-editor` vitest: `PDFViewer.test.tsx` 9 tests pass (the 2 pluralization
tests + the existing 7). `tsc --noEmit` clean. (One-time setup: `schema-editor`'s
`node_modules` was empty in the main repo -- ran `npm ci` there, then junctioned
it into the worktree, same pattern as the frontend FE-test harness.)

## Closeout notes

- **Doc-freshness:** the freshness gate flagged several STALE docs
  (`confirmation-and-audit.md`, `hipaa-pii-policy.md`, `stateless-architecture.md`,
  `schema-forms.md`, `risk-rating.md`, `terminology.md`, `context-compression.md`,
  `auth.md`). EVERY one tracks backend/frontend files this PR did NOT touch
  (callback_handler, form_filling_service, websocket_routes, schemaFormState,
  webFormConnection, connection.ts, manifest_service) -- pre-existing staleness
  carried in from other merged work. This PR touches only `PDFViewer.tsx`,
  `PDFViewer.test.tsx`, and `deploy-all.sh`, none of which any tier-2 doc's
  `**Tracks:**` line covers. Per the doc-freshness rule, a doc stale on files this
  branch didn't change is not this PR's to bump.
- **Beads slip:** housekeeping flagged 2 stale IN_PROGRESS beads (`hrn`, `jf6w`) --
  both belong to OTHER active sessions (the harness-tuning and connection-timeout
  epics), not this work, and `jf6w` is on the maintainer's do-not-touch list. Left
  untouched.
