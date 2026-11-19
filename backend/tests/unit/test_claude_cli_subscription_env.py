"""Every `claude` CLI spawn must run WITHOUT ANTHROPIC_API_KEY in its env.

WHY THIS FILE EXISTS (bd polyglot-pdf-hfhtp). The local `claude -p` CLI is the
repo's "free" provider: it authenticates with the maintainer's subscription
login. But when ANTHROPIC_API_KEY is in its environment, the CLI uses the key
instead and bills the metered Claude API. The maintainer keeps that key set
machine-wide for scripts that genuinely need the API (the sim-user actor, and
other projects), so every spawn site here must strip it.

This pins the SET, not the instances (CLAUDE.md scar #8):
  - a static AST scan finds every function under backend/ and scripts/ that
    resolves the CLI via shutil.which("claude"), and requires every subprocess
    spawn in it to pass env=claude_cli_env();
  - the discovered set must equal EXPECTED_SITES, so a new spawn site has to be
    added here deliberately and the scanner cannot go vacuous;
  - every claude_cli_env() definition is checked behaviorally, and two real
    entry points are driven with subprocess.run captured to read the env they
    actually pass.

Hermetic: no CLI is ever run. ASCII only.
"""
from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCAN_DIRS = ("backend", "scripts")
SPAWN_ATTRS = {"run", "Popen", "call", "check_output", "check_call"}

# Every (file, function) that spawns the claude CLI. Adding a site means adding
# it here AND passing env=claude_cli_env() -- both are checked.
EXPECTED_SITES = {
    ("backend/adapters/text_ai_claude_cli.py", "_run_cli"),
    ("backend/scripts/probe_secretary_recall.py", "_judge_case"),
    ("scripts/bakeoff/llm_providers.py", "run"),
    ("scripts/bakeoff/llm_providers.py", "run_json_claude_cli"),
    ("scripts/bakeoff/order_probe.py", "ask_order"),
}

# Modules that DEFINE claude_cli_env (probe_secretary_recall imports the
# backend adapter's copy).
HELPER_MODULES = (
    "backend/adapters/text_ai_claude_cli.py",
    "scripts/bakeoff/llm_providers.py",
    "scripts/bakeoff/order_probe.py",
)


def _is_which_claude(node: ast.AST) -> bool:
    return (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "which"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "shutil"
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "claude")


def _is_spawn(node: ast.AST) -> bool:
    return (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in SPAWN_ATTRS
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "subprocess")


def _passes_scrubbed_env(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg == "env":
            v = kw.value
            return (isinstance(v, ast.Call) and isinstance(v.func, ast.Name)
                    and v.func.id == "claude_cli_env")
    return False


def _tracked_py_files():
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "--", *SCAN_DIRS],
        capture_output=True, text=True, check=True)
    for rel in out.stdout.splitlines():
        if rel.endswith(".py"):
            yield rel


def _claude_spawn_sites():
    """{(relpath, func): [spawn Call nodes]} for every function that calls
    shutil.which("claude") AND spawns a subprocess."""
    sites: dict = {}
    for rel in _tracked_py_files():
        path = REPO_ROOT / rel
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except (SyntaxError, UnicodeDecodeError):
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = list(ast.walk(fn))
            if not any(_is_which_claude(n) for n in body):
                continue
            spawns = [n for n in body if _is_spawn(n)]
            # A function that only checks the CLI is on PATH (no spawn) is not
            # a spawn site.
            if spawns:
                sites[(rel, fn.name)] = spawns
    return sites


def test_spawn_site_set_is_exactly_the_expected_set():
    found = set(_claude_spawn_sites())
    assert found == EXPECTED_SITES, (
        "The set of functions that spawn the claude CLI changed.\n"
        f"  new (add to EXPECTED_SITES and pass env=claude_cli_env()): "
        f"{sorted(found - EXPECTED_SITES)}\n"
        f"  gone (remove from EXPECTED_SITES): {sorted(EXPECTED_SITES - found)}")


def test_every_claude_spawn_passes_scrubbed_env():
    offenders = []
    for (rel, func), spawns in sorted(_claude_spawn_sites().items()):
        for call in spawns:
            if not _passes_scrubbed_env(call):
                offenders.append(f"{rel}:{call.lineno} ({func})")
    assert not offenders, (
        "These claude CLI spawns do not pass env=claude_cli_env(), so a "
        "machine-wide ANTHROPIC_API_KEY moves them from the subscription onto "
        "metered API billing (bd polyglot-pdf-hfhtp):\n  "
        + "\n  ".join(offenders))


def _load(rel: str):
    path = REPO_ROOT / rel
    name = "_hfhtp_" + rel.replace("/", "_").replace(".py", "")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("rel", HELPER_MODULES)
def test_helper_strips_key_and_keeps_the_rest(rel, monkeypatch):
    mod = _load(rel)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-real")
    monkeypatch.setenv("HFHTP_SENTINEL", "kept")
    env = mod.claude_cli_env()
    assert "ANTHROPIC_API_KEY" not in env
    assert env["HFHTP_SENTINEL"] == "kept"
    assert "PATH" in env or "Path" in env  # the CLI still has to be findable


def test_helper_is_a_noop_without_the_key(monkeypatch):
    mod = _load("backend/adapters/text_ai_claude_cli.py")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert "ANTHROPIC_API_KEY" not in mod.claude_cli_env()


class _Captured(Exception):
    pass


def _capture_env(monkeypatch, module):
    seen = {}

    def fake_run(cmd, **kw):
        seen["env"] = kw.get("env")
        raise _Captured()

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    return seen


def test_editor_adapter_entry_point_passes_no_key(monkeypatch):
    # Drive the REAL _run_cli (the schema editor's translation/guidance path).
    from backend.adapters import text_ai_claude_cli as cli
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-real")
    seen = _capture_env(monkeypatch, cli)
    inst = cli.TextAIClaudeCli.__new__(cli.TextAIClaudeCli)
    inst._model_name = "sonnet"
    with pytest.raises(_Captured):
        inst._run_cli("hello", None)
    assert seen["env"] is not None, "spawned with the inherited environment"
    assert "ANTHROPIC_API_KEY" not in seen["env"]


def test_bakeoff_extractor_entry_point_passes_no_key(monkeypatch):
    # Drive the REAL run_json_claude_cli (the extractor's JSON path).
    mod = _load("scripts/bakeoff/llm_providers.py")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-real")
    seen = _capture_env(monkeypatch, mod)
    with pytest.raises(_Captured):
        mod.run_json_claude_cli("hello", "sonnet")
    assert seen["env"] is not None, "spawned with the inherited environment"
    assert "ANTHROPIC_API_KEY" not in seen["env"]
