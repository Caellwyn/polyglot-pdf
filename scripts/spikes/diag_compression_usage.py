"""Diagnostic (bd polyglot-pdf-l3a.1): does Live API context-window compression
ACTIVATE, or is it a silent no-op? -- read the RAW usage_metadata.

The 45o sweep found prompt_token_count kept compounding past the trigger with
compression on (no plateau), but the adapter only logs prompt/response/total tokens
-- it never captured the fields that would distinguish "compression ran but the cost
field doesn't reflect it" from "the server ignored the config entirely". Those fields
exist on usage_metadata: cached_content_token_count, cache_tokens_details, traffic_type.

This harness drives a short REAL audio session (native-audio model needs audio; it
rejects TEXT with 1007) through the production adapter, registers the adapter's
diagnostic _on_raw_usage hook to dump the FULL usage_metadata per turn, and runs the
SAME script twice: compression OFF (baseline) then ON (low trigger so it must fire
within a few turns). Then it diffs the raw fields.

Interpretation (bd polyglot-pdf-h04c):
  - THE EVICTION SIGNAL IS A DROP IN prompt_token_count ACROSS TURNS with
    compression on (e.g. 1,972 -> 1,046 crossing trigger=1500/window=800, bd eycd).
    The server evicts old context, so the next turn re-bills a SMALLER prompt.
  - cached_content_token_count is a SECONDARY diagnostic only; on SDK 2.8 it stays
    None even while eviction is demonstrably working. Do not key the verdict on it.
  - If prompt_token_count climbs past the trigger with no drop -> silent no-op.

No PII: fictional prompts; synthetic form ids. Run from repo root with GEMINI_API_KEY:
    backend/.venv/Scripts/python.exe scripts/spikes/diag_compression_usage.py \
        --trigger 1500 --window 800 --turns 10
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import sys
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

from backend.adapters.live_ai_gemini import LiveAIGemini  # noqa: E402
from backend import config as _config  # noqa: E402

MODEL = "gemini-3.1-flash-live-preview"  # 2.5 is unstable on audio (bd daa)

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

_AUDIO_IN_RATE = 16000
_CHUNK_MS = 40
_clip_cache: dict[str, bytes] = {}

# The raw usage_metadata fields we care about for activation-vs-no-op. We dump ALL
# scalar fields anyway, but these are the headline ones.
_KEY_FIELDS = [
    "prompt_token_count",
    "cached_content_token_count",
    "response_token_count",
    "total_token_count",
    "traffic_type",
]


def _synth_pcm16(text: str) -> bytes:
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
    if sr != _AUDIO_IN_RATE:
        n_out = int(len(y) * _AUDIO_IN_RATE / sr)
        y = np.interp(np.linspace(0, len(y), n_out, endpoint=False),
                      np.arange(len(y)), y).astype("float32")
    pcm = (np.clip(y, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    _clip_cache[text] = pcm
    return pcm


def _pcm_chunks(pcm: bytes) -> list[bytes]:
    bytes_per_chunk = int(_AUDIO_IN_RATE * (_CHUNK_MS / 1000.0)) * 2
    return [pcm[i:i + bytes_per_chunk] for i in range(0, len(pcm), bytes_per_chunk)]


def _make_settings(enabled: bool, trigger: int, window: int):
    overrides = {"CONTEXT_COMPRESSION_ENABLED": enabled}
    if enabled:
        overrides["CONTEXT_COMPRESSION_TRIGGER_TOKENS"] = trigger
        overrides["CONTEXT_COMPRESSION_WINDOW_TOKENS"] = window
    s = _config.Settings(**overrides)
    # Neutralize the VAD 1007 bug (bd p1t): send only {disabled: True}.
    s.VAD_START_SENSITIVITY = "UNSPECIFIED"
    s.VAD_END_SENSITIVITY = "UNSPECIFIED"
    s.VAD_PREFIX_PADDING_MS = None
    s.VAD_SILENCE_DURATION_MS = None
    return s


def _dump_usage(usage) -> dict:
    """Snapshot every scalar field of a usage_metadata object (pydantic model)."""
    out: dict = {}
    try:
        # google-genai usage_metadata is a pydantic model; model_dump gives everything.
        out = usage.model_dump(exclude_none=False)
    except Exception:
        # Fallback: pull the known fields by getattr.
        for f in _KEY_FIELDS:
            out[f] = getattr(usage, f, None)
    return out


async def _drive(label: str, settings, n_turns: int) -> list[dict]:
    """Drive one audio session; return the raw usage dump for each billed turn."""
    _orig = _config.get_settings
    _config.get_settings = lambda s=settings: s
    captured: list[dict] = []
    try:
        adapter = LiveAIGemini(api_key=os.getenv("GEMINI_API_KEY"), model=MODEL)
        adapter.set_session_context(form_session_id=f"diag-{label}", form_id="DIAG")
        adapter._on_raw_usage = lambda u: captured.append(_dump_usage(u))

        async def _noop(*_a, **_k):
            return None

        adapter.set_callbacks(
            on_form_update=_noop, on_transcript=_noop, on_audio=_noop,
            on_tool_call=_noop,
            system_instruction="You are a form-filling assistant. Keep spoken replies very short.",
            tool_declarations=None, enable_transcripts=False,
        )

        ready = False
        for _ in range(150):
            if getattr(adapter, "_session_ready", False):
                ready = True
                break
            await asyncio.sleep(0.1)
        if not ready:
            print(f"  [warn] {label}: session never ready; skipping")
            try:
                await adapter.finalize()
            except Exception:
                pass
            return captured

        last_total = 0
        for i in range(n_turns):
            pcm = _synth_pcm16(PROMPTS[i % len(PROMPTS)])
            await adapter.send_activity_start()
            for chunk in _pcm_chunks(pcm):
                await adapter.stream_audio(chunk)
                await asyncio.sleep(_CHUNK_MS / 1000.0)
            await adapter.send_activity_end()
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
                print(f"  [warn] {label} turn {i + 1}: no token update in 45s")
        try:
            await adapter.finalize()
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] {label} finalize: {type(e).__name__}: {e}")
    finally:
        _config.get_settings = _orig
    return captured


def _print_turns(label: str, dumps: list[dict]) -> None:
    print(f"\n{'=' * 78}\n{label}\n{'=' * 78}")
    if not dumps:
        print("  (no usage captured)")
        return
    hdr = "  " + " ".join(f"{k:>14}" for k in ["turn"] + _KEY_FIELDS)
    print(hdr)
    for i, d in enumerate(dumps, 1):
        row = [f"{i:>14}"]
        for k in _KEY_FIELDS:
            v = d.get(k)
            row.append(f"{v if v is not None else '-':>14}")
        print("  " + " ".join(row))


def _all_field_union(dumps_on: list[dict], dumps_off: list[dict]) -> list[str]:
    keys = set()
    for d in dumps_on + dumps_off:
        keys.update(d.keys())
    return sorted(keys)


async def main_async(args: argparse.Namespace) -> int:
    if not os.getenv("GEMINI_API_KEY"):
        print("GEMINI_API_KEY not set; cannot run the diagnostic.")
        return 1
    try:
        for p in PROMPTS[: min(args.turns, len(PROMPTS))]:
            _synth_pcm16(p)
    except Exception as e:  # noqa: BLE001
        print(f"Audio synth failed ({type(e).__name__}: {e}); cannot run.")
        return 1
    print(f"Synthesized {len(_clip_cache)} clips. Model={MODEL}, "
          f"trigger={args.trigger}, window={args.window}, turns={args.turns}\n")

    off = await _drive("off", _make_settings(False, 0, 0), args.turns)
    on = await _drive("on", _make_settings(True, args.trigger, args.window), args.turns)

    _print_turns("COMPRESSION OFF (baseline) -- raw usage_metadata", off)
    _print_turns("COMPRESSION ON  (low trigger) -- raw usage_metadata", on)

    # Verdict (bd polyglot-pdf-h04c): the eviction signal is a turn-over-turn DROP
    # in prompt_token_count with compression on. cached_content_token_count stays
    # None on SDK 2.8 even while eviction works -- it is reported as a secondary
    # diagnostic only, never the verdict.
    print(f"\n{'=' * 78}\nVERDICT\n{'=' * 78}")
    prompts_on = [d.get("prompt_token_count") or 0 for d in on]
    # Tolerate small jitter; a real eviction drops by hundreds of tokens.
    drops = [(i + 2, prompts_on[i], prompts_on[i + 1])
             for i in range(len(prompts_on) - 1)
             if prompts_on[i + 1] < prompts_on[i] - 50]
    evicted = bool(drops)
    peak_prompt_on = max(prompts_on) if prompts_on else 0
    crossed = peak_prompt_on > args.trigger
    cached_on = [d.get("cached_content_token_count") for d in on]
    cached_nonzero = any(c for c in cached_on if c)

    # Fields present in the dumps that aren't the three the adapter already uses.
    extra_fields = [f for f in _all_field_union(on, off)
                    if f not in ("prompt_token_count", "response_token_count",
                                 "total_token_count", "prompt_tokens_details",
                                 "response_tokens_details")]
    print(f"  prompt_token_count (ON) peaked at {peak_prompt_on} "
          f"({'CROSSED' if crossed else 'did NOT cross'} trigger {args.trigger})")
    for turn, before, after in drops:
        print(f"  prompt DROP at turn {turn}: {before} -> {after} (eviction signal)")
    print(f"  cached_content_token_count (ON) ever non-zero: {cached_nonzero} (secondary only)")
    print(f"  extra usage_metadata fields seen: {extra_fields or 'NONE'}")
    print("  traffic_type (ON, last): "
          f"{on[-1].get('traffic_type') if on else '-'} | "
          f"(OFF, last): {off[-1].get('traffic_type') if off else '-'}")

    if evicted:
        print("\n  => EVICTION CONFIRMED: prompt_token_count dropped across a turn with")
        print("     compression on. The sliding window is working on this model.")
    elif crossed:
        print("\n  => Prompt crossed the trigger but never dropped: SILENT NO-OP on this")
        print("     model (config accepted, no eviction).")
    else:
        print("\n  => Prompt never crossed the trigger -- inconclusive; lower --trigger or")
        print("     raise --turns so compression is actually eligible to fire.")

    if args.json:
        Path(args.json).write_text(
            json.dumps({"off": off, "on": on}, indent=2, default=str), encoding="utf-8")
        print(f"\nWrote raw dumps: {args.json}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Probe Live API compression activation via raw usage_metadata.")
    ap.add_argument("--trigger", type=int, default=1500)
    ap.add_argument("--window", type=int, default=800)
    ap.add_argument("--turns", type=int, default=10)
    ap.add_argument("--json", type=str, default=None, help="optional path to dump raw per-turn usage")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
