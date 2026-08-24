"""Client-tier kit read gates: publish status + firm-scoped visibility.

Shared by EVERY route that serves kit bytes or schema to the CLIENT tier.
The set is PINNED BY TEST, not by this prose
(test_http_route_auth.py::test_every_client_tier_kit_read_is_visibility_gated
derives it from the shipped route sources): today that is form_kit_routes.py's
catalogue list, schema GET, pdf GET, and archived-schema GET (bd
polyglot-pdf-qfyxr; the archive LIST route gates too, it just reads no kit
bytes), plus pdf_fill_routes.py's fill read. The gates originally lived
inside form_kit_routes.py, which left the fill door unlocked (bd
polyglot-pdf-vy6id, Opus cross-surface finding on bd polyglot-pdf-vccy): a
POST /api/fill-pdf with a private kit_id and an empty field_values returned
the private kit's blank template to any authed user. Living in services/
(not a routes file) keeps the dependency edge clean, and the test makes a
NEW ungated read site fail CI instead of shipping.

The /api/editor/* surface is deliberately NOT in the set: it is the
maintainer/contractor tooling behind the role tokens, not the client tier
(sprint-19 plan).

ASCII only.
"""
import asyncio
import re

import structlog
from typing import Optional

from backend.services.firms import get_allowed_kits
from backend.services.form_kits import (
    FormKitNotFound,
    FormKitStoreError,
    safe_filename,
    sibling_marker,
)
from backend.utils.confirmation_logger import resolve_edition_marker

# An ENCODED revision marker's contract (form_kits.encode_marker): charset
# [A-Za-z0-9._-], <= 128 chars, dot-runs collapsed -- so a legitimate marker
# never contains ".." or a separator. ONE definition serving both the client
# and editor archive routes (qfyxr fresh-eyes: the regex was duplicated
# byte-for-byte across the two route files).
_log = structlog.get_logger().bind(module="kit_gates")

MARKER_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def is_safe_marker(marker: str) -> bool:
    """True when marker is a legitimate encode_marker output segment."""
    return ".." not in marker and bool(MARKER_SEGMENT_RE.fullmatch(marker))


async def load_live_metadata(store, kit_id: str) -> Optional[dict]:
    """ONE live metadata read feeding BOTH gates (publish + visibility) --
    each gate loading independently doubled the GCS read per request (vccy
    fresh-eyes round 2). Returns None when the store has no loader (legacy
    test doubles) or the loader returns a non-dict; an unreadable-metadata
    FormKitStoreError propagates (502 fail-closed), and a FormKitNotFound
    from a NONSTANDARD loader (the real stores return None for absence,
    never raise) lands in the route's except handler as the same 404 denial.
    """
    loader = getattr(store, "load_metadata", None)
    if loader is None:
        return None
    meta = await loader(kit_id)  # FormKitStoreError propagates -> fail closed
    return meta if isinstance(meta, dict) else None


# A revision that is LIVE or RETIRED -- both are published bytes a
# confirmation record can name. Mirrors editor_kit_routes._PUBLISHED_STATUSES.
_ARCHIVE_READABLE_STATUSES = ("complete", "unpublished")


def require_archive_readable(store, kit_id: str, meta: Optional[dict]) -> None:
    """Gate for the ARCHIVE (history) reads: allow complete OR unpublished.

    History must OUTLIVE retirement (bd polyglot-pdf-z6bk9, Opus outer r1,
    reproduced). The archive exists so a confirmation record naming a revision
    stays resolvable -- and retirement is the moment a revision most needs
    that, because the live schema is gone. Gating history on "complete" meant
    the archive-then-retire sequence archived the bytes and, in the SAME
    request, made them unreachable to the only party entitled to read them:
    the owning firm. (Staff were never affected -- /api/editor/* is ungated.)

    The widening is deliberately SCOPED to the two archive routes:
    require_published still guards the LIVE schema/pdf reads and the catalogue
    filter, so a retired revision is never served as the current form. (This
    gate ADMITS STRICTLY MORE than require_published -- "complete" is a subset
    of the tuple above; it is the scope that is narrow, not the predicate.)
    Visibility is unchanged and still applies -- require_visible runs after
    this, so another firm still cannot see the archive at all.
    """
    if not getattr(store, "enforce_complete_on_public_reads", False):
        return
    if getattr(store, "load_metadata", None) is None:
        return
    if not isinstance(meta, dict) or meta.get("status") not in _ARCHIVE_READABLE_STATUSES:
        raise FormKitNotFound(f"Kit not published: {kit_id}")


def require_published(store, kit_id: str, meta: Optional[dict]) -> None:
    """Refuse to serve a kit whose LIVE metadata status is not "complete", on
    stores that enforce it (GCS -- the editor-writable shared store).

    The deploy-time manifest gate stopped being sufficient when the store
    became WRITABLE (bd 92qe.1): a contractor reverting a published kit to
    draft (to polish it) must unpublish it IMMEDIATELY, otherwise their
    work-in-progress saves would keep streaming to voice users through the
    still-listed manifest entry (Codex P1, PR #279). Local mode is ungated by
    design (the flag is False), and legacy test doubles without load_metadata
    are treated as ungated. Under the flag, MISSING metadata fails closed
    (every legitimately deployed/onboarded kit carries metadata.json). The
    metadata comes pre-loaded from load_live_metadata (one read serves this
    gate AND the visibility gate).
    """
    if not getattr(store, "enforce_complete_on_public_reads", False):
        return
    if getattr(store, "load_metadata", None) is None:
        return
    if not isinstance(meta, dict) or meta.get("status") != "complete":
        raise FormKitNotFound(f"Kit not published: {kit_id}")


async def firm_allowed_kits(user: Optional[dict]) -> frozenset:
    """Resolve the caller's firm-allowed kit ids from the firm_id claim.

    Fail-closed at every step (bd polyglot-pdf-vccy): no user, no firm_id
    claim, or a disabled/broken firms store all resolve to an EMPTY set --
    public kits only. get_allowed_kits itself never raises and never returns
    None (backend/services/firms.py), and its Firestore read is sync (Admin
    SDK), so it runs off the event loop.
    """
    # isinstance, not truthiness: a DIRECT call (tests) can leave the Depends()
    # default object in the user parameter, which is truthy but not a dict.
    firm_id = user.get("firm_id") if isinstance(user, dict) else None
    if not isinstance(firm_id, str) or not firm_id:
        return frozenset()

    # A CLIENT SEES EXACTLY ONE KIT -- the one their link names (bd
    # polyglot-pdf-ugm6). A client-link credential carries the firm's id
    # because the session must be firm-keyed for telemetry, but the firm's
    # ALLOWLIST is the set of kits the FIRM may use, which is emphatically
    # not the set a client may read: resolving it here would hand every
    # client a directory of that firm's private intake forms, and let them
    # fetch the schema and blank PDF of forms they were never sent.
    #
    # Narrow by INTERSECTING the allowlist read -- the read still happens,
    # because it is what refuses a kit the firm has since lost. (An earlier
    # version of this comment claimed the narrowing saved a Firestore
    # round-trip. It does not: both branches make exactly one
    # get_allowed_kits call.)
    #
    # COST NOTE for bd polyglot-pdf-ik7e: a client HTTP request that touches
    # a private kit costs TWO uncached Firestore reads -- this one, plus
    # require_auth's redemption read. Size the per-session datastore spend
    # from that, not from one.
    if user.get("is_client_link"):
        link_kit = user.get("link_kit_id")
        if not isinstance(link_kit, str) or not link_kit:
            return frozenset()
        allowed = await asyncio.to_thread(get_allowed_kits, firm_id)
        return frozenset({link_kit} & set(allowed))

    return frozenset(await asyncio.to_thread(get_allowed_kits, firm_id))


def kit_visibility(meta: Optional[dict]) -> str:
    """Return the kit's visibility ("public" | "private") from LIVE metadata.

    Absence of metadata or the key means PUBLIC -- existing kits are not
    migrated (absence of the key means public, sprint-19 plan), and anything
    except the exact string "private" is public, so a typo can neither hide
    a public kit nor expose a private one as some third state. The metadata
    comes pre-loaded from load_live_metadata (whose docstring carries the
    fail-closed error contract).
    """
    if not isinstance(meta, dict):
        return "public"
    return "private" if meta.get("visibility") == "private" else "public"


async def require_visible(kit_id: str, meta: Optional[dict], user: Optional[dict]) -> None:
    """Refuse (404) a PRIVATE kit unless the caller's firm allowlist has it.

    404 -- not 401/403 -- deliberately: a private kit must not reveal its
    EXISTENCE to another firm or a legacy authed user (epic 02ye rubric #2:
    invisible on every surface). Access = kit_id in the firm's allowed_kits;
    owner_firm_id is bookkeeping for the write path (bd z6bk9), not the read
    gate.
    """
    if kit_visibility(meta) != "private":
        return
    allowed = await firm_allowed_kits(user)
    if kit_id not in allowed:
        raise FormKitNotFound(f"Kit not visible: {kit_id}")


def _resolve_meta_names(meta: Optional[dict]) -> tuple[str, str]:
    """(schema_file, pdf_file) from a kit's metadata, defaulted + sanitized."""
    meta = meta if isinstance(meta, dict) else {}
    schema_file = safe_filename(meta.get("schema") or "schema.json", "schema.json")
    pdf_file = safe_filename(meta.get("pdf") or "form.pdf", "form.pdf")
    return schema_file, pdf_file


async def _archive_published_revision(store, kit_id: str, meta: Optional[dict]) -> Optional[str]:
    """Copy the currently-PUBLISHED revision into the archive before it can be
    edited. Returns the marker archived under, or None when nothing was archived.

    bd polyglot-pdf-w3zw. The confirmation audit trail records kit_id + a
    revision marker, but a marker is not a storage address and kit storage is
    one slot per kit -- so overwriting a published schema used to destroy the
    only copy of what an old record was confirmed against.

    WHY THIS FIRES WHEN A REVISION IS RETIRED, not on promotion: a published
    kit's schema cannot be written at all (every editing route refuses while it
    is write-locked -- the publish gate). So retirement is the LAST moment the
    published bytes still exist; by promotion time the new schema has already
    replaced them.

    FOUR triggers retire a revision, and each archives first (bd
    polyglot-pdf-6dz0 widened this from one; bd polyglot-pdf-z6bk9 added the
    fourth). They are only THREE call SITES -- triggers 1 and 2 share one
    guarded line -- and the call-site SET is pinned by
    test_kit_revision_archive.py::test_the_complete_set_of_archive_call_sites_is_pinned,
    so a new caller fails CI instead of a review round:
      1. complete -> draft   -- the classic edit cycle
         (complete -> draft -> save -> complete).
      2. complete -> unpublished -- retiring a revision outright.
      3. the OUTGOING kit of a `replaces_kit_id` supersede, where a new edition
         onboarded as its own kit takes over. Note this route produces a new
         live revision WITHOUT any draft step, which is why the one-way
         "complete -> draft -> ..." framing above is not the whole story.
      4. the CLIENT-TIER firm retire route (form_kit_routes.retire_own_kit,
         bd polyglot-pdf-z6bk9) -- the ONLY non-editor caller, and the reason
         this helper lives in kit_gates.py rather than editor_kit_routes.py.
    Keep this list in step with docs/components/pdf-filling.md, which states the
    same four triggers.

    The marker is resolved from the SUPERSEDED revision's OWN schema, so it
    matches what that revision's confirmation records carry (an edition_date if
    the form has one, else the shape fingerprint) -- that is what makes a
    fingerprint-era record still retrievable later.

    Best-effort by design: an archive failure must not block the retirement
    (which would strand a kit published-and-uneditable). It is logged LOUDLY --
    the same posture as the confirmation sink, where losing the record is worse
    than a slow path but never worth failing the user's action over.
    """
    schema_file, _pdf = _resolve_meta_names(meta)
    try:
        schema = await store.load_schema(kit_id, schema_file)
    except (FormKitNotFound, FormKitStoreError) as exc:
        _log.warning("kit_revision_archive_no_schema", kit_id=kit_id, error=str(exc))
        return None

    # Resolve through the SAME three ranks the confirmation record used, or the
    # archive is keyed on something no record names and the retrieval this whole
    # mechanism exists for silently fails (bd polyglot-pdf-xzw5; caught by Opus
    # fresh-eyes, which showed an author_version kit archiving under a sha256:
    # fingerprint while its records named the version).
    _meta_block = schema.get("form_metadata")
    _meta_block = _meta_block if isinstance(_meta_block, dict) else {}
    marker = resolve_edition_marker(
        _meta_block.get("edition_date"),
        schema,
        _meta_block.get("author_version"),
    )
    if not marker:
        # No edition date AND no fingerprintable shape (an empty/fieldless
        # schema): nothing a confirmation record could name, so nothing to key
        # an archive on.
        _log.warning("kit_revision_archive_no_marker", kit_id=kit_id)
        return None

    # Idempotence (exit criterion 2) vs. NOT LOSING A REVISION: skip only when
    # the archived copy IS this schema, never merely because the marker name is
    # taken. Markers are not unique keys -- an author who edits fields without
    # bumping the government edition string produces two DIFFERENT revisions
    # under one edition_date, and a marker-only check would treat the second as
    # "already archived" and destroy it (fresh-eyes on this bead, reproduced
    # live: retrieval then returns the WRONG schema, which for a legal record is
    # worse than a missing one).
    #
    # So: same marker + same bytes -> skip (the cheap re-press case). Same marker
    # + different bytes -> archive under a disambiguated segment so BOTH survive.
    # Retrieval by the plain marker still finds the first; the sibling keeps the
    # later revision recoverable instead of silently gone.
    try:
        existing = await store.load_archived_revision_or_none(kit_id, marker)
        if existing == schema:
            return None
        store_marker = marker
        if existing is not None:
            # Distinct revision under a taken marker: suffix with this
            # revision's own shape fingerprint, which is what actually
            # distinguishes it (and is stable, so a repeat of THIS revision
            # re-collides with itself and skips above on the next pass).
            fingerprint = resolve_edition_marker(None, schema) or "revision"
            # sibling_marker budgets the fingerprint against the segment length
            # cap FIRST: naively joining the raw marker would let a long
            # edition_date truncate the fingerprint away, at which point the
            # sibling collides with the base and OVERWRITES the earlier
            # revision (verified live by fresh-eyes on this bead).
            store_marker = sibling_marker(marker, fingerprint)
            if await store.load_archived_revision_or_none(kit_id, store_marker) == schema:
                return None
        await store.put_archived_revision(kit_id, store_marker, schema, meta)
    except FormKitStoreError as exc:
        _log.error("kit_revision_archive_failed", kit_id=kit_id, marker=marker,
                   error=str(exc))
        return None
    _log.info("kit_revision_archived", kit_id=kit_id, marker=marker,
              store_marker=store_marker)
    return store_marker
