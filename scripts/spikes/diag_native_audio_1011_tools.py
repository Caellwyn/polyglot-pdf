"""Isolation experiment: what EXACTLY causes the gemini-2.5-flash-native-audio
`1011 Internal error` that closes a Live session after turn 1?

Companion to scripts/spikes/diag_native_audio_1011.py (the rate probe). That
probe + the bd-h04c matrix established the crash is real and tied to "tool
declarations," but a confound was found: the production adapter NEVER sends a
true no-tools config -- it injects a name-only fallback stub -- and the SDK
ITSELF collapses a typed `tools=[]` to no-tools before the wire
(google/genai/live.py:1174-1175: `model_copy(update={'tools': None})` then
`if parameter_model.tools:` -- [] is falsy). So neither the config object nor a
`model_dump` of it proves what reached the server.

This probe controls and PROVES the wire shape by wrapping the SDK's websocket
`send`: it captures the first send (the `{"setup": {...}}` packet) as
ground-truth `wire_setup`, and for the empty-array shapes the typed config can't
express it MUTATES `setup["tools"]` in the wrapper before forwarding. Each cell's
verdict is reported with its captured wire `tools`, so the result is about wire
shapes that actually reached the server.

Design + decision table: docs/.../let-s-do-some-more-shimmering-moon.md (the
research plan). Hypotheses: H1 a tools array with >=1 FULLY-FORMED declaration is
required; H2 mere presence of a non-empty entry suffices; H3 the tools key
present (even empty on the wire) suffices; H4 crash is solicitation-dependent.

No PII (fictional prompts / pirate chat). Model fixed to the 2.5 preview.
Run from repo root with GEMINI_API_KEY:
    backend/.venv/Scripts/python.exe scripts/spikes/diag_native_audio_1011_tools.py \
        --cells P1,P2,P3,C1 --json scripts/spikes/data/diag_1011_tools.json
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

import numpy as np  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from google import genai  # noqa: E402
from google.genai import errors as genai_errors  # noqa: E402
from google.genai import types  # noqa: E402
from google.genai import live as genai_live  # noqa: E402
from websockets.exceptions import ConnectionClosed  # noqa: E402

from backend.config import Settings  # noqa: E402

_CLOSE_ERRORS = (ConnectionClosed, genai_errors.APIError)

MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"
MODEL_3P1 = "gemini-3.1-flash-live-preview"

# --- personas (Factor B) ----------------------------------------------------
SI_FORM = "You are a form-filling assistant. Keep spoken replies very short."
PROMPTS_FORM = [
    "Hi, I'd like to start filling out the form.",
    "My first name is Alex.",
    "My last name is Rivera.",
    "I was born on January second, nineteen ninety.",
    "I currently live in Austin, Texas.",
]
SI_PIRATE = ("You are a pirate. Just have a casual chat. Do not fill any forms "
             "or use any tools.")
PROMPTS_PIRATE = [
    "Ahoy there, how is your day going?",
    "Tell me a short story about the sea.",
    "What is your favorite kind of weather for sailing?",
    "Do you have any songs you like to sing?",
    "That sounds lovely, thank you.",
]
PERSONAS = {
    "form": (SI_FORM, PROMPTS_FORM),
    "pirate": (SI_PIRATE, PROMPTS_PIRATE),
}

# --- audio (reused shape from diag_native_audio_1011.py) --------------------
_RATE = 16000
_CHUNK_MS = 40
_clip_cache: dict[str, bytes] = {}


def _synth(text: str) -> bytes:
    if text in _clip_cache:
        return _clip_cache[text]
    from gtts import gTTS
    import soundfile as sf
    buf = io.BytesIO()
    gTTS(text, lang="en").write_to_fp(buf)
    buf.seek(0)
    y, sr = sf.read(buf, dtype="float32")
    if y.ndim > 1:
        y = y.mean(axis=1)
    if sr != _RATE:
        n = int(len(y) * _RATE / sr)
        y = np.interp(np.linspace(0, len(y), n, endpoint=False),
                      np.arange(len(y)), y).astype("float32")
    pcm = (np.clip(y, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    _clip_cache[text] = pcm
    return pcm


def _chunks(pcm: bytes) -> list[bytes]:
    n = int(_RATE * (_CHUNK_MS / 1000.0)) * 2
    return [pcm[i:i + n] for i in range(0, len(pcm), n)]


# --- tool-shape construction (Factor A) -------------------------------------
# typed1/full/stub2 are real production declarations (deploy fidelity). The
# "shape" determines (a) what we pass to LiveConnectConfig.tools and (b) the
# expected wire `setup.tools`, which the send wrapper ASSERTS. empty_list and
# empty_decls cannot be expressed via the typed config (the SDK erases them), so
# their expected wire value is produced by mutation in the wrapper.

def _prod_decls() -> list[dict]:
    return copy.deepcopy(Settings().TOOL_DECLARATIONS)


def _config_tools_for(shape: str):
    """Return the `tools` value to put in LiveConnectConfig for a shape, or None
    to omit. For empty_list/empty_decls we deliberately pass None here and let
    the send wrapper inject the true wire shape (the SDK would erase [] anyway)."""
    decls = _prod_decls()
    update = next(d for d in decls if d.get("name") == "update_form_fields")
    if shape == "omit":
        return None
    if shape in ("empty_list", "empty_decls"):
        return None  # injected at the wire by the send wrapper
    if shape == "name1":
        return [types.Tool(function_declarations=[
            types.FunctionDeclaration(name="update_form_fields")])]
    if shape == "typed1":
        return [types.Tool(function_declarations=[
            types.FunctionDeclaration(**_to_fn_decl(update))])]
    if shape == "full":
        return [types.Tool(function_declarations=[
            types.FunctionDeclaration(**_to_fn_decl(d)) for d in decls])]
    if shape == "stub2":
        return [types.Tool(function_declarations=[
            types.FunctionDeclaration(name="update_form_fields"),
            types.FunctionDeclaration(name="get_form_status")])]
    raise ValueError(f"unknown shape: {shape}")


def _to_fn_decl(decl: dict) -> dict:
    """Map a production TOOL_DECLARATIONS dict (name/description/parameters) to
    FunctionDeclaration kwargs, building a types.Schema for parameters."""
    out: dict = {"name": decl["name"]}
    if decl.get("description"):
        out["description"] = decl["description"]
    params = decl.get("parameters")
    if params:
        out["parameters"] = _to_schema(params)
    return out


def _to_schema(node: dict) -> types.Schema:
    kwargs: dict = {}
    t = node.get("type")
    if t:
        kwargs["type"] = t.upper()  # genai Type enum accepts upper-case strings
    if node.get("description"):
        kwargs["description"] = node["description"]
    if "enum" in node:
        kwargs["enum"] = node["enum"]
    if node.get("type") == "object" and "properties" in node:
        kwargs["properties"] = {k: _to_schema(v) for k, v in node["properties"].items()}
        if node.get("required"):
            kwargs["required"] = node["required"]
    if node.get("type") == "array" and "items" in node:
        kwargs["items"] = _to_schema(node["items"])
    return types.Schema(**kwargs)


def _wire_tools_override(shape: str):
    """The exact `setup.tools` value to FORCE onto the wire for shapes the typed
    config cannot express, or None to leave whatever the SDK serialized.
    Returns a sentinel ('__OMIT__') meaning 'assert no tools key'."""
    if shape == "empty_list":
        return []
    if shape == "empty_decls":
        return [{"functionDeclarations": []}]
    return None  # no override; assert against the SDK-serialized value


def _expected_wire_tools(shape: str):
    """What setup.tools SHOULD look like on the wire, for the assertion."""
    if shape == "omit":
        return "__ABSENT__"
    if shape == "empty_list":
        return []
    if shape == "empty_decls":
        return [{"functionDeclarations": []}]
    # name1/typed1/full/stub2: a non-empty list with >=1 functionDeclarations
    # entry; we assert structurally (count of decls) rather than byte-exact.
    return "__NONEMPTY__"


# --- wire capture + injection via ws_connect monkeypatch --------------------
# The setup packet is sent at live.py:1104 (`await ws.send(request)`) BEFORE the
# AsyncSession is built, so wrapping session._ws is too late. We wrap the SDK's
# ws_connect so the yielded connection's `send` (a) records the first send (the
# setup JSON) and (b) optionally rewrites setup["tools"] before forwarding.

class _CaptureState:
    def __init__(self, tools_override, capture_sink: dict):
        self.tools_override = tools_override  # value, or None for no override
        self.sink = capture_sink              # we write wire_setup here
        self.first_seen = False


class _WrappedConnect:
    """Async-CM wrapper around the SDK's `ws_connect(...)` instance. `async with`
    resolves __aenter__/__aexit__ on the CLASS, so the interception MUST live at
    class level here (an earlier instance-level cm.__aenter__ assignment was
    silently ignored -- smoke run showed no capture). On enter it wraps the
    yielded connection's `send` to capture (and optionally rewrite) the first
    setup packet."""

    def __init__(self, inner_cm, state: "_CaptureState"):
        self._inner_cm = inner_cm
        self._state = state

    async def __aenter__(self):
        ws = await self._inner_cm.__aenter__()
        state = self._state
        orig_send = ws.send

        async def wrapped_send(message, *a, **k):
            if not state.first_seen:
                state.first_seen = True
                try:
                    obj = json.loads(message)
                except (TypeError, json.JSONDecodeError):
                    obj = None
                if obj is not None and "setup" in obj:
                    if state.tools_override is not None:
                        obj["setup"]["tools"] = state.tools_override
                        message = json.dumps(obj)
                    state.sink["wire_setup"] = obj.get("setup", {})
            return await orig_send(message, *a, **k)

        ws.send = wrapped_send
        return ws

    async def __aexit__(self, *exc):
        return await self._inner_cm.__aexit__(*exc)


def _install_ws_capture(state: _CaptureState):
    """Monkeypatch genai_live.ws_connect to return a class-level async-CM wrapper;
    returns a restore() callable."""
    orig_ws_connect = genai_live.ws_connect

    def patched_ws_connect(*args, **kwargs):
        return _WrappedConnect(orig_ws_connect(*args, **kwargs), state)

    genai_live.ws_connect = patched_ws_connect

    def restore():
        genai_live.ws_connect = orig_ws_connect
    return restore


# --- one session ------------------------------------------------------------
async def _drive_session(model: str, shape: str, persona: str,
                         modalities: list[str], n_turns: int) -> dict:
    si, prompts = PERSONAS[persona]
    config = types.LiveConnectConfig(
        response_modalities=modalities,
        system_instruction=si,
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(disabled=True)),
        tools=_config_tools_for(shape),
    )
    rec = {
        "model": model, "shape": shape, "persona": persona, "modalities": modalities,
        "turns_attempted": 0, "clean_turn_count": 0, "close_code": None,
        "close_payload": None, "first_failure_turn": None, "failure_phase": None,
        "connect_failed": None, "wire_setup_tools": None, "wire_assert_ok": None,
    }
    capture: dict = {}
    state = _CaptureState(_wire_tools_override(shape), capture)
    restore = _install_ws_capture(state)
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    try:
        async with client.aio.live.connect(model=model, config=config) as session:
            _record_wire(rec, capture, shape)
            for i in range(n_turns):
                rec["turns_attempted"] += 1
                pcm = _synth(prompts[i % len(prompts)])
                phase = "send"
                try:
                    await session.send_realtime_input(activity_start=types.ActivityStart())
                    for ch in _chunks(pcm):
                        await session.send_realtime_input(
                            audio=types.Blob(data=ch, mime_type="audio/pcm;rate=16000"))
                        await asyncio.sleep(_CHUNK_MS / 1000.0)
                    await session.send_realtime_input(activity_end=types.ActivityEnd())
                    phase = "receive_predrain"
                    billed = False
                    waited = 0.0
                    while waited < 30.0:
                        try:
                            evt = await asyncio.wait_for(
                                session.receive().__anext__(), timeout=2.0)
                        except asyncio.TimeoutError:
                            waited += 2.0
                            continue
                        except StopAsyncIteration:
                            break
                        if getattr(evt, "usage_metadata", None) is not None:
                            billed = True
                            break
                    if billed:
                        rec["clean_turn_count"] += 1
                    print(f"    turn {i + 1:>2}: {'clean' if billed else 'no-bill'}")
                except _CLOSE_ERRORS as exc:
                    code = (getattr(exc, "code", None)
                            or getattr(getattr(exc, "rcvd", None), "code", None))
                    rec["close_code"] = code
                    rec["close_payload"] = str(exc)
                    rec["first_failure_turn"] = i + 1
                    # phase: send (during the audio burst) vs at the boundary
                    # (after >=1 clean turn) vs predrain (first receive, no bill yet)
                    if rec["clean_turn_count"] >= 1:
                        rec["failure_phase"] = "turn_boundary"
                    else:
                        rec["failure_phase"] = phase
                    print(f"    turn {i + 1:>2}: CLOSED code={code} -- {str(exc)[:80]}")
                    break
    except _CLOSE_ERRORS as exc:
        code = getattr(exc, "code", None) or getattr(getattr(exc, "rcvd", None), "code", None)
        rec["connect_failed"] = f"code={code}: {str(exc)[:90]}"
        rec["close_code"] = code
        rec["close_payload"] = str(exc)
        _record_wire(rec, capture, shape)
    except Exception as exc:  # noqa: BLE001
        rec["connect_failed"] = f"{type(exc).__name__}: {str(exc)[:90]}"
        _record_wire(rec, capture, shape)
    finally:
        restore()
    return rec


def _record_wire(rec: dict, capture: dict, shape: str) -> None:
    setup = capture.get("wire_setup")
    if setup is None:
        return
    tools = setup.get("tools", "__ABSENT__")
    rec["wire_setup_tools"] = tools
    rec["wire_assert_ok"] = _assert_wire(shape, tools)


def _assert_wire(shape: str, tools) -> bool:
    expected = _expected_wire_tools(shape)
    if expected == "__ABSENT__":
        return tools == "__ABSENT__"
    if expected == "__NONEMPTY__":
        return (isinstance(tools, list) and len(tools) >= 1
                and isinstance(tools[0], dict)
                and len(tools[0].get("functionDeclarations", [])) >= 1)
    return tools == expected


# --- cell matrix ------------------------------------------------------------
# (shape, persona); modalities default ["AUDIO"].
CELLS = {
    "P1": ("name1", "form"),
    "P2": ("typed1", "form"),
    "P3": ("omit", "form"),
    "C1": ("full", "form"),
    "C2": ("empty_list", "form"),
    "C3": ("empty_decls", "form"),
    "C4": ("stub2", "form"),
    "S1": ("name1", "pirate"),
    "S2": ("typed1", "pirate"),
}
TIER1 = {"P1", "P2", "P3", "C1"}


def _verdict(runs: list[dict]) -> str:
    n = len(runs)
    crashed = sum(1 for r in runs if r["close_code"] is not None or r["connect_failed"])
    survived = sum(1 for r in runs if r["close_code"] is None and not r["connect_failed"]
                   and r["clean_turn_count"] >= 1)
    if crashed == n:
        return "CRASH"
    if survived == n:
        return "SURVIVE"
    return f"FLAKY ({survived} survive / {crashed} crash of {n})"


async def main_async(args: argparse.Namespace) -> int:
    if not os.getenv("GEMINI_API_KEY"):
        print("GEMINI_API_KEY not set.")
        return 1
    cells = (list(CELLS) if args.cells in (None, "all")
             else [c.strip() for c in args.cells.split(",") if c.strip()])
    model = MODEL_3P1 if args.include_3p1 else MODEL
    modalities = ["AUDIO", "TEXT"] if args.modalities == "audio_text" else ["AUDIO"]

    sdk_version = getattr(genai, "__version__", "unknown")
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    all_records: list[dict] = []
    summary: list[dict] = []

    for cell in cells:
        shape, persona = CELLS[cell]
        reps = (args.repeats if cell in TIER1 else args.confirm_repeats)
        print(f"\n=== {cell}: shape={shape} persona={persona} "
              f"modalities={modalities} model={model} N={reps} ===")
        runs = []
        for r in range(reps):
            print(f"  -- {cell} rep {r + 1}/{reps}")
            rec = await _drive_session(model, shape, persona, modalities, args.turns)
            rec.update({"cell": cell, "rep": r + 1, "sdk_version": sdk_version,
                        "ts": stamp})
            runs.append(rec)
            all_records.append(rec)
            await asyncio.sleep(args.cooldown)
        verdict = _verdict(runs)
        # escalate a non-unanimous Tier-1 cell
        if args.auto_escalate and verdict.startswith("FLAKY") and cell in TIER1:
            print(f"  [escalate] {cell} flaky at N={reps}; running {args.escalate_to - reps} more")
            for r in range(reps, args.escalate_to):
                rec = await _drive_session(model, shape, persona, modalities, args.turns)
                rec.update({"cell": cell, "rep": r + 1, "sdk_version": sdk_version,
                            "ts": stamp, "escalated": True})
                runs.append(rec)
                all_records.append(rec)
                await asyncio.sleep(args.cooldown)
            verdict = _verdict(runs)
        wire = runs[0].get("wire_setup_tools")
        captured = [r for r in runs if r.get("wire_assert_ok") is not None]
        # vacuous-True guard: if NOTHING captured, wire_ok is False (capture broke),
        # not a misleading True from all([]).
        assert_ok = bool(captured) and all(r["wire_assert_ok"] for r in captured)
        summary.append({"cell": cell, "shape": shape, "persona": persona,
                        "n": len(runs), "verdict": verdict,
                        "wire_tools": wire, "wire_assert_ok": assert_ok,
                        "close_codes": sorted({r["close_code"] for r in runs if r["close_code"]}),
                        "phases": sorted({r["failure_phase"] for r in runs if r["failure_phase"]})})

    print(f"\n{'=' * 78}\nSUMMARY -- tool-shape isolation (model={model}, sdk={sdk_version})\n{'=' * 78}")
    print(f"  {'cell':<5}{'shape':<12}{'persona':<8}{'N':>3} {'verdict':<28} wire_ok close")
    for s in summary:
        print(f"  {s['cell']:<5}{s['shape']:<12}{s['persona']:<8}{s['n']:>3} "
              f"{s['verdict']:<28} {str(s['wire_assert_ok']):<7} "
              f"{','.join(str(c) for c in s['close_codes']) or '-'}")
    _print_decision(summary)

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(
            {"model": model, "sdk_version": sdk_version, "ts": stamp,
             "summary": summary, "records": all_records}, indent=2, default=str),
            encoding="utf-8")
        print(f"\nwrote {out}")
    return 0


def _print_decision(summary: list[dict]) -> None:
    by = {s["cell"]: s["verdict"] for s in summary}

    def is_crash(c):
        return by.get(c, "").startswith("CRASH")

    def is_survive(c):
        return by.get(c, "").startswith("SURVIVE")

    print(f"\n{'-' * 78}\nDECISION (auto-evaluated; see the research plan's decision table)\n{'-' * 78}")
    if "C1" in by and is_crash("C1"):
        print("  C1 (full production) CRASHED -> harness/env INVALID. Stop; do not trust other cells.")
        return
    lines = []
    if is_survive("P2") and is_crash("P1") and is_crash("P3"):
        lines.append("H1: a fully-formed declaration is required; name-only AND key-absence crash.")
    if is_survive("P2") and is_crash("P1") and is_survive("P3"):
        lines.append("H3-refined: an INCOMPLETE tools array is the poison; omitting tools is fine "
                     "-> fix is 'complete decl OR omit', NOT 'empty list'.")
    if all(is_survive(c) for c in ("P1", "P2", "P3")):
        lines.append("Tools shape NOT the cause (P1/P2/P3 all survive) -- reopen; prior crash coupled.")
    if "C2" in by and is_survive("C2"):
        lines.append("EMPTY-LIST on the wire SURVIVES -> 'always pass []' IS safe/effective.")
    if "C2" in by and is_crash("C2"):
        lines.append("EMPTY-LIST on the wire CRASHES -> do NOT recommend 'always pass []'; "
                     "require >=1 complete declaration.")
    if "C2" in by and is_survive("C2") and "C3" in by and is_crash("C3"):
        lines.append("inner functionDeclarations:[] is the malformation (empty list ok, empty decls bad).")
    if "C4" in by and is_crash("C4"):
        lines.append("stub2 (two name-only) CRASHES -> completeness, NOT count.")
    if "S1" in by and is_survive("S1") and is_crash("P1"):
        lines.append("H4 ALIVE: broken shape survives without solicitation (pirate) -> "
                     "run the SI/prompt split before publishing H4.")
    if "S1" in by and is_crash("S1") and "S2" in by and is_survive("S2"):
        lines.append("H4 REJECTED: shape dominates, persona irrelevant -> strengthens H1.")
    if not lines:
        lines.append("No decision-table row matched cleanly; inspect the per-cell verdicts + wire_tools.")
    for ln in lines:
        print(f"  - {ln}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Isolate the gemini-2.5 native-audio 1011 cause by wire tool-shape.")
    ap.add_argument("--cells", default="all",
                    help="comma list of cell ids (P1,P2,P3,C1,C2,C3,C4,S1,S2) or 'all'")
    ap.add_argument("--repeats", type=int, default=10, help="N for Tier-1 cells (P1/P2/P3/C1)")
    ap.add_argument("--confirm-repeats", type=int, default=5, help="N for confirmatory/solicitation cells")
    ap.add_argument("--auto-escalate", action="store_true", help="bump a flaky Tier-1 cell to --escalate-to")
    ap.add_argument("--escalate-to", type=int, default=20)
    ap.add_argument("--turns", type=int, default=3, help="audio turns per session (crash is turn 1)")
    ap.add_argument("--modalities", choices=["audio", "audio_text"], default="audio")
    ap.add_argument("--cooldown", type=float, default=2.0, help="seconds between sessions")
    ap.add_argument("--include-3p1", action="store_true", help="use the 3.1 model (sanity only)")
    ap.add_argument("--json", default=None, help="path to dump per-run records + summary")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
