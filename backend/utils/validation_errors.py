"""A 422 that never echoes the request.

FastAPI's default RequestValidationError handler returns each error's
`input` -- the offending VALUE -- and pydantic's `ctx` alongside `loc`,
`type` and `msg`. On a form-filling app that value is a client's field
answer (an over-long name on /api/fill-pdf, a malformed date on the
disclaimer route), so the default turns every validation failure into a
response that repeats the client's PII to the caller. The caller already
holds that value, but the 422 body also travels through browser devtools,
proxies and any error reporter that captures responses, none of which
should carry it (docs/standards/hipaa-pii-policy.md; sprint 23 PF-3).

Both FastAPI apps install this handler at import (backend/main.py,
admin_backend/main.py); backend/tests/test_no_pii_logging.py posts a
sentinel into a malformed body on each and asserts it is absent from the
response, and pins that `debug` is off on both apps (a debug app renders
tracebacks, with locals, into 500 bodies).
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# The ONLY keys of a pydantic error that reach the response. `input` is the
# client's value; `ctx` can embed it too (a pattern mismatch quotes the
# input); `url` is documentation noise.
_SAFE_ERROR_KEYS = ("loc", "type", "msg")

# `msg` is pydantic's own catalogue text for built-in error types (limits and
# expectations, never the input) -- EXCEPT for a custom validator's
# `raise ValueError(...)` / `assert`, which pydantic renders verbatim as
# "Value error, <text>". Route validators do interpolate the submitted value
# into that text (disclaimer_routes bounds a timestamp with it), so for those
# types the message is replaced by the type's generic phrase rather than
# trusting every validator site in both backends to stay value-free.
_CUSTOM_MESSAGE_TYPES = {"value_error": "Value error", "assertion_error": "Assertion failed"}


def _safe_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for err in exc.errors():
        safe = {k: err[k] for k in _SAFE_ERROR_KEYS if k in err}
        if err.get("type") in _CUSTOM_MESSAGE_TYPES:
            safe["msg"] = _CUSTOM_MESSAGE_TYPES[err["type"]]
        # loc may carry non-JSON-native items (ints for list indexes are
        # fine; anything else is stringified rather than dropped).
        safe["loc"] = [x if isinstance(x, (str, int)) else str(x)
                       for x in (safe.get("loc") or ())]
        out.append(safe)
    return out


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": _safe_errors(exc)})


def install_validation_error_handler(app: FastAPI) -> None:
    """Register the value-free 422 on `app`; idempotent."""
    app.add_exception_handler(RequestValidationError, validation_error_handler)
