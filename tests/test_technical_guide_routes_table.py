"""THE SET PIN for docs/technical_guide.md's routes table (bd polyglot-pdf-abn4o).

The routes table is a merge-collision hotspot: 7 of the 12 commits touching the
guide in the week to 2026-08-20 edited that ~20-line region, because every
kit/editor feature adds a row there. Parallel PRs land on adjacent lines and
conflict.

Generating the table outright was rejected: each row's value is its
hand-written "Surface doc" prose (which surface owns the route, what the auth
gate is, why a 409 fires), and a generator would either discard that or need
the prose stored somewhere else -- moving the conflict rather than removing it.

So the table stays hand-written and this test pins the SET instead. It derives
the shipped set of (path, METHOD) pairs from EVERY LIVE FastAPI app the image
ships and asserts the doc documents every one, so a new route -- or a new
method on an already-listed path -- fails HERE (naming itself) instead of
silently drifting out of the doc for weeks. That drift was real: when this test
was written the table was missing NINE shipped routes, and it recurred the day
a SECOND app landed (bd polyglot-pdf-pnoik) because the gate derived its set
from `backend.main` alone -- so the admin service's routes were not
under-covered but invisible, with this file green.

Each app therefore owns its own table section and every check below is
parametrized over `_APPS`. That per-app key is load-bearing, not tidiness: both
apps declare `/health` and `/version`, so a single (path, method) key would let
each app's rows satisfy the other's pin. And because `_APPS` is itself
hand-listed -- the exact shape that caused the recurrence -- the REQUIRED set
is derived from the Dockerfile's `COPY <pkg> /app/<pkg>` lines.

Mutations that must turn this red:
  - add a route to any router without adding its doc row
  - add a new METHOD on an already-documented path without its own row
  - delete a documented row while its route still ships
  - typo a path in the doc table
  - ship a second ASGI app without adding it to _APPS with a table
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GUIDE = REPO_ROOT / "docs" / "technical_guide.md"
DOCKERFILE = REPO_ROOT / "Dockerfile"

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


# The DEPLOYED ASGI apps, each with the guide section documenting it. The repo
# ships ONE image serving either app depending on the runtime APP_MODULE env
# var (bd polyglot-pdf-pnoik), so "the routes this repo ships" is no longer
# backend.main's routes alone.
#
# Deriving from `backend.main` alone was the bug this vocabulary fixes: the
# admin service's /health and /version were invisible to the whole gate below,
# which is the same hand-scoped-vocabulary trap that _DEPLOYED_PACKAGES in
# test_runtime_paths_are_cwd_independent.py exists to close (CLAUDE.md scar
# #8). Both apps declare /health and /version with DIFFERENT bodies, so the
# key must carry the app -- a (path, method) key alone would let the admin
# rows be "documented" by the public backend's rows and vice versa.
#
# Each entry is (import path of the app module, the guide's `##` heading that
# holds that app's table). test_every_deployed_app_has_its_own_routes_table
# below derives the required set from the Dockerfile so a THIRD app cannot ship
# without being added here, with a table of its own.
_APPS = (
    ("backend.main", "## Routes / endpoints"),
    ("admin_backend.main", "## Admin service routes"),
)


def _shipped_routes(app_module: str = "backend.main") -> set[tuple[str, str]]:
    """Every (path, method) pair the named app actually serves, normalized.

    Keyed on the METHOD too, not the path alone. Three paths in this table
    already ship two methods each (`/api/editor/kits` GET+POST,
    `.../{kit_id}/lock` POST+DELETE, `.../{kit_id}/schema` GET+PUT) and each
    needed its own hand-written row -- so a path-only key would let a NEW
    method on an already-documented path ship undocumented with the suite
    green, which is the exact drift this gate exists to stop.
    """
    import importlib

    app = importlib.import_module(app_module).app

    shipped = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        if not path:
            continue
        if path.startswith(WS_MIRROR_PREFIX):
            path = path[len("/api"):]  # fold /api/ws/x onto /ws/x
        if path in EXEMPT:
            continue
        # A websocket route has no .methods; the table spells those "WS".
        methods = getattr(route, "methods", None) or {"WS"}
        for method in methods:
            # HEAD is auto-added alongside GET by Starlette, and OPTIONS by
            # CORS handling -- neither is a hand-declared product surface, so
            # neither earns a row. Verified: no route in this app declares
            # OPTIONS at all, and HEAD appears only on the four
            # FastAPI-generated doc endpoints already in EXEMPT. If a genuine
            # OPTIONS surface is ever added deliberately, it will be hidden by
            # this skip -- drop it from the tuple then.
            if method in ("HEAD", "OPTIONS"):
                continue
            shipped.add((path, method))
    return shipped


def _table_rows(heading: str = "## Routes / endpoints") -> list[str]:
    """One app's routes-table body rows, in file order.

    The single place the table's location is decided; every check below reads
    the table through this, so none of them can disagree about which lines
    are rows. Parameterized by the section heading because each deployed app
    owns its OWN table -- both apps serve /health and /version, so a single
    merged table could not say which service a row describes.
    """
    text = GUIDE.read_text(encoding="utf-8")
    assert heading in text, (
        "docs/technical_guide.md has no {!r} section, so the app it documents "
        "has no routes table at all".format(heading))
    start = text.index(heading)
    end = text.index("\n## ", start + 1)
    lines = text[start:end].split("\n")

    header = next(i for i, l in enumerate(lines) if l.startswith("| Method "))
    body = header + 2  # skip the header and its |---| separator
    rows = []
    while body < len(lines) and lines[body].startswith("|"):
        rows.append(lines[body])
        body += 1
    return rows


def _parse_row(line: str) -> tuple[str, str]:
    """One table row -> (method cell, path cell). Raises on a row it cannot
    parse -- never returns a silently-wrong column.

    THE RECURRING BUG THIS EXISTS TO END. Successive versions of this parser
    drew a doc claim from text that was not the row's route claim: shorthand
    resolved across the WHOLE TABLE (inventing 21 ghost paths), then a
    WHOLE-ROW scan catching paths name-dropped in descriptions ("the `/status`
    promotion gate"), then a hardcoded `cells[2]` that a literal `|` before
    the Path column shifts -- the table already uses an escaped `\\|` in one
    description -- leaving `cells[2]` holding "ST" instead of a path while the
    row silently documents NOTHING.

    All of them share one shape: the evidence region stopped matching the
    claim, and the checker stayed GREEN while checking less than it claimed.
    The structural fix is not a fourth filter -- it is refusing to guess.
    Every consumer reads rows through this function, so a row whose columns
    cannot be located fails LOUDLY instead of quietly contributing nothing.

    What this deliberately does NOT do: it locates the columns, it does not
    judge their content. A hand-crafted row carrying a backticked
    path-shaped DECOY ahead of the real path (6+ cells, bare-alpha method, no
    unescaped pipe) would parse to the decoy. No such row exists, and no
    purely positional parser can rule that out -- ruling it out needs a
    semantic check, which is a different tool. Recorded so the next reader
    does not re-derive it.
    """
    cells = line.split("|")
    # A well-formed row is: "" | method | path | description | "" -> 5 cells.
    # More cells means a literal `|` inside some cell; only an escaped `\|`
    # AFTER the path column is safe, because it cannot shift the path left.
    if len(cells) < 5:
        raise AssertionError(f"routes-table row has too few columns: {line!r}")
    method, path_cell = cells[1].strip(), cells[2]
    if "\\" in cells[1] or not method.isalpha():
        raise AssertionError(
            f"routes-table Method cell is not a bare verb ({method!r}) -- an "
            f"escaped pipe here would shift the Path column: {line!r}"
        )
    if not re.search(r"`\s*(?:/|\.\.\.)", path_cell):
        raise AssertionError(
            f"routes-table row has no backticked path in its Path column "
            f"(column shift? unparseable row?): {line!r}"
        )
    return method, path_cell


def _documented_routes(
        heading: str = "## Routes / endpoints") -> set[tuple[str, str]]:
    """Every (path, method) pair documented by ONE app's routes table.

    Keyed on the method too, matching _shipped_routes -- a row documents its
    own verb, not every verb on that path.

    Parses only the named section so a path mentioned in prose elsewhere
    (Gotchas, Surface contracts) cannot satisfy the pin, and only the Path
    COLUMN of each row, so a path name-dropped in a description ("the
    `/status` promotion gate", "no `/api` prefix") cannot either. Scoping to
    ONE section is also what keeps the two apps' identically-named /health and
    /version rows from cross-satisfying each other's pin.

    Shorthand is resolved PER ROW, never across the table. The table
    abbreviates a repeated prefix within one row ("`/api/editor/kits/{kit_id}/
    schema`, `.../pdf`"), so `...` means "the sibling path in THIS row".
    """
    documented = set()
    for line in _table_rows(heading):
        method, path_cell = _parse_row(line)

        # A row may carry several path tokens ("`/api/x/{id}/schema`,
        # `.../pdf`"). Collect this row's own, in order, so `...` resolves
        # against a sibling from the SAME row.
        row_paths: list[str] = []
        row_shorthand: list[str] = []
        for match in re.findall(r"`([^`]+)`", path_cell):
            token = match.strip()
            if token.startswith("/"):
                row_paths.append(token)
            elif token.startswith("..."):
                row_shorthand.append(token)

        documented.update((p, method) for p in row_paths)
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
            documented.add((base.rsplit("/", 1)[0] + suffix, method))
    return documented


@pytest.mark.parametrize("app_module,heading", _APPS)
def test_every_routes_table_row_parses_unambiguously(app_module, heading):
    """PINS THE CLASS, not another instance.

    Three rounds of review found three versions of one bug: the parser drew a
    doc claim from text that was not the row's route claim (shorthand resolved
    across the whole table; a whole-row scan catching prose; a shifted column).
    Every one stayed GREEN -- the checker kept passing while quietly checking
    less than it claimed.

    Fixing a fourth instance would repeat the pattern, so this asserts the
    property all three violated: every row must parse into locatable columns
    with a real path in the Path column. A row that does not -- because a
    literal `|` shifted the columns, or the table's shape changed -- fails
    HERE, loudly, instead of silently contributing nothing to the other checks.

    Mutation: put an escaped `\\|` in any row's Method cell -- red.
    """
    rows = _table_rows(heading)
    assert rows, "routes table body not found -- has the table shape changed?"

    for row in rows:
        _parse_row(row)  # raises AssertionError naming the offending row

    # Every row must also yield a sort key and at least one documented path,
    # so no row can be present yet invisible to the checks below.
    assert len({_row_sort_key(r) for r in rows}) == len(rows), (
        "two routes-table rows share a (path, method) key -- a duplicate row?"
    )


@pytest.mark.parametrize("app_module,heading", _APPS)
def test_every_shipped_route_is_in_the_guide_routes_table(app_module, heading):
    """A shipped route missing from the doc table fails HERE, naming itself."""
    shipped = _shipped_routes(app_module)
    documented = _documented_routes(heading)

    undocumented = sorted(
        f"{method} {path}" for path, method in shipped - documented
    )
    assert not undocumented, (
        "routes shipping but absent from docs/technical_guide.md's routes "
        f"table: {undocumented}\n"
        "Add a row (with its owning surface doc), or add it to EXEMPT here "
        "with the reason it is not a documented product surface. NOTE a new "
        "METHOD on an already-documented path needs its OWN row."
    )


def test_every_deployed_app_has_its_own_routes_table():
    """_APPS is hand-listed, so it needs its own derived pin.

    Every check above is parametrized over _APPS, which means a deployed app
    MISSING from that tuple is not under-tested -- it is untested, silently,
    with the whole file green. That is precisely how the admin service's
    /health and /version shipped undocumented: the gate derived its route set
    from `backend.main` alone and had no way to notice a second app existed.
    Fixing that by adding one more hand-written entry would leave the same
    trap armed for the third app, so the REQUIRED set is derived from the
    Dockerfile -- the file that decides which packages are in the image at all
    (CLAUDE.md scar #8).

    The Dockerfile's `COPY <pkg> /app/<pkg>` lines are the ground truth: a
    package it does not copy cannot serve anything, and one it does copy is a
    candidate ASGI target for the runtime APP_MODULE env var.

    Mutation: drop the admin_backend entry from _APPS -- red.
    """
    text = DOCKERFILE.read_text(encoding="utf-8")
    copied = set(re.findall(r"^COPY\s+(\w+)\s+/app/\1\s*$", text, re.MULTILINE))
    assert copied, "no `COPY <pkg> /app/<pkg>` lines found in the Dockerfile"

    # Only packages that actually expose an ASGI `app` are servable; a package
    # copied purely as a library (none today) is not a routes-table candidate.
    import importlib

    servable = set()
    for pkg in copied:
        module = pkg + ".main"
        try:
            servable.add(module) if hasattr(
                importlib.import_module(module), "app") else None
        except ModuleNotFoundError:
            continue

    covered = {app_module for app_module, _ in _APPS}
    missing = sorted(servable - covered)
    assert not missing, (
        "these ASGI apps ship in the image but are NOT in _APPS, so none of "
        "the checks in this file inspect them and their routes can ship "
        "undocumented:\n  " + "\n  ".join(missing))

    # And no dead entries: a stale _APPS row would parametrize every check
    # against an app that no longer ships, failing confusingly.
    dead = sorted(covered - servable)
    assert not dead, (
        "_APPS names apps that the Dockerfile does not ship: " + repr(dead))


def _row_sort_key(row: str) -> tuple[str, str]:
    """(path, method) -- the table's stable order.

    The path is the Path column's FIRST backticked token, which is the route
    the row is about; later tokens are shorthand siblings. Shares _parse_row
    with the completeness check so both agree on where the columns are.
    """
    method, path_cell = _parse_row(row)
    match = re.search(r"`([^`]+)`", path_cell)
    path = match.group(1).strip() if match else path_cell.strip()
    return (path, method)


@pytest.mark.parametrize("app_module,heading", _APPS)
def test_guide_routes_table_is_sorted_by_path_then_method(app_module, heading):
    """THE COLLISION FIX. Drift is only half the problem this table has -- the
    other half is that 7 of the 12 commits touching the guide in the week to
    2026-08-20 edited this ~20-line region, and parallel PRs collided there.

    A row order that is merely conventional gives a new row no determined
    home, so two parallel PRs pick different insertion points and conflict.
    Sorting by (path, method) gives every row EXACTLY ONE correct position:
    two PRs adding different routes land on different lines, and a reviewer
    can tell where a row belongs without reading the whole table.

    Mutation: swap any two adjacent rows -- red.
    """
    rows = _table_rows(heading)
    assert rows, "routes table body not found -- has the table shape changed?"

    actual = [_row_sort_key(r) for r in rows]
    expected = sorted(actual)
    assert actual == expected, (
        "the routes table is out of order; sort rows by (path, method).\n"
        f"first divergence: {next(a for a, e in zip(actual, expected) if a != e)}"
    )


@pytest.mark.parametrize("app_module,heading", _APPS)
def test_guide_routes_table_documents_no_phantom_routes(app_module, heading):
    """A documented row whose route no longer ships fails HERE.

    Guards the other direction: a deleted route leaving a stale doc row that
    tells the next reader a surface exists when it does not.
    """
    shipped = _shipped_routes(app_module)
    documented = _documented_routes(heading)

    phantom = sorted(
        f"{method} {path}"
        for path, method in documented - shipped
        if path not in EXEMPT
        # The guide documents the bare WS path and notes the /api mirror
        # inline ("`/ws/fill` (+ `/api/ws/fill`)"); _shipped_routes folds the
        # mirror away, so the mirror is a real doc claim, not a phantom.
        and not path.startswith(WS_MIRROR_PREFIX)
    )
    assert not phantom, (
        f"documented in the guide but not shipped by the app: {phantom}\n"
        "Remove the stale row, or fix the path/method typo."
    )
