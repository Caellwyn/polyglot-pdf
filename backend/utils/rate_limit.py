"""Per-instance rate limiter for the unauthenticated write doors (sprint 23
PF-5, bd polyglot-pdf-o2fub; the maintainer's 2026-09-17 decision).

WHAT THIS IS. A token bucket per caller address, per door, held in this
process. `POST /api/links/open`, `POST /api/signup/check` and
`POST /api/disclaimer-acceptance` take it as a dependency. A caller over the
budget is refused with a response BYTE-IDENTICAL to the door's ordinary
refusal (links/open and signup/check are oracle-sensitive: a limited caller
must learn nothing a wrong-token caller would not), or 429 where the door
has no oracle to protect (disclaimer-acceptance).

WHAT THIS IS NOT. Not a network-edge control: the bucket lives in one Cloud
Run instance, resets when the instance is recycled or the service scales,
and a distributed caller spreads around it. It stops the casual guessing
loop and bounds one address's spend; Cloud Armor is the deferred real fix
(the decision table in docs/standards/security-posture.md). The spend
ceiling that pairs with it is `--max-instances` on the Cloud Run deploys.

The caller address is the FIRST hop of X-Forwarded-For (Cloud Run sets it;
`request.client.host` there is the front end's internal address), else the
socket peer locally. The address is the bucket KEY only: the refusal log
line carries the door name and the budget, never the address
(docs/standards/hipaa-pii-policy.md).
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Dict, Tuple

import structlog
from fastapi import HTTPException, Request

from ..config import get_settings

_log = structlog.get_logger().bind(module="rate_limit")

# door -> {address: (tokens, last_refill_monotonic)}
_buckets: Dict[str, Dict[str, Tuple[float, float]]] = {}
_lock = threading.Lock()

# Refuse with the door's own phrase so a limited caller and a wrong-token
# caller are indistinguishable on the oracle-sensitive doors.
NOT_FOUND_LINK = "This link is not valid."
NOT_FOUND = "Not found"
TOO_MANY = "Too many requests"


def client_address(request: Request) -> str:
    """The caller's address as the bucket key (never logged)."""
    forwarded = request.headers.get("x-forwarded-for") or ""
    first = forwarded.split(",")[0].strip()
    if first:
        return first
    client = request.client
    return client.host if client and client.host else "unknown"


def _take(door: str, key: str, budget: int, window_sec: float, now: float) -> bool:
    """One token from the (door, key) bucket; True when the call may proceed.
    Refills continuously at budget/window per second, capped at budget."""
    with _lock:
        per_door = _buckets.setdefault(door, {})
        tokens, last = per_door.get(key, (float(budget), now))
        rate = budget / window_sec if window_sec > 0 else float("inf")
        tokens = min(float(budget), tokens + (now - last) * rate)
        if tokens >= 1.0:
            per_door[key] = (tokens - 1.0, now)
            allowed = True
        else:
            per_door[key] = (tokens, now)
            allowed = False
        # Keep the map bounded: drop keys that have fully refilled and sat
        # idle for a window (they would behave as brand new anyway).
        if len(per_door) > 1024:
            stale = [k for k, (t, l) in per_door.items()
                     if t >= budget - 1e-9 and now - l > window_sec]
            for k in stale:
                per_door.pop(k, None)
        return allowed


def reset() -> None:
    """Tests only: forget every bucket."""
    with _lock:
        _buckets.clear()


def rate_limited(door: str, *, status_code: int, detail: str) -> Callable:
    """A FastAPI dependency: one bucket per caller address on this door.

    `status_code`/`detail` are the refusal, chosen per door so the oracle
    posture of the door is preserved (404 + the door's own phrase) or 429
    where there is no oracle. Reads the settings at call time so a deployed
    override and a test override both apply."""

    async def _dependency(request: Request) -> None:
        settings = get_settings()
        if not settings.RATE_LIMIT_ENABLED:
            return
        budget = int(settings.RATE_LIMIT_BUDGET)
        window = float(settings.RATE_LIMIT_WINDOW_SEC)
        if _take(door, client_address(request), budget, window, time.monotonic()):
            return
        # Counts only -- the address is the key, never a log value.
        _log.warning("rate_limited", door=door, budget=budget, window_sec=window)
        raise HTTPException(status_code=status_code, detail=detail)

    # The access matrix's ungated-door pin finds the dependency by this mark.
    _dependency._rate_limit_door = door  # type: ignore[attr-defined]
    _dependency.__name__ = "rate_limited_" + door
    return _dependency
