import path from "node:path";

/**
 * The copy predicate for the static form-kit bundle (bd polyglot-pdf-w3zw).
 *
 * Lives in its own module so the build script and its test share ONE
 * definition. A test that re-implements the predicate cannot detect the real
 * one drifting -- and the drift that matters here is subtle: a filter scoped to
 * the TOP level only still looks correct, still contains every keyword, and
 * still re-leaks the archive. That is the exact mistake the deploy scripts'
 * `case "$kit_id" in _*)` guards already make.
 *
 * Excludes any path whose BASENAME starts with "_", at every level:
 *   - `<kit>/_archive/**` -- SUPERSEDED revisions. An operator-only,
 *     legal-retention surface read through the authenticated store by
 *     scripts/read_kit_revision.py. Firebase Hosting serves whatever lands in
 *     the bundle, so shipping these would publish every superseded schema at
 *     /form-kits/<kit>/_archive/<marker>/schema.json.
 *   - `_translation/` -- authoring data read through the backend, never fetched
 *     from the public bundle.
 *
 * Node's fs.cp prunes the whole subtree when the filter returns false for a
 * directory, so returning false for `_archive` is enough -- its children are
 * never visited.
 */
export function shouldCopyKitPath(src: string): boolean {
  return !path.basename(src).startsWith("_");
}
