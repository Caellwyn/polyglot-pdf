"""Matrix diagnostic (bd polyglot-pdf-h04c): per-model compression-support verdict
on google-genai 2.8.x.

Establishes, per model tier, whether Live API context-window compression (a) evicts
and (b) destabilizes the session -- separating "the model is unstable on audio probes
generally" (the bd daa 1011 class; bd eycd saw 2.5 throw 1011 BEFORE the trigger could
fire) from "the compression config causes the failure". Three configs per model:

  off      -- no compression config at all (the CONTROL: failures here are baseline
              instability, not compression)
  on-inert -- config present but trigger so high it can never fire (failures here
              mean the mere PRESENCE of the config destabilizes the session)
  on-live  -- trigger=1500/window=800, the config bd eycd confirmed evicting on 3.1
              (failures only here mean the EVICTION PATH is the problem)

The eviction signal is a turn-over-turn DROP in prompt_token_count (bd eycd:
1,972 -> 1,046 on 3.1). cached_content_token_count stays None on SDK 2.8 even while
eviction works -- never key a verdict on it.

Errors are captured by tapping the adapter's structlog logger (the adapter swallows
connection drops into a log event + graceful break; the tap records the reason and
close code without touching adapter code).

Run from repo root with GEMINI_API_KEY (each (model, config) cell runs --repeats
sessions; a full default matrix is 2 models x 3 configs x 5 repeats = 30 live
sessions, roughly an hour):

    backend/.venv/Scripts/python.exe scripts/spikes/diag_compression_matrix_sdk28.py \
        --repeats 5 --tools real

Per-run records append to --out (JSONL; default
scripts/spikes/diag_compression_matrix_sdk28_runs.jsonl) so repeated runs
accumulate in one file; the summary table prints per cell at the end. ALWAYS
pass --tools real (deploy fidelity: the no-tools default exists only as a
labeled artifact-control; it reproduces the 2.5 1011 probe trap). The original
2-separate-days protocol was dropped 2026-06-12 (maintainer; the failure
classification proved configuration-based, not time-based).
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
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

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.adapters.live_ai_gemini import LiveAIGemini  # noqa: E402
from backend import config as _config  # noqa: E402
from backend.config import MODEL_NATIVE_PREMIUM, MODEL_NATIVE_STANDARD  # noqa: E402


def _live_adapter_kwargs() -> dict:
    """Vertex by DEFAULT (maintainer directive 2026-07-12, reaffirmed
    2026-07-28: AI Studio is not currently available to this project, so a
    key-defaulting path errors outright). VERTEXAI=true (default) -> ADC +
    GOOGLE_CLOUD_PROJECT; set VERTEXAI=false with GEMINI_API_KEY only for a
    deliberate AI Studio run (kept reachable for future 3.1-Live
    experimentation -- bd polyglot-pdf-kbi1). Mirrors the sibling spikes'
    _client() convention and the production adapter's construction."""
    if os.environ.get("VERTEXAI", "true").lower() == "true":
        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project:
            print(
                "VERTEXAI mode but GOOGLE_CLOUD_PROJECT unset; relying on ADC's "
                "default project (gcloud config get-value project).",
                flush=True,
            )
        return {
            "vertexai": True,
            "project": project,
            "location": os.environ.get("VERTEX_LOCATION", "us-central1"),
        }
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("VERTEXAI=false but NO KEY in env GEMINI_API_KEY", flush=True)
        sys.exit(2)
    return {"api_key": key}


def _live_auth_preflight() -> int:
    """0 when auth is usable. Only the deliberate AI-Studio opt-out needs a
    key; the DEFAULT Vertex path must never abort for a missing key."""
    if os.environ.get("VERTEXAI", "true").lower() != "true"             and not os.getenv("GEMINI_API_KEY"):
        print("VERTEXAI=false but GEMINI_API_KEY not set.")
        return 1
    return 0


# Reuse the single-config probe's synth/prompts/settings helpers (same dir, not a
# package -- load by path so the two scripts cannot drift apart).
_diag_path = Path(__file__).resolve().parent / "diag_compression_usage.py"
_spec = importlib.util.spec_from_file_location("diag_compression_usage", _diag_path)
_diag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_diag)

MODELS = {
    "2.5": MODEL_NATIVE_STANDARD,
    "3.1": MODEL_NATIVE_PREMIUM,
    # 2.5 routing-hypothesis aliases (bd h04c classification): UNVERIFIED strings --
    # a connect rejection is itself a data point (rules the alias out).
    "2.5-latest": "gemini-2.5-flash-native-audio-latest",
    "2.5-0925": "gemini-2.5-flash-native-audio-preview-09-2025",
}

# (label, enabled, trigger, window). on-inert trigger is far above anything a short
# probe session can accumulate, so the config is present but can never fire.
CONFIGS = [
    ("off", False, 0, 0),
    ("on-inert", True, 100_000, 50_000),
    ("on-live", True, 1_500, 800),
]

_ERROR_EVENTS = {
    "gemini_session_connection_closed",
    "gemini_session_no_events_received",
    "receive_loop_unexpected_error",
    "gemini_session_error",
}


class _LogTap:
    """Proxy around the adapter's structlog logger that records error/warning
    events (with their kwargs) into a shared sink, then delegates. bind() returns
    a new tap around the bound inner logger so rebinding cannot drop the tap."""

    _CAPTURE = ("warning", "error", "exception", "critical")

    def __init__(self, inner, sink: list):
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_sink", sink)

    def bind(self, **kw):
        return _LogTap(self._inner.bind(**kw), self._sink)

    def __getattr__(self, name):
        orig = getattr(self._inner, name)
        if name in self._CAPTURE and callable(orig):
            sink = self._sink

            def _wrapped(event, *a, **kw):
                try:
                    sink.append({
                        "level": name,
                        "event": str(event),
                        "fields": {k: str(v) for k, v in kw.items()},
                    })
                except Exception:
                    pass
                return orig(event, *a, **kw)

            return _wrapped
        return orig


def _detect_api_version(adapter) -> str | None:
    """Best-effort read of the api_version the genai client connects with."""
    try:
        api_client = getattr(adapter._client, "_api_client", None)
        opts = getattr(api_client, "_http_options", None)
        ver = getattr(opts, "api_version", None)
        if ver:
            return str(ver)
        if isinstance(opts, dict):
            return str(opts.get("api_version"))
    except Exception:
        pass
    return None


async def _drive_run(model_name: str, label: str, settings, n_turns: int,
                     tool_declarations=None, trigger: int | None = None) -> dict:
    """Drive one audio session; return the full per-run record."""
    orig_get_settings = _config.get_settings
    _config.get_settings = lambda s=settings: s
    usage_dumps: list[dict] = []
    log_sink: list[dict] = []
    record: dict = {
        "turns_completed": 0,
        "session_ready": False,
        "api_version": None,
    }
    try:
        adapter = LiveAIGemini(model=model_name, **_live_adapter_kwargs())
        adapter.set_session_context(form_session_id=f"matrix-{label}", form_id="DIAG")
        adapter._log = _LogTap(adapter._log, log_sink)
        adapter._on_raw_usage = lambda u: usage_dumps.append(_diag._dump_usage(u))

        async def _noop(*_a, **_k):
            return None

        adapter.set_callbacks(
            on_form_update=_noop, on_transcript=_noop, on_audio=_noop,
            on_tool_call=_noop,
            system_instruction="You are a form-filling assistant. Keep spoken replies very short.",
            tool_declarations=tool_declarations, enable_transcripts=False,
        )
        record["api_version"] = _detect_api_version(adapter)

        for _ in range(150):
            if getattr(adapter, "_session_ready", False):
                record["session_ready"] = True
                break
            await asyncio.sleep(0.1)
        if not record["session_ready"]:
            try:
                await adapter.finalize()
            except Exception:
                pass
            return _finish_record(record, usage_dumps, log_sink, trigger)

        last_total = 0
        consecutive_timeouts = 0
        for i in range(n_turns):
            pcm = _diag._synth_pcm16(_diag.PROMPTS[i % len(_diag.PROMPTS)])
            try:
                await adapter.send_activity_start()
                for chunk in _diag._pcm_chunks(pcm):
                    await adapter.stream_audio(chunk)
                    await asyncio.sleep(_diag._CHUNK_MS / 1000.0)
                await adapter.send_activity_end()
            except Exception as e:  # send path raises raw ConnectionClosed post-close
                log_sink.append({"level": "error", "event": "probe_send_failed",
                                 "fields": {"turn": str(i + 1),
                                            "error": f"{type(e).__name__}: {e}"}})
                break

            waited = 0.0
            turn_billed = False
            while waited < 30.0:
                await asyncio.sleep(0.5)
                waited += 0.5
                cur = getattr(adapter, "_session_total_tokens", 0)
                if cur > last_total:
                    last_total = cur
                    turn_billed = True
                    await asyncio.sleep(1.0)
                    break
                if any(s["event"] in _ERROR_EVENTS for s in log_sink):
                    break
            if turn_billed:
                record["turns_completed"] = i + 1
                consecutive_timeouts = 0
            else:
                consecutive_timeouts += 1
            if any(s["event"] in _ERROR_EVENTS for s in log_sink):
                break  # session is gone; stop burning turns
            if consecutive_timeouts >= 2:
                log_sink.append({"level": "warning", "event": "probe_stalled",
                                 "fields": {"after_turn": str(i + 1)}})
                break
        try:
            await adapter.finalize()
        except Exception:
            pass
    finally:
        _config.get_settings = orig_get_settings
    return _finish_record(record, usage_dumps, log_sink, trigger)


def _finish_record(record: dict, usage_dumps: list[dict], log_sink: list[dict],
                   trigger: int | None = None) -> dict:
    prompts = [d.get("prompt_token_count") or 0 for d in usage_dumps]
    drops = [[i + 2, prompts[i], prompts[i + 1]]
             for i in range(len(prompts) - 1)
             if prompts[i + 1] < prompts[i] - 50]
    record["prompt_curve"] = prompts
    record["peak_prompt"] = max(prompts) if prompts else 0
    record["drops"] = drops
    record["evicted"] = bool(drops)
    # Compression is ASYNC server-side: the drop lands 1-3 turns after the trigger
    # is crossed (eycd findings). post_cross_turns < 4 makes "no eviction" an
    # INCONCLUSIVE-short-runway result, not a negative.
    first_cross = next((i + 1 for i, p in enumerate(prompts)
                        if trigger and p > trigger), None)
    record["first_cross_turn"] = first_cross
    record["post_cross_turns"] = (len(prompts) - first_cross) if first_cross else 0
    record["errors"] = [s for s in log_sink
                        if s["event"] in _ERROR_EVENTS
                        or s["event"].startswith("probe_")
                        or s["level"] in ("error", "exception", "critical")]
    return record


def _summarize(records: list[dict]) -> None:
    print(f"\n{'=' * 88}\nMATRIX SUMMARY (all accumulated runs, incl. prior days in the same --out)\n{'=' * 88}")
    print(f"  {'model':>5} {'config':>9} {'runs':>5} {'completed':>10} {'evicted':>8} "
          f"{'died':>5}  error reasons (distinct, truncated)")
    cells: dict[tuple, list[dict]] = {}
    for r in records:
        cells.setdefault((r["model_tier"], r["config"]), []).append(r)
    for (tier, cfg), runs in sorted(cells.items()):
        died = [r for r in runs if r["errors"]]
        evicted = [r for r in runs if r["evicted"]]
        # Records written before the runway accounting landed lack
        # post_cross_turns entirely; they count as runway-unknown (0), so an
        # old cell can read "0/0" -- consult the raw curves for those.
        runway_ok = [r for r in runs if r.get("post_cross_turns", 0) >= 4]
        full = [r for r in runs if r["turns_completed"] >= r["turns_requested"]]
        reasons: list[str] = []
        for r in died:
            for e in r["errors"]:
                msg = e["fields"].get("reason") or e["fields"].get("error") or e["event"]
                short = msg[:60]
                if short not in reasons:
                    reasons.append(short)
        print(f"  {tier:>5} {cfg:>9} {len(runs):>5} {len(full):>10} "
              f"{len(evicted)}/{len(runway_ok):>4} "
              f"{len(died):>5}  {'; '.join(reasons[:3]) or '-'}")
    print()
    print("  Reading the matrix: failures in OFF = baseline instability (bd daa class);")
    print("  failures appearing only in ON-INERT = the config destabilizes; failures only")
    print("  in ON-LIVE = the eviction path destabilizes. evicted is shown as x/y where")
    print("  y = runs with >=4 post-cross turns of runway: compression is ASYNC (drop")
    print("  lands 1-3 turns after crossing the trigger), so short-runway non-evictions")
    print("  are inconclusive, not negative. x>0 in ON-LIVE = sliding window works.")


async def main_async(args: argparse.Namespace) -> int:
    if _live_auth_preflight():
        return 1
    try:
        for p in _diag.PROMPTS[: min(args.turns, len(_diag.PROMPTS))]:
            _diag._synth_pcm16(p)
    except Exception as e:  # noqa: BLE001
        print(f"Audio synth failed ({type(e).__name__}: {e}); cannot run.")
        return 1

    import google.genai as genai
    genai_version = getattr(genai, "__version__", "unknown")
    if args.api_version:
        # The adapter constructs genai.Client() directly (and its tests patch that
        # name), so an api_version override is a probe-side Client wrap.
        _orig_client = genai.Client

        def _client_with_api_version(*a, **kw):
            kw.setdefault("http_options", {"api_version": args.api_version})
            return _orig_client(*a, **kw)

        genai.Client = _client_with_api_version
        print(f"[api-version override] {args.api_version}")
    tool_decls = None
    if args.tools == "real":
        tool_decls = _config.Settings().TOOL_DECLARATIONS
        print(f"[tools] passing {len(tool_decls)} production tool declaration(s)")
    model_tiers = [t.strip() for t in args.models.split(",") if t.strip()]
    config_labels = [c.strip() for c in args.configs.split(",") if c.strip()]
    configs = [c for c in CONFIGS if c[0] in config_labels]
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    total = len(model_tiers) * len(configs) * args.repeats
    print(f"genai={genai_version}; matrix = {model_tiers} x {[c[0] for c in configs]} "
          f"x {args.repeats} repeats = {total} sessions, {args.turns} turns each\n")

    n = 0
    for tier in model_tiers:
        model_name = MODELS[tier]
        for (label, enabled, trigger, window) in configs:
            for rep in range(args.repeats):
                n += 1
                run_label = f"{tier}-{label}-r{rep + 1}"
                print(f"[{n}/{total}] {run_label} ({model_name}) ...", flush=True)
                settings = _diag._make_settings(enabled, trigger, window)
                rec = await _drive_run(model_name, run_label, settings, args.turns,
                                       tool_declarations=tool_decls,
                                       trigger=trigger if enabled else None)
                rec.update({
                    "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "genai_version": genai_version,
                    "model_tier": tier,
                    "model": model_name,
                    "config": label,
                    "trigger": trigger if enabled else None,
                    "window": window if enabled else None,
                    "run": rep + 1,
                    "turns_requested": args.turns,
                    "tools": args.tools,
                    "api_version_requested": args.api_version,
                })
                with out_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec) + "\n")
                status = ("EVICTED" if rec["evicted"]
                          else "died" if rec["errors"]
                          else "ok")
                print(f"    -> turns {rec['turns_completed']}/{args.turns}, "
                      f"peak_prompt {rec['peak_prompt']}, {status}", flush=True)
                await asyncio.sleep(args.cooldown)

    all_records = [json.loads(line) for line in
                   out_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    _summarize(all_records)
    print(f"Raw per-run records: {out_path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Per-model compression support matrix on google-genai 2.8.x (bd h04c).")
    ap.add_argument("--models", default="2.5,3.1",
                    help="comma list of tiers: 2.5,3.1,2.5-latest,2.5-0925")
    ap.add_argument("--configs", default="off,on-inert,on-live",
                    help="comma list of: off,on-inert,on-live")
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--turns", type=int, default=20,
                    help="20 minimum for eviction verdicts: compression is async "
                         "(drop lands 1-3 turns post-cross); 10-turn runs under-detect")
    ap.add_argument("--tools", choices=["none", "real"], default="none",
                    help="'real' passes the production TOOL_DECLARATIONS "
                         "(2.5 classification cell: the with-tools 4sv7 spike got "
                         "clean 2.5 sessions while this no-tools probe dies)")
    ap.add_argument("--api-version", default=None,
                    help="override the genai client api_version (e.g. v1alpha)")
    ap.add_argument("--cooldown", type=float, default=3.0,
                    help="seconds between sessions")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent
                                         / "diag_compression_matrix_sdk28_runs.jsonl"))
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
