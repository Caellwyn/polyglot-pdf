/**
 * Which FILES inside a published kit reach the public bundle
 * (bd polyglot-pdf-983wp).
 *
 * kitPublishFilter.ts decides WHICH KITS ship; this decides which files within
 * one. They are separate questions and are kept in separate modules so neither
 * grows a second meaning.
 *
 * WHY AN ALLOWLIST. A published kit's directory holds far more than the client
 * needs, and the extra files were all being served by Firebase Hosting at
 * guessable paths:
 *
 *   schema_archived.json        superseded revision
 *   <id>_schema_backup.json     superseded revision
 *   migration_report.json       authoring artifact
 *   <id>-annotated.pdf          authoring artifact
 *   <id>-instructions.pdf       editor-side INPUT for booklet extraction
 *                               (_BOOKLET_PATTERNS in editor_kit_routes.py),
 *                               never fetched by the client
 *
 * The first two are the real problem: they are superseded schemas, the same
 * class of bytes the revision archive (bd polyglot-pdf-w3zw / xzw5) exists to
 * keep behind authenticated access. Publishing them at /form-kits/<id>/... undoes
 * that. bd w3zw already excluded `_`-prefixed names at every level, which
 * catches `_archive` and `_translation` -- these slipped through because they
 * carry ordinary names.
 *
 * A denylist would be one new filename away from leaking again, which is
 * exactly how these survived that earlier fix. So the rule is inverted: a file
 * ships only if the client actually fetches it.
 *
 * WHAT THE CLIENT FETCHES, verified rather than assumed: SchemaFormDemo reads
 * `schemaPath` and `pdfPath` from the manifest, and the manifest builds both
 * from metadata's `schema`/`pdf` keys, falling back to schema.json/form.pdf.
 * Nothing else in frontend/src requests a bundle path other than index.json --
 * INCLUDING metadata.json, which is why it is no longer shipped either.
 *
 * An earlier version of this module allowlisted metadata.json, justified as
 * "carrying the label the catalogue renders". That was wrong twice over: the
 * manifest already embeds label and description, so nothing needed it; and the
 * editor has since grown that file, which now carries a `readiness` block
 * (review counts, error totals, schema_sha1, who stamped it) and an
 * `editing_lock` naming the role currently holding the kit. Publishing it
 * served internal review state to anonymous clients at a guessable path --
 * the exact class this module exists to close, admitted by the allowlist doing
 * the closing (Opus fresh-eyes round 5).
 */

/** The conventional names, used when metadata does not override them. */
export const DEFAULT_SCHEMA_FILE = "schema.json";
export const DEFAULT_PDF_FILE = "form.pdf";

/** Mirrors backend/services/form_kits.py `_SAFE_FILENAME_RE`. */
const SAFE_FILENAME = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

/**
 * Coerce a kit-declared filename to a safe BARE filename, else the default.
 *
 * This is the frontend half of `safe_filename` in backend/services/form_kits.py
 * and deliberately degrades the same way -- to the conventional name -- rather
 * than raising, so one malformed kit neither breaks the build nor escapes its
 * own directory.
 *
 * Without it the two halves of this script DISAGREED: `collectKits` accepted a
 * declared `"sub/schema.json"` verbatim and emitted a manifest entry pointing
 * at it, while the copy filter compared that whole string against a single path
 * segment and never matched -- so the kit was listed in the catalogue and
 * published with no schema, a silent per-form outage (Opus fresh-eyes round 1,
 * reproduced against both branches). A declared `"../secret.json"` had the same
 * split: refused by the copy filter, but still emitted into the manifest as a
 * path that normalises outside the kit.
 *
 * Coercing HERE means the manifest and the bundle are built from the same
 * value, so they cannot disagree again.
 */
export function safeKitFilename(name: unknown, fallback: string): string {
  if (typeof name !== "string") {
    return fallback;
  }
  // Redundant with the charset rule below, which rejects / \ and .. anyway --
  // deleting this block alone keeps every test green. Kept because it mirrors
  // backend safe_filename line-for-line, and a cross-language pair that reads
  // identically is worth more than minimality: the next person to change one
  // will see the other. The CHARSET rule is the load-bearing half and is
  // pinned (Opus fresh-eyes round 3).
  if (name.includes("/") || name.includes("\\") || name.includes("..")) {
    return fallback;
  }
  return SAFE_FILENAME.test(name) ? name : fallback;
}

/**
 * The files a published kit may serve.
 *
 * `schemaFile`/`pdfFile` come from the kit's own metadata, so a kit that names
 * a non-conventional schema or PDF still ships the right one -- after the same
 * coercion the manifest uses.
 */
export function publishableKitFiles(
  schemaFile: string | undefined,
  pdfFile: string | undefined,
): Set<string> {
  return new Set([
    safeKitFilename(schemaFile, DEFAULT_SCHEMA_FILE),
    safeKitFilename(pdfFile, DEFAULT_PDF_FILE),
  ]);
}
