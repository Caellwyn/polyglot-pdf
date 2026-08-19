"""Client-tier kit read gates: publish status + firm-scoped visibility.

Shared by EVERY route that serves kit bytes or schema to the CLIENT tier --
the set is exactly four read sites (bd polyglot-pdf-vy6id, Opus cross-surface
finding on bd polyglot-pdf-vccy): the three reads in form_kit_routes.py
(catalogue list, schema GET, pdf GET) and pdf_fill_routes.py's fill read.
The gates originally lived inside form_kit_routes.py, which left the fourth
door unlocked -- a POST /api/fill-pdf with a private kit_id and an empty
field_values returned the private kit's blank template to any authed user.
Living in services/ (not a routes file) keeps the dependency edge clean and
makes the set pinnable: test_http_route_auth.py asserts every client-tier
load_pdf_bytes/load_schema call site runs these gates, so a FIFTH read site
fails CI instead of shipping ungated.

The /api/editor/* surface is deliberately NOT in the set: it is the
maintainer/contractor tooling behind the role tokens, not the client tier
(sprint-19 plan).

ASCII only.
"""
import asyncio
from typing import Optional

from backend.services.firms import get_allowed_kits
from backend.services.form_kits import FormKitNotFound


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
