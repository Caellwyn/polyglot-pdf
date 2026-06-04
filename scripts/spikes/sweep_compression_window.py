"""Experiment (bd polyglot-pdf-45o, epic -l3a): sweep the Gemini Live context-window
compression sliding-window size and measure cost + UX empirically across sizes.

This is the validation/tuning harness for context-window compression. It drives the
SAME scripted multi-turn AUDIO session (reused from measure_live_token_curve.py) once
per sliding-window size, plus an unbounded baseline (compression off = the status
quo), against the REAL Live API through the production adapter
(backend/adapters/live_ai_gemini.py). For each configuration it captures:

  COST: per-turn prompt/total tokens + session-cumulative cost (read back from the
        adapter's own token log, backend/logs/token_usage.jsonl), which is what shows
        the headline quadratic->linear shape: prompt tokens should PLATEAU near the
        window size instead of compounding (the unbounded baseline compounds ~6.6x;
        see docs/components/context-compression.md).

  UX:   per-turn RESPONSE LATENCY -- wall-clock from send_activity_end() (we finished
        sending the user's audio) to the FIRST audio-out chunk for that turn (the
        on_audio callback). Compression fires when trigger_tokens is exceeded; the
        question this measures is whether that adds perceptible latency on the turns
        where it kicks in. We report median + p90 + max per configuration.

The point of the sweep is to replace the design doc's MODELED cost table (directional
math) with MEASURED numbers and pick trigger/window from real data.

How each window size is applied: backend/config.Settings binds its env-var defaults
at import time, so mutating os.environ mid-process does NOT re-read them. Instead we
construct a Settings() per configuration with explicit kwargs and patch
backend.config.get_settings to return it -- which is exactly what the adapter resolves
at session start (_run_session_loop calls get_settings()).

No PII: prompts are fictional; the only identifiers sent to the logger are synthetic
(form_id="SWEEP", form_session_id="sweep-<label>-<run>"). Mirrors the no-PII contract
of the tak spike.

Run (from repo root, with GEMINI_API_KEY in env + network for gTTS). The script
injects the repo root into sys.path itself, so PYTHONPATH is not required:
    # Windows:       backend\\.venv\\Scripts\\python.exe scripts/spikes/sweep_compression_window.py
    # macOS / Linux: backend/.venv/bin/python      scripts/spikes/sweep_compression_window.py
Options:
    --windows 2000,3000,4000   sliding-window target_tokens to sweep (default 2000,3000,4000)
    --trigger 5000             trigger_tokens (compression fires above this); shared across windows
    --turns 12                 scripted audio turns per session (default 12)
    --runs 1                   sessions per configuration (default 1)
    --baseline / --no-baseline include the unbounded (compression-off) run (default: included)
    --csv <path>               write a per-configuration summary CSV
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import statistics
import sys
import time
from pathlib import Path

# The production adapter's structlog logger emits emoji warnings; on a Windows cp1252
# console that raises UnicodeEncodeError and kills the adapter's background loop. Force
# UTF-8 BEFORE importing/driving the adapter. (Same pattern as measure_live_token_curve.py.)
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

from backend.adapters.live_ai_gemini import LiveAIGemini  # noqa: E402
from backend import config as _config  # noqa: E402


def _patch_vad_bug_for_sweep(settings) -> None:
    """Neutralize the VAD sensitivity/padding fields on a Settings instance so the
    adapter sends only {disabled: True} (bd polyglot-pdf-p1t -- the API rejects
    disabled=True alongside sensitivity fields with 1007). Mutates the passed
    instance; no production file is touched.
    """
    settings.VAD_START_SENSITIVITY = "UNSPECIFIED"
    settings.VAD_END_SENSITIVITY = "UNSPECIFIED"
    settings.VAD_PREFIX_PADDING_MS = None
    settings.VAD_SILENCE_DURATION_MS = None


# standard-2.5 is EXCLUDED (reliably 1011 on the first real-audio turn -- bd
# polyglot-pdf-daa). The curve is measured on 3.1, stable on audio. Re-add once daa lands.
MODEL = "gemini-3.1-flash-live-preview"

# Fictional, no-PII spoken prompts (intake-style turns). Same set as the tak spike so
# the sweep is comparable to the baseline curve.
PROMPTS = [
    "Hi, I'd like to start filling out the form.",
    "My first name is Alex.",
    "My last name is Rivera.",
    "I was born on January second, nineteen ninety.",
    "I currently live in Austin, Texas.",
    "My phone number is five five five, zero one four two.",
    "I am applying to replace a lost card.",
    "I have lived at my current address for three years.",
    "I do not have a middle name.",
    "Can you read back what you have so far?",
    "That all looks correct.",
    "Thank you, I think that's everything for now.",
]

_TOKEN_LOG = _REPO_ROOT / "backend" / "logs" / "token_usage.jsonl"
_AUDIO_IN_RATE = 16000
_CHUNK_MS = 40  # ~40ms PCM chunks (within the 20-100ms guidance)
_clip_cache: dict[str, bytes] = {}


def _synth_pcm16(text: str) -> bytes:
    """gTTS(text) -> mp3 -> mono 16k PCM16 little-endian bytes. Cached per text."""
    if text in _clip_cache:
        return _clip_cache[text]
    from gtts import gTTS  # imported lazily so --help works without network
    import soundfile as sf

    buf = io.BytesIO()
    gTTS(text, lang="en").write_to_fp(buf)
    buf.seek(0)
    y, sr = sf.read(buf, dtype="float32")  # libsndfile decodes mp3
    if y.ndim > 1:
        y = y.mean(axis=1)  # to mono
    if sr != _AUDIO_IN_RATE:
        n_out = int(len(y) * _AUDIO_IN_RATE / sr)
        y = np.interp(
            np.linspace(0, len(y), n_out, endpoint=False), np.arange(len(y)), y
        ).astype("float32")
    pcm = (np.clip(y, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    _clip_cache[text] = pcm
    return pcm


def _pcm_chunks(pcm: bytes) -> list[bytes]:
    bytes_per_chunk = int(_AUDIO_IN_RATE * (_CHUNK_MS / 1000.0)) * 2  # 2 bytes/sample
    return [pcm[i:i + bytes_per_chunk] for i in range(0, len(pcm), bytes_per_chunk)]


def _make_settings(enabled: bool, trigger: int, window: int):
    """Build a Settings instance for one sweep configuration.

    Settings binds env defaults at import time, so we construct with explicit kwargs
    (the only reliable per-run override in-process) and neutralize the VAD bug.
    """
    overrides = {"CONTEXT_COMPRESSION_ENABLED": enabled}
    if enabled:
        overrides["CONTEXT_COMPRESSION_TRIGGER_TOKENS"] = trigger
        overrides["CONTEXT_COMPRESSION_WINDOW_TOKENS"] = window
    s = _config.Settings(**overrides)
    _patch_vad_bug_for_sweep(s)
    return s


async def _drive_session(form_session_id: str, n_turns: int) -> list[float]:
    """Drive one scripted multi-turn AUDIO session through the production adapter.

    Returns the per-turn response latency in seconds (send_activity_end -> first
    audio-out chunk). get_settings() must already be patched for this configuration.
    """
    adapter = LiveAIGemini(api_key=os.getenv("GEMINI_API_KEY"), model=MODEL)
    adapter.set_session_context(form_session_id=form_session_id, form_id="SWEEP")

    # Latency capture: the harness owns on_audio, so we timestamp the first audio-out
    # chunk after each turn's activity_end. A per-turn event is armed before activity_end
    # and disarmed by the first chunk.
    first_audio_at: dict[str, float] = {}
    audio_armed = {"t": None, "got": False}

    async def _on_audio(_audio_bytes):
        if audio_armed["t"] is not None and not audio_armed["got"]:
            first_audio_at["latency"] = time.monotonic() - audio_armed["t"]
            audio_armed["got"] = True

    async def _noop(*_args, **_kwargs):
        return None

    adapter.set_callbacks(
        on_form_update=_noop,
        on_transcript=_noop,
        on_audio=_on_audio,
        on_tool_call=_noop,
        system_instruction="You are a form-filling assistant. Keep spoken replies very short.",
        tool_declarations=None,
        enable_transcripts=False,
    )

    # Wait for the session to be truly READY (connected). _session_ready flips True only
    # after connect; is_session_active() is True earlier, which makes turn 1 fire into a
    # not-yet-connected session. (Same readiness gate as measure_live_token_curve.py.)
    ready = False
    for _ in range(150):  # up to ~15s
        if getattr(adapter, "_session_ready", False):
            ready = True
            break
        await asyncio.sleep(0.1)
    if not ready:
        print("  [warn] session never became ready; skipping this session")
        try:
            await adapter.finalize()
        except Exception:
            pass
        return []

    latencies: list[float] = []
    last_total = 0
    for i in range(n_turns):
        pcm = _synth_pcm16(PROMPTS[i % len(PROMPTS)])
        await adapter.send_activity_start()
        for chunk in _pcm_chunks(pcm):
            await adapter.stream_audio(chunk)
            await asyncio.sleep(_CHUNK_MS / 1000.0)  # pace like a real mic
        # Arm latency capture right as we stop sending the user's audio.
        audio_armed["t"] = time.monotonic()
        audio_armed["got"] = False
        first_audio_at.pop("latency", None)
        await adapter.send_activity_end()

        # Wait until this turn bills (usage_metadata -> _session_total_tokens climbs).
        waited = 0.0
        while waited < 45.0:
            await asyncio.sleep(0.5)
            waited += 0.5
            cur = getattr(adapter, "_session_total_tokens", 0)
            if cur > last_total:
                last_total = cur
                await asyncio.sleep(1.0)
                break
        else:
            print(f"  [warn] turn {i + 1}: no token update within 45s; continuing")

        # Disarm and record this turn's latency (None if no audio-out chunk arrived).
        audio_armed["t"] = None
        if "latency" in first_audio_at:
            latencies.append(first_audio_at["latency"])
        else:
            print(f"  [warn] turn {i + 1}: no audio-out chunk seen; latency unmeasured")

    try:
        await adapter.finalize()
    except Exception as e:  # noqa: BLE001 -- teardown best-effort in a throwaway harness
        print(f"  [warn] finalize() raised: {type(e).__name__}: {e}")
    return latencies


def _read_run_lines(form_session_id: str) -> list[dict]:
    if not _TOKEN_LOG.exists():
        return []
    out: list[dict] = []
    for line in _TOKEN_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("form_session_id") == form_session_id:
            out.append(rec)
    return out


def _summarize(label: str, records: list[dict], latencies: list[float]) -> dict:
    print(f"\n{'=' * 84}")
    print(f"CONFIG: {label}")
    print(f"{'=' * 84}")
    if not records:
        print("  (no token records captured)")
        return {"config": label, "turns": 0}

    print(f"  {'turn':>4} {'prompt':>9} {'aud_in':>8} {'turn_tok':>9} "
          f"{'cum_tok':>9} {'cum_$':>11} {'latency_s':>10}")
    first_prompt = None
    for idx, rec in enumerate(records, start=1):
        ev = rec.get("event", {})
        cum = rec.get("session_cumulative", {})
        prompt = ev.get("prompt_tokens", 0)
        if first_prompt is None:
            first_prompt = prompt
        lat = latencies[idx - 1] if idx - 1 < len(latencies) else None
        lat_s = f"{lat:.2f}" if lat is not None else "-"
        print(f"  {idx:>4} {prompt:>9,} {ev.get('audio_input', 0):>8,} "
              f"{ev.get('total_tokens', 0):>9,} {cum.get('total_tokens', 0):>9,} "
              f"{cum.get('total_cost_usd', 0.0):>11.6f} {lat_s:>10}")

    last = records[-1]
    last_prompt = last.get("event", {}).get("prompt_tokens", 0)
    cum = last.get("session_cumulative", {})
    growth = (last_prompt / first_prompt) if first_prompt else 0.0

    lat_median = statistics.median(latencies) if latencies else None
    lat_p90 = (statistics.quantiles(latencies, n=10)[-1]
               if len(latencies) >= 2 else (latencies[0] if latencies else None))
    lat_max = max(latencies) if latencies else None

    print(f"\n  prompt_tokens {first_prompt:,} -> {last_prompt:,} ({growth:.1f}x over "
          f"{len(records)} turns) {'[PLATEAU -- compression bounding]' if growth < 2.0 else '[COMPOUNDING]'}")
    print(f"  session cumulative: {cum.get('total_tokens', 0):,} tokens, "
          f"${cum.get('total_cost_usd', 0.0):.6f}")
    if lat_median is not None:
        print(f"  response latency (s): median {lat_median:.2f}, p90 "
              f"{lat_p90:.2f}, max {lat_max:.2f}  (n={len(latencies)})")
    else:
        print("  response latency: (none measured)")
    return {
        "config": label, "turns": len(records),
        "first_prompt_tokens": first_prompt, "last_prompt_tokens": last_prompt,
        "prompt_growth_x": round(growth, 2),
        "cum_tokens": cum.get("total_tokens", 0),
        "cum_cost_usd": round(cum.get("total_cost_usd", 0.0), 6),
        "lat_median_s": round(lat_median, 3) if lat_median is not None else "",
        "lat_p90_s": round(lat_p90, 3) if lat_p90 is not None else "",
        "lat_max_s": round(lat_max, 3) if lat_max is not None else "",
    }


def _configs(args: argparse.Namespace) -> list[tuple[str, bool, int, int]]:
    """(label, enabled, trigger, window) for each sweep point, baseline first."""
    out: list[tuple[str, bool, int, int]] = []
    if args.baseline:
        out.append(("unbounded (compression off)", False, 0, 0))
    for w in args.windows:
        out.append((f"window {w} / trigger {args.trigger}", True, args.trigger, w))
    return out


async def main_async(args: argparse.Namespace) -> int:
    if not os.getenv("GEMINI_API_KEY"):
        print("GEMINI_API_KEY not set; cannot run the live sweep.")
        return 1

    # Pre-synthesize clips up front so a gTTS/network failure fails clearly BEFORE we
    # burn live-API turns (rather than mid-run with a bogus silent turn).
    try:
        for p in PROMPTS[: min(args.turns, len(PROMPTS))]:
            _synth_pcm16(p)
    except Exception as e:  # noqa: BLE001
        print(f"Audio synthesis failed ({type(e).__name__}: {e}); cannot run audio "
              f"sweep. Check network + gTTS, and that soundfile/libsndfile decodes MP3.")
        return 1
    print(f"Synthesized {len(_clip_cache)} prompt clips (16k mono PCM16).")

    # Do NOT clear token_usage.jsonl -- we read back only OUR lines, filtered by the
    # synthetic form_session_id, so pre-existing records are harmless and preserved.

    _orig_get_settings = _config.get_settings
    summaries = []
    for label, enabled, trigger, window in _configs(args):
        settings = _make_settings(enabled, trigger, window)
        # Patch get_settings for the duration of this configuration's runs -- the adapter
        # resolves it fresh at each session start (_run_session_loop).
        _config.get_settings = lambda s=settings: s
        try:
            for run in range(args.runs):
                fsid = f"sweep-{label.split()[0]}-{window}-{run}"
                print(f"\n--- {label} | run {run + 1}/{args.runs} | {args.turns} audio turns ---")
                latencies: list[float] = []
                try:
                    latencies = await _drive_session(fsid, args.turns)
                except Exception as e:  # noqa: BLE001
                    print(f"  [error] {type(e).__name__}: {e}")
                summaries.append(_summarize(f"{label} (run {run + 1})",
                                            _read_run_lines(fsid), latencies))
        finally:
            _config.get_settings = _orig_get_settings

    print(f"\n{'=' * 84}\nSWEEP SUMMARY (cost + UX across window sizes)\n{'=' * 84}")
    print(f"  {'config':<34} {'prompt_growth':>13} {'cum_$':>10} {'lat_med_s':>10} {'lat_p90_s':>10}")
    for s in summaries:
        if s.get("turns"):
            print(f"  {s['config']:<34} {str(s['prompt_growth_x']) + 'x':>13} "
                  f"{s['cum_cost_usd']:>10.5f} {str(s['lat_median_s']):>10} {str(s['lat_p90_s']):>10}")
        else:
            print(f"  {s['config']:<34} {'(no data)':>13}")

    print(
        "\nReading the sweep: prompt_growth should PLATEAU (<2x) once a window bounds the "
        "context,\nvs. the unbounded baseline which compounds; cum_$ should drop with "
        "smaller windows;\nwatch lat_p90 for any latency cost on the turns where "
        "compression fires. Tune\ntrigger/window from here (docs/components/context-compression.md)."
    )

    if args.csv:
        csv_path = Path(args.csv)
        head = ("config,turns,first_prompt_tokens,last_prompt_tokens,prompt_growth_x,"
                "cum_tokens,cum_cost_usd,lat_median_s,lat_p90_s,lat_max_s")
        rows = [head]
        for s in summaries:
            rows.append(
                f"\"{s.get('config')}\",{s.get('turns', 0)},"
                f"{s.get('first_prompt_tokens', '')},{s.get('last_prompt_tokens', '')},"
                f"{s.get('prompt_growth_x', '')},{s.get('cum_tokens', '')},"
                f"{s.get('cum_cost_usd', '')},{s.get('lat_median_s', '')},"
                f"{s.get('lat_p90_s', '')},{s.get('lat_max_s', '')}"
            )
        csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        print(f"\nWrote sweep CSV: {csv_path}")
    return 0


def _parse_windows(raw: str) -> list[int]:
    return [int(x) for x in raw.split(",") if x.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Sweep Gemini Live compression window sizes; measure cost + latency.")
    ap.add_argument("--windows", type=_parse_windows, default=[2000, 3000, 4000],
                    help="comma-separated sliding-window target_tokens to sweep")
    ap.add_argument("--trigger", type=int, default=5000,
                    help="trigger_tokens (compression fires above this), shared across windows")
    ap.add_argument("--turns", type=int, default=12, help="scripted audio turns per session")
    ap.add_argument("--runs", type=int, default=1, help="sessions per configuration")
    ap.add_argument("--baseline", dest="baseline", action="store_true", default=True,
                    help="include the unbounded (compression-off) baseline run (default)")
    ap.add_argument("--no-baseline", dest="baseline", action="store_false",
                    help="skip the unbounded baseline run")
    ap.add_argument("--csv", type=str, default=None, help="optional path to write a summary CSV")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
