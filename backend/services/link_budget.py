"""Tunable spend + minting caps for the CLIENT LINK tier (bd polyglot-pdf-ik7e).

WHAT THIS IS. Two MVP protection caps, deliberately quick and dirty, and
deliberately TUNABLE without a code change (maintainer, 2026-08-27):

  1. per-FIRM minting cap  -- how many links one firm may mint (default 30)
  2. per-LINK cost ceiling -- USD of AI spend one link may buy (default $10)

WHY A SEPARATE MODULE. These are policy numbers, not mechanism. They are read
at CALL TIME (never captured at import), so an operator retunes a live
deployment with no redeploy of a new image. That is the same shape
LINK_MINTING_ENABLED already uses in routes/link_routes.py, kept deliberately
consistent.

THE ADMIN CONSOLE IS THE HOME NOW (bd polyglot-pdf-bg313). firm_link_cap()
and default_cost_ceiling_usd() resolve through backend.services.runtime_config,
which reads app_config/{channel} in Firestore (TTL-cached, falling back to
the DEFAULT_* constants below when nothing has ever been read successfully)
instead of os.getenv. Everything here is nonetheless written as "resolve a
number for THIS firm / THIS kit", not as a global constant -- so a later
console slice can add a per-firm or per-kit override without the call sites
changing.

PER-FORM CAPS ARE SUPPORTED HERE, BUT ARE NOT YET IN FORCE. The maintainer
flagged possible per-form pricing (a $5 form and a $15 form under one firm).
`cost_ceiling_usd_for_kit` takes kit metadata and honours a
`link_cost_ceiling_usd` key when the kit carries one, falling back to the
global default. A kit that omits it behaves exactly as before.

Two kits DO set it now -- w7 and i-90 at $3 (bd polyglot-pdf-gob8l). AT THE
SOCKET (bd polyglot-pdf-ah5d3 / A4, closing polyglot-pdf-4tjt7) the per-form
number reaches a connecting client through a DIFFERENT path than this
function: `cost_ceiling_usd_for_claims` reads the token's own `cap_usd`
claim, resolved once at MINT time (by A3) from the kit's price commercial and
signed in -- never a per-connect kit metadata load. `cost_ceiling_usd_for_kit`
itself is unchanged and still real: it is what A3's mint route calls to
resolve that claim in the first place, and it is what any future caller that
DOES hold kit metadata (not a token) should keep using. Fails safe -- a higher ceiling, never an
absent one.

WHAT THIS MODULE DOES NOT DO. It holds no counters and reaches no datastore.
It answers "what is the limit?" only. Enforcement -- accumulating spend against
a link and refusing when it is exceeded -- lives with the code that owns the
session. Keeping the policy numbers separate from the counting is what lets the
console retune them later without touching the enforcement path.
"""

from __future__ import annotations

from typing import Any, Optional

from backend.services.runtime_config import (
    link_cost_ceiling_usd as _rc_link_cost_ceiling_usd,
    link_firm_cap as _rc_link_firm_cap,
)

# ---------------------------------------------------------------------------
# Defaults (maintainer, 2026-08-27). MVP protection caps, not a pricing model.
# ---------------------------------------------------------------------------

# Links one firm may mint. Bounds the blast radius of a leaked or misused firm
# credential: without it, one compromised staff account mints unlimited paid
# entry points.
DEFAULT_FIRM_LINK_CAP = 30

# USD of AI spend a single link may buy across its whole life -- every session
# and every reconnect on that link, not one connection. Measured baseline for
# context: ~$0.05/field, so a full 22-field W-7 runs $0.59 happy / $1.25
# unhappy all-in (bd polyglot-pdf-89mt). $10 is therefore several times a
# normal form: it stops a client chatting for a week, not a client having a
# hard day.
DEFAULT_LINK_COST_CEILING_USD = 10.0

# The kit-metadata key that overrides the global ceiling for ONE form. Reserved
# now so per-form pricing does not need a schema migration later.
KIT_COST_CEILING_KEY = "link_cost_ceiling_usd"


def _positive_float(raw: str, fallback: float) -> float:
    """Parse a positive float, falling back on anything unusable.

    A malformed or non-positive override must NOT silently disable the cap --
    that is the one failure mode a spend ceiling cannot have. Zero and negative
    values are rejected for the same reason: read literally, `0` would mean "no
    spend allowed", but as a typo in an env var it far more likely means "unset",
    and guessing wrong in that direction breaks every client session. An operator
    who genuinely wants no AI spend turns minting off instead.
    """
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return fallback
    if value <= 0 or value != value or value == float("inf"):
        return fallback
    return value


def firm_link_cap() -> int:
    """How many links one firm may mint.

    Resolved via runtime_config (app_config/{channel} in Firestore, TTL-
    cached) so an operator can retune without a redeploy.
    """
    return _rc_link_firm_cap()


def default_cost_ceiling_usd() -> float:
    """The global per-link spend ceiling, in USD.

    Resolved via runtime_config -- see firm_link_cap() above.
    """
    return _rc_link_cost_ceiling_usd()


def cost_ceiling_usd_for_kit(kit_metadata: Optional[dict[str, Any]]) -> float:
    """The spend ceiling for a link on THIS form.

    Per-form pricing room (maintainer, 2026-08-27: "we may want to make
    different caps for different forms ... so some forms are $5 and some are
    $15"). A kit whose metadata carries `link_cost_ceiling_usd` gets that
    number; every other kit gets the global default.

    A malformed or non-positive kit value falls back to the global default
    rather than to "unlimited" -- a typo in one kit's metadata must not remove
    that form's ceiling.
    """
    fallback = default_cost_ceiling_usd()
    if not isinstance(kit_metadata, dict):
        return fallback
    raw = kit_metadata.get(KIT_COST_CEILING_KEY)
    if raw is None:
        return fallback
    if isinstance(raw, bool):
        # bool is an int subclass, so `true` would otherwise reach the numeric
        # branch and resolve to a $1.00 ceiling. Belt-and-braces with the str()
        # round-trip below (float("True") already raises), and deliberately
        # kept: the two together survive either being removed alone, which a
        # mutation check confirmed. Delete both and a `true` silently caps that
        # form at a fifth of one normal session.
        return fallback
    if isinstance(raw, (int, float)):
        return _positive_float(str(raw), fallback)
    if isinstance(raw, str):
        return _positive_float(raw.strip(), fallback)
    return fallback


# The token-payload key carrying the per-link cap, once signed in at mint
# (bd polyglot-pdf-ah5d3 / A4; `services/link_tokens.py`'s `mint_link_token`).
CLAIM_COST_CEILING_KEY = "cap_usd"


def cost_ceiling_usd_for_claims(claims: Optional[dict[str, Any]]) -> float:
    """The spend ceiling for a CLIENT LINK socket connection.

    PRECEDENCE, AND NOTHING ELSE: token `cap_usd` beats the global ceiling.
    No per-connect Firestore kit read exists here or anywhere upstream of it
    -- deliberately, because after the open-requires-a-mint-record cutover
    (A3) every token that CAN open already carries `cap_usd` (it was resolved
    once from the kit's `burn_cap_usd`, at mint, by A3). A per-connect kit
    load would therefore pay a Firestore read on every client connect for a
    case -- "an openable token with no cap claim" -- that cannot occur once
    A3 has shipped. Before A3 ships, or for a token minted without a resolvable
    kit ceiling, the claim is simply absent and this function falls through to
    the global -- the SAME safe default `cost_ceiling_usd_for_kit` uses for a
    kit with no opinion. The global is a defensive floor, never "no ceiling":
    a malformed or missing claim must never read as unlimited spend.

    Uses the SAME parsing helper as `cost_ceiling_usd_for_kit` (both funnel
    an untrusted numeric-ish value through `_positive_float`), so a bad
    `cap_usd` fails exactly the way a bad per-kit override does -- one
    defensive-parsing rule for "a spend ceiling read from outside this
    module", not two that could drift.
    """
    fallback = default_cost_ceiling_usd()
    if not isinstance(claims, dict):
        return fallback
    raw = claims.get(CLAIM_COST_CEILING_KEY)
    if raw is None:
        return fallback
    if isinstance(raw, bool):
        # bool is an int subclass -- see cost_ceiling_usd_for_kit's identical
        # carve-out. link_tokens.mint_link_token already refuses to sign a
        # bool in as cap_usd, so this is belt-and-braces against a claims
        # dict assembled by a future caller that did not go through minting
        # (e.g. a test, or a later reconciliation path).
        return fallback
    if isinstance(raw, (int, float)):
        return _positive_float(str(raw), fallback)
    if isinstance(raw, str):
        return _positive_float(raw.strip(), fallback)
    return fallback
