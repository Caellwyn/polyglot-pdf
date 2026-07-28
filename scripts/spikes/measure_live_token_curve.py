"""Spike (bd polyglot-pdf-tak): measure the Gemini Live token+cost curve over a
multi-turn AUDIO session, to quantify the compounding-context cost that epic
polyglot-pdf-l3a (context-window compression) aims to cut.

THROWAWAY measurement harness, not app code. It drives a scripted multi-turn
session against the REAL Live API through the production adapter
(backend/adapters/live_ai_gemini.py) so the adapter's existing per-turn token
logging (-> backend/logs/token_usage.jsonl) does the instrumenting; we read that
JSONL back and emit the curve.

Why AUDIO (not text): real sessions are audio-to-audio, and audio input is billed
~6x text input (3.00 vs 0.50 per 1M). A text probe would measure the wrong cost
basis. So each turn synthesizes a spoken prompt (gTTS -> mp3 -> 16k mono PCM16 via
soundfile) and feeds it on the realtime path, bracketed by activity_start/end
(required because DISABLE_GEMINI_VAD=True means audio alone won't bill a turn).

No PII: prompts are fictional; the only identifiers sent to the logger are
synthetic (form_id="SPIKE", form_session_id="spike-<tier>-<run>").

Run (from repo root, with GEMINI_API_KEY in env + network for gTTS). The script
injects the repo root into sys.path itself, so PYTHONPATH is not required:
    # Windows:       backend\\.venv\\Scripts\\python.exe scripts/spikes/measure_live_token_curve.py
    # macOS / Linux: backend/.venv/bin/python      scripts/spikes/measure_live_token_curve.py
Options: --turns N (default 10), --runs M per tier (default 2), --csv <path>.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import sys
from pathlib import Path

# The production adapter's structlog logger emits emoji (e.g. ⚠️) warnings. On a
# Windows cp1252 console that raises UnicodeEncodeError and kills the adapter's
# background session loop. Force UTF-8 (errors="replace") BEFORE importing/driving
# the adapter. Same reconfigure pattern as bd_prime.py; harness-only, no production
# change. (cf. bead polyglot-pdf-amy / -39a.)
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



def _patch_vad_bug_for_spike() -> None:
    """Harness-local workaround for bd polyglot-pdf-p1t.

    With the default config the adapter sends automatic_activity_detection with
    BOTH disabled=True AND the VAD_* sensitivity/padding fields, which the Live API
    rejects with 1007. Until p1t lands, neutralize the sensitivity/padding fields in
    THIS process's Settings so the adapter sends only {disabled: True}. This mirrors
    exactly what the p1t fix will do; it does NOT touch any production file.
    """
    _orig_get_settings = _config.get_settings

    def _patched():
        s = _orig_get_settings()
        s.VAD_START_SENSITIVITY = "UNSPECIFIED"
        s.VAD_END_SENSITIVITY = "UNSPECIFIED"
        s.VAD_PREFIX_PADDING_MS = None
        s.VAD_SILENCE_DURATION_MS = None
        return s

    _config.get_settings = _patched

# NOTE: standard-2.5 (gemini-2.5-flash-native-audio-preview-12-2025) is EXCLUDED:
# it reliably hit code=1011 ("Internal error") on the first real-audio turn here,
# while 3.1 billed cleanly. That 1011 (audio-path-specific) is tracked separately in
# bd polyglot-pdf-daa. We measure the curve on 3.1, which is stable on audio.
# Re-add 2.5 here once daa resolves the 1011.
TIERS = {
    "premium-3.1": "gemini-3.1-flash-live-preview",
}

# Fictional, no-PII spoken prompts (intake-style turns).
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


async def _drive_session(model: str, form_session_id: str, n_turns: int) -> None:
    """Drive one scripted multi-turn AUDIO session through the production adapter."""
    adapter = LiveAIGemini(model=model, **_live_adapter_kwargs())
    adapter.set_session_context(form_session_id=form_session_id, form_id="SPIKE")

    async def _noop(*_args, **_kwargs):
        return None

    adapter.set_callbacks(
        on_form_update=_noop,
        on_transcript=_noop,
        on_audio=_noop,
        on_tool_call=_noop,
        system_instruction="You are a form-filling assistant. Keep spoken replies very short.",
        tool_declarations=None,
        enable_transcripts=False,
    )

    # Wait for the session to be truly READY (connected), not just the bg task to
    # exist. _session_ready flips True only after connect (live_ai_gemini.py:808);
    # is_session_active() is True earlier, which made turn 1's audio/activity fire
    # into a not-yet-connected session ("ACTIVITY_START called but session is None").
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
        return

    last_total = 0
    for i in range(n_turns):
        pcm = _synth_pcm16(PROMPTS[i % len(PROMPTS)])
        # Bracket the audio with activity signals (required under DISABLE_GEMINI_VAD=True).
        await adapter.send_activity_start()
        for chunk in _pcm_chunks(pcm):
            await adapter.stream_audio(chunk)
            await asyncio.sleep(_CHUNK_MS / 1000.0)  # pace like a real mic
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

    try:
        await adapter.finalize()
    except Exception as e:  # noqa: BLE001 -- teardown best-effort in a throwaway spike
        print(f"  [warn] finalize() raised: {type(e).__name__}: {e}")


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


def _summarize(tier_label: str, model: str, records: list[dict]) -> dict:
    print(f"\n{'=' * 84}")
    print(f"TIER: {tier_label}  ({model})")
    print(f"{'=' * 84}")
    if not records:
        print("  (no token records captured)")
        return {"tier": tier_label, "model": model, "turns": 0}

    print(f"  {'turn':>4} {'prompt':>9} {'aud_in':>8} {'resp':>7} {'aud_out':>8} "
          f"{'turn_tok':>9} {'cum_tok':>9} {'cum_$':>11}")
    first_prompt = None
    for idx, rec in enumerate(records, start=1):
        ev = rec.get("event", {})
        cum = rec.get("session_cumulative", {})
        prompt = ev.get("prompt_tokens", 0)
        if first_prompt is None:
            first_prompt = prompt
        print(f"  {idx:>4} {prompt:>9,} {ev.get('audio_input', 0):>8,} "
              f"{ev.get('response_tokens', 0):>7,} {ev.get('audio_output', 0):>8,} "
              f"{ev.get('total_tokens', 0):>9,} {cum.get('total_tokens', 0):>9,} "
              f"{cum.get('total_cost_usd', 0.0):>11.6f}")

    last = records[-1]
    last_prompt = last.get("event", {}).get("prompt_tokens", 0)
    cum = last.get("session_cumulative", {})
    total_audio_in = sum(r.get("event", {}).get("audio_input", 0) for r in records)
    growth = (last_prompt / first_prompt) if first_prompt else 0.0
    print(f"\n  prompt_tokens grew {first_prompt:,} -> {last_prompt:,} "
          f"({growth:.1f}x over {len(records)} turns) "
          f"{'[COMPOUNDING confirmed]' if last_prompt > first_prompt else '[flat]'}")
    print(f"  audio_input tokens this session: {total_audio_in:,} "
          f"{'[on audio cost basis ✓]' if total_audio_in > 0 else '[WARN: no audio_input — was audio actually sent?]'}")
    print(f"  session cumulative: {cum.get('total_tokens', 0):,} tokens, "
          f"${cum.get('total_cost_usd', 0.0):.6f}")
    return {
        "tier": tier_label, "model": model, "turns": len(records),
        "first_prompt_tokens": first_prompt, "last_prompt_tokens": last_prompt,
        "prompt_growth_x": round(growth, 2),
        "audio_input_tokens": total_audio_in,
        "cum_tokens": cum.get("total_tokens", 0),
        "cum_cost_usd": round(cum.get("total_cost_usd", 0.0), 6),
    }


async def main_async(args: argparse.Namespace) -> int:
    if _live_auth_preflight():
        return 1

    _patch_vad_bug_for_spike()  # workaround for bd polyglot-pdf-p1t (1007 on connect)

    # Pre-synthesize clips up front so a gTTS/network failure fails clearly BEFORE
    # we burn live-API turns (rather than mid-run with a bogus silent turn).
    try:
        # Turns cycle through PROMPTS (PROMPTS[i % len]), so synth the distinct
        # prompts we'll actually use (all of them once --turns >= len(PROMPTS)).
        for p in PROMPTS[: min(args.turns, len(PROMPTS))]:
            _synth_pcm16(p)
    except Exception as e:  # noqa: BLE001
        # Covers gTTS (network/synthesis) AND soundfile mp3 decode (libsndfile MP3
        # support is build-dependent). Aborts cleanly BEFORE burning live-API turns.
        print(f"Audio synthesis failed ({type(e).__name__}: {e}); cannot run audio "
              f"spike. Check network + gTTS, and that soundfile/libsndfile decodes MP3.")
        return 1
    print(f"Synthesized {len(_clip_cache)} prompt clips (16k mono PCM16).")

    # Do NOT clear token_usage.jsonl -- it may hold real local session logs. We read
    # back only OUR lines, filtered by the synthetic form_session_id (spike-<tier>-<n>),
    # so pre-existing records are harmless and preserved. (fresh-eyes PR #34)

    summaries = []
    for tier_label, model in TIERS.items():
        for run in range(args.runs):
            fsid = f"spike-{tier_label}-{run}"
            print(f"\n--- driving {tier_label} run {run + 1}/{args.runs} "
                  f"({args.turns} audio turns) ---")
            try:
                await _drive_session(model, fsid, args.turns)
            except Exception as e:  # noqa: BLE001
                print(f"  [error] {type(e).__name__}: {e}")
            summaries.append(_summarize(f"{tier_label} run{run + 1}", model,
                                        _read_run_lines(fsid)))

    print(f"\n{'=' * 84}\nSPIKE SUMMARY\n{'=' * 84}")
    for s in summaries:
        if s.get("turns"):
            print(f"  {s['tier']:<22} prompt {s['first_prompt_tokens']:,}->"
                  f"{s['last_prompt_tokens']:,} ({s['prompt_growth_x']}x), "
                  f"audio_in {s['audio_input_tokens']:,}, "
                  f"cum {s['cum_tokens']:,} tok / ${s['cum_cost_usd']:.6f}")
        else:
            print(f"  {s['tier']:<22} (no data)")

    print(
        "\nNOTE: real-audio probe (gTTS spoken prompts on the realtime path, bracketed "
        "by\nactivity_start/end). audio_input>0 confirms we're on the AUDIO cost basis. "
        "Cadence is\nscripted, so absolute per-second accrual is approximate, but the "
        "COMPOUNDING prompt-\ntoken re-billing (the l3a cost lever) is measured directly."
    )

    if args.csv:
        csv_path = Path(args.csv)
        head = ("tier,model,turns,first_prompt_tokens,last_prompt_tokens,"
                "prompt_growth_x,audio_input_tokens,cum_tokens,cum_cost_usd")
        rows = [head]
        for s in summaries:
            rows.append(
                f"{s.get('tier')},{s.get('model')},{s.get('turns', 0)},"
                f"{s.get('first_prompt_tokens', '')},{s.get('last_prompt_tokens', '')},"
                f"{s.get('prompt_growth_x', '')},{s.get('audio_input_tokens', '')},"
                f"{s.get('cum_tokens', '')},{s.get('cum_cost_usd', '')}"
            )
        csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        print(f"\nWrote summary CSV: {csv_path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Measure Gemini Live AUDIO token+cost curve over a session.")
    ap.add_argument("--turns", type=int, default=10, help="scripted audio turns per session")
    ap.add_argument("--runs", type=int, default=2, help="sessions per tier (variance)")
    ap.add_argument("--csv", type=str, default=None, help="optional path to write a summary CSV")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
