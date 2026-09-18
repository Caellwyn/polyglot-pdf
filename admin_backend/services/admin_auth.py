"""Per-user identity for the ADMIN service (bd polyglot-pdf-7w17m).

MIRRORS backend/services/editor_auth.py -- same shape (dev-bypass check first,
then verify_id_token with no check_revoked, a 401/403 split with a
machine-readable prefix on the "no access at all" 403), same reasons:

  * The admin service reads its OWN claim (APP_ADMIN_CLAIM), not the voice
    app's firm_role or the editor's schema_editor_role. None of the three
    grants access to either of the others.
  * check_revoked stays OFF, on purpose (same scar as the editor and the
    public backend, CLAUDE.md scar #7): it forces a Firebase USER-RECORD
    FETCH needing firebaseauth.users.get. admin-backend-sa DOES hold
    roles/firebaseauth.admin (plan: "Admin service" gating,
    scripts/setup-admin-service.sh) -- unlike the public backend's narrow SA,
    it COULD afford this call. It is left off anyway for symmetry with the
    other two verifiers and because nothing in this bead's scope measured a
    need for instant revocation; if the admin service ever needs it, this
    comment is the note to revisit for THIS service specifically, since the
    IAM justification that ruled it out for the other two does not apply
    here.
  * admin-backend-sa's revoke_refresh_tokens still makes bootstrap_admin_
    user.py's --revoke take effect on the caller's NEXT token mint, same
    caveat as the editor's revoke path.

This is the FIRST of the four gates the plan names
(require_app_admin; require_firm_manager; require_app_admin_or_owning_
manager; require_google_oidc). ALL FOUR now exist: require_app_admin_or_
owning_manager is the composite defined further down this module (bd
polyglot-pdf-dmjl5), shipping with the four /admin/users routes;
require_firm_manager lives on the PUBLIC backend (backend/services/auth.py)
over the shared rule backend/services/firms.py::manager_firm_id, and no
route declares it yet for the reason documented there;
require_google_oidc(audience, allowed_caller_emails) is defined at the
bottom of this module (bd polyglot-pdf-8vgfh), shipping with its first
consuming route, POST /admin/links/sweep-expired. See
admin_backend/tests/unit/test_admin_route_auth.py, which derives the
registered route set and asserts each route carries exactly one of the four
names.

A FIFTH dependency, require_app_admin_or_owning_manager_or_employee (bd
polyglot-pdf-scaig), lives beside the composite for the ONE route that
needs a third actor kind (GET /admin/firms/{firm_id}/links) -- see that
function's own docstring for why it is a separate dependency rather than a
widening of require_app_admin_or_owning_manager. It is deliberately NOT
part of the "four gates" vocabulary test_admin_route_auth.py enforces:
that test's known-gate set is the plan's own named vocabulary, and this
dependency's presence is instead pinned directly on the one route that
carries it (test_admin_link_routes.py), the same way require_google_oidc's
own route is pinned beyond the generic set check.
"""
from __future__ import annotations

import os
from typing import Annotated, Optional

import structlog
from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel, model_validator

_log = structlog.get_logger(module="admin_auth")

# The custom claim granting admin-console access. Boolean, per the plan
# ("Admin service" gating): a person either holds full admin access or does
# not -- there is no admin role gradient in this epic. Named for THIS
# surface so neither a firm claim nor an editor claim can grant it by
# accident, mirroring EDITOR_ROLE_CLAIM's isolation.
APP_ADMIN_CLAIM = "app_admin"

# Marks the ONE 403 that means "this account holds no admin access at all",
# so the console can route it to a refused/sign-out screen rather than
# surfacing it as an ordinary in-app refusal. Same idiom as
# editor_auth.NO_EDITOR_ACCESS_PREFIX: a machine-readable prefix, not prose a
# client string-matches -- every previous attempt in this repo to key on
# message text has been defeated by a rewording.
NO_ADMIN_ACCESS_PREFIX = "NO_ADMIN_ACCESS:"


class AdminActor(BaseModel):
    """WHO is acting, as an app admin.

    Mirrors EditorActor's shape (uid, email, label()) without the role field
    -- APP_ADMIN_CLAIM is boolean, so there is no second value to carry.
    """

    uid: str
    email: Optional[str] = None

    def label(self) -> str:
        """Human-facing name for this person -- for audit rows and log lines.

        Email when known, else the uid. Never empty: an audit row that names
        nobody is worse than one naming an opaque id.
        """
        return self.email or self.uid


def _dev_bypass_allowed() -> bool:
    """True only for genuine local dev, never on a deployed instance.

    Identical rule to editor_auth._dev_bypass_allowed and
    backend.services.auth's bypass: K_SERVICE is Cloud Run's marker, so its
    presence means we are deployed and the bypass is refused however the env
    is set. Fail-closed by construction rather than by discipline.
    """
    if os.getenv("VFF_DISABLE_AUTH", "").lower() != "true":
        return False
    if os.getenv("K_SERVICE"):
        _log.error("admin_auth_dev_bypass_refused_on_deployed_instance")
        return False
    return True


def verify_admin_token(token: str) -> AdminActor:
    """Resolve a Firebase ID token to an AdminActor, or raise 401/403.

    401 for a token that does not verify; 403 for a VALID account with no
    app_admin claim -- the distinction matters, since the second means "you
    are who you say you are, but you are not listed here".
    """
    if _dev_bypass_allowed():
        return AdminActor(uid="dev_admin", email="dev@example.com")

    import firebase_admin
    from firebase_admin import auth as fb_auth

    # OWN the init rather than inheriting whichever module happened to import
    # first -- same reasoning as editor_auth: without this, standing up the
    # admin service alone (no public backend, no editor import ahead of it)
    # would 401 every sign-in blaming the user's credential.
    if not firebase_admin._apps:
        firebase_admin.initialize_app()

    try:
        # NO check_revoked -- see the module docstring.
        claims = fb_auth.verify_id_token(token)
    except Exception:
        # Deliberately opaque: the reason a token failed is not the caller's
        # business, and the specific exception types vary by SDK version.
        raise HTTPException(status_code=401,
                            detail="Invalid or expired sign-in")

    if claims.get(APP_ADMIN_CLAIM) is not True:
        # A REAL account with no admin claim. Not 401 -- they authenticated
        # fine; they are simply not an admin here.
        raise HTTPException(
            status_code=403,
            detail=(NO_ADMIN_ACCESS_PREFIX
                    + " This account does not have admin console access"),
        )

    uid = claims.get("uid") or claims.get("sub")
    if not uid:
        # A verified token with no subject should be impossible; treat it as
        # a failure rather than inventing an identity, since every
        # downstream use (audit attribution) depends on uid being real.
        raise HTTPException(status_code=401,
                            detail="Invalid or expired sign-in")

    return AdminActor(uid=uid, email=claims.get("email"))


async def require_app_admin(
    authorization: Annotated[Optional[str], Header()] = None,
) -> AdminActor:
    """FastAPI dependency: the caller, as a person holding app_admin.

    `Authorization: Bearer` ONLY -- there is no legacy shared-token header on
    this surface to carry forward (unlike the editor's retired
    X-Editor-Token).

    The bypass is checked FIRST, matching both sibling verifiers: a
    tokenless local request must not 401 ahead of the bypass check.
    _dev_bypass_allowed refuses this outright on a deployed instance.
    """
    if _dev_bypass_allowed():
        return AdminActor(uid="dev_admin", email="dev@example.com")

    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Sign-in required")
    return verify_admin_token(token)


# ---------------------------------------------------------------------------
# The COMPOSITE gate: app admin OR the owning firm's manager
# (bd polyglot-pdf-dmjl5)
# ---------------------------------------------------------------------------
#
# The plan's third gate. Two very different people reach the same routes:
#
#   * an APP ADMIN, who serves every firm and therefore must NAME the firm
#     they are acting on -- there is no other way to know which one;
#   * a FIRM MANAGER, whose firm comes from their VERIFIED TOKEN and who may
#     therefore not name one at all.
#
# THE REFUSAL IS THE POINT. A manager whose request body names a firm is
# refused with 403 rather than having the body quietly ignored. Silently
# overriding a caller-supplied firm_id with the token's would be SAFE (the
# token still wins) but it would be dishonest: a console bug that sent the
# wrong firm would look like it worked, and the operator would believe they
# had acted on a firm they had not. Refusing makes the disagreement visible
# at the one moment it is cheap to fix.

# The shapes an actor can have on a composite route, as a machine-readable
# discriminator rather than "did email come back None" inference.
ACTOR_KIND_APP_ADMIN = "app_admin"
ACTOR_KIND_FIRM_MANAGER = "firm_manager"
# The third actor kind, added for the link-listing route only (bd
# polyglot-pdf-scaig) -- see require_app_admin_or_owning_manager_or_employee
# below for why this does NOT widen require_app_admin_or_owning_manager
# itself.
ACTOR_KIND_FIRM_EMPLOYEE = "firm_employee"


class CompositeActor(BaseModel):
    """WHO is acting on a route both actors can reach.

    firm_id is the manager's (or employee's) own firm, taken from the token,
    and is None for an app admin -- an admin's target firm arrives in the
    request and is resolved by the ROUTE (which is also where the "a
    manager may not name one" refusal lives, since only the route can see
    its own body).

    employee_id is set ONLY for ACTOR_KIND_FIRM_EMPLOYEE (the caller's own
    uid, restated under this name so a route scoping a query to "this
    employee's own records" reads employee_id off the actor rather than
    reaching for uid and risking confusion with an app admin's or manager's
    uid, neither of which means "an employee_id to filter by"). None for
    the other two kinds.
    """

    uid: str
    email: Optional[str] = None
    kind: str
    firm_id: Optional[str] = None
    employee_id: Optional[str] = None

    @model_validator(mode="after")
    def _employee_id_matches_kind(self) -> "CompositeActor":
        """Pins the invariant this class's own docstring only states in
        prose: employee_id is set if and only if kind is
        ACTOR_KIND_FIRM_EMPLOYEE (bd polyglot-pdf-wiju0).

        Without this, a CompositeActor with kind=firm_employee and
        employee_id=None (or empty) is constructible, and
        list_firm_links's `if employee_id is not None` scoping filter
        FAILS OPEN on it -- the employee actor silently widens to see the
        WHOLE FIRM's links instead of none. Every production constructor
        happens to pair these correctly today, so guarding it at the type
        (rather than trusting every future constructor to keep pairing
        them by hand) is what keeps a future caller from reintroducing the
        data-exposure regression with no error and no failing test.
        """
        is_employee = self.kind == ACTOR_KIND_FIRM_EMPLOYEE
        has_employee_id = bool(self.employee_id)
        if is_employee and not has_employee_id:
            raise ValueError(
                "CompositeActor(kind=ACTOR_KIND_FIRM_EMPLOYEE) requires a "
                "non-empty employee_id")
        if not is_employee and has_employee_id:
            raise ValueError(
                "CompositeActor(kind={!r}) must not carry an employee_id "
                "(employee_id is only meaningful for "
                "ACTOR_KIND_FIRM_EMPLOYEE)".format(self.kind))
        return self

    @property
    def is_app_admin(self) -> bool:
        return self.kind == ACTOR_KIND_APP_ADMIN

    def label(self) -> str:
        """Human-facing name for audit rows and log lines. Never empty."""
        return self.email or self.uid


def _resolve_admin_or_manager_or_employee_actor(
    token: str, *, allow_employee: bool,
) -> CompositeActor:
    """Shared body behind BOTH require_app_admin_or_owning_manager and
    require_app_admin_or_owning_manager_or_employee (bd polyglot-pdf-scaig).

    ONE HOME for the token-verification branch order (CLAUDE.md scar #8),
    so the two public dependencies cannot drift on how they decide "app
    admin first, then manager/employee" -- only on WHETHER the employee
    branch is reachable at all, via allow_employee. See the two public
    wrappers for why a THIRD actor kind is a new function rather than a
    widening of the existing one: test_composite_gate.py's
    test_neither_an_admin_nor_a_manager_is_403 already pins an employee
    claims dict as a 403 through the ORIGINAL name, because /admin/users and
    every other existing composite route must keep refusing an employee.

    401 when the token does not verify at all; 403 when it verifies and the
    account matches none of the kinds this call allows.
    """
    # Branch 1: app admin. verify_admin_token raises 403 for a VALID account
    # with no app_admin claim -- which is not a refusal here, it is the
    # signal to try the next branch. A 401 IS terminal: an unverifiable
    # token will not verify differently for a later reader.
    try:
        admin = verify_admin_token(token)
    except HTTPException as exc:
        if exc.status_code == 401:
            raise
        admin = None
    if admin is not None:
        return CompositeActor(
            uid=admin.uid, email=admin.email, kind=ACTOR_KIND_APP_ADMIN)

    # Branch 2 (and, when allowed, branch 3): firm manager, or firm
    # employee. THIS MODULE VERIFIES THE TOKEN ITSELF, with the same
    # fb_auth.verify_id_token the admin branch used -- it does not call
    # backend.services.auth.verify_token. That module is the VOICE app's
    # verifier: importing it would make the admin service depend on the
    # voice surface's enrolment rules (which have nothing to do with
    # managing staff) and would break this module's liftability, pinned by
    # test_admin_auth.py::test_admin_auth_does_not_import_the_other_two_
    # auth_modules.
    #
    # What IS shared is the manager/employee RULES, and only the rules:
    # backend.services.firms.manager_firm_id and .employee_firm_id are pure,
    # side-effect-free predicates over an already-verified claims dict,
    # living in the module that owns what a firm IS. Sharing them is what
    # keeps each rule in ONE home without sharing a verifier.
    from backend.services.firms import employee_firm_id, manager_firm_id

    import firebase_admin
    from firebase_admin import auth as fb_auth

    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    try:
        claims = fb_auth.verify_id_token(token)
    except Exception:
        raise HTTPException(status_code=401,
                            detail="Invalid or expired sign-in")

    firm_id = manager_firm_id(claims)
    if firm_id:
        uid = claims.get("uid") or claims.get("sub")
        if not uid:
            raise HTTPException(status_code=401,
                                detail="Invalid or expired sign-in")
        return CompositeActor(
            uid=uid,
            email=claims.get("email"),
            kind=ACTOR_KIND_FIRM_MANAGER,
            firm_id=firm_id,
        )

    if allow_employee:
        employee_of = employee_firm_id(claims)
        if employee_of:
            uid = claims.get("uid") or claims.get("sub")
            if not uid:
                raise HTTPException(status_code=401,
                                    detail="Invalid or expired sign-in")
            return CompositeActor(
                uid=uid,
                email=claims.get("email"),
                kind=ACTOR_KIND_FIRM_EMPLOYEE,
                firm_id=employee_of,
                employee_id=uid,
            )

    raise HTTPException(
        status_code=403,
        detail=(NO_ADMIN_ACCESS_PREFIX
                + " This account is neither an admin nor a firm manager"),
    )


async def require_app_admin_or_owning_manager(
    authorization: Annotated[Optional[str], Header()] = None,
) -> CompositeActor:
    """FastAPI dependency: an app admin, OR a manager of some firm.

    ORDER MATTERS AND IS DELIBERATE. The app_admin claim is checked FIRST, so
    an account holding both app_admin and a firm manager claim acts as an app
    admin -- the strictly wider role. The reverse order would silently
    downgrade such an account to its own firm, which is the surprising
    outcome (and the one an operator would debug for an hour).

    Both branches verify the SAME token through the SAME call --
    firebase_admin.auth.verify_id_token, made by THIS module in both cases
    (see _resolve_admin_or_manager_or_employee_actor, the shared body).

    401 when the token does not verify at all; 403 when it verifies and the
    account is neither an app admin nor any firm's manager -- an EMPLOYEE
    included, on purpose: this is the gate the four /admin/users routes
    carry, where a firm employee has never had access, and widening it here
    would widen those too. See require_app_admin_or_owning_manager_or_
    employee below for the one route that needs the third actor kind.
    """
    if _dev_bypass_allowed():
        return CompositeActor(
            uid="dev_admin",
            email="dev@example.com",
            kind=ACTOR_KIND_APP_ADMIN,
        )

    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Sign-in required")

    return _resolve_admin_or_manager_or_employee_actor(
        token, allow_employee=False)


async def require_app_admin_or_owning_manager_or_employee(
    authorization: Annotated[Optional[str], Header()] = None,
) -> CompositeActor:
    """FastAPI dependency: an app admin, a manager of some firm, OR an
    EMPLOYEE of some firm (bd polyglot-pdf-scaig).

    THE ONE ROUTE THIS GATE IS FOR: GET /admin/firms/{firm_id}/links. The
    plan's own composite gate (require_app_admin_or_owning_manager, above)
    has exactly two actor kinds by design -- widening IT to accept an
    employee would silently widen every route already gated by it (the four
    /admin/users routes), where an employee legitimately has no business
    (test_composite_gate.py's test_neither_an_admin_nor_a_manager_is_403
    already pins an employee claims dict as 403 through that name). This is
    a SEPARATE dependency, scoped to the ONE route that needs a third actor
    kind, rather than a parameter that changes the older gate's behavior for
    every caller of it.

    REVOKE (POST /admin/links/{jti}/revoke) DELIBERATELY STAYS ON THE
    NARROWER require_app_admin_or_owning_manager -- an employee must never
    revoke a link, so the write-side route keeps the existing two-actor
    gate untouched, per the bead's own shape-(a)-vs-(b) analysis: this is
    the same choice, made as a wholly separate dependency (shape (b))
    rather than a widened one (shape (a)) with an extra guard bolted onto
    the write route, so there is no third actor kind that revoke's gate can
    even resolve to without deliberately calling this function.

    An employee actor's firm_id is their OWN firm (backend.services.firms.
    employee_firm_id) and employee_id is their own uid -- both taken from
    the VERIFIED TOKEN, never the request, matching the plan's own words
    ("ids come from the token, not the query"). The route itself is
    responsible for using employee_id to scope (or override) any
    employee_id query parameter for this actor kind; this dependency only
    resolves WHO is calling.

    401 when the token does not verify at all; 403 when it verifies and the
    account is none of the three kinds.
    """
    if _dev_bypass_allowed():
        return CompositeActor(
            uid="dev_admin",
            email="dev@example.com",
            kind=ACTOR_KIND_APP_ADMIN,
        )

    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Sign-in required")

    return _resolve_admin_or_manager_or_employee_actor(
        token, allow_employee=True)


def resolve_target_firm(actor: CompositeActor,
                        body_firm_id: Optional[str]) -> str:
    """The firm this request acts on, or the refusal that ends it.

    THE ONE HOME for the two-actor firm rule (CLAUDE.md scar #8), so every
    composite route resolves it identically instead of each restating it:

      * a MANAGER's firm comes from the token; a body that names ANY firm is
        403, including one naming their own -- "the same value" is not the
        test, "did you try to choose" is. Accepting a matching value would
        make the refusal depend on what the caller happened to send, and the
        next console version that sends it for every request would silently
        stop being refused.
      * an APP ADMIN must name one; omitting it is 422, since there is no
        firm to fall back to and defaulting to any particular firm would be
        a guess with a write behind it.
    """
    if not actor.is_app_admin:
        if body_firm_id is not None:
            raise HTTPException(
                status_code=403,
                detail=("a firm manager may not name a firm; the firm is "
                        "taken from your sign-in"),
            )
        if not actor.firm_id:
            # Unreachable through the gate above, which never builds a
            # manager actor without a firm_id. A real check rather than an
            # assert because asserts vanish under python -O, and the
            # failure mode if this ever became reachable is an empty
            # firm_id used as a Firestore key -- a query that matches
            # nothing while the caller looks authorized.
            raise HTTPException(
                status_code=403,
                detail=(NO_ADMIN_ACCESS_PREFIX
                        + " This account is not a manager of a firm"),
            )
        return actor.firm_id
    if not body_firm_id:
        raise HTTPException(
            status_code=422,
            detail="firm_id is required when acting as an app admin",
        )
    return body_firm_id


# ---------------------------------------------------------------------------
# require_google_oidc: the gate for Cloud Scheduler / Pub/Sub push callers
# (bd polyglot-pdf-8vgfh)
# ---------------------------------------------------------------------------
#
# The fourth and last gate the plan names. No human signs in here -- the
# caller is a Google-managed service (Cloud Scheduler today; Pub/Sub push in
# Epic 4) presenting a Google-signed OIDC ID token in its own Authorization
# header, minted by attaching a service account to the job/subscription and
# letting Google sign the token, never a credential this repo issues or
# stores.
#
# WHY AUDIENCE ALONE DOES NOT PROVE THE CALLER. On a PUBLIC Cloud Run service
# (--allow-unauthenticated, same as every other admin route), the audience
# claim is not a secret: it is simply this route's own URL, and anyone who
# can read this source file -- or simply guess the URL -- can mint a request
# with a Google-signed token carrying that SAME audience from their OWN GCP
# project (Cloud Scheduler, a Cloud Function, `gcloud auth print-identity-
# token --audiences=...` from any account). A valid signature and a matching
# audience together prove only "Google vouches this token was minted for
# this URL", never "this specific caller is the scheduler job we created".
# So the gate ALSO pins the token's `email` claim (the service account that
# minted it) against an explicit allowlist -- the same two-factor shape
# require_admin_or_owning_manager's callers get from a firm_id, applied here
# to a machine identity instead of a human one.
class GoogleServiceActor(BaseModel):
    """WHO is acting, as a Google-managed service caller.

    email is never None here (unlike AdminActor's) -- an OIDC token with no
    email claim can never pass the allowlist check below, so by the time
    this is constructed the field is always populated.
    """

    email: str

    def label(self) -> str:
        return self.email


class OidcVerificationUnavailable(Exception):
    """google-auth could not be imported, or its own request transport
    failed (DNS, network) while fetching Google's signing certs.

    Raised rather than silently treated as "token invalid": a caller must be
    able to tell "this token is bad" (401 -- retrying with a fresh token
    would not help) apart from "we could not check" (503 -- retrying might).
    Cloud Scheduler retries a 503 on its own backoff; retrying a 401 forever
    would never succeed and would paper over a real misconfiguration.
    """


def _verify_google_id_token(token: str, audience: str) -> dict:
    """The raw claims of a Google-signed ID token for `audience`, or raise.

    Isolated from require_google_oidc() below so a unit test can monkeypatch
    ONE seam (this function) rather than reaching into google.auth's own
    HTTP transport. Raises ValueError for an invalid token (bad signature,
    expired, wrong audience -- what google-auth itself raises directly),
    and OidcVerificationUnavailable if the library itself is missing, or a
    TRANSPORT-layer failure (google.auth.exceptions.TransportError, a raw
    requests.exceptions.RequestException/OSError) kept the certs fetch from
    completing at all.
    """
    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token
        import google.auth.exceptions as google_auth_exceptions
        import requests.exceptions as requests_exceptions
    except ImportError as exc:  # pragma: no cover -- google-auth is a
        # pinned direct dependency (backend/requirements.txt); this only
        # fires if the deployed image's dependency install is broken.
        raise OidcVerificationUnavailable(
            "google-auth is not importable: {}".format(exc)) from exc

    try:
        return google_id_token.verify_oauth2_token(
            token, google_requests.Request(), audience=audience)
    except Exception as exc:  # noqa: BLE001
        # google-auth's own exception hierarchy is not uniform across
        # failure modes (a bad signature is ValueError; a certs-fetch
        # network failure is a transport.Request exception) -- narrowing
        # to "the token itself is malformed/wrong" vs. "we could not reach
        # Google's certs endpoint" would require re-deriving that
        # hierarchy here. Treated as OidcVerificationUnavailable when the
        # exception is a TRANSPORT-layer failure rather than a verification
        # failure, and everything else is a 401-shaped verification
        # failure, since a forged or expired token is by far the common
        # case and must not be mistaken for a 503 an attacker could induce
        # simply by presenting garbage.
        #
        # NOTE: builtin ConnectionError/TimeoutError are NOT what the real
        # transport raises. google.auth.transport.requests.Request.__call__
        # wraps every failure (including a raw requests.exceptions.
        # ConnectionError) as google.auth.exceptions.TransportError, which
        # chains from GoogleAuthError -> Exception, NOT from builtin
        # ConnectionError; _fetch_certs raises the same type on a non-200
        # certs response. And requests.exceptions.RequestException itself
        # chains from OSError, not builtin ConnectionError. Verified
        # against the installed google-auth 2.53.0 sources (bd
        # polyglot-pdf-8vgfh cross-surface review finding 1): catching only
        # builtin (ConnectionError, TimeoutError) left this branch
        # unreachable in production, misclassifying every real certs-fetch
        # outage as a 401 "bad token" instead of a 503 "could not check".
        if isinstance(exc, (
            google_auth_exceptions.TransportError,
            requests_exceptions.RequestException,
            ConnectionError,
            TimeoutError,
            OSError,
        )):
            raise OidcVerificationUnavailable(str(exc)) from exc
        raise ValueError(str(exc)) from exc


def require_google_oidc(audience, allowed_caller_emails):
    """Build a FastAPI dependency gating a route to specific Google service
    identities: require_google_oidc(audience="https://...", allowed_caller_
    emails=("scheduler-sa@project.iam.gserviceaccount.com",)).

    A FACTORY, not a dependency itself -- unlike the other three gates,
    which need no per-route configuration, this one needs the route's OWN
    URL (the expected audience) and the specific caller(s) it should accept,
    both of which vary per route and per deployment. A route wires it as
    Depends(require_google_oidc(audience=..., allowed_caller_emails=...)).

    EACH ARGUMENT MAY BE THE VALUE ITSELF OR A ZERO-ARG CALLABE returning
    it, resolved FRESH ON EVERY REQUEST rather than once when the route
    module is imported. This matters because both values come from
    deploy-time environment variables (the admin service's own Cloud Run
    URL is not known until its first deploy; the scheduler job's service-
    account email is set by an operator): a route module imports at process
    START, and reading os.environ at IMPORT time would freeze in whatever
    value existed before a real deployment finished configuring the
    service -- and would make a test that wants to exercise "unconfigured"
    vs. "configured" unable to do so without reloading the module. Passing
    a callable defers the read to request time, exactly where it belongs.

    allowed_caller_emails resolves to a tuple (not a single string) because
    Epic 4's Pub/Sub push route will need to pin a DIFFERENT service-account
    email than the scheduler route does, and a future route could
    legitimately accept either of two identities (e.g. during a service-
    account rotation) -- a single-string parameter would need a breaking
    signature change for that case.

    401 for a token that fails verification outright (bad signature,
    expired, wrong audience -- retrying with a fresh token might help); 403
    for a token that verifies but whose email is not on the allowlist (a
    real Google-signed token, just not from a caller this route accepts --
    retrying will never help, the caller is wrong); 503 when the
    verification machinery itself could not run OR when this route's own
    configuration is incomplete (fail CLOSED: an empty audience or an empty
    allowlist must never be read as "nothing to check against, allow it").
    """
    def _resolve(value):
        return value() if callable(value) else value

    async def _dependency(
        authorization: Annotated[Optional[str], Header()] = None,
    ) -> GoogleServiceActor:
        resolved_audience = _resolve(audience)
        resolved_allowed_emails = _resolve(allowed_caller_emails)
        if not resolved_audience or not resolved_allowed_emails:
            _log.error(
                "google_oidc_route_not_configured",
                has_audience=bool(resolved_audience),
                has_allowed_emails=bool(resolved_allowed_emails),
            )
            raise HTTPException(
                status_code=503,
                detail="this route is not yet configured for scheduler access",
            )

        token = None
        if authorization and authorization.startswith("Bearer "):
            token = authorization[7:]
        if not token:
            raise HTTPException(status_code=401,
                                detail="Sign-in required")

        try:
            claims = _verify_google_id_token(token, resolved_audience)
        except OidcVerificationUnavailable as exc:
            _log.error("google_oidc_verification_unavailable", error_type=type(exc).__name__)
            raise HTTPException(
                status_code=503,
                detail="identity verification unavailable") from exc
        except ValueError:
            raise HTTPException(status_code=401,
                                detail="Invalid or expired sign-in")

        email = claims.get("email")
        # email_verified matters here in a way it does not for a human
        # sign-in flow: a Google SERVICE ACCOUNT's email is always
        # verified by construction (there is no email-confirmation step
        # for a service account), so a token claiming email_verified is
        # not True is either a non-service-account token or malformed --
        # either way, not a caller this gate should ever accept.
        if not email or claims.get("email_verified") is not True \
                or email not in resolved_allowed_emails:
            _log.warning(
                "google_oidc_caller_not_allowed",
                email_length=len(email or ""), audience=resolved_audience,
            )
            raise HTTPException(
                status_code=403,
                detail=(NO_ADMIN_ACCESS_PREFIX
                        + " This caller is not authorized for this route"),
            )

        return GoogleServiceActor(email=email)

    # RENAMED to the FACTORY's own name, not left as "_dependency". FastAPI's
    # dependant graph records a dependency by ITS CALLABLE, and
    # test_admin_route_auth.py's route/gate set pin reads sub.call.__name__
    # to learn which of the four known gates a route carries -- an inner
    # closure named "_dependency" would make every route wired through this
    # factory look like it carries a gate called "_dependency", which is not
    # in the four-name vocabulary and would flag a correctly-gated route as
    # ungated. Every other gate in this module IS its own name (require_app_
    # admin, etc. are not factories); this is the one exception, so its
    # returned closure must present as require_google_oidc for that
    # detection to keep working uniformly across all four.
    _dependency.__name__ = "require_google_oidc"
    return _dependency
