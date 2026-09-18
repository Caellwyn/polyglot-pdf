"""Per-instance rate limiter for the unauthenticated write doors (sprint 23
PF-5, bd polyglot-pdf-o2fub; the maintainer's 2026-09-17 decision).

WHAT THIS IS. Token buckets held in this process, taken by
`POST /api/links/open`, `POST /api/signup/check` and
`POST /api/disclaimer-acceptance` as a dependency. A caller over budget is
refused with a response BYTE-IDENTICAL to the door's ordinary refusal
(links/open and signup/check are oracle-sensitive: a limited caller must
learn nothing a wrong-token caller would not), or 429 where the door has no
oracle to protect (disclaimer-acceptance).

THE KEY, and why there are two buckets. `X-Forwarded-For` is a list the
caller can seed: a client may send `X-Forwarded-For: 9.9.9.9` and every
proxy on the way APPENDS the address it saw, so only the hops at the END are
trustworthy -- Cloud Run's front end appends the address that connected to
it; the Firebase Hosting `/api/**` rewrite (the path every browser call
takes in production) appends the browser's address before Hosting's own
egress connects to Cloud Run. So:

  direct call to run.app:   [<anything the caller sent>..., CALLER]
  browser through Hosting:  [<anything the browser sent>..., BROWSER, HOSTING_EGRESS]

The first hop is worthless as a key (a rotating forged value would give an
attacker a fresh bucket per request); the last hop alone would make every
browser user behind one Hosting egress share a bucket. Hence two buckets
per door, both taken from the END of the chain:

  1. the CLIENT bucket, keyed on the SECOND-TO-LAST hop alone (the last
     hop when there is only one): through Hosting that is the browser's
     address as Hosting appended it -- unforgeable by the browser, and
     STABLE while Hosting's egress address changes (measured on staging
     2026-09-18: 48 requests through the rewrite arrived from 48 distinct
     egress addresses, so any key that includes the last hop is fresh on
     every request and never limits browser traffic). On a direct call a
     caller can forge that entry, which is why bucket 2 exists. Budget
     `RATE_LIMIT_BUDGET` per `RATE_LIMIT_WINDOW_SEC`.
  2. the CONNECTION bucket, keyed on the last hop alone -- unforgeable on
     both paths. It is shared by everyone behind one Hosting egress, so its
     budget is wide (`RATE_LIMIT_SHARED_BUDGET`): it is the backstop that
     caps a direct caller who rotates forged hops, and a botnet's aggregate
     through one egress, at that rate per instance.

A request is refused when EITHER bucket is empty; a request the client
bucket refuses does not draw on the connection bucket, so one abuser behind
Hosting cannot drain the shared bucket for everyone (they are held at the
client rate first).

WHAT THIS IS NOT. Not a network-edge control: the buckets live in one Cloud
Run instance, reset when the instance is recycled or the service scales,
and a distributed caller spreads around them. The maintainer accepted that;
Cloud Armor is the deferred real fix (the decision table in
docs/standards/security-posture.md). The spend ceiling that pairs with it
is `--max-instances` on the Cloud Run deploys.

The addresses are bucket KEYS only: the refusal log line carries the door,
which bucket refused and the budget, never an address
(docs/standards/hipaa-pii-policy.md). The per-door maps are bounded
(`MAX_KEYS_PER_DOOR`, oldest key evicted), so a flood of forged hops costs
memory nothing and the lookup stays O(1).
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Callable, Dict, Tuple

import structlog
from fastapi import HTTPException, Request

from ..config import get_settings

_log = structlog.get_logger().bind(module="rate_limit")

# (door, bucket-kind) -> OrderedDict{key: (tokens, last_refill_monotonic)}
_buckets: Dict[Tuple[str, str], "OrderedDict[str, Tuple[float, float]]"] = {}
_lock = threading.Lock()
MAX_KEYS_PER_DOOR = 4096

# Refuse with the door's own phrase so a limited caller and a wrong-token
# caller are indistinguishable on the oracle-sensitive doors.
NOT_FOUND_LINK = "This link is not valid."
NOT_FOUND = "Not found"
TOO_MANY = "Too many requests"


def forwarded_hops(request: Request) -> list:
    """The X-Forwarded-For chain, oldest first, empty entries dropped."""
    forwarded = request.headers.get("x-forwarded-for") or ""
    return [h.strip() for h in forwarded.split(",") if h.strip()]


def client_keys(request: Request) -> Tuple[str, str]:
    """(client_key, connection_key): the second-to-last hop (the last when
    the chain has one), and the last hop. With no forwarded chain (local
    dev) the socket peer is both."""
    hops = forwarded_hops(request)
    if hops:
        last = hops[-1]
        client_key = hops[-2] if len(hops) >= 2 else last
    else:
        client = request.client
        last = client.host if client and client.host else "unknown"
        client_key = last
    return client_key, last


def _take(door: str, kind: str, key: str, budget: int, window_sec: float, now: float) -> bool:
    """One token from the (door, kind, key) bucket; True when the call may
    proceed. Refills continuously at budget/window per second, capped at
    budget. The map is an LRU bounded at MAX_KEYS_PER_DOOR."""
    with _lock:
        per = _buckets.setdefault((door, kind), OrderedDict())
        tokens, last = per.get(key, (float(budget), now))
        rate = budget / window_sec if window_sec > 0 else float("inf")
        tokens = min(float(budget), tokens + (now - last) * rate)
        allowed = tokens >= 1.0
        per[key] = (tokens - 1.0 if allowed else tokens, now)
        per.move_to_end(key)
        while len(per) > MAX_KEYS_PER_DOOR:
            per.popitem(last=False)
        return allowed


def reset() -> None:
    """Tests only: forget every bucket."""
    with _lock:
        _buckets.clear()


def rate_limited(door: str, *, status_code: int, detail: str) -> Callable:
    """A FastAPI dependency: the two buckets above on this door.

    `status_code`/`detail` are the refusal, chosen per door so the oracle
    posture of the door is preserved (404 + the door's own phrase) or 429
    where there is no oracle. Reads the settings at call time so a deployed
    override and a test override both apply."""

    async def _dependency(request: Request) -> None:
        settings = get_settings()
        if not settings.RATE_LIMIT_ENABLED:
            return
        budget = int(settings.RATE_LIMIT_BUDGET)
        shared = int(settings.RATE_LIMIT_SHARED_BUDGET)
        window = float(settings.RATE_LIMIT_WINDOW_SEC)
        client_key, connection_key = client_keys(request)
        hops = len(forwarded_hops(request))
        now = time.monotonic()
        refused_by = None
        # ORDER MATTERS: the client bucket first, and the connection bucket only
        # when the client bucket allowed. A client-refused call must not draw
        # on the shared bucket, or one abuser behind Hosting's egress would
        # drain it for everyone behind it. (A direct caller cannot make its
        # last hop equal that egress, so it cannot reach the shared bucket of
        # real browsers at all.)
        if not _take(door, "client", client_key, budget, window, now):
            refused_by = "client"
        elif not _take(door, "connection", connection_key, shared, window, now):
            refused_by = "connection"
        if refused_by is None:
            return
        # Counts and names only -- the addresses are keys, never log values.
        # hops: the chain LENGTH (a count) -- how the staging burst proves
        # which hop the client key came from.
        _log.warning("rate_limited", door=door, bucket=refused_by,
                     budget=budget if refused_by == "client" else shared,
                     window_sec=window, hops=hops)
        raise HTTPException(status_code=status_code, detail=detail)

    # The access matrix's ungated-door pin finds the dependency by this mark.
    _dependency._rate_limit_door = door  # type: ignore[attr-defined]
    _dependency.__name__ = "rate_limited_" + door
    return _dependency
