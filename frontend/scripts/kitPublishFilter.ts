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

/** The one visibility value (beyond an absent key) the PUBLIC bundle ships. */
export const PUBLIC_VISIBILITY = "public";

export interface KitStatusCarrier {
  status?: unknown;
  visibility?: unknown;
}

/**
 * True only when this kit's metadata proves it is published AND public.
 *
 * `null`/`undefined` metadata means unreadable or absent -- both withhold.
 *
 * VISIBILITY (bd polyglot-pdf-kkos, closing the bd polyglot-pdf-17opi
 * exposure): a firm's PRIVATE kit must never enter the world-readable
 * Hosting bundle. The key ABSENT means public (existing kits are not
 * migrated -- sprint-19 plan), and the exact string "public" means public;
 * ANY other value withholds. This is a DELIBERATE divergence from the
 * backend routes' coercion (there, anything except exact "private" serves
 * as public): the fail directions differ by surface. A route wrongly
 * hiding a public kit is a visible, reversible service break; this bundle
 * wrongly shipping a mistyped private kit ("prvate", "Private") is the
 * silent, irreversible leak the firm tier exists to prevent -- the same
 * fail-closed doctrine as the status half above.
 */
export function isPubliclyServable(metadata: KitStatusCarrier | null | undefined): boolean {
  if (metadata?.status !== PUBLISHED_STATUS) {
    return false;
  }
  const visibility = metadata.visibility;
  return visibility === undefined || visibility === PUBLIC_VISIBILITY;
}
