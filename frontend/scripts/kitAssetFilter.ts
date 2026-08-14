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
 * Nothing else in frontend/src requests a bundle path other than index.json.
 * metadata.json itself ships too -- it is small, carries the label the
 * catalogue renders, and a kit that reaches this filter is published by
 * definition, so its status is not a disclosure.
 */

/** The conventional names, used when metadata does not override them. */
export const DEFAULT_SCHEMA_FILE = "schema.json";
export const DEFAULT_PDF_FILE = "form.pdf";
export const METADATA_FILE = "metadata.json";

/**
 * The files a published kit may serve.
 *
 * `schemaFile`/`pdfFile` come from the kit's own metadata, so a kit that names
 * a non-conventional schema or PDF still ships the right one.
 */
export function publishableKitFiles(
  schemaFile: string | undefined,
  pdfFile: string | undefined,
): Set<string> {
  return new Set([
    schemaFile || DEFAULT_SCHEMA_FILE,
    pdfFile || DEFAULT_PDF_FILE,
    METADATA_FILE,
  ]);
}
