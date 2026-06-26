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
import csv
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
    render_static_catalog,
    render_values_tail,
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
            # 5xx (e.g. 503 overload) -- availability; try the next model.
            last = "%s: %s" % (m, type(exc).__name__)
            print("  (model %s unavailable [5xx], trying next)" % m, flush=True)
        except genai.errors.ClientError as exc:
            # 4xx. 404 (model not found) / 429 (rate/quota) are AVAILABILITY cases
            # for fallback purposes -- try the next model. Other 4xx (401/403 auth,
            # 400 bad request) are config errors -- fail fast, do not mask them.
            code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            if code in (404, 429):
                last = "%s: ClientError %s" % (m, code)
                print("  (model %s unavailable [%s], trying next)" % (m, code), flush=True)
            else:
                print("ABORT: config/auth error on model %s: %s"
                      % (m, type(exc).__name__), flush=True)
                raise
    print("ALL fallback models unavailable (%s)" % last, flush=True)
    sys.exit(2)


async def _timed_call(client, *, contents, cached_content=None, mime="application/json",
                      max_retries=5):
    """One generate_content call; returns (call_s, blocked_s, cached, prompt).

    Retries transient 503 UNAVAILABLE (flash-lite demand spikes) with exponential
    backoff. Returns TWO latencies (Codex finding -- the principal is blocked for the
    WHOLE retry interval, so the gate must not hide backoff):
      call_s    -- the successful attempt's wall time (the clean round-trip);
      blocked_s -- wall time from the FIRST attempt incl. all retry backoff (the
                   real conversational pause when the model is overloaded).
    On a clean call the two are equal. The report uses blocked_s for the gate and
    flags any case where they diverge (a retry happened).
    """
    cfg_kwargs = {"response_mime_type": mime}
    if cached_content is not None:
        cfg_kwargs["cached_content"] = cached_content
    config = types.GenerateContentConfig(**cfg_kwargs)
    attempt = 0
    t_first = time.monotonic()
    while True:
        t0 = time.monotonic()
        try:
            resp = await client.aio.models.generate_content(
                model=MODEL, contents=contents, config=config,
            )
            now = time.monotonic()
            call_s = now - t0
            blocked_s = now - t_first
            um = resp.usage_metadata
            cached = getattr(um, "cached_content_token_count", 0) or 0 if um else 0
            prompt = getattr(um, "prompt_token_count", 0) or 0 if um else 0
            return call_s, blocked_s, cached, prompt
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
    ap.add_argument("--n", type=int, default=0,
                    help="Queries to time per arm. DEFAULT 0 = FULL corpus (the "
                         "verdict basis -- a small n samples only the easy tiers and "
                         "hides the latency tail, Codex finding). Pass a small n only "
                         "for a quick smoke check, NOT for a GO/KILL.")
    ap.add_argument("--arms", default="uncached,implicit",
                    help="Comma list from {uncached,implicit,explicit}. Default omits "
                         "explicit: the secretary uses IMPLICIT caching now "
                         "(explicit deferred to scale, bd jnjj.41). Add explicit "
                         "to gather the deferred-decision numbers.")
    ap.add_argument("--dry-run", action="store_true", help="No API calls; wiring check.")
    ap.add_argument("--model", default=None,
                    help="Override the preferred model (else the fallback chain "
                         "starting at gemini-2.5-flash-lite). Falls through to an "
                         "available model on a single-model outage.")
    args = ap.parse_args()

    arms_in = [a.strip() for a in args.arms.split(",") if a.strip()]
    valid_arms = {"uncached", "implicit", "explicit"}
    bad_arms = [a for a in arms_in if a not in valid_arms]
    if bad_arms:
        print("ERROR: unknown arm(s) %s; valid: %s" % (bad_arms, sorted(valid_arms)),
              flush=True)
        sys.exit(2)

    arms = arms_in
    # STRATIFY across difficulty tiers, not the first-N (which is one tier block):
    # the corpus is grouped by tier, so build_corpus()[:n] would skip the longer
    # synthesis/distant/applicability queries whose generation dominates latency.
    # Round-robin by tier so a small --n still spans easy..applicability. n<=0 or
    # n>=len uses the FULL corpus.
    full = build_corpus()
    if args.n <= 0 or args.n >= len(full):
        corpus = full
    else:
        by_tier = {}
        for c in full:
            by_tier.setdefault(c.tier, []).append(c)
        corpus, ti = [], 0
        tiers = list(by_tier.values())
        while len(corpus) < args.n:
            row = tiers[ti % len(tiers)]
            idx = ti // len(tiers)
            if idx < len(row):
                corpus.append(row[idx])
            ti += 1
            if ti > 10000:  # safety
                break
    queries = [c.query for c in corpus]

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    schema = json.load(open(os.path.join(root, "form-kits", "i-90", "schema.json"),
                            encoding="utf-8"))
    # Value-FREE static catalog = the cacheable prefix (session-invariant). Values +
    # applicability ride a SEPARATE fresh tail, so the cached prefix stays stable as
    # answers change (Codex finding: do not bake per-user values into the catalog).
    catalog = render_static_catalog(schema)
    values_tail = render_values_tail(schema, FIELD_VALUES, SHOWN_MAP)
    cat_tokens = estimate_tokens(catalog)
    tail_tokens = estimate_tokens(values_tail)
    tier_counts = {}
    for c in corpus:
        tier_counts[c.tier] = tier_counts.get(c.tier, 0) + 1
    print("static catalog ~%d tok | values tail ~%d tok | %d queries %s | arms=%s" % (
        cat_tokens, tail_tokens, len(queries), tier_counts, arms), flush=True)

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
    per_case_rows = []
    cache_create_latency = None
    cache_name = None

    for arm in arms:
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
            # explicit: the catalog lives in the cache; only the fresh tail + query
            # go in contents.
            await _timed_call(client, contents=[values_tail + "\n\nQUESTION: " + warm_q],
                              cached_content=cache_name)
        else:
            await _timed_call(client, contents=[SECRETARY_SI + "\n\n" + catalog + "\n\n"
                                                + values_tail + "\n\nQUESTION: " + warm_q])

        lats, blocked_lats, cached_hits, n_retried = [], [], [], 0
        for i, case in enumerate(corpus):
            q = case.query
            if arm == "explicit":
                contents = [values_tail + "\n\nQUESTION: " + q]
                call_s, blocked_s, cached, prompt = await _timed_call(
                    client, contents=contents, cached_content=cache_name)
            else:
                # uncached + implicit send: [SI][static catalog][fresh values tail]
                # [query]. The VALUE-FREE catalog is the stable leading prefix that
                # implicit caching keys on; values ride the fresh tail.
                contents = [SECRETARY_SI + "\n\n" + catalog + "\n\n" + values_tail
                            + "\n\nQUESTION: " + q]
                call_s, blocked_s, cached, prompt = await _timed_call(
                    client, contents=contents)
            lats.append(call_s)
            blocked_lats.append(blocked_s)
            cached_hits.append(cached)
            retried = blocked_s - call_s > 0.05
            if retried:
                n_retried += 1
            # Per-case row -- so the tail characterization (which case_id/tier spiked,
            # and whether it correlated with cache state) is AUDITABLE from the
            # artifact (Codex finding), not just an aggregate claim.
            per_case_rows.append({
                "arm": arm, "case_id": case.case_id, "tier": case.tier,
                "call_s": round(call_s, 3), "blocked_s": round(blocked_s, 3),
                "cached_tokens": cached, "prompt_tokens": prompt,
                "retried": int(retried),
            })
            print("    [%s %d/%d] %-26s (%s) call=%.3fs blocked=%.3fs (cached=%d, prompt=%d)%s" % (
                arm, i + 1, len(corpus), case.case_id, case.tier, call_s, blocked_s,
                cached, prompt, " RETRIED" if retried else ""), flush=True)

        summ = _summary(arm, lats)
        # blocked-latency summary (retry-inclusive) -- the honest gate number.
        bsumm = _summary(arm + "_blocked", blocked_lats)
        summ["blocked"] = {k: bsumm[k] for k in bsumm if k != "arm"}
        summ["n_retried"] = n_retried
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
    print("\n=== LATENCY (seconds) -- call_s = clean round-trip; blocked = "
          "retry-inclusive (the real conversational pause) ===", flush=True)
    print("%-10s %4s %7s %8s %6s %6s %8s %8s %7s %11s" % (
        "arm", "n", "mean", "median", "p90", "max", "blk_mean", "blk_max",
        "retried", "cache_hit%"), flush=True)
    for arm in arms:
        s = results.get(arm, {})
        if not s.get("n"):
            continue
        blk = s.get("blocked", {})
        print("%-10s %4d %7.3f %8.3f %6.3f %6.3f %8.3f %8.3f %7d %10.0f%%" % (
            arm, s["n"], s["mean_s"], s["median_s"], s["p90_s"], s["max_s"],
            blk.get("mean_s", s["mean_s"]), blk.get("max_s", s["max_s"]),
            s.get("n_retried", 0), 100 * s.get("cache_hit_rate", 0)),
            flush=True)
    if any(results.get(a, {}).get("n_retried", 0) for a in arms):
        print("NOTE: some calls retried (503); blk_* columns include backoff -- the "
              "honest blocking pause. For the GO use a run with retried=0, or the "
              "clean call_s of a 0-retry run.", flush=True)
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
            "static_catalog_tokens_est": cat_tokens,
            "values_tail_tokens_est": tail_tokens,
            "queries": len(queries),
            "query_tiers": tier_counts,
            "arms": results,
            "explicit_cache_create_latency_s": cache_create_latency,
        }, f, indent=2)
    # Per-case rows (CSV) -- so the tail claim (which case spiked, cache state) is
    # auditable, not just aggregates (Codex finding).
    csv_path = os.path.join(OUT_DIR, "secretary_latency_%s.csv" % stamp)
    if per_case_rows:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(per_case_rows[0].keys()))
            w.writeheader()
            w.writerows(per_case_rows)
    print("\nwrote %s\nwrote %s" % (meta_path, csv_path), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
