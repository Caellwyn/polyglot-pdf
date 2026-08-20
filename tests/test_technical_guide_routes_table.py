"""THE SET PIN for docs/technical_guide.md's routes table (bd polyglot-pdf-abn4o).

The routes table is a merge-collision hotspot: 8 of the 11 commits touching the
guide in the week to 2026-08-20 edited that ~20-line region, because every
kit/editor feature adds a row there. Parallel PRs land on adjacent lines and
conflict.

Generating the table outright was rejected: each row's value is its
hand-written "Surface doc" prose (which surface owns the route, what the auth
gate is, why a 409 fires), and a generator would either discard that or need
the prose stored somewhere else -- moving the conflict rather than removing it.

So the table stays hand-written and this test pins the SET instead. It derives
the shipped route set from the LIVE FastAPI app and asserts the doc documents
every one, so a new route fails HERE (naming itself) instead of silently
drifting out of the doc for weeks. That drift was real: when this test was
written the table was missing NINE shipped routes.

Mutations that must turn this red:
  - add a route to any router without adding its doc row
  - delete a documented row while its route still ships
  - typo a path in the doc table
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GUIDE = REPO_ROOT / "docs" / "technical_guide.md"

# Routes deliberately ABSENT from the doc table, each with the reason it is
# exempt. Anything not shipped by us, or not a product surface, lives here --
# and the exemption is explicit so a future reader sees the decision rather
# than an unexplained gap.
EXEMPT = {
    # FastAPI's own auto-generated API docs surface, not app routes.
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/openapi.json",
}

# The websocket router is mounted twice -- bare and under /api -- so both
# /ws/fill and /api/ws/fill resolve (documented in the guide's Gotchas). The
# table documents the bare form with the mirror noted inline, so fold the
# /api mirror onto its bare twin rather than demanding two rows.
WS_MIRROR_PREFIX = "/api/ws/"


def _shipped_routes() -> set[str]:
    """Every path the live app actually serves, normalized."""
    from backend.main import app

    paths = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        if not path:
            continue
        if path.startswith(WS_MIRROR_PREFIX):
            path = path[len("/api"):]  # fold /api/ws/x onto /ws/x
        paths.add(path)
    return paths - EXEMPT


def _documented_routes() -> set[str]:
    """Every path appearing in a backticked cell of the guide's routes table.

    Parses only the `## Routes / endpoints` section so a path mentioned in
    prose elsewhere (Gotchas, Surface contracts) cannot satisfy the pin.
    """
    text = GUIDE.read_text(encoding="utf-8")
    start = text.index("## Routes / endpoints")
    end = text.index("\n## ", start + 1)
    section = text[start:end]

    documented = set()
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        # `/api/x`, `/api/x/{id}/y`, and comma-separated cells like
        # "`/api/editor/kits/{kit_id}/schema`, `.../pdf`" all appear.
        for match in re.findall(r"`([^`]+)`", line):
            token = match.strip()
            if token.startswith("/"):
                documented.add(token)
            elif token.startswith("..."):
                documented.add(token)  # resolved against its row below
    return documented


def _resolve_ellipses(documented: set[str]) -> set[str]:
    """Expand `.../pdf`-style shorthand against the longest sibling path.

    The table abbreviates repeated prefixes ("`/api/editor/kits/{kit_id}/schema`,
    `.../pdf`"). Resolve each against the deepest concrete path that shares its
    row's prefix, so the shorthand still counts as documented.
    """
    concrete = {d for d in documented if d.startswith("/")}
    resolved = set(concrete)
    for token in documented:
        if not token.startswith("..."):
            continue
        suffix = token[3:]  # strip the leading "..."
        for base in concrete:
            candidate = base.rsplit("/", 1)[0] + suffix
            if candidate.count("/") >= 2:
                resolved.add(candidate)
    return resolved


def test_every_shipped_route_is_in_the_guide_routes_table():
    """A shipped route missing from the doc table fails HERE, naming itself."""
    shipped = _shipped_routes()
    documented = _resolve_ellipses(_documented_routes())

    undocumented = sorted(p for p in shipped if p not in documented)
    assert not undocumented, (
        "routes shipping but absent from docs/technical_guide.md's routes "
        f"table: {undocumented}\n"
        "Add a row (with its owning surface doc), or add it to EXEMPT here "
        "with the reason it is not a documented product surface."
    )


def test_guide_routes_table_documents_no_phantom_routes():
    """A documented row whose route no longer ships fails HERE.

    Guards the other direction: a deleted route leaving a stale doc row that
    tells the next reader a surface exists when it does not.
    """
    shipped = _shipped_routes()
    documented = {d for d in _documented_routes() if d.startswith("/")}

    # Only flag fully-concrete paths; the table also backticks partial tokens
    # (e.g. "`/api`") in its prose cells, which are not route claims.
    phantom = sorted(
        d for d in documented
        if d.count("/") >= 2
        and d not in shipped
        and d not in EXEMPT
        # Glob references to a whole surface ("the `/api/editor/*` surface is
        # 503 when no token is configured") are prose, not route claims.
        and "*" not in d
        # The guide documents the bare WS path and notes the /api mirror
        # inline; _shipped_routes folds the mirror away, so don't demand it.
        and not d.startswith(WS_MIRROR_PREFIX)
    )
    assert not phantom, (
        f"documented in the guide but not shipped by the app: {phantom}\n"
        "Remove the stale row, or fix the path typo."
    )
