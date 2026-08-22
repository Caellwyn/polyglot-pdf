"""Client magic-link tokens: mint + verify (bd polyglot-pdf-ugm6).

THE CLIENT'S ONLY ENTRY PATH. A firm's client never signs in and never uses a
staff-signed-in machine (maintainer, 2026-08-17): they open a link that is
good for ONE form, ONE completion, inside a time window.

WHY A HAND-ROLLED SIGNED TOKEN AND NOT JWT: this token is produced and
consumed by the same service, so there is no interop reason to take a JWT
dependency, and JWT's headline footgun -- the caller trusting an attacker's
`alg` header -- cannot exist in a format with no algorithm field. HMAC-SHA256
over a canonical payload with a constant-time compare is the whole
requirement. stdlib only.

THE NO-CLIENT-IDENTIFIER INVARIANT (the reason this design exists):
the token carries {firm_id, kit_id, jti, employee_id, exp} and DELIBERATELY
no client identifier -- no name, no email, no case number. This is a
SPLIT-KEY arrangement, and it is evidentiary, not merely privacy hygiene
(maintainer, 2026-08-19):

  - WE hold a pseudonymous record (disclaimer acceptance + field
    confirmations, joined on the session), keyed by `jti`.
  - THE FIRM holds the identity mapping (which client got which link).
  - Neither side alone can connect a record to a person.

Re-identification therefore requires the FIRM to act, which puts the
disclosure decision -- and the legal process behind it -- on the party with
the attorney-client relationship rather than on us. Adding a client
identifier here would collapse that split and is a breaking change to the
product's legal posture, not a convenience.

`employee_id` IS carried: it identifies the STAFF member who sent the link
(the maintainer's telemetry requirement -- every session logs firm, form, and
originating employee). Staff are our customer's people, not the form's
subject, so this does not touch the invariant.

THREE CREDENTIAL SYSTEMS EXIST, AND THEY MUST NOT MERGE (checked against
epic polyglot-pdf-ijntk, editor identity, 2026-08-22):

  1. VOICE-APP / FIRM STAFF -- per-user Firebase ID tokens carrying
     firm_id + firm_role custom claims (bd lo88). services/auth.py.
  2. SCHEMA EDITOR -- today two shared secrets; epic ijntk is replacing
     them with per-user editor identity in its OWN services/editor_auth.py.
     Nothing here touches that path.
  3. CLIENT LINKS -- this module. The ONLY credential a firm's CLIENT ever
     holds, because a client never signs in at all.

WHY (3) IS NOT REDUNDANT WITH (1): a client has no account and must never
have one -- they are the firm's customer, not ours. There is nothing to sign
in to, so a Firebase token cannot exist for them.

WHY THE MINT ENDPOINT DOES NOT GET ITS OWN SECRET: this bead originally
specified a per-firm API key, "X-Editor-Token-style". That is superseded --
the minting caller is FIRM STAFF, who already hold (1). A per-firm shared
secret would be a weaker duplicate of a credential they already have, would
re-introduce exactly the shared-secret pattern epic ijntk is deleting, and
CANNOT identify which employee minted a link -- which this bead's own
telemetry requirement needs. employee_id therefore comes from the verified
Firebase uid, never from the request body.

The two token FORMATS are structurally distinct (a link token has one dot, a
Firebase JWT has two), so neither verifier can silently accept the other's
token. That property is pinned by test_link_tokens.py.

ASCII only.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Optional

import structlog

_log = structlog.get_logger().bind(module="link_tokens")

# Bumped only for a BREAKING payload change. Verification refuses an unknown
# version outright rather than guessing, so an old link fails closed instead
# of being reinterpreted under new rules.
TOKEN_VERSION = 1

# Maintainer's defaults (2026-08-17), confirmed at build time: ~48h to OPEN
# from issuance, ~24h to COMPLETE after opening. Both are overridable per
# mint so a firm with a slower intake process is not forced to re-issue.
DEFAULT_OPEN_WINDOW_S = 48 * 3600
DEFAULT_COMPLETE_WINDOW_S = 24 * 3600


class LinkTokenError(Exception):
    """A token that must not grant access. The MESSAGE IS FOR LOGS ONLY.

    Callers return one indistinguishable refusal to the client: a bad
    signature, an expired window, and a well-formed token for a suspended
    firm must look identical from outside, or the differences become an
    oracle for probing which links or firms exist.
    """


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _signing_key() -> bytes:
    """The HMAC key, from LINK_TOKEN_SECRET.

    FAILS CLOSED and LOUDLY: with no secret configured there is no safe
    fallback -- a default or generated-per-process key would either be
    forgeable by anyone reading the source, or would silently invalidate
    every outstanding link on each deploy/restart (a client mid-intake would
    find their link dead with no explanation). Refusing to mint or verify is
    the honest failure.
    """
    secret = os.getenv("LINK_TOKEN_SECRET", "")
    if not secret or len(secret) < 32:
        raise LinkTokenError(
            "LINK_TOKEN_SECRET missing or too short (>=32 chars required)"
        )
    return secret.encode("utf-8")


def _sign(payload_b64: str) -> str:
    return _b64u(hmac.new(_signing_key(), payload_b64.encode("ascii"),
                          hashlib.sha256).digest())


def mint_link_token(
    firm_id: str,
    kit_id: str,
    employee_id: str,
    open_window_s: int = DEFAULT_OPEN_WINDOW_S,
    complete_window_s: int = DEFAULT_COMPLETE_WINDOW_S,
    now: Optional[float] = None,
) -> tuple[str, str]:
    """Mint one client link token. Returns (token, jti).

    The `jti` is the FIRM'S JOIN KEY: it is what the firm records against
    their client's case, and what our session records carry, so the two sides
    can be matched later WITHOUT us ever holding the identity. The caller
    must return it to the minting employee.

    `complete_window_s` rides in the token but is enforced at REDEMPTION
    (the completion clock starts when the link is first opened, which has not
    happened yet at mint time).
    """
    if not all(isinstance(v, str) and v for v in (firm_id, kit_id, employee_id)):
        raise LinkTokenError("firm_id, kit_id and employee_id are required")

    issued = int(now if now is not None else time.time())
    # 16 bytes: collision-free in practice, and unguessable -- the jti is the
    # firm's join key, so a predictable one would let an outsider correlate
    # links to sessions.
    jti = _b64u(secrets.token_bytes(16))

    payload = {
        "v": TOKEN_VERSION,
        "firm_id": firm_id,
        "kit_id": kit_id,
        "employee_id": employee_id,
        "jti": jti,
        "iat": issued,
        "exp": issued + int(open_window_s),      # deadline to OPEN
        "cw": int(complete_window_s),            # completion window, once opened
    }
    # sort_keys + compact separators: the signature covers these exact bytes,
    # so the encoding must be deterministic or a re-serialization breaks it.
    payload_b64 = _b64u(json.dumps(payload, sort_keys=True,
                                   separators=(",", ":")).encode("utf-8"))
    return payload_b64 + "." + _sign(payload_b64), jti


def verify_link_token(token: str, now: Optional[float] = None) -> dict:
    """Verify a token and return its payload, or raise LinkTokenError.

    Checks, in order: shape, SIGNATURE (before anything reads the payload as
    meaningful -- an unverified payload is attacker-controlled text), version,
    required fields, then the open deadline.

    Deliberately does NOT check one-time use or firm status: those need
    external state (the redemption store, the firms collection) and belong to
    the caller. This function answers only "did we issue this, unmodified,
    and is it still within its opening window?".
    """
    if not isinstance(token, str) or token.count(".") != 1:
        raise LinkTokenError("malformed token")
    payload_b64, sig = token.split(".", 1)
    if not payload_b64 or not sig:
        raise LinkTokenError("malformed token")

    # CONSTANT-TIME. A byte-by-byte comparison leaks, through timing, how much
    # of a forged signature was correct, which is enough to reconstruct one.
    if not hmac.compare_digest(sig, _sign(payload_b64)):
        raise LinkTokenError("bad signature")

    try:
        payload = json.loads(_b64u_decode(payload_b64))
    except Exception as exc:  # noqa: BLE001 -- any decode failure is a refusal
        raise LinkTokenError("undecodable payload") from exc
    if not isinstance(payload, dict):
        raise LinkTokenError("payload is not an object")

    # Refuse an unknown version rather than interpreting an old payload under
    # today's rules.
    if payload.get("v") != TOKEN_VERSION:
        raise LinkTokenError("unsupported token version")

    for key in ("firm_id", "kit_id", "employee_id", "jti", "iat", "exp", "cw"):
        if key not in payload:
            raise LinkTokenError("missing field: " + key)
    for key in ("firm_id", "kit_id", "employee_id", "jti"):
        if not isinstance(payload[key], str) or not payload[key]:
            raise LinkTokenError("field must be a non-empty string: " + key)
    for key in ("iat", "exp", "cw"):
        # bool is an int subclass in Python; exclude it explicitly so a JSON
        # `true` cannot pass as a timestamp.
        if not isinstance(payload[key], int) or isinstance(payload[key], bool):
            raise LinkTokenError("field must be an integer: " + key)

    if int(now if now is not None else time.time()) >= payload["exp"]:
        raise LinkTokenError("link expired before it was opened")

    return payload


def completion_deadline(payload: dict, opened_at: int) -> int:
    """When a link that was OPENED at `opened_at` stops being completable.

    The completion clock starts at first open, not at mint: a client who
    opens the link 47 hours in still gets their full completion window.
    """
    return int(opened_at) + int(payload["cw"])
