#!/usr/bin/env python3
"""drain_flag.py -- PreCompact-triggered clean-drain / handover plumbing (R2).

The deterministic, zero-model-turn half of the R2 drain/handover step (bd
polyglot-pdf-h2r.2). It is the mechanism behind the doctrine in
``docs/doctrine/drain-handover.md``: when a session approaches context-fill and
Claude Code auto-compacts, this script raises a session-scoped "drain" flag so
the post-compaction orchestrator knows to finish (or SPLIT) its in-flight bead,
close out, ping the maintainer, and STOP -- rather than claiming yet more work
into an ever-compacting session.

There is NO handover-note file: the beads tracker IS the handoff. A clean drain
closes its in-flight bead (rewriting its exit criteria to what shipped) and files
a new bead for any remainder; the successor session rehydrates purely from
``bd ready``. The bead-split protocol (cases A-D) lives in the doctrine doc; this
script only raises the flag and surfaces the directive.

Why it is shaped this way (verified against the Claude Code hooks docs)
----------------------------------------------------------------------
PreCompact stdout is NOT injected into the model's context -- only a small set of
hooks (SessionStart among them) can inject ``additionalContext``. So a single
PreCompact hook cannot itself tell the orchestrator to drain. The viable pattern
is TWO hooks sharing a durable marker file:

  1. ``PreCompact`` (auto only) -> ``precompact`` mode writes a session-scoped
     marker file. Nothing reaches the model here; the marker is the durable
     signal.
  2. The post-compaction ``SessionStart`` (``source == "compact"``) ->
     ``sessionstart`` mode reads the marker and prints the documented
     ``hookSpecificOutput.additionalContext`` JSON, so the FIRST post-compaction
     orchestrator turn sees the drain directive.

A drain only fires for AUTO compaction (the context-fill signal). A manual
``/compact`` is a deliberate user action, not a reason to retire the session, so
``trigger == "manual"`` never writes a marker.

Robustness choices (each maps to an undocumented-but-load-bearing assumption):

* **trigger detection is belt-and-suspenders.** The hooks docs are sparse on
  whether the PreCompact stdin carries ``trigger``; the hook is *also* registered
  in settings.json with ``matcher: "auto"`` so it only fires on auto-compaction.
  We read ``trigger`` from stdin when present and otherwise trust the matcher
  (treating a missing trigger under this hook as auto). Either source alone is
  sufficient; together they are robust to the doc ambiguity.
* **session_id stability across compaction is undocumented.** We therefore match
  a marker to the post-compaction SessionStart by EITHER ``session_id`` OR
  ``transcript_path`` (the transcript path is stable across an auto-compaction --
  it is the same conversation file). A match on either drains.
* **stale markers never drain a fresh session.** Markers are written under a
  gitignored runtime dir keyed by session_id. A non-compact SessionStart
  (``startup`` / ``resume`` / ``clear``) sweeps that session's marker (and any
  stale markers) so a leftover flag from a prior run cannot spuriously drain a
  brand-new session.

A hook must NEVER hard-fail the session: every entry point degrades to a no-op
(exit 0, nothing surfaced) on any error.

Worktree-safe: the runtime dir is resolved from the git common dir (the MAIN
repo's ``.beads``), so a PreCompact in one worktree and the SessionStart that
follows resolve the SAME marker location regardless of cwd.

Exit code is always 0 (a hook that exits non-zero or crashes is worse than one
that quietly does nothing). The CLI returns 0 unconditionally from ``main``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

# Suppress the child console window every subprocess opens on Windows
# (bd polyglot-pdf-5k32 / bd polyglot-pdf-rdftu). Duplicated rather than
# imported from swarm_config because importing that module mutates PATH and
# loads a config file -- side effects this script must not take on.
def windowless_creationflags() -> int:
    """subprocess creationflags that suppress child console windows on Windows."""
    if sys.platform == "win32":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


# Force UTF-8 on the hook's streams so a stray non-ASCII byte in stdin/echo never
# crashes on Windows' cp1252 default (the same guard bd_prime.py uses). Guarded
# because reconfigure() can be absent or raise on a detached stream.
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def _runtime_dir() -> Path:
    """The gitignored runtime dir for transient drain markers, under the MAIN
    repo's ``.beads`` so every worktree and the post-compaction SessionStart
    resolve the same marker location.

    Resolves via the git common dir; falls back to this file's repo root if git
    is unavailable (a hook must not depend on git succeeding)."""
    base = None
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10,
            creationflags=windowless_creationflags(),
        )
        if proc.returncode == 0 and (proc.stdout or "").strip():
            # parent of .../.git is the main repo root
            base = Path(proc.stdout.strip()).resolve().parent
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        base = None
    if base is None:
        base = Path(__file__).resolve().parent.parent
    return base / ".beads" / ".runtime"


def _session_key(session_id: str) -> str:
    """Filesystem-safe key for a session id. session_id is normally a UUID, but
    hash defensively so an unexpected value can never escape the runtime dir."""
    sid = (session_id or "").strip() or "unknown"
    return hashlib.sha256(sid.encode("utf-8", "replace")).hexdigest()[:16]


def _marker_path(runtime: Path, session_id: str) -> Path:
    return runtime / "drain-{}.flag".format(_session_key(session_id))


def _read_stdin_json() -> dict:
    """Parse the hook's stdin JSON. Returns {} on any problem (no stdin, empty,
    malformed) so callers degrade to a no-op."""
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return {}
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}


# ---------------------------------------------------------------------------
# PreCompact: raise the drain flag on auto-compaction.
# ---------------------------------------------------------------------------

def cmd_precompact(args: argparse.Namespace) -> int:
    data = _read_stdin_json()
    # trigger comes from stdin when present; the hook's settings.json matcher
    # ("auto") is the belt-and-suspenders fallback. A missing trigger under THIS
    # hook means auto (the matcher already filtered out manual).
    trigger = str(data.get("trigger", "") or "").strip().lower()
    if trigger == "manual":
        return 0  # deliberate /compact -- never a drain signal
    # trigger == "auto" OR trigger absent (matcher guaranteed auto) -> drain.

    session_id = str(data.get("session_id", "") or "")
    transcript = str(data.get("transcript_path", "") or "")
    runtime = _runtime_dir()
    try:
        runtime.mkdir(parents=True, exist_ok=True)
        payload = {
            "session_id": session_id,
            "transcript_path": transcript,
            "raised_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "trigger": trigger or "auto",
        }
        _marker_path(runtime, session_id).write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
    except OSError:
        return 0  # never hard-fail the compaction
    return 0


# ---------------------------------------------------------------------------
# SessionStart: surface the drain directive after compaction; sweep stale
# markers otherwise.
# ---------------------------------------------------------------------------

_DRAIN_DIRECTIVE = (
    "DRAIN SIGNAL (R2 clean drain / handover -- bd polyglot-pdf-h2r.2): this "
    "session auto-compacted near context-fill. Do NOT claim a new bead. Follow "
    "the drain protocol in docs/doctrine/drain-handover.md: finish ONLY the bead "
    "already in flight (or SPLIT it -- close what is done, file a new bead for the "
    "remainder with its own exit criteria), run /closeout, ping the maintainer, "
    "and STOP. The tracker IS the handoff: the successor rehydrates from `bd "
    "ready` -- there is no side-channel note."
)


def _emit_session_context(text: str) -> None:
    """Print the documented SessionStart additionalContext JSON to stdout."""
    out = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": text,
        }
    }
    sys.stdout.write(json.dumps(out))


def _marker_matches(marker_file: Path, session_id: str, transcript: str) -> bool:
    """A marker drains the current SessionStart if it shares the session_id OR the
    transcript_path (the latter is stable across an auto-compaction even if the
    session_id is not -- that stability is undocumented, so we accept either)."""
    try:
        rec = json.loads(marker_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return False
    if session_id and rec.get("session_id") == session_id:
        return True
    if transcript and rec.get("transcript_path") == transcript:
        return True
    return False


# Stale markers older than this are swept on any SessionStart so a crashed
# session that never reached its post-compaction SessionStart cannot leave a flag
# that drains an unrelated future session. Generous: a real drain is consumed
# within seconds (the very next SessionStart), so this only catches orphans.
_STALE_MARKER_SECONDS = 12 * 60 * 60


def _sweep_stale_markers(runtime: Path, keep: Path | None) -> None:
    """Delete drain markers older than the stale threshold (except ``keep``)."""
    try:
        now = time.time()
        for f in runtime.glob("drain-*.flag"):
            if keep is not None and f == keep:
                continue
            try:
                if now - f.stat().st_mtime > _STALE_MARKER_SECONDS:
                    f.unlink()
            except OSError:
                continue
    except OSError:
        pass


def cmd_sessionstart(args: argparse.Namespace) -> int:
    data = _read_stdin_json()
    source = str(data.get("source", "") or "").strip().lower()
    session_id = str(data.get("session_id", "") or "")
    transcript = str(data.get("transcript_path", "") or "")
    runtime = _runtime_dir()

    if source == "compact":
        # Post-compaction: drain if THIS session's marker is present (match by
        # session_id or transcript_path), then consume it so the directive is
        # surfaced exactly once.
        marker = _marker_path(runtime, session_id)
        drained = False
        if marker.exists() and _marker_matches(marker, session_id, transcript):
            drained = True
        else:
            # session_id may have changed across compaction (undocumented); fall
            # back to a transcript_path match across all markers.
            try:
                for f in runtime.glob("drain-*.flag"):
                    if _marker_matches(f, session_id, transcript):
                        marker, drained = f, True
                        break
            except OSError:
                drained = False
        if drained:
            try:
                marker.unlink()
            except OSError:
                pass
            # The drain directive is the only signal. There is NO handover note:
            # the tracker is the handoff. The SAME session that compacted continues
            # here and drains via the bead-split protocol (finish or split the
            # in-flight bead); the successor rehydrates purely from `bd ready`.
            _emit_session_context(_DRAIN_DIRECTIVE)
        return 0

    # startup / resume / clear (or unknown): this is a FRESH session, never a
    # drain. Sweep this session's own marker (if somehow present) plus any stale
    # orphans so a leftover flag cannot drain us. Nothing is surfaced -- a fresh
    # session rehydrates from `bd ready` on its own (bd_prime SessionStart).
    try:
        own = _marker_path(runtime, session_id)
        if own.exists():
            own.unlink()
    except OSError:
        pass
    _sweep_stale_markers(runtime, keep=None)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PreCompact drain-flag + SessionStart drain-directive plumbing (R2)."
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    p_pre = sub.add_parser(
        "precompact", help="PreCompact hook: raise the drain flag on auto-compact."
    )
    p_pre.set_defaults(func=cmd_precompact)

    p_ss = sub.add_parser(
        "sessionstart",
        help="SessionStart hook: surface the drain directive / sweep stale flags.",
    )
    p_ss.set_defaults(func=cmd_sessionstart)

    return parser


def main(argv: list | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        args.func(args)
    except SystemExit:
        # argparse error (e.g. no subcommand). A hook must not surface a non-zero
        # exit; swallow it.
        return 0
    except Exception as exc:  # noqa: BLE001 -- a hook must never crash the session
        sys.stderr.write("drain_flag.py: degraded to no-op: {}\n".format(exc))
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
