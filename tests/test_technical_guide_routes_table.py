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
    """Every path documented by the guide's routes table.

    Parses only the `## Routes / endpoints` section so a path mentioned in
    prose elsewhere (Gotchas, Surface contracts) cannot satisfy the pin.

    Shorthand is resolved PER ROW, never across the table. The table
    abbreviates a repeated prefix within one row ("`/api/editor/kits/{kit_id}/
    schema`, `.../pdf`"), so `...` means "the sibling path in THIS row". An
    earlier version resolved each `...` against every concrete path in the
    whole table, which invented 21 paths that no row documents (e.g.
    `/api/tts/pdf`, `/api/editor/kits/{kit_id}/draft-snapshots/
    {snapshot_id}/pdf`) -- and a genuinely undocumented route matching one of
    those ghosts passed the completeness check silently.
    """
    text = GUIDE.read_text(encoding="utf-8")
    start = text.index("## Routes / endpoints")
    end = text.index("\n## ", start + 1)
    section = text[start:end]

    documented = set()
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        # Cells are `-quoted; a row may carry several ("`/api/x/{id}/schema`,
        # `.../pdf`"). Collect this row's own tokens, in order, so `...`
        # resolves against a sibling from the SAME row.
        row_paths: list[str] = []
        row_shorthand: list[str] = []
        for match in re.findall(r"`([^`]+)`", line):
            token = match.strip()
            if token.startswith("/"):
                row_paths.append(token)
            elif token.startswith("..."):
                row_shorthand.append(token)

        documented.update(row_paths)
        if not row_shorthand:
            continue
        # Resolve against the row's LAST concrete path -- the one the
        # shorthand is abbreviating. A shorthand with no concrete sibling in
        # its row documents nothing (and must not silently expand).
        if not row_paths:
            continue
        base = row_paths[-1]
        for token in row_shorthand:
            suffix = token[3:]  # strip the leading "..." only
            if not suffix.startswith("/"):
                continue  # malformed cell ("`...pdf`") documents nothing
            documented.add(base.rsplit("/", 1)[0] + suffix)
    return documented


def test_every_shipped_route_is_in_the_guide_routes_table():
    """A shipped route missing from the doc table fails HERE, naming itself."""
    shipped = _shipped_routes()
    documented = _documented_routes()

    undocumented = sorted(p for p in shipped if p not in documented)
    assert not undocumented, (
        "routes shipping but absent from docs/technical_guide.md's routes "
        f"table: {undocumented}\n"
        "Add a row (with its owning surface doc), or add it to EXEMPT here "
        "with the reason it is not a documented product surface."
    )


def _table_rows() -> list[str]:
    """The routes table's body rows, in file order."""
    text = GUIDE.read_text(encoding="utf-8")
    start = text.index("## Routes / endpoints")
    end = text.index("\n## ", start + 1)
    lines = text[start:end].split("\n")

    header = next(i for i, l in enumerate(lines) if l.startswith("| Method "))
    body = header + 2  # skip the header and its |---| separator
    rows = []
    while body < len(lines) and lines[body].startswith("|"):
        rows.append(lines[body])
        body += 1
    return rows


def _row_sort_key(row: str) -> tuple[str, str]:
    """(path, method) -- the table's stable order.

    The path is the row's FIRST backticked token, which is the route the row
    is about; later tokens are shorthand siblings or prose.
    """
    cells = row.split("|")
    method = cells[1].strip()
    match = re.search(r"`([^`]+)`", cells[2])
    path = match.group(1).strip() if match else cells[2].strip()
    return (path, method)


def test_guide_routes_table_is_sorted_by_path_then_method():
    """THE COLLISION FIX. Drift is only half the problem this table has -- the
    other half is that 8 of the 11 commits touching the guide in the week to
    2026-08-20 edited this ~20-line region, and parallel PRs collided there.

    A row order that is merely conventional gives a new row no determined
    home, so two parallel PRs pick different insertion points and conflict.
    Sorting by (path, method) gives every row EXACTLY ONE correct position:
    two PRs adding different routes land on different lines, and a reviewer
    can tell where a row belongs without reading the whole table.

    Mutation: swap any two adjacent rows -- red.
    """
    rows = _table_rows()
    assert rows, "routes table body not found -- has the table shape changed?"

    actual = [_row_sort_key(r) for r in rows]
    expected = sorted(actual)
    assert actual == expected, (
        "the routes table is out of order; sort rows by (path, method).\n"
        f"first divergence: {next(a for a, e in zip(actual, expected) if a != e)}"
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
