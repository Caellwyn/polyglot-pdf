"""HTTP routers for the admin service.

Empty at the skeleton stage (bd polyglot-pdf-pnoik): the first real routers
arrive with the app_admin claim + require_app_admin gate (bd
polyglot-pdf-7w17m). Every route registered here must carry exactly one auth
dependency; that set is pinned by
admin_backend/tests/unit/test_admin_route_auth.py once the gates land.
"""
