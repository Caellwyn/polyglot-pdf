"""Per-channel runtime config, backed by Firestore app_config/{channel}
(bd polyglot-pdf-bg313, Epic 1 child 1.5).

WHAT MOVES HERE. Four keys, moved off deploy-time env so an operator can
retune them without a redeploy:

    LINK_MINTING_ENABLED   (bool)  -- was backend/routes/link_routes.py
    LINK_COST_CEILING_USD  (float) -- was backend/services/link_budget.py
    LINK_FIRM_CAP          (int)   -- was backend/services/link_budget.py
    CREDITS_ENFORCED       (bool)  -- NEW; never had an env read. Read only
                                      through this module (Epic 2 bead A3
                                      gates a zero-balance mint on it).
    CREDIT_LOW_THRESHOLD   (int)   -- NEW; never had an env read, like
                                      CREDITS_ENFORCED. Read only through
                                      this module (Epic 3 bead E3.5's
                                      backend/services/alerts.py compares a
                                      firm's post-debit balance against it).

NOT MOVED (deliberately -- see the bead body): LINK_TOKEN_SECRET (Secret
Manager -- moving a secret into a plain Firestore doc would be a regression),
LINK_BASE_URL, LINK_CHANNEL (topology; moving them would reopen the channel-
isolation bead polyglot-pdf-3q9qn).

ONE DOC PER CHANNEL: app_config/{channel}, `channel` from
backend.services.link_tokens.link_channel() -- the SAME resolver the link
collections already key on, so "which channel am I" has exactly one answer
across the backend. Unknown keys in the doc are ignored and logged (a typo'd
key must not silently do nothing while looking configured).

FALLBACK ORDER on a read failure (Firestore unreachable, doc missing, or a
key absent from the doc): LAST-KNOWN-GOOD from the previous successful read
of THAT key on THIS process, then -- only when nothing was ever read -- the
env default. Env-first would be wrong for the ceiling: a console that just
LOWERED LINK_COST_CEILING_USD must not see the higher env default reappear
during a Firestore blip, which would silently restore a higher spend limit
than the operator intended. Minting's default is `false` either way, so the
ordering does not change its fail-safe direction.

THE "ENV DEFAULT" IS A LIVE os.getenv READ, NOT A COMPILED CONSTANT -- for
the three legacy keys (LINK_MINTING_ENABLED, LINK_COST_CEILING_USD,
LINK_FIRM_CAP). This is deliberate and load-bearing: deploy-staging.sh and
deploy-demo.sh set LINK_MINTING_ENABLED=true in BACKEND_EXTRA_ENV, and that
line must keep working as the fallback until an operator seeds
app_config/{channel}. A compiled-in constant here would make the deploy
scripts' env line silently inert and turn link minting OFF on the next
deploy of either channel until someone ran the seed step -- exactly the
regression this module exists to avoid reintroducing. Each of the three env
reads is parsed with the SAME rules the pre-bg313 call sites used (see
_legacy_env_default below); an unset or unparsable env var falls through to
the historical compiled constant. CREDITS_ENFORCED is the one exception: it
is brand new, never had an env var, and its default stays the compiled
`False` with no os.getenv call at all (see credits_enforced()).

CACHING. A per-process, per-channel TTL cache (30-60s): frequent enough that
flipping a flag from the console is visible within the TTL with no redeploy
(criterion 3), infrequent enough that this is not a Firestore read on every
request. Deliberately NOT get_settings() (backend/config.py) -- that is
lru_cached for the whole process lifetime and would never pick up a config
change at all.

CALL-SITE SWAP. The three existing os.getenv reads become calls into this
module: backend/routes/link_routes.py's _minting_enabled(),
backend/services/link_budget.py's firm_link_cap() and
default_cost_ceiling_usd(). CREDITS_ENFORCED has no os.getenv call to swap;
it is read ONLY via credits_enforced() below.

FIRESTORE ACCESS pattern matches services/firms.py and
services/link_redemptions.py: lazy-imported backend.services.auth.get_db()
(Admin SDK, bypasses Security Rules) so this module's import never requires
firebase_admin to be initialized, and so tests can patch get_db freely.

ASCII only.
"""
from __future__ import annotations

import os
import time
from typing import Any, Optional

import structlog

_log = structlog.get_logger().bind(module="runtime_config")

COLLECTION = "app_config"

KEY_LINK_MINTING_ENABLED = "LINK_MINTING_ENABLED"
KEY_LINK_COST_CEILING_USD = "LINK_COST_CEILING_USD"
KEY_LINK_FIRM_CAP = "LINK_FIRM_CAP"
KEY_CREDITS_ENFORCED = "CREDITS_ENFORCED"
KEY_CREDIT_LOW_THRESHOLD = "CREDIT_LOW_THRESHOLD"

# The complete set of keys this module will read from a channel's doc. A key
# present in the doc but NOT in this set is ignored (logged), not applied --
# see _read_channel_doc. Extend this set (and the typed getter below it) when
# a later bead moves another setting here; nothing else should need to change.
RUNTIME_CONFIG_KEYS = frozenset({
    KEY_LINK_MINTING_ENABLED,
    KEY_LINK_COST_CEILING_USD,
    KEY_LINK_FIRM_CAP,
    KEY_CREDITS_ENFORCED,
    KEY_CREDIT_LOW_THRESHOLD,
})

# Compiled fallback constants -- used ONLY when a key has never been
# successfully read from Firestore on this process AND (for the three legacy
# keys) the environment variable of the same name is unset or unparsable.
# Mirrors the pre-bg313 defaults so a fresh process with no Firestore access
# and no env override behaves exactly as it did before this module existed.
_ENV_DEFAULTS: dict[str, Any] = {
    KEY_LINK_MINTING_ENABLED: False,
    KEY_LINK_COST_CEILING_USD: 10.0,
    KEY_LINK_FIRM_CAP: 30,
    KEY_CREDITS_ENFORCED: False,
    KEY_CREDIT_LOW_THRESHOLD: 10,
}


def _legacy_env_default(key: str) -> Any:
    """The env-shaped default for one key: a live os.getenv read for the
    three legacy keys, parsed exactly as the pre-bg313 call sites parsed
    them, falling back to the compiled constant in _ENV_DEFAULTS when the
    variable is unset or fails to parse. CREDITS_ENFORCED and
    CREDIT_LOW_THRESHOLD never read env -- both are brand new and have no
    pre-bg313 call site to match -- so they always return their compiled
    constant (False, 10).

    This is what keeps deploy-staging.sh's and deploy-demo.sh's
    LINK_MINTING_ENABLED=true (BACKEND_EXTRA_ENV) a real fallback rather than
    a dead line: a compiled constant here would silently turn minting off on
    the next deploy of either channel until an operator seeded
    app_config/{channel}.
    """
    if key == KEY_LINK_MINTING_ENABLED:
        # Pre-bg313: link_routes.py's _minting_enabled() --
        # os.getenv("LINK_MINTING_ENABLED", "false").lower() == "true"
        raw = os.getenv("LINK_MINTING_ENABLED")
        if raw is None:
            return _ENV_DEFAULTS[key]
        return raw.strip().lower() == "true"
    if key == KEY_LINK_COST_CEILING_USD:
        # Pre-bg313: link_budget.py's _positive_float(os.getenv(..., ""), ...)
        raw = os.getenv("LINK_COST_CEILING_USD")
        if raw is None:
            return _ENV_DEFAULTS[key]
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return _ENV_DEFAULTS[key]
        if value <= 0 or value != value or value == float("inf"):
            return _ENV_DEFAULTS[key]
        return value
    if key == KEY_LINK_FIRM_CAP:
        # Pre-bg313: link_budget.py's _positive_int(os.getenv(..., ""), ...)
        raw = os.getenv("LINK_FIRM_CAP")
        if raw is None:
            return _ENV_DEFAULTS[key]
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return _ENV_DEFAULTS[key]
        return value if value > 0 else _ENV_DEFAULTS[key]
    # KEY_CREDITS_ENFORCED, KEY_CREDIT_LOW_THRESHOLD (and anything else):
    # compiled constant only -- neither ever had a pre-bg313 env reader.
    return _ENV_DEFAULTS[key]


# 30-60s TTL cache, keyed by channel. A module-level dict is fine here: this
# process is the only reader/writer of its own cache, and the value is a
# plain dict swap (no partial-read hazard). Public name (no underscore):
# scripts/set_runtime_config.py quotes it in an operator-facing message.
TTL_SECONDS = 45.0

# {channel: (fetched_monotonic, {key: value})}
_cache: dict[str, tuple[float, dict[str, Any]]] = {}

# Last-known-good per (channel, key) -- survives past the TTL and past a
# failed read, so a Firestore blip cannot fall back past the OPERATOR'S last
# successful value. Never cleared; only ever overwritten by a successful read.
_last_known_good: dict[tuple[str, str], Any] = {}


def _coerce(key: str, raw: Any) -> Optional[Any]:
    """Coerce a raw Firestore value to this key's type, or None if unusable.

    A malformed stored value (wrong type, unparsable string) must not crash
    the read or silently disable the setting -- it is treated exactly like an
    absent key, which falls through to last-known-good / env default below.
    """
    if key in (KEY_LINK_MINTING_ENABLED, KEY_CREDITS_ENFORCED):
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            lowered = raw.strip().lower()
            if lowered in ("true", "false"):
                return lowered == "true"
        return None
    if key == KEY_LINK_COST_CEILING_USD:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        if value <= 0 or value != value or value == float("inf"):
            return None
        return value
    if key == KEY_LINK_FIRM_CAP:
        # bool is an int subclass -- reject it explicitly so a stray `true`
        # does not resolve to a cap of 1 (same trap link_budget.py's
        # cost_ceiling_usd_for_kit documents for the kit-metadata override).
        if isinstance(raw, bool):
            return None
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None
    if key == KEY_CREDIT_LOW_THRESHOLD:
        # Same bool-rejection trap as LINK_FIRM_CAP. Zero IS a legitimate
        # threshold (an operator who only wants the zero-balance/exhausted
        # alert and no separate "low" warning) -- unlike the cap and the
        # ceiling, negative is the only value rejected here.
        if isinstance(raw, bool):
            return None
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        return value if value >= 0 else None
    return None


def coerce_value(key: str, raw: Any) -> Optional[Any]:
    """Public entry point to _coerce, for callers outside this module
    (scripts/set_runtime_config.py) that need to validate a value BEFORE
    writing it -- using the exact same coercion a real read would apply, so
    a value the CLI accepts is guaranteed not to be silently treated as
    malformed on the next read.
    """
    return _coerce(key, raw)


def _read_channel_doc(channel: str) -> dict[str, Any]:
    """One Firestore read of app_config/{channel}, coerced and filtered to
    RUNTIME_CONFIG_KEYS. Raises on any store failure -- the caller decides
    the fallback; this function's only job is "read, or fail loudly".
    """
    # Lazy import: this module must be importable with no firebase_admin app
    # initialized (mirrors services/firms.py, services/link_redemptions.py).
    from backend.services.auth import get_db

    db = get_db()
    if db is None:
        raise RuntimeError("no firestore client")
    snap = db.collection(COLLECTION).document(channel).get()
    if not snap.exists:
        return {}
    doc = snap.to_dict() or {}

    result: dict[str, Any] = {}
    for name, raw in doc.items():
        if name not in RUNTIME_CONFIG_KEYS:
            _log.info("runtime_config_unknown_key", channel=channel, key=name)
            continue
        coerced = _coerce(name, raw)
        if coerced is None:
            _log.warning(
                "runtime_config_malformed_value",
                channel=channel, key=name, raw=repr(raw),
            )
            continue
        result[name] = coerced
    return result


def _fetch_fresh(channel: str) -> dict[str, Any]:
    """Read the channel doc and fold successful values into last-known-good.

    A read failure returns {} (never raises to the caller) -- _resolve then
    falls back to last-known-good / env default per key. This is the ONE
    place _last_known_good is written.
    """
    try:
        doc = _read_channel_doc(channel)
    except Exception as exc:  # noqa: BLE001 -- any store failure is a miss
        _log.error("runtime_config_read_failed", channel=channel, error=str(exc))
        return {}
    for key, value in doc.items():
        _last_known_good[(channel, key)] = value
    return doc


def _cached_doc(channel: str) -> dict[str, Any]:
    """The channel's config doc, refreshed at most once per TTL window."""
    now = time.monotonic()
    cached = _cache.get(channel)
    if cached is not None and (now - cached[0]) < TTL_SECONDS:
        return cached[1]
    doc = _fetch_fresh(channel)
    _cache[channel] = (now, doc)
    return doc


def _resolve(channel: str, key: str) -> Any:
    """One key's value for one channel, per the fallback order documented
    at module level: fresh/cached Firestore value, then last-known-good,
    then the env default (a live os.getenv read for the three legacy keys;
    see _legacy_env_default).
    """
    doc = _cached_doc(channel)
    if key in doc:
        return doc[key]
    if (channel, key) in _last_known_good:
        return _last_known_good[(channel, key)]
    return _legacy_env_default(key)


def _current_channel() -> str:
    # Lazy import: avoids a hard import-order dependency on link_tokens for
    # callers that only need a different key.
    from backend.services.link_tokens import link_channel

    return link_channel()


def minting_enabled(channel: Optional[str] = None) -> bool:
    """Is client-link minting turned on for this channel?"""
    return bool(_resolve(channel or _current_channel(), KEY_LINK_MINTING_ENABLED))


def link_cost_ceiling_usd(channel: Optional[str] = None) -> float:
    """The global per-link USD spend ceiling for this channel."""
    return float(_resolve(channel or _current_channel(), KEY_LINK_COST_CEILING_USD))


def link_firm_cap(channel: Optional[str] = None) -> int:
    """How many links one firm may mint, for this channel."""
    return int(_resolve(channel or _current_channel(), KEY_LINK_FIRM_CAP))


def credits_enforced(channel: Optional[str] = None) -> bool:
    """Whether a zero credit balance refuses a mint (Epic 2 bead A3).

    NEW key -- never had an os.getenv fallback of its own, so its env
    default (False) is the ONLY pre-Firestore behaviour: credits are
    unenforced until an operator (or a later migration) turns this on.
    """
    return bool(_resolve(channel or _current_channel(), KEY_CREDITS_ENFORCED))


def credit_low_threshold(channel: Optional[str] = None) -> int:
    """The credit balance at or below which a firm's debit fires the
    `credit_low` telemetry alert (Epic 3 bead E3.5,
    backend/services/alerts.py). NEW key, like CREDITS_ENFORCED -- never had
    an os.getenv fallback, so its compiled default (10) is the ONLY
    pre-Firestore behaviour.
    """
    return int(_resolve(channel or _current_channel(), KEY_CREDIT_LOW_THRESHOLD))


def clear_cache() -> None:
    """Test-only: drop the TTL cache and last-known-good state so a test
    does not leak state into the next one. Not called by production code.
    """
    _cache.clear()
    _last_known_good.clear()
