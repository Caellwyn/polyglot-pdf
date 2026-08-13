/**
 * Which kits may enter the PUBLIC static bundle (bd polyglot-pdf-fqexm).
 *
 * Lives beside kitCopyFilter.ts and for the same reason: the manifest INDEX and
 * the file COPY are two separate code paths, and a kit must be dropped from
 * both or neither. A predicate re-implemented at each site drifts, and the
 * drift is invisible -- an index that omits a retired form while its schema and
 * PDF still sit at /form-kits/<id>/ reads as "fixed" until someone requests the
 * path directly.
 *
 * WHY THIS EXISTS. The kit lifecycle (bd polyglot-pdf-6dz0, polyglot-pdf-hqztg)
 * says a form is served to clients only at `status: complete`. The backend
 * honours it (form_kit_routes.py `_require_published` + the list filter) and so
 * do both deploy scripts (`kit_is_complete`). The frontend build did not: it
 * copied the whole form-kits tree to Firebase Hosting and indexed every kit
 * with a schema and a PDF, so drafts, kits awaiting review, and RETIRED forms
 * were all published. SchemaFormDemo falls back to this bundled manifest
 * whenever the backend call fails, so a retired form stayed reachable there --
 * which is precisely what `unpublished` exists to prevent.
 *
 * KNOWN INTERACTION -- local dev (bd polyglot-pdf-pk2ns). The local backend
 * store is deliberately permissive (`enforce_complete_on_public_reads = False`)
 * so a maintainer can test-drive drafts, and its manifest hardcodes the STATIC
 * path `/form-kits/<id>/schema.json`. That path is exactly what this gate stops
 * producing, so local mode now lists a draft it cannot load. Deployed surfaces
 * are unaffected (GCS filters by status and deploy-all.sh never uploaded a
 * draft). The fix belongs in the local store -- serve the draft through the API
 * it already has, rather than pointing at a bundle that legitimately excludes
 * it -- which is why it is pk2ns's and not this module's.
 *
 * FAIL CLOSED. Anything that is not demonstrably `complete` is withheld:
 * unreadable metadata, absent metadata.json, a missing `status` key, or a
 * status this build does not recognise. A kit wrongly withheld is a visible,
 * reversible mistake; a retired form wrongly published is the failure the
 * lifecycle exists to prevent, and it is silent.
 */

/** The one status whose kits the voice app serves to clients. */
export const PUBLISHED_STATUS = "complete";

export interface KitStatusCarrier {
  status?: unknown;
}

/**
 * True only when this kit's metadata proves it is published.
 *
 * `null`/`undefined` metadata means unreadable or absent -- both withhold.
 */
export function isPubliclyServable(metadata: KitStatusCarrier | null | undefined): boolean {
  return metadata?.status === PUBLISHED_STATUS;
}
