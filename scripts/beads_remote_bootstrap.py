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

2. **The dolt-ignored ``wisps`` tables.** ``wisps`` / ``wisp_*`` are registered in
   ``dolt_ignore`` (so per-clone wisp state never causes merge conflicts), which
   also means they are absent from ``refs/dolt/data``. On a fresh clone bd runs
   its schema migrations up to the latest level, but migration
   ``0047_recompute_mixed_is_blocked`` references the ``wisps`` table -- which does
   not exist -- so ``bd`` aborts with "table not found: wisps" and **cannot open
   the database at all**. (Long-lived local checkouts never hit this because they
   only ever *pull* into a DB that already has the local wisp tables; only a fresh
   clone trips it.)

This script makes a remote session self-heal: clone over the proxy, then recreate
the missing wisp tables (with the *exact* schema of whatever bd version is
installed -- extracted from a throwaway ``bd init`` -- so there is no hand-written
DDL to rot), and let bd finish its last migration and open normally. It is
idempotent: if bd already opens, it does nothing.

It NEVER pushes. The recreated wisp tables and the forward-migration commits are
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


def log(msg: str) -> None:
    print(f"[beads-bootstrap] {msg}", flush=True)


def vlog(msg: str) -> None:
    if VERBOSE:
        print(f"[beads-bootstrap]   {msg}", flush=True)


def run(cmd, cwd=None, check=False, capture=True, timeout=300, **kw):
    """Thin subprocess wrapper. Returns CompletedProcess; never raises on
    non-zero unless check=True."""
    vlog("$ " + " ".join(str(c) for c in cmd) + (f"   (cwd={cwd})" if cwd else ""))
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
    local-proxy git origin. In that case the committed ``.beads/issues.jsonl`` is
    never authoritative -- the live store must come from ``refs/dolt/data`` -- and
    the destructive wipe-and-clone below is safe (the container is disposable)."""
    try:
        p = run(["git", "remote", "get-url", "origin"], cwd=REPO_ROOT, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return "local_proxy" in (p.stdout or "")


def mark_hydrated() -> None:
    """Record that this container now holds the live store (hydrated from the ref)."""
    HYDRATION_MARKER.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    HYDRATION_MARKER.write_text(f"hydrated from refs/dolt/data at {stamp}\n", encoding="utf-8")


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


def repair_wisps(dolt: str) -> None:
    """Recreate the dolt-ignored ``wisps`` / ``wisp_*`` tables in the freshly cloned
    DB, using the exact schema of the installed bd version (sourced from a
    throwaway ``bd init``). bd then runs its final migration and opens."""
    clone_db = _dolt_db_dir(_data_dir_from_config())
    if clone_db is None:
        raise RuntimeError("could not locate the cloned Dolt database directory")
    vlog(f"clone db: {clone_db}")

    with tempfile.TemporaryDirectory(prefix="bd-wisp-src-") as tmp:
        # 1) A throwaway bd db at the installed version -- has wisp tables at the
        #    correct (current) schema.
        log("sourcing wisp schema from a throwaway 'bd init' ...")
        run(["bd", "init", "--prefix", "wispsrc"], cwd=tmp, timeout=120)
        src_db = _dolt_db_dir(Path(tmp) / ".beads" / "embeddeddolt") \
            or _dolt_db_dir(Path(tmp) / ".beads" / "dolt")
        if src_db is None:
            raise RuntimeError("throwaway bd init produced no Dolt database")

        # 2) Extract CREATE TABLE for every wisp* table (wisps first -- others FK to it).
        def q(db: Path, sql: str):
            p = run([dolt, "sql", "-r", "json", "-q", sql], cwd=db, timeout=120)
            out = (p.stdout or "").strip()
            return json.loads(out).get("rows", []) if out else []

        tbls = [list(r.values())[0] for r in q(src_db, "SHOW TABLES LIKE 'wisp%'")]
        tbls.sort(key=lambda t: (t != "wisps", t))
        if "wisps" not in tbls:
            raise RuntimeError("throwaway db has no wisp tables -- bd internals changed?")
        vlog(f"wisp tables: {tbls}")

        ddl = ["SET FOREIGN_KEY_CHECKS=0;"]
        for t in tbls:
            create_rows = q(src_db, f"SHOW CREATE TABLE `{t}`")
            if not create_rows or "Create Table" not in create_rows[0]:
                raise RuntimeError(f"could not read CREATE TABLE for {t!r} from throwaway db")
            create = create_rows[0]["Create Table"]
            ddl.append(create.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS", 1) + ";")
        ddl.append("SET FOREIGN_KEY_CHECKS=1;")
        schema_sql = "\n".join(ddl)

        # 3) Apply into the clone and commit (local-only; never pushed).
        log("recreating wisp tables in the cloned database ...")
        run([dolt, "sql"], cwd=clone_db, input=schema_sql, timeout=120, check=True)
        # A throwaway local identity scoped to this clone's dolt repo (gitignored).
        run([dolt, "config", "--local", "--add", "user.name", "beads-remote-bootstrap"],
            cwd=clone_db, timeout=30)
        run([dolt, "config", "--local", "--add", "user.email", "bootstrap@local"],
            cwd=clone_db, timeout=30)
        run([dolt, "add", "."], cwd=clone_db, timeout=120, check=True)
        run([dolt, "commit", "-m", "local: recreate dolt-ignored wisp tables post-clone"],
            cwd=clone_db, timeout=120)


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
    if HYDRATION_MARKER.exists() and is_hydrated():
        log(f"beads database already hydrated this container "
            f"({bd_total_issues()} issues) -- nothing to do.")
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

    # Remote container: drop any empty/partial/stale DB (the one `bd prime`
    # auto-creates, or a stale JSONL import) so the clone is clean, then hydrate
    # over the authenticated proxy.
    wipe_local_db()
    hydrate_via_proxy()
    if is_hydrated():
        mark_hydrated()
        log(f"hydrated ({bd_total_issues()} issues). Done.")
        return 0

    log("clone is missing the dolt-ignored wisp tables; repairing ...")
    dolt = ensure_dolt()
    if not dolt:
        log("ERROR: could not obtain a 'dolt' CLI to repair wisp tables. "
            "Install dolt (https://github.com/dolthub/dolt) and re-run.")
        return 1
    try:
        repair_wisps(dolt)
    except Exception as e:  # noqa: BLE001
        log(f"ERROR: wisp repair failed: {e}")
        return 1

    if is_hydrated():
        mark_hydrated()
        log(f"hydrated + repaired ({bd_total_issues()} issues). Done.")
        return 0
    log("ERROR: bd still cannot open a populated database after repair. Re-run with "
        "--verbose and inspect, or read docs/components/beads-remote-bootstrap.md.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
