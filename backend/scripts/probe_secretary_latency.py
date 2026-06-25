"""Secretary Gate 2 LATENCY probe -- is a cached flash-lite lookup fast enough?

bd polyglot-pdf-jnjj.27. The ask_secretary call is BLOCKING: the principal (live
voice model) waits mid-conversation for the secretary's answer. This probe measures
the real round-trip latency of that lookup against LIVE gemini-2.5-flash-lite, in
three caching arms over the same I-90 static catalog + a battery of prose queries
(reused from the Gate-1 corpus):

  uncached   every call sends the full ~9.5k-token catalog inline (no explicit
             cache). NOTE: this arm is NOT a cold/no-cache floor -- the warm-up call
             below seeds Gemini's IMPLICIT cache (on by default for 2.5+), so the
             stable catalog prefix still gets implicit hits here too. In practice
             this arm measures the same warm round-trip as `implicit`; the pair
             exists to confirm that (it does -- the latencies match). For a true
             cold floor, warm-up would have to be disabled.
  implicit   stable catalog prefix repeated call-to-call; Gemini's implicit cache
             fires. A warm-up call primes it; measured calls report
             cached_content_token_count to confirm hits.
  explicit   client.caches.create() the catalog once (creation latency measured
             separately), then cached_content= calls. Guaranteed cache hit.

SCOPING NOTE (decided, not a deploy ask): the bead says "measure on the live demo"
with the principal emitting ask_secretary. That tool is not built yet and the demo
would need a deploy (a per-instance maintainer ask). The LATENCY the gate cares
about -- "is the blocking flash-lite lookup too slow for live conversation UX" -- is
the generate_content round-trip itself, which is measurable directly against live
Gemini WITHOUT the principal/tool wiring or a deploy (same approach as the Gate-1
recall probe, which called flash-lite directly). This probe measures that API
round-trip. It does NOT include the in-session WS tool-call hop (principal->backend
->secretary->back); that overhead is small and already characterized by the cost
harness's per-turn latency, and is additive to the numbers here. Recorded as a
caveat in the findings.

PII: the corpus is SYNTHETIC (fabricated values). Latency artifacts are safe to
persist. Still logs model/timings/token-counts only, never content.

Usage:
    GEMINI_API_KEY=... PYTHONPATH=. python backend/scripts/probe_secretary_latency.py
    # fewer queries / arms for a quick check:
    ... probe_secretary_latency.py --n 8 --arms uncached,implicit
    # validate wiring offline (no API calls):
    ... probe_secretary_latency.py --dry-run

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import os
import statistics
import sys
import time

from google import genai
from google.genai import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.scripts.secretary_context import (  # noqa: E402
    render_secretary_context,
    estimate_tokens,
)
from backend.scripts.secretary_recall_corpus import (  # noqa: E402
    build_corpus,
    FIELD_VALUES,
    SHOWN_MAP,
)

MODEL = "gemini-2.5-flash-lite"

# Cheap-model fallback chain (all Gemini, so within the same BAA family). If the
# preferred model is in a 503 outage (as 2.5-flash-lite was 2026-06-19), the probe
# degrades to the next AVAILABLE one so measurement is not blocked by a Google-side
# outage. The model actually used is recorded in the artifact.
MODEL_FALLBACKS = [
    "gemini-2.5-flash-lite",        # preferred (the secretary's target model)
    "gemini-3.1-flash-lite",        # newer lite tier; sub-second when 2.5-lite is down
    "gemini-flash-lite-latest",     # rolling alias to the current lite model
]

OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts", "spikes", "data",
)

SECRETARY_SI = (
    "You are the secretary for a USCIS I-90 form-filling assistant. Answer the "
    "colleague's prose question about the form briefly, using only the field "
    "values provided. Return JSON: {\"answer\": \"<prose>\", \"sourced_from\": "
    "[\"<field_id>\", ...]}."
)


def _client() -> genai.Client:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("NO KEY in env GEMINI_API_KEY", flush=True)
        sys.exit(2)
    return genai.Client(api_key=key)


async def _resolve_model(client, preferred=None) -> str:
    """Return the first AVAILABLE model from the fallback chain (a 1-token probe
    per candidate). Lets the measurement survive a single-model outage. Reassigns
    the module global MODEL so the rest of the probe uses the chosen one."""
    global MODEL
    chain = ([preferred] if preferred else []) + [m for m in MODEL_FALLBACKS
                                                  if m != preferred]
    first = chain[0]  # the requested/preferred model -- success on it is NOT a fallback
    last = None
    for m in chain:
        try:
            await client.aio.models.generate_content(model=m, contents="OK")
            MODEL = m
            if m != first:
                print("NOTE: requested model %s unavailable; using fallback %s"
                      % (first, m), flush=True)
            return m
        except genai.errors.ServerError as exc:
            last = "%s: %s" % (m, type(exc).__name__)
            print("  (model %s unavailable, trying next)" % m, flush=True)
    print("ALL fallback models unavailable (%s)" % last, flush=True)
    sys.exit(2)


def _values_block(field_values: dict) -> str:
    """The small fresh tail: current values, one per line (the per-query part)."""
    lines = ["CURRENT VALUES:"]
    for fid, v in field_values.items():
        lines.append("  %s = %s" % (fid, v))
    return "\n".join(lines)


async def _timed_call(client, *, contents, cached_content=None, mime="application/json",
                      max_retries=5):
    """One generate_content call; returns (latency_s, cached_tokens, prompt_tokens).

    Retries transient 503 UNAVAILABLE (flash-lite demand spikes) with exponential
    backoff. The RETRY WAIT is excluded from the measured latency -- only the
    successful call's wall time is timed, so an overloaded-model retry does not
    inflate the round-trip number we report.
    """
    cfg_kwargs = {"response_mime_type": mime}
    if cached_content is not None:
        cfg_kwargs["cached_content"] = cached_content
    config = types.GenerateContentConfig(**cfg_kwargs)
    attempt = 0
    while True:
        t0 = time.monotonic()
        try:
            resp = await client.aio.models.generate_content(
                model=MODEL, contents=contents, config=config,
            )
            dt = time.monotonic() - t0
            um = resp.usage_metadata
            cached = getattr(um, "cached_content_token_count", 0) or 0 if um else 0
            prompt = getattr(um, "prompt_token_count", 0) or 0 if um else 0
            return dt, cached, prompt
        except genai.errors.ServerError as exc:
            attempt += 1
            if attempt > max_retries:
                raise
            wait = min(2 ** attempt, 30)
            print("    (503/transient; retry %d/%d after %ds)" % (attempt, max_retries, wait),
                  flush=True)
            await asyncio.sleep(wait)


def _summary(label, lats):
    if not lats:
        return {"arm": label, "n": 0}
    s = sorted(lats)
    return {
        "arm": label, "n": len(s),
        "mean_s": round(statistics.mean(s), 3),
        "median_s": round(statistics.median(s), 3),
        "p90_s": round(s[min(len(s) - 1, int(0.9 * len(s)))], 3),
        "min_s": round(s[0], 3), "max_s": round(s[-1], 3),
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12, help="Number of queries to time per arm.")
    ap.add_argument("--arms", default="uncached,implicit",
                    help="Comma list: uncached,implicit,explicit. Default omits "
                         "explicit: the secretary uses IMPLICIT caching now "
                         "(explicit deferred to scale, bd jnjj.41). Add explicit "
                         "to gather the deferred-decision numbers.")
    ap.add_argument("--dry-run", action="store_true", help="No API calls; wiring check.")
    ap.add_argument("--model", default=None,
                    help="Override the preferred model (else the fallback chain "
                         "starting at gemini-2.5-flash-lite). Falls through to an "
                         "available model on a single-model outage.")
    args = ap.parse_args()

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    corpus = build_corpus()[: args.n]
    queries = [c.query for c in corpus]

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    schema = json.load(open(os.path.join(root, "form-kits", "i-90", "schema.json"),
                            encoding="utf-8"))
    catalog = render_secretary_context(schema, FIELD_VALUES, SHOWN_MAP)
    values_tail = _values_block(FIELD_VALUES)
    cat_tokens = estimate_tokens(catalog)
    print("catalog ~%d tokens | %d queries | arms=%s" % (cat_tokens, len(queries), arms),
          flush=True)

    if args.dry_run:
        print("[dry-run] wiring ok; would time %d calls/arm against %s." % (len(queries), MODEL),
              flush=True)
        return

    client = _client()
    preferred_model = args.model or MODEL_FALLBACKS[0]
    used_model = await _resolve_model(client, preferred=args.model)
    is_fallback = used_model != preferred_model
    print("using model: %s%s" % (used_model, " (fallback)" if is_fallback else ""),
          flush=True)
    results = {}
    cache_create_latency = None
    cache_name = None

    for arm in arms:
        lats, cached_hits = [], []
        if arm == "explicit":
            # Create the cache once; time creation separately.
            t0 = time.monotonic()
            cache = await client.aio.caches.create(
                model=MODEL,
                config=types.CreateCachedContentConfig(
                    system_instruction=SECRETARY_SI,
                    contents=[catalog],
                    ttl="600s",
                ),
            )
            cache_create_latency = round(time.monotonic() - t0, 3)
            cache_name = cache.name
            print("  [explicit] cache created in %.3fs: %s" % (cache_create_latency, cache_name),
                  flush=True)

        # Warm-up (not timed): primes implicit cache / first-call overhead.
        warm_q = "What is their date of birth?"
        if arm == "explicit":
            await _timed_call(client, contents=[values_tail + "\n\nQUESTION: " + warm_q],
                              cached_content=cache_name)
        else:
            await _timed_call(client, contents=[SECRETARY_SI + "\n\n" + catalog + "\n\n"
                                                + values_tail + "\n\nQUESTION: " + warm_q])

        for i, q in enumerate(queries):
            if arm == "explicit":
                contents = [values_tail + "\n\nQUESTION: " + q]
                dt, cached, prompt = await _timed_call(client, contents=contents,
                                                       cached_content=cache_name)
            else:
                # uncached + implicit send the same payload; implicit relies on the
                # stable leading catalog prefix firing Gemini's automatic cache.
                contents = [SECRETARY_SI + "\n\n" + catalog + "\n\n" + values_tail
                            + "\n\nQUESTION: " + q]
                dt, cached, prompt = await _timed_call(client, contents=contents)
            lats.append(dt)
            cached_hits.append(cached)
            print("    [%s %d/%d] %.3fs (cached_tokens=%d, prompt=%d)" % (
                arm, i + 1, len(queries), dt, cached, prompt), flush=True)

        summ = _summary(arm, lats)
        summ["mean_cached_tokens"] = round(statistics.mean(cached_hits), 1) if cached_hits else 0
        summ["cache_hit_rate"] = round(sum(1 for c in cached_hits if c > 0) / len(cached_hits), 3) if cached_hits else 0
        results[arm] = summ

        if arm == "explicit" and cache_name:
            try:
                await client.aio.caches.delete(name=cache_name)
                print("  [explicit] cache deleted", flush=True)
            except Exception as exc:  # noqa: BLE001
                print("  [explicit] cache delete failed: %s" % type(exc).__name__, flush=True)

    # ---- report ----
    print("\n=== LATENCY (seconds) ===", flush=True)
    print("%-10s %4s %7s %8s %6s %6s %6s %11s %9s" % (
        "arm", "n", "mean", "median", "p90", "min", "max", "cache_hit%", "cachedTok"),
        flush=True)
    for arm in arms:
        s = results.get(arm, {})
        if not s.get("n"):
            continue
        print("%-10s %4d %7.3f %8.3f %6.3f %6.3f %6.3f %10.0f%% %9.1f" % (
            arm, s["n"], s["mean_s"], s["median_s"], s["p90_s"], s["min_s"],
            s["max_s"], 100 * s.get("cache_hit_rate", 0), s.get("mean_cached_tokens", 0)),
            flush=True)
    if cache_create_latency is not None:
        print("\nexplicit cache CREATE latency: %.3fs (one-time, per session)" % cache_create_latency,
              flush=True)

    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    meta_path = os.path.join(OUT_DIR, "secretary_latency_%s.meta.json" % stamp)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "bead": "polyglot-pdf-jnjj.27",
            "stamp": stamp,
            "model": MODEL,
            "preferred_model": preferred_model,
            "is_fallback_model": is_fallback,
            "catalog_tokens_est": cat_tokens,
            "queries": len(queries),
            "arms": results,
            "explicit_cache_create_latency_s": cache_create_latency,
        }, f, indent=2)
    print("\nwrote %s" % meta_path, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
