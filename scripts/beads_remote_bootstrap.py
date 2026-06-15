#!/usr/bin/env python3
"""Hydrate the beads (Dolt) issue database in a fresh remote/ephemeral container.

Why this exists
---------------
Claude Code on the web (and any ephemeral remote session) starts in a freshly
cloned container. The *code* is cloned, but the beads database is **not**: it
lives in the Dolt ref ``refs/dolt/data`` (a repo-level ref, not a branch), which
a normal ``git clone`` does not materialise. Worse, the generic ``bd prime`` hook
prints "No git remote configured -- issues are saved locally only", which is
flatly wrong for this repo: the store syncs through ``refs/dolt/data`` over the
same authenticated git origin the code came from.

Two things then block a naive ``bd bootstrap`` in a remote container:

1. **Credentials.** ``sync.remote`` in ``.beads/config.yaml`` points at the
   public ``github.com`` URL, so ``bd bootstrap`` attempts a *Dolt-native* clone
   of github.com -- which has no credentials in the sandbox and fails. Git here
   only works through the session's authenticated local proxy origin
   (``git+http://local_proxy@127.0.0.1:<port>/...``). Neutralising ``sync.remote``
   makes ``bd bootstrap`` fall back to cloning over that git origin, which works.

2. **The dolt-ignored local tables.** ``wisps`` / ``wisp_*``, ``local_metadata``,
   and ``repo_mtimes`` are registered in ``dolt_ignore`` (so per-clone local state
   never causes merge conflicts), which also means they are absent from
   ``refs/dolt/data`` and never arrive on a fresh clone. Older bd ABORTED on open
   when ``wisps`` was missing (migration ``0047_recompute_mixed_is_blocked``
   references it -> "table not found: wisps"), so the clone could not open at all.
   The CURRENT bd is harder to diagnose: the fresh clone OPENS and serves every
   READ without these tables, but any WRITE that recomputes is_blocked
   (``bd import``/``create``/``close``, and so ``/closeout``) dies with
   "table not found: wisps", and ``bd create``/``migrate`` die on the missing
   ``local_metadata``. So "does bd open?" (reads) is NOT a sufficient signal -- the
   repair is gated on the tables themselves. (Long-lived local checkouts never hit
   this because they only ever *pull* into a DB that already has these local tables;
   only a fresh clone trips it.)

This script makes a remote session self-heal: clone over the proxy, then recreate
every MISSING dolt-ignored local table (with the *exact* schema of whatever bd
version is installed -- extracted from a throwaway ``bd init`` -- so there is no
hand-written DDL to rot), gated on the tables' actual presence rather than on
whether bd opens. It is idempotent: if all the local tables are already present,
it does nothing.

It NEVER pushes. The recreated local tables and the forward-migration commits are
local to this ephemeral clone. NB: a remote session runs bd ``@latest`` (a newer
schema than the maintainer's level-40 canonical), so the first ``bd dolt push``
from a remote session (e.g. via ``/closeout``) will bump the canonical schema --
keep the local ``bd`` upgraded to match. See
``docs/components/beads-remote-bootstrap.md``.

Usage
-----
    python scripts/beads_remote_bootstrap.py            # hydrate + repair
    python scripts/beads_remote_bootstrap.py --verbose  # show every sub-step

Exit codes: 0 = bd can open the database (already or after repair); 1 = failed.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG = REPO_ROOT / ".beads" / "config.yaml"
# Cache the fetched dolt CLI here so repeated runs in one container are cheap.
DOLT_CACHE = REPO_ROOT / ".beads" / ".cache"
# Per-container marker, written ONLY after a successful hydrate from refs/dolt/data.
# Its presence -- not a mere issue count -- is the authoritative "this container
# holds the live store" signal: a stale committed .beads/issues.jsonl can make bd
# report a populated-but-outdated store, which would otherwise fool the idempotency
# check (and the bd_prime banner) into thinking all is well. See main().
HYDRATION_MARKER = DOLT_CACHE / ".hydrated"
DOLT_RELEASE = "https://github.com/dolthub/dolt/releases/latest/download/{asset}.tar.gz"

VERBOSE = False

# Secret values (e.g. BEADS_GITHUB_TOKEN) that must never appear in output.
# Every log/vlog line is filtered through _mask(); run() echoes command lines
# through vlog, so a token embedded in a remote URL is masked there too.
_SECRET_VALUES: list[str] = []


def _mask(msg: str) -> str:
    for secret in _SECRET_VALUES:
        if secret:
            msg = msg.replace(secret, "***")
    return msg


def log(msg: str) -> None:
    print(f"[beads-bootstrap] {_mask(msg)}", flush=True)


def vlog(msg: str) -> None:
    if VERBOSE:
        print(f"[beads-bootstrap]   {_mask(msg)}", flush=True)


# CREATE_NO_WINDOW on Windows suppresses the console-window storm a bd dolt /
# dolt / git conjoin spawns (bd polyglot-pdf-5k32). No-op off Windows. Inlined
# here (rather than importing swarm_config) so the bootstrap stays standalone --
# it can run before scripts/ is importable. A caller's explicit creationflags in
# **kw wins (setdefault, not override).
_WINDOWLESS_FLAGS = (
    getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
)


def run(cmd, cwd=None, check=False, capture=True, timeout=300, **kw):
    """Thin subprocess wrapper. Returns CompletedProcess; never raises on
    non-zero unless check=True."""
    vlog("$ " + " ".join(str(c) for c in cmd) + (f"   (cwd={cwd})" if cwd else ""))
    kw.setdefault("creationflags", _WINDOWLESS_FLAGS)
    return subprocess.run(
        cmd, cwd=cwd, check=check,
        capture_output=capture, text=True, timeout=timeout, **kw
    )


# --------------------------------------------------------------------------- #
# hydration state                                                             #
# --------------------------------------------------------------------------- #
def bd_total_issues() -> int | None:
    """``summary.total_issues`` from ``bd stats --json``, or None if bd cannot
    open the database at all (fresh / wisp-wedged)."""
    try:
        p = run(["bd", "stats", "--json"], cwd=REPO_ROOT, timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if p.returncode != 0 or not (p.stdout or "").strip():
        return None
    try:
        return int(json.loads(p.stdout)["summary"]["total_issues"])
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


def is_hydrated() -> bool:
    """Hydrated == bd opens AND the store is populated. The crucial AND: a fresh
    ``bd prime`` (run by the SessionStart hook) auto-creates an *empty* but
    perfectly-openable DB, so "does bd open?" alone is a false positive that would
    leave the session pointed at an empty tracker."""
    n = bd_total_issues()
    return n is not None and n > 0


def wipe_local_db() -> None:
    """Remove any local (empty/partial/auto-created/stale-JSONL) embedded DB so
    ``bd bootstrap`` clones a clean copy. Only the gitignored, ephemeral data dir
    is touched."""
    for cand in (".beads/embeddeddolt", ".beads/dolt"):
        d = REPO_ROOT / cand
        if d.is_dir():
            vlog(f"removing stale local db dir: {d}")
            shutil.rmtree(d, ignore_errors=True)


def is_remote_container() -> bool:
    """True in an ephemeral remote/web container, detected by the authenticated
    local-proxy git origin's ``local_proxy@`` username marker. In that case the
    committed ``.beads/issues.jsonl`` is never authoritative -- the live store
    must come from ``refs/dolt/data`` -- and the destructive wipe-and-clone
    below is safe (the container is disposable)."""
    try:
        p = run(["git", "remote", "get-url", "origin"], cwd=REPO_ROOT, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return "local_proxy@" in (p.stdout or "")


def mark_hydrated(live_ref: str | None = None) -> None:
    """Record that this container now holds the live store (hydrated from the ref).
    Stamp the canonical ``refs/dolt/data`` commit it was verified against, so
    freshness is checkable, not inferred from an issue count (bd polyglot-pdf-j47)."""
    HYDRATION_MARKER.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    ref = f" (refs/dolt/data {live_ref})" if live_ref else ""
    HYDRATION_MARKER.write_text(
        f"hydrated from refs/dolt/data at {stamp}{ref}\n", encoding="utf-8")


def refresh_remote_and_pull() -> bool:
    """Re-point the dolt ``origin`` remote at the CURRENT proxy git origin, then pull
    the freshest canonical state. Cheap; meant to run every session.

    Why re-point every time: the authenticated proxy origin's **port rotates** each
    session (and the whole filesystem -- including the dolt remote and the hydration
    marker -- is snapshot-cached), so a remote URL baked into the snapshot points at
    a dead port. We rewrite it from the live ``git remote get-url origin`` before
    pulling. Remote-container only; a local checkout's dolt remote is already right."""
    if not repoint_dolt_remote_to_proxy():
        return False
    # Plain git reliably lands refs/dolt/data over the proxy even when bd's
    # dolt-native pull stalls -- do it first so a reconcile always has the ref.
    _git_fetch_dolt_ref()
    ok, msg = bd_dolt_pull()
    if ok:
        vlog("pull complete")
        return True
    # A container hydrated BEFORE the bd polyglot-pdf-0q8 fix is frozen on a stale
    # JSONL seed whose history is unrelated to the ref, so the pull's merge aborts
    # with "no common ancestor". The fetch above still landed the ref into
    # origin/main, so self-heal by resetting the working branch onto it.
    if "no common ancestor" in msg or "diverged" in msg:
        log("local store diverged from the ref (pre-0q8 stale-seed bug); reconciling ...")
        dolt = ensure_dolt()
        if dolt:
            try:
                if reconcile_working_branch_onto_ref(dolt):
                    ok2, _ = bd_dolt_pull()
                    log("reconciled onto the canonical ref"
                        + ("; pull complete." if ok2
                           else "; post-reconcile pull failed (may be behind live)."))
                    return ok2  # only claim 'refreshed' if the re-pull confirmed it
            except Exception as e:  # noqa: BLE001
                vlog(f"reconcile failed: {e}")
        else:
            vlog("no dolt CLI available to reconcile the diverged store")
    vlog("pull failed: " + (msg[-300:]))
    return False


# --------------------------------------------------------------------------- #
# dolt CLI acquisition (only needed for the wisp repair)                       #
# --------------------------------------------------------------------------- #
def _platform_asset() -> str:
    sysname = platform.system().lower()        # linux / darwin / windows
    machine = platform.machine().lower()
    arch = {"x86_64": "amd64", "amd64": "amd64",
            "aarch64": "arm64", "arm64": "arm64"}.get(machine, "amd64")
    osname = {"linux": "linux", "darwin": "darwin", "windows": "windows"}.get(sysname, "linux")
    return f"dolt-{osname}-{arch}"


def ensure_dolt() -> str | None:
    """Return a path to a usable ``dolt`` binary, or None if none can be obtained.

    Order: PATH -> previously cached download -> download latest release ->
    ``go install``. The container has no ``dolt`` by default, so download is the
    normal path; the others are fallbacks for stricter network policies.
    """
    onpath = shutil.which("dolt")
    if onpath:
        vlog(f"dolt on PATH: {onpath}")
        return onpath

    asset = _platform_asset()
    cached = DOLT_CACHE / asset / "bin" / "dolt"
    if cached.exists():
        vlog(f"dolt cached: {cached}")
        return str(cached)

    # Download the latest release tarball.
    DOLT_CACHE.mkdir(parents=True, exist_ok=True)
    url = DOLT_RELEASE.format(asset=asset)
    try:
        log(f"fetching dolt CLI ({asset}) ...")
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tf:
            with urllib.request.urlopen(url, timeout=120) as resp:
                shutil.copyfileobj(resp, tf)
            tarball = tf.name
        try:
            with tarfile.open(tarball) as t:
                t.extractall(DOLT_CACHE)
        finally:
            if os.path.exists(tarball):
                os.unlink(tarball)
        if cached.exists():
            cached.chmod(0o755)
            return str(cached)
        vlog("download extracted but binary not at expected path")
    except Exception as e:  # noqa: BLE001 -- fall through to go install
        vlog(f"download failed: {e}")

    # Fallback: build via the Go toolchain (same proxy that installed bd).
    if shutil.which("go"):
        try:
            log("download unavailable; building dolt via 'go install' (slow) ...")
            env = dict(os.environ, GOBIN=str(DOLT_CACHE / "gobin"))
            run(["go", "install", "github.com/dolthub/dolt/go/cmd/dolt@latest"],
                env=env, timeout=600, check=True)
            built = DOLT_CACHE / "gobin" / "dolt"
            if built.exists():
                return str(built)
        except Exception as e:  # noqa: BLE001
            vlog(f"go install failed: {e}")

    return None


# --------------------------------------------------------------------------- #
# clone over the authenticated proxy origin                                   #
# --------------------------------------------------------------------------- #
def hydrate_via_proxy() -> None:
    """Run ``bd bootstrap`` with ``sync.remote`` neutralised so it clones over the
    authenticated git origin (the proxy) instead of the credential-less github URL.
    Restores config.yaml exactly afterwards."""
    original = CONFIG.read_text(encoding="utf-8")
    try:
        patched = re.sub(
            r"^sync\.remote:.*$",
            "# sync.remote neutralised by beads_remote_bootstrap.py (restored below)",
            original, flags=re.M,
        )
        CONFIG.write_text(patched, encoding="utf-8")
        log("cloning beads store over authenticated git origin ...")
        p = run(["bd", "bootstrap", "--yes"], cwd=REPO_ROOT, timeout=600)
        vlog((p.stdout or "").strip()[-500:])
        if p.stderr.strip():
            vlog("stderr: " + p.stderr.strip()[-500:])
    finally:
        CONFIG.write_text(original, encoding="utf-8")
        vlog("restored .beads/config.yaml")


# --------------------------------------------------------------------------- #
# wisp-table repair                                                           #
# --------------------------------------------------------------------------- #
def _dolt_db_dir(data_dir: Path) -> Path | None:
    """Locate the Dolt database dir (the one containing ``.dolt``) under data_dir."""
    for d in sorted(data_dir.glob("*")):
        if (d / ".dolt").is_dir():
            return d
    return None


def _data_dir_from_config() -> Path:
    text = CONFIG.read_text(encoding="utf-8") if CONFIG.exists() else ""
    m = re.search(r"^\s*data-dir:\s*(\S+)", text, flags=re.M)
    if m:
        p = Path(m.group(1))
        return p if p.is_absolute() else (REPO_ROOT / p)
    # Defaults: bd uses .beads/dolt, but embedded mode here uses .beads/embeddeddolt.
    for cand in (".beads/embeddeddolt", ".beads/dolt"):
        if (REPO_ROOT / cand).is_dir():
            return REPO_ROOT / cand
    return REPO_ROOT / ".beads" / "dolt"


def _ignored_tables_need_repair(dolt: str | None) -> bool | None:
    """Whether the clone is missing any dolt-IGNORED local table -- the WRITE-path
    gate. Returns True if at least one ``dolt_ignore`` pattern matches NO table in
    the clone, False if every pattern matches at least one, or None if it cannot be
    determined (no dolt CLI / query failure -- callers treat None conservatively and
    attempt the idempotent repair anyway).

    Why this exists: ``bd stats`` and every READ work without these tables, so
    ``is_hydrated()`` (reads OK) does NOT imply a usable store. ``wisps`` is needed
    by the is_blocked recompute on every WRITE (import/create/close/update, and so
    /closeout); ``local_metadata`` by ``bd create``/``bd migrate``. So the repair
    must be gated on the TABLES, not on whether bd opens (bd polyglot-pdf-080y)."""
    if dolt is None:
        return None
    clone_db = _dolt_db_dir(_data_dir_from_config())
    if clone_db is None:
        return None

    def q(sql: str):
        try:
            p = run([dolt, "sql", "-r", "json", "-q", sql], cwd=clone_db, timeout=60)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        out = (p.stdout or "").strip()
        try:
            return json.loads(out).get("rows", []) if out else []
        except (ValueError, json.JSONDecodeError):
            return None

    pats = q("SELECT pattern FROM dolt_ignore WHERE ignored = 1")
    if not pats:
        # None (query failed) OR [] (no ignored patterns -- unexpected: dolt_ignore
        # should always carry the beads local-table patterns). Treat both as
        # undeterminable so the caller attempts the idempotent repair rather than
        # skipping it on a false "all present" (bd polyglot-pdf-080y, fresh-eyes).
        return None
    for r in pats:
        pattern = list(r.values())[0]
        rows = q(f"SHOW TABLES LIKE '{pattern}'")
        if rows is None:
            return None
        if len(rows) == 0:
            return True  # this ignore pattern matches no table in the clone
    return False


def repair_ignored_tables(dolt: str) -> None:
    """Recreate the dolt-IGNORED local tables (``wisps`` / ``wisp_*``,
    ``local_metadata``, ``repo_mtimes``, ...) that a fresh clone lacks, using the
    exact schema of the installed bd version (sourced from a throwaway ``bd init``).

    These tables are registered in ``dolt_ignore`` (so per-clone local state never
    causes merge conflicts), which also means they are ABSENT from ``refs/dolt/data``
    and never arrive on a clone. bd is meant to create them lazily but does not
    before they are needed -- ``wisps`` by the is_blocked recompute on every write,
    ``local_metadata`` by tip-tracking and ``bd migrate``. We recreate EVERY missing
    ignored table, not just the wisp ones: an earlier version repaired only
    ``wisp%`` and left ``local_metadata`` broken, so ``bd create``/``migrate`` still
    failed (bd polyglot-pdf-080y). Idempotent (``CREATE TABLE IF NOT EXISTS``);
    local-only (never pushed -- these tables are dolt-ignored)."""
    clone_db = _dolt_db_dir(_data_dir_from_config())
    if clone_db is None:
        raise RuntimeError("could not locate the cloned Dolt database directory")
    vlog(f"clone db: {clone_db}")

    with tempfile.TemporaryDirectory(prefix="bd-ignored-src-") as tmp:
        # 1) A throwaway bd db at the installed version -- carries every dolt-ignored
        #    local table at the correct (current) schema.
        log("sourcing dolt-ignored table schema from a throwaway 'bd init' ...")
        run(["bd", "init", "--prefix", "wispsrc"], cwd=tmp, timeout=120)
        src_db = _dolt_db_dir(Path(tmp) / ".beads" / "embeddeddolt") \
            or _dolt_db_dir(Path(tmp) / ".beads" / "dolt")
        if src_db is None:
            raise RuntimeError("throwaway bd init produced no Dolt database")

        def q(db: Path, sql: str):
            p = run([dolt, "sql", "-r", "json", "-q", sql], cwd=db, timeout=120)
            out = (p.stdout or "").strip()
            return json.loads(out).get("rows", []) if out else []

        # 2) Expand the dolt_ignore patterns (some are globs, e.g. 'wisp_%') against
        #    the throwaway source -- that is the set of local tables a clone SHOULD
        #    carry -- then keep only the ones actually MISSING from this clone. Read
        #    the patterns from the clone (it always has dolt_ignore); read the real
        #    table names + DDL from the source.
        patterns = [list(r.values())[0]
                    for r in q(clone_db, "SELECT pattern FROM dolt_ignore WHERE ignored = 1")]
        want: list[str] = []
        for pattern in patterns:
            for r in q(src_db, f"SHOW TABLES LIKE '{pattern}'"):
                t = list(r.values())[0]
                if t not in want:
                    want.append(t)
        if "wisps" not in want:
            raise RuntimeError("throwaway db has no 'wisps' table -- bd internals changed?")
        have = {list(r.values())[0] for r in q(clone_db, "SHOW TABLES")}
        missing = [t for t in want if t not in have]
        if not missing:
            vlog("all dolt-ignored tables already present in the clone")
            return
        # wisps before wisp_* (the others FK to it); FK checks are off anyway.
        missing.sort(key=lambda t: (t != "wisps", t))
        vlog(f"recreating dolt-ignored tables: {missing}")

        # 3) Copy each missing table's CREATE statement.
        ddl = ["SET FOREIGN_KEY_CHECKS=0;"]
        for t in missing:
            create_rows = q(src_db, f"SHOW CREATE TABLE `{t}`")
            if not create_rows or "Create Table" not in create_rows[0]:
                raise RuntimeError(f"could not read CREATE TABLE for {t!r} from throwaway db")
            create = create_rows[0]["Create Table"]
            ddl.append(create.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS", 1) + ";")
        ddl.append("SET FOREIGN_KEY_CHECKS=1;")
        schema_sql = "\n".join(ddl)

        # 4) Apply into the clone and commit (local-only; never pushed).
        log(f"recreating {len(missing)} dolt-ignored table(s) in the cloned database ...")
        run([dolt, "sql"], cwd=clone_db, input=schema_sql, timeout=120, check=True)
        # A throwaway local identity scoped to this clone's dolt repo (gitignored).
        run([dolt, "config", "--local", "--add", "user.name", "beads-remote-bootstrap"],
            cwd=clone_db, timeout=30)
        run([dolt, "config", "--local", "--add", "user.email", "bootstrap@local"],
            cwd=clone_db, timeout=30)
        run([dolt, "add", "."], cwd=clone_db, timeout=120, check=True)
        run([dolt, "commit", "-m", "local: recreate dolt-ignored tables post-clone"],
            cwd=clone_db, timeout=120)


# --------------------------------------------------------------------------- #
# reconcile the working branch with the fetched ref (the stale-seed fix)       #
# --------------------------------------------------------------------------- #
def _remote_tracking_ref(dolt: str, clone_db: Path) -> str | None:
    """The dolt remote-tracking branch holding the real refs/dolt/data history
    (normally ``origin/main``). ``bd bootstrap`` fetches the ref into this branch
    even in the failure mode where it seeds the WORKING branch from stale JSONL."""
    p = run([dolt, "branch", "-a"], cwd=clone_db, timeout=30)
    refs = [m.group(1) for ln in (p.stdout or "").splitlines()
            if (m := re.search(r"remotes/(origin/\S+)", ln))]
    if not refs:
        return None
    return "origin/main" if "origin/main" in refs else refs[0]


def _issue_count(dolt: str, clone_db: Path, ref: str | None = None) -> int | None:
    """Rows in ``issues`` on the working branch (ref=None) or ``as of`` a branch/
    commit. None if the query fails (e.g. the table is absent on a wedged clone)."""
    escaped_ref = ref.replace("'", "''") if ref else None
    sql = "select count(*) as n from issues" + (f" as of '{escaped_ref}'" if escaped_ref else "")
    p = run([dolt, "sql", "-r", "json", "-q", sql], cwd=clone_db, timeout=120)
    try:
        return int(json.loads((p.stdout or "").strip())["rows"][0]["n"])
    except (ValueError, KeyError, IndexError, json.JSONDecodeError):
        return None


def reconcile_working_branch_onto_ref(dolt: str) -> bool:
    """Ensure the working branch DESCENDS from refs/dolt/data, not a stale JSONL seed.

    The fresh-clone bug (bd polyglot-pdf-0q8): in a remote container ``bd bootstrap``
    fetches refs/dolt/data into the remote-tracking branch (``origin/main``) but,
    because the cloned history can't open until the dolt-ignored wisp tables are
    repaired, it seeds the WORKING branch from the stale committed
    ``.beads/issues.jsonl`` instead. The working branch and ``origin/main`` then sit
    on UNRELATED roots: the session is frozen on the stale snapshot and every
    ``bd dolt pull``/``push`` dies with "no common ancestor".

    Fix: hard-reset the working branch onto the ref so it shares the ref's history.
    The dolt-IGNORED wisp tables are local working state (not committed), so they
    SURVIVE the reset -- bd still opens the DB and no wisp re-repair is needed
    (verified against the live 124-issue store under bd polyglot-pdf-0q8). Returns
    True iff it reset.

    No-op (returns False) when the working branch already holds the ref's data
    (count >= ref): a healthy, in-sync container is never disturbed."""
    clone_db = _dolt_db_dir(_data_dir_from_config())
    if clone_db is None:
        vlog("reconcile: no dolt db dir found")
        return False
    ref = _remote_tracking_ref(dolt, clone_db)
    if ref is None:
        vlog("reconcile: no remote-tracking ref to reconcile onto")
        return False
    ref_n = _issue_count(dolt, clone_db, ref)
    work_n = _issue_count(dolt, clone_db, None)
    if ref_n is None:
        vlog(f"reconcile: could not count issues on {ref}")
        return False
    if work_n is None:
        # Could not count the working branch (transient dolt error / table absent).
        # Do NOT reset blindly -- a failed count must never trigger a destructive
        # hard-reset of a possibly-healthy branch. Skip; the next session re-checks.
        vlog("reconcile: could not count working-branch issues; skipping reset")
        return False
    if work_n >= ref_n:
        vlog(f"reconcile: working branch already current ({work_n} >= {ref_n} on {ref})")
        return False
    log(f"working branch is a stale seed ({work_n} issues) vs ref {ref} ({ref_n}); "
        "resetting onto the ref ...")
    run([dolt, "reset", "--hard", ref], cwd=clone_db, timeout=180, check=True)
    return True


# --------------------------------------------------------------------------- #
# freshness anchor + proxy sync (bd polyglot-pdf-j47)                          #
# --------------------------------------------------------------------------- #
# The report from a fresh remote session showed bd's dolt-NATIVE sync can fail or
# hang (`Error 1105: no remote` / 180s) against the proxy, while PLAIN git over the
# same proxy reaches refs/dolt/data fine. So we use plain git as the reliable
# freshness anchor and never trust a silent "hydrated".
def _live_ref_commit() -> str | None:
    """Commit of ``refs/dolt/data`` on the proxy origin -- the freshness anchor.
    Plain ``git ls-remote`` works over the proxy even when bd's dolt sync does not.
    None if unreachable (then we cannot verify freshness)."""
    try:
        p = run(["git", "ls-remote", "origin", "refs/dolt/data"], cwd=REPO_ROOT, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    out = (p.stdout or "").split()
    return out[0] if p.returncode == 0 and out else None


def _git_fetch_dolt_ref() -> bool:
    """Fetch ``refs/dolt/data`` over the proxy with PLAIN git -- reliable even when
    bd's dolt-native pull isn't. Lands the canonical dolt ref locally so a
    subsequent reconcile/pull has it to work from. Best-effort."""
    try:
        # Force (+) the local-side ref update: refs/dolt/data can advance
        # non-fast-forward, and a non-ff update of a direct local ref FAILS without
        # the leading '+', silently leaving us on a stale ref (fresh-eyes j47).
        p = run(["git", "fetch", "origin", "+refs/dolt/data:refs/dolt/data"],
                cwd=REPO_ROOT, timeout=120)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return p.returncode == 0


def _direct_github_dolt_url(proxy_origin: str) -> str | None:
    """Build a token-authenticated ``git+https`` URL straight to github.com for the
    dolt remote, bypassing the session's git proxy entirely.

    Why: the web-container proxy forwards fetches and ``refs/heads/*`` pushes but
    returns HTTP 403 on a push of ``refs/dolt/data`` (observed 2026-06-10/11), so
    ``bd dolt push`` -- and therefore the live cross-session bead store -- silently
    cannot sync from remote sessions. github.com itself IS directly reachable from
    the container, so when the maintainer provides a fine-grained PAT (repo-scoped,
    Contents read/write) in ``BEADS_GITHUB_TOKEN``, we push around the proxy.

    Returns None (caller falls back to the proxy URL) when the token is absent or
    the ``owner/repo`` slug cannot be derived from the proxy origin URL
    (``http://local_proxy@127.0.0.1:<port>/git/<owner>/<repo>``)."""
    token = os.environ.get("BEADS_GITHUB_TOKEN", "").strip()
    if not token:
        # Say so (fresh-eyes, PR #152): a silent fallback hides a misnamed /
        # mis-set token -- the operator would just see push 403s with no clue.
        log("BEADS_GITHUB_TOKEN not set -- dolt remote stays on the proxy "
            "(bd dolt pull works; bd dolt push will 403; see "
            "docs/components/beads-remote-bootstrap.md).")
        return None
    m = re.search(r"/git/([^/]+/[^/]+?)(?:\.git)?/?$", proxy_origin)
    if not m:
        log("BEADS_GITHUB_TOKEN is set but the repo slug could not be derived "
            f"from the git origin ({proxy_origin}); falling back to the proxy "
            "(pushes to refs/dolt/data will fail with HTTP 403).")
        return None
    if token not in _SECRET_VALUES:
        _SECRET_VALUES.append(token)
    return f"git+https://token:{token}@github.com/{m.group(1)}"


def repoint_dolt_remote_to_proxy() -> bool:
    """Point the dolt-level ``origin`` remote at THIS session's live proxy git origin
    -- or, when ``BEADS_GITHUB_TOKEN`` is set, straight at github.com so ``bd dolt
    push`` works from the container (the proxy 403s pushes to ``refs/dolt/data``;
    see ``_direct_github_dolt_url``).
    The proxy port rotates each session and the dolt remote is snapshot-cached, so a
    baked URL is dead -- and the committed ``sync.remote`` points at the unreachable
    public github URL. ``bd dolt remote add`` also rewrites ``sync.remote`` in the
    tracked config.yaml, so we restore config.yaml to keep the tree clean (the
    dolt-level remote is what ``bd dolt pull`` actually uses). Returns True if set."""
    try:
        origin = run(["git", "remote", "get-url", "origin"], cwd=REPO_ROOT, timeout=10).stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    if not origin:
        return False
    direct = _direct_github_dolt_url(origin)
    if direct:
        dolt_url = direct
        log("dolt remote: using direct github.com (BEADS_GITHUB_TOKEN set; "
            "proxy bypassed for refs/dolt/data push support)")
    else:
        dolt_url = origin if origin.startswith("git+") else "git+" + origin
    existed = CONFIG.exists()
    original = CONFIG.read_text(encoding="utf-8") if existed else None
    try:
        run(["bd", "dolt", "remote", "remove", "origin"], cwd=REPO_ROOT, timeout=30)  # ignore if absent
        run(["bd", "dolt", "remote", "add", "origin", dolt_url], cwd=REPO_ROOT, timeout=30)
        vlog(f"re-pointed dolt origin -> {dolt_url}")
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        vlog(f"could not re-point dolt remote ({e})")
        return False
    finally:
        # Keep the tree clean: `bd dolt remote add` rewrites sync.remote in the
        # tracked config.yaml. Restore prior content, or remove the file entirely
        # if bd created it where none existed (fresh-eyes j47).
        if existed:
            CONFIG.write_text(original, encoding="utf-8")
        elif CONFIG.exists():
            CONFIG.unlink()
    return True


def bd_dolt_pull(timeout: int = 90) -> tuple[bool, str]:
    """``bd dolt pull`` BOUNDED so it can never silently hang (the report saw a 180s
    hang reported as nothing). Returns (ok, combined-output)."""
    try:
        p = run(["bd", "dolt", "pull"], cwd=REPO_ROOT, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"bd dolt pull timed out after {timeout}s (proxy dolt-sync hang)"
    return p.returncode == 0, (p.stderr or "") + (p.stdout or "")


def origin_main_present(dolt: str) -> bool:
    """Whether the dolt remote-tracking branch (``origin/main``) EXISTS -- i.e. bd
    actually loaded the canonical ref. This is the freshness gate's real signal: an
    ABSENT branch means the dolt fetch never landed the ref and bd is serving the
    stale committed JSONL. Keyed on branch PRESENCE, not an issue count, so a
    transient `dolt sql` count failure on a healthy store can't false-trip the gate
    (fresh-eyes j47)."""
    clone_db = _dolt_db_dir(_data_dir_from_config())
    if clone_db is None:
        return False
    return _remote_tracking_ref(dolt, clone_db) is not None


def quiet_beads_hygiene() -> None:
    """Silence the per-command noise the report flagged (best-effort, never fatal):
    tighten ``.beads`` perms (the clone leaves 0755) and set a default
    ``beads.role`` (a remote ephemeral session is a contributor)."""
    try:
        (REPO_ROOT / ".beads").chmod(0o700)
    except OSError:
        pass
    try:
        run(["git", "config", "beads.role", "contributor"], cwd=REPO_ROOT, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


# --------------------------------------------------------------------------- #
def main() -> int:
    global VERBOSE
    ap = argparse.ArgumentParser(description="Hydrate the beads DB in a remote container.")
    ap.add_argument("--verbose", action="store_true", help="show every sub-step")
    VERBOSE = ap.parse_args().verbose

    # Already hydrated THIS container? The marker -- not a mere issue count -- is the
    # signal. A stale committed .beads/issues.jsonl can make bd report a populated
    # but outdated store (e.g. a 5-day-old snapshot), which would otherwise fool this
    # check into a no-op and strand the session on stale data.
    #
    # NB: "hydrated" is NOT "fresh". The filesystem (store + marker + dolt remote) is
    # snapshot-cached, so a session inherits a store frozen at snapshot time while
    # other sessions keep pushing. So when we already hold the store, we still pull
    # the freshest canonical state (re-pointing the rotated proxy port first). This
    # is what makes a SessionStart invocation keep every session current.
    if HYDRATION_MARKER.exists() and is_hydrated():
        if is_remote_container():
            ok = refresh_remote_and_pull()
            # Even a marked/cached container can be missing the dolt-ignored local
            # tables: the marker is stamped on a READ-OK store, so a snapshot taken
            # before the post-clone repair (or by a bd that opened without them)
            # inherits a write-broken store. Recreate any that are absent so a later
            # bd write / /closeout does not die on 'table not found' (bd polyglot-pdf-080y).
            dolt = ensure_dolt()
            if dolt is not None and _ignored_tables_need_repair(dolt) is not False:
                log("cached store is missing dolt-ignored local tables; repairing ...")
                try:
                    repair_ignored_tables(dolt)
                except Exception as e:  # noqa: BLE001
                    log(f"WARNING: dolt-ignored table repair failed: {e} -- WRITES may fail.")
            elif dolt is None:
                # No dolt CLI -> we could neither verify nor recreate the dolt-ignored
                # tables. Warn rather than report a silent success (bd polyglot-pdf-080y,
                # fresh-eyes): the same write-broken-but-readable hazard the fresh-clone
                # path warns about applies to a cached container too.
                log("WARNING: no 'dolt' CLI available to verify/recreate the dolt-ignored "
                    "local tables -- READS work but WRITES (bd import/create/close, and "
                    "/closeout) may fail with 'table not found' (e.g. wisps / local_metadata). "
                    "Install dolt (https://github.com/dolthub/dolt) and re-run to repair.")
            if ok:
                log(f"already hydrated; refreshed from remote ({bd_total_issues()} issues).")
            else:
                log("WARNING: already hydrated but could NOT refresh from the remote "
                    f"({bd_total_issues()} issues may be stale); pull before trusting "
                    "'bd ready' (see docs/components/beads-remote-bootstrap.md).")
        else:
            log(f"already hydrated (local, {bd_total_issues()} issues); "
                "standing pull-before-read doctrine applies.")
        return 0

    if not is_remote_container():
        # This script wipes and re-clones the local DB -- only safe in a disposable
        # remote container. On a real local checkout, never destroy local state.
        if is_hydrated():
            log("not a remote container; local store is populated -- leaving it "
                "untouched. (This self-heal is for remote/web sessions only.)")
            return 0
        log("not a remote container and no local store found; run 'bd bootstrap' "
            "manually. (This self-heal only runs in remote/web containers.)")
        return 1

    # Remote container: quiet the noisy per-command warnings, then drop any
    # empty/partial/stale DB (the one `bd prime` auto-creates, or a stale JSONL
    # import) so the clone is clean, then hydrate over the authenticated proxy.
    quiet_beads_hygiene()
    wipe_local_db()
    hydrate_via_proxy()
    # A fresh clone never carries the dolt-IGNORED local tables (wisps/wisp_*,
    # local_metadata, repo_mtimes). Recreate any that are MISSING -- gated on the
    # tables, NOT on is_hydrated(). Older bd ABORTED on open when 'wisps' was absent
    # (migration 0047 -> 'table not found: wisps'), so "not hydrated" used to imply
    # "tables missing"; the current bd OPENS for reads without them while every WRITE
    # (is_blocked recompute: import/create/close, and so /closeout) still dies on the
    # missing table -- and 'bd create'/'migrate' die on the missing local_metadata.
    # Gating on is_hydrated() silently shipped a read-only store (bd polyglot-pdf-080y).
    dolt: str | None = ensure_dolt()
    if dolt is not None and _ignored_tables_need_repair(dolt) is not False:
        # True (something missing) or None (undeterminable) -> attempt the idempotent repair.
        log("clone is missing dolt-ignored local tables; repairing ...")
        try:
            repair_ignored_tables(dolt)
        except Exception as e:  # noqa: BLE001
            log(f"ERROR: dolt-ignored table repair failed: {e}")
            return 1
    if not is_hydrated():
        if dolt is None:
            log("ERROR: bd cannot open a populated database and no 'dolt' CLI is "
                "available to recreate the missing dolt-ignored local tables. Install "
                "dolt (https://github.com/dolthub/dolt) and re-run.")
        else:
            log("ERROR: bd still cannot open a populated database after repair. Re-run "
                "with --verbose and inspect, or read docs/components/beads-remote-bootstrap.md.")
        return 1
    if dolt is None:
        # Reads work, but with no dolt CLI we could neither verify nor recreate the
        # dolt-ignored tables -- WRITES may still be broken. Do NOT claim a silent
        # success (bd polyglot-pdf-080y).
        log("WARNING: no 'dolt' CLI available to verify/recreate the dolt-ignored "
            "local tables -- READS work but WRITES (bd import/create/close, and "
            "/closeout) may fail with 'table not found' (e.g. wisps / local_metadata). "
            "Install dolt (https://github.com/dolthub/dolt) and re-run to repair.")

    # bd now opens a populated DB, but `bd bootstrap` may have left the dolt remote
    # pointing at the unreachable public `sync.remote` and seeded the WORKING branch
    # from the stale committed JSONL (origin/main absent). Re-point the dolt remote
    # at the LIVE proxy and land refs/dolt/data over PLAIN git (reliable even when
    # bd's dolt-native pull stalls -- bd polyglot-pdf-j47), then reconcile the
    # working branch onto it (bd polyglot-pdf-0q8).
    if dolt is None:
        dolt = ensure_dolt()
    repoint_dolt_remote_to_proxy()
    _git_fetch_dolt_ref()
    bd_dolt_pull()
    if dolt:
        try:
            reconcile_working_branch_onto_ref(dolt)
        except Exception as e:  # noqa: BLE001 -- best-effort; keep the openable DB we have
            vlog(f"reconcile skipped ({e}); proceeding on the current working branch")

    if not is_hydrated():
        log("ERROR: store not populated after reconcile.")
        return 1

    # Freshness gate (bd polyglot-pdf-j47): NEVER report success on a stale store.
    # The previous bug was SILENT -- a false "Done." over a stale JSONL snapshot, so
    # the agent had no signal to distrust `bd ready`. refs/dolt/data is the reachable
    # freshness anchor (plain git works over the proxy even when dolt sync does not).
    # If bd did not load it -- origin/main absent => serving the committed JSONL --
    # FAIL LOUD and non-zero instead of marking a stale snapshot as hydrated.
    live = _live_ref_commit()
    if live is None:
        # Cannot reach refs/dolt/data to verify freshness. Do NOT certify (no
        # marker) so the next session re-verifies -- marking here would be the same
        # silent-success-over-unverified-data failure this fix exists to kill
        # (fresh-eyes j47). The store is usable this session but may be stale.
        log("WARNING: refs/dolt/data is unreachable -- cannot verify freshness; "
            "NOT marking hydrated (next session re-verifies). 'bd ready' may be "
            "stale this session -- pull before trusting it.")
        return 0
    if dolt is None:
        log(f"WARNING: no 'dolt' CLI to verify the store against refs/dolt/data @ "
            f"{live[:10]}; NOT marking hydrated (next session re-verifies). "
            "'bd ready' may be stale.")
        return 0
    if not origin_main_present(dolt):
        log("ERROR: STALE STORE -- the live tracker refs/dolt/data @ "
            f"{live[:10]} was NOT loaded (origin/main absent); bd is serving the "
            "committed .beads/issues.jsonl snapshot. DO NOT trust 'bd ready' / "
            "'bd show' / 'bd list'. Re-run 'python scripts/beads_remote_bootstrap.py "
            "--verbose' and see docs/components/beads-remote-bootstrap.md.")
        return 1

    mark_hydrated(live)
    log(f"hydrated ({bd_total_issues()} issues). Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
