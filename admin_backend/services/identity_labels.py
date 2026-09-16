"""Batch uid -> human-readable label resolution (bd polyglot-pdf-cpsi0).

WHY THIS EXISTS. Two ledger/link writers (backend/routes/link_routes.py's
mint reservation, and this service's own grant/adjust/plan/top-up/revoke/
acknowledge routes via credit_ledger.append_entry's new `actor_email` kwarg)
now stamp a human-readable email ALONGSIDE the acting uid at write time. But
every row written BEFORE that change carries only the uid -- a maintainer's
own complaint on staging: "the ledger shows a raw Firebase uid (QOtm...),
not really useful as is". This module is the READ-SIDE fallback: for a row
with no stored label, resolve its uid to an email via Firebase Auth, once,
in a single batched call per request.

ONE BATCHED CALL, NOT N. firebase_admin.auth.get_users() takes a LIST of
UidIdentifier and returns every match in one round trip -- calling
get_user(uid) once per row would turn a 50-row ledger page into 50 Auth API
calls. labels_for_uids() below is the ONE place this repo calls get_users();
a caller with many rows collects the DISTINCT uids first (see
firm_routes.py's and link_routes.py's own callers) so a firm's ledger page,
which repeats the same few staff uids across many entries, costs one Auth
call for the whole page, not one per row.

A SYSTEM ACTOR ("system:<origin>") IS NEVER A REAL UID -- it must not be
sent to get_users(), which would either no-op (a string with a colon is
never a valid Firebase uid) or, worse, waste a batch slot. Callers filter
those out before calling this module; labels_for_uids() itself does not
special-case the "system:" prefix; it just returns whatever the caller
handed it as the fallback for a uid Firebase Auth cannot find, which for a
system-actor string handed in by mistake is the string itself -- exactly
the same fallback an unknown real uid gets.

UNKNOWN UID FALLS BACK TO THE UID ITSELF (the plan's own words). A uid that
no longer resolves -- a deleted account, a decommissioned service identity,
or simply Firebase Auth being unreachable for this request -- must not
blank the row or 500 the page: the console still needs SOMETHING to show,
and the uid itself is exactly what was already showing before this bead.
Fail-soft, not fail-closed: an operator viewing a ledger page cares more
about seeing the page than about a fully-resolved label on every row.

CACHED, PER-PROCESS, WITH A TTL (mirrors backend/services/runtime_config.py's
own per-key TTL cache shape, one call over: keyed by uid rather than by
channel). A staff roster changes rarely -- an email address does not change
between one page load and the next -- so re-hitting Auth for the same uid on
every request would cost a batch call per page view for no freshness
benefit. TTL_SECONDS is deliberately much longer than runtime_config's 45s
(a config flag flip needs to be visible almost immediately; a staff email
does not), but still bounded so a renamed/reassigned account is not cached
forever.

NO PII IN LOGS (docs/standards/hipaa-pii-policy.md): this module logs uid
COUNTS and outcome counts only, never an email, on either the cache-hit or
the Auth-call path.

ASCII only.
"""
from __future__ import annotations

import time
from typing import Optional

import structlog

_log = structlog.get_logger().bind(module="identity_labels")

# Per-uid TTL: long enough that a console session's several page loads in a
# row all hit the cache, short enough that a changed/deleted account is not
# stuck showing a stale label indefinitely. See the module docstring's
# "CACHED, PER-PROCESS" section for why this differs from runtime_config's
# much shorter 45s.
TTL_SECONDS = 600.0

# uid -> (cached_at, label). A module-level dict, like runtime_config._cache
# -- this process only, no cross-instance sharing, which is fine: a cold
# cache just means the next request's page pays one batch Auth call.
_cache: dict[str, tuple[float, str]] = {}


def clear_cache() -> None:
    """Test-only: drop every cached label so a test can control what the
    next lookup sees, mirroring runtime_config.clear_cache()'s own docstring
    and purpose."""
    _cache.clear()


def _fb_auth():
    """The Firebase Auth admin module, imported lazily -- same shape as
    user_admin.py's own _fb_auth(): module import must not require an
    initialized firebase_admin app, and this module OWNS the init the same
    way, so the admin service standing up alone does not depend on whichever
    module happened to import first."""
    import firebase_admin
    from firebase_admin import auth as fb_auth

    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    return fb_auth


def labels_for_uids(uids) -> dict:
    """Resolve every uid in `uids` to a human-readable label.

    Returns {uid: label} for EVERY uid passed in (never a partial dict) --
    a caller can always index the result with any uid it handed in. The
    label is:
      1. the cached or freshly-resolved EMAIL, when Firebase Auth has an
         account for that uid;
      2. the uid ITSELF, when the account is unknown, deleted, or the Auth
         call could not be made at all (fail-soft; see module docstring).

    Duplicate uids in the input are resolved once -- the function
    de-duplicates before the batch call so a ledger page repeating the same
    staff member across many rows costs exactly one Auth lookup for that
    uid, not one per occurrence.

    ONE BATCH CALL for every uid not already cached. A caller with many rows
    should call this ONCE with every distinct uid it needs, not once per
    row (see module docstring).
    """
    # De-duplicate and drop anything that is not a non-empty string --
    # a caller-side bug (None slipping through, an empty string) must not
    # reach the Auth SDK, which would raise on a malformed identifier and
    # cost the caller its WHOLE page rather than just that one blank label.
    distinct = sorted({u for u in uids if isinstance(u, str) and u})
    result: dict[str, str] = {}

    now = time.time()
    to_fetch = []
    for uid in distinct:
        cached = _cache.get(uid)
        if cached is not None and (now - cached[0]) < TTL_SECONDS:
            result[uid] = cached[1]
        else:
            to_fetch.append(uid)

    if to_fetch:
        try:
            fb_auth = _fb_auth()
            identifiers = [fb_auth.UidIdentifier(uid) for uid in to_fetch]
            fetched = fb_auth.get_users(identifiers)
            found_by_uid = {u.uid: u for u in fetched.users}
            for uid in to_fetch:
                record = found_by_uid.get(uid)
                email = getattr(record, "email", None) if record else None
                label = email if isinstance(email, str) and email else uid
                result[uid] = label
                _cache[uid] = (now, label)
            _log.info(
                "identity_labels_resolved",
                requested=len(to_fetch),
                found=len(found_by_uid),
            )
        except Exception as exc:  # noqa: BLE001 -- fail-soft, see docstring
            # The store (Firebase Auth) is unreachable, or get_users itself
            # raised (a malformed identifier that slipped past the filter
            # above, a transient API error). Every uid not already resolved
            # from cache falls back to itself -- the SAME degraded label an
            # unknown/deleted account gets, so a caller sees no difference
            # between "this uid does not exist" and "we could not ask".
            _log.error("identity_labels_lookup_failed", requested=len(to_fetch),
                       error=str(exc))
            for uid in to_fetch:
                if uid not in result:
                    result[uid] = uid

    # Every uid in the ORIGINAL input (including duplicates and, for
    # completeness, anything filtered out above) resolves to something the
    # caller can index -- a filtered-out non-string/blank input is returned
    # unchanged as its own "label", since there is nothing else to show.
    return {uid: result.get(uid, uid) if isinstance(uid, str) and uid else uid
            for uid in uids}


def label_for_actor(actor: Optional[str], actor_email: Optional[str],
                    labels: dict) -> Optional[str]:
    """The ONE label-selection rule, shared by every route that renders a
    ledger/link actor column: prefer the STORED label written at mint/grant
    time (actor_email / employee_email), fall back to the BATCH LOOKUP
    result (`labels`, from labels_for_uids) for a legacy row that has
    neither, and fall back to the raw actor/uid string itself when both are
    absent (a null actor, or a uid the lookup could not resolve for a
    reason other than "not found" -- labels_for_uids already folds that
    into "uid as its own label", so this is really only reached for a None
    actor).

    A caller passes ITS OWN pre-stamped email first (the row already
    answers the question, no lookup needed) and the batch-resolved map
    second (the fallback for a row from before this bead landed) -- this
    function is the one place that PRECEDENCE is decided, so a route cannot
    accidentally prefer a resolved-from-uid label over a stored one or vice
    versa.
    """
    if isinstance(actor_email, str) and actor_email:
        return actor_email
    if actor is None:
        return None
    return labels.get(actor, actor)
