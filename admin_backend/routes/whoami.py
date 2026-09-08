"""GET /admin/whoami -- the FIRST real route on the admin service (bd
polyglot-pdf-7w17m).

Deliberately the simplest possible gated route: it exists to prove
require_app_admin end to end (a stamped account passes, an unstamped valid
account 403s with the NO_ADMIN_ACCESS: prefix, a tokenless caller 401s)
before any business logic lands on this service. The admin console's
sign-in screen calls this to confirm the signed-in account actually holds
admin access, the same role /admin/whoami-shaped routes play in other
Firebase-authed apps in this repo.
"""
from fastapi import APIRouter, Depends
from typing import Annotated

from admin_backend.services.admin_auth import AdminActor, require_app_admin

router = APIRouter()


@router.get("/admin/whoami")
async def whoami(
    actor: Annotated[AdminActor, Depends(require_app_admin)],
) -> dict:
    return {"uid": actor.uid, "email": actor.email}
