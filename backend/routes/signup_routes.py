"""POST /api/signup/check -- the email-signup allowlist, checked SERVER-SIDE.

Sprint 23 C3 (PF-6). The voice app's email signup used to query the
`authorized_emails` collection straight from the browser, before the account
existed, which forced `allow read: if true` on that collection -- and a public
read on a collection of staff emails is a LIST: anyone holding the public web
config could enumerate every allowlisted address. The rule is now a full
client deny (Admin-SDK-only) and this route does the lookup with the backend's
Admin SDK credentials instead.

Posture, deliberately the same as POST /api/links/open:

- Unauthenticated by design (the caller has no account yet).
- Uniform 404 on EVERY refusal -- an address that is not allowlisted, a
  malformed address, and a Firestore failure are indistinguishable from the
  outside, so the route is not an oracle for which addresses exist beyond the
  one bit a signup attempt already reveals. The cause is logged, never
  returned, and the address itself is never logged (it is staff PII).
- 204 on success: nothing to say but "go ahead".
- Not rate-limited yet: that is the sprint's PF-5 decision (rate limiting is
  new infrastructure or a cost call), tracked separately.
"""
import asyncio

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

import structlog

_log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/signup", tags=["signup"])

# The collection the allowlist lives in, keyed on its `email` field (entries
# are managed out of band in the Firebase console; no code writes it).
ALLOWLIST_COLLECTION = "authorized_emails"
_EMAIL_MAX_LEN = 254  # RFC 5321 path limit; anything longer is not an address


class SignupCheckRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=_EMAIL_MAX_LEN)


def email_is_allowlisted(email: str) -> bool:
    """One Admin-SDK read: is `email` (lower-cased) in the allowlist?

    Fails CLOSED: any Firestore error is `False`, and the caller turns that
    into the same 404 as a miss.
    """
    from backend.services.auth import get_db

    needle = email.strip().lower()
    if "@" not in needle:
        return False
    try:
        col = get_db().collection(ALLOWLIST_COLLECTION)
        try:
            # Keyword FieldFilter, like every other query site in the repo:
            # newer google-cloud-firestore deprecates the positional where().
            from google.cloud.firestore_v1.base_query import FieldFilter

            query = col.where(filter=FieldFilter("email", "==", needle))
        except ImportError:
            query = col.where("email", "==", needle)
        docs = list(query.limit(1).stream())
    except Exception as exc:
        _log.error("signup_check_lookup_failed", error_type=type(exc).__name__)
        return False
    return bool(docs)


@router.post("/check", status_code=204, response_class=Response)
async def signup_check(body: SignupCheckRequest) -> Response:
    allowed = await asyncio.to_thread(email_is_allowlisted, body.email)
    if not allowed:
        # Length only: the address is staff PII and must not reach the log.
        _log.info("signup_check_refused", email_length=len(body.email))
        raise HTTPException(status_code=404, detail="Not found")
    return Response(status_code=204)
