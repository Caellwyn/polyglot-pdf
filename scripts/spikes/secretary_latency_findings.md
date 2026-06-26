# Secretary Gate 2 (LATENCY + caching facts) -- findings

bd polyglot-pdf-jnjj.27. Second secretary gate (runs after Gate 1 RECALL, which
shipped with a "feasibility promising" characterization, PR #240). The
`ask_secretary` call is BLOCKING -- the principal (live voice model) waits
mid-conversation for the answer -- so the question is: **is a cached flash-lite
lookup fast enough for live conversation UX?** Two parts: (a) establish Gemini
context-caching facts from authoritative sources; (b) measure the real round-trip.

Verdict stance: like Gate 1, this is a CHARACTERIZATION with a GO/KILL recorded on
"fast enough for live conversation" -- the maintainer reads the latency numbers.

> **VERDICT: CONDITIONAL GO.** On a full-corpus run (n=49/arm, all tiers) the
> blocking lookup is **median ~0.95s, p90 ~1.25s** -- conversational -- BUT the tail
> is heavy: 2/98 calls spiked to **8.5s and 20.2s** (no retries, not cache-related;
> random model-side spikes). Median-fast, but the tail is a real UX risk: ship it
> WITH a timeout + graceful filler on the blocking call (bd jnjj.43), not raw.
> Implicit caching hits 94-98% (zero setup) and is a COST lever, not a latency one.
> DECISION: implicit caching now; explicit deferred to scale (bd jnjj.41). Caveat:
> measured on `gemini-3.1-flash-lite` (target `gemini-2.5-flash-lite` was in a 503
> outage) -- so the tail may be partly a degraded-service artifact; re-confirm on a
> healthy 2.5-flash-lite, but design for the tail regardless.

## Part (a) -- Gemini context-caching facts (authoritative)

Sources: the gemini-docs MCP (authoritative SDK/docs surface) + the live pricing
and caching pages (`ai.google.dev/gemini-api/docs/pricing`, `.../docs/caching`).
The vendored `docs/genai_docs/` is Live-API-only and has NO caching content, so the
bead's "vendored first" source did not cover this; recorded here from the next
authoritative tier (the live Google docs), per the bead's fallback order.

### The two caching modes

| | Implicit caching | Explicit caching |
|---|---|---|
| Enabled | ON by default, all Gemini 2.5+ models; nothing to do | Manual: `client.caches.create(...)` + `cached_content=` |
| Hit guarantee | Best-effort prefix match; NO guaranteed savings | Guaranteed hit while the cache lives |
| Min tokens (2.5 Flash family) | ~1024-2048 (docs cite 2048 for 2.5 Flash; a later reduction to 1024 reported) | 2048 for 2.5 Flash / 2.5 Pro (per gemini-docs MCP table) |
| Cost | discount passed on WHEN it hits (no storage fee) | 90% input-token discount + a storage fee per hour |
| Lifecycle | none (automatic) | TTL (default 1h, configurable), create/get/update/delete |
| Interactions API | supported | NOT supported (generateContent API only) |

To raise implicit-hit odds: put the large/common content FIRST in the prompt, and
send similar-prefix requests close together in time -- which a continuous fill
session naturally does.

### gemini-2.5-flash-lite specifics (the secretary model)

Pricing (paid/standard tier, per 1M tokens), from the live pricing page:
- input (text/image/video): **$0.10**; audio input: $0.30
- output: **$0.40**
- **cached input tokens (text/image/video): $0.01** (the 90%-off rate)
- **cache storage: $1.00 / 1M tokens / hour**
- free tier: context caching "Not available"

So flash-lite DOES support caching on the paid tier. NOTE: the gemini-docs MCP
table lists explicit-cache minimums for 2.5 Flash / 2.5 Pro but does NOT name
2.5-flash-lite; the published flash-lite caching PRICING confirms support, and the
2048 figure for the 2.5 Flash family is the best authoritative minimum to assume
until a flash-lite-specific number surfaces. Treat 2048 as the working minimum.

### Does our catalog clear the minimum?

YES, comfortably. The Gate-1 rendered static catalog measured **~9,500 tokens**
(grouped-by-section I-90, 132 fields) -- ~4.6x the 2048 explicit minimum and well
above the ~1-2k implicit minimum. Caching is viable on token-size grounds.

### Cost of holding an explicit cache (flash-lite)

At $1.00 / 1M tokens / hour, a ~9,500-token cache costs ~**$0.0095/hour** to store
(~1 cent/hr). For a session of minutes, storage cost is negligible; the question is
whether the 90% input discount on repeated secretary calls beats $0 storage +
best-effort implicit hits.

### DECISION (maintainer, 2026-06-19): implicit now, explicit at scale

**Use IMPLICIT caching for the secretary now.** It is free, on-by-default for 2.5+,
needs no lifecycle management, and the catalog clears its minimum. The existing
`TextAIGemini` adapter already sends requests as a stable catalog prefix + small
fresh tail -- the exact structure that maximizes implicit-hit odds.

**EXPLICIT caching is deferred to scale (~100 concurrent users; bd jnjj.41).** At
low/demo concurrency the per-hour storage fee + create/TTL/delete lifecycle is
overhead the input-discount does not pay back; explicit only wins once enough
concurrent sessions share the same cached catalog to amortize storage. Revisit when
the concurrency makes the discount beat implicit's best-effort hits net of storage.

### Cache-creation latency

NOT documented in any authoritative source found (the docs describe TTL/lifecycle
but not creation latency). This is exactly what part (b) must MEASURE, not cite.

### SDK shape (google-genai), for the eventual wiring

```python
cache = client.caches.create(
    model="gemini-2.5-flash-lite",
    config=types.CreateCachedContentConfig(
        system_instruction=SECRETARY_SI,
        contents=[static_catalog],     # the ~9.5k-token field catalog
        ttl="600s",
    ),
)
resp = client.models.generate_content(
    model="gemini-2.5-flash-lite",
    contents=[current_values + prose_query],   # small fresh tail
    config=types.GenerateContentConfig(cached_content=cache.name),
)
```

The existing `backend/adapters/text_ai_gemini.py` already factors the request as
`stable_prefix + fresh_tail` and logs `cached_content_token_count` / `cache_hit`
from `usage_metadata` -- built for IMPLICIT caching today, with a code note that
explicit `caches.create()` lands "once Gate 2" (this bead).

## Part (b) -- round-trip latency

### Methodology

`backend/scripts/probe_secretary_latency.py` times the BLOCKING flash-lite lookup
against live Gemini over the I-90 static catalog (~9.5k tokens) + a battery of prose
queries (reused from the Gate-1 corpus). Since the secretary uses IMPLICIT caching
now (decision above), the GO/KILL rests on the first two arms; the explicit arm is
informational for the deferred jnjj.41 decision (run with `--arms ...,explicit`):
- **uncached** -- full catalog sent fresh each call (the no-caching floor);
- **implicit** (the operative arm) -- stable catalog prefix repeated; Gemini's
  automatic implicit cache may fire (a warm-up call primes it;
  `cached_content_token_count` confirms hits);
- **explicit** (informational, deferred) -- `caches.create()` the catalog once
  (creation timed separately), then `cached_content=` calls (guaranteed hit).

SCOPING (decided, not a deploy ask): the gate's real question is whether the
blocking flash-lite `generate_content` round-trip is fast enough. That is
measurable directly against live Gemini WITHOUT building the `ask_secretary` tool or
deploying the demo (same as the Gate-1 recall probe). The in-session WS tool-call
hop (principal->backend->secretary->back) is additive and small, already
characterized by the cost harness's per-turn latency. CAVEAT recorded: these are
API round-trip numbers, not full in-session tool-call numbers.

### Latency result: CONDITIONAL GO -- ~1s typical, but a heavy unpredictable tail

Numbers from the committed full-corpus run (artifact
`secretary_latency_20260625T181149.meta.json`, **n=49 per arm across ALL 6
difficulty tiers**, value-FREE static catalog ~8.4k tokens cached prefix + ~1.6k
values tail + per-query prose). `retried=0` on every call, so these are clean
(no retry-backoff contamination). This SUPERSEDES an earlier n=12 run that, by
sampling only the first (easy/aliasing) tier block, hid the tail (Codex finding).

| arm | mean | median | p90 | **max** | retried | implicit-cache hit |
|---|---|---|---|---|---|---|
| uncached | 1.17s | 0.99s | 1.25s | **8.55s** | 0 | 94% (~7628 tok) |
| implicit | 1.35s | 0.94s | 1.24s | **20.22s** | 0 | 98% (~7960 tok) |

**VERDICT: CONDITIONAL GO.** The TYPICAL lookup is fine for live conversation --
**median ~0.95s, p90 ~1.25s** is a natural conversational beat. BUT the **tail is
heavy and unpredictable**: 2 of 98 calls spiked to **8.5s and 20.2s**, with
`retried=0` (NOT outage/retry artifacts) and NOT correlated with cache state (the
20s call was a normal cache HIT) or query tier -- i.e. random model-side generation
spikes. A 20s blocking pause mid-conversation is a real UX failure.

So the blocking round-trip is fast enough ON THE MEDIAN, but shipping it
unmitigated is NOT safe. **Required mitigation (a real follow-up, bd jnjj.43):** a
**timeout + graceful filler** on the blocking ask_secretary call -- if the secretary
hasn't answered in ~2-3s, the principal says a natural "let me check that for you"
and either continues async or proceeds. With that guard the median-fast lookup is a
clear GO; without it the tail is a liability. (This tail behavior may also be
partly the fallback model / a degraded service window -- see the model caveat -- so
re-confirm on a healthy 2.5-flash-lite, but DESIGN for the tail regardless.)

Two structural findings hold:
1. **Implicit caching hit 94-98%** -- ~7.6-8.0k of ~11.8k prompt tokens cached
   (`cached_content_token_count`) with ZERO setup, just the VALUE-FREE static
   catalog prefix. Confirms the prefix/tail split works AND still caches: the
   cacheable prefix is now genuinely session-invariant (no per-user values baked in
   -- Codex finding fixed). The cost lever works. Feeds Gate 3 (cost, jnjj.28).
2. **uncached vs implicit median latency is ~the same** (~0.95s) -- implicit caching
   is a COST lever, NOT a latency one; generation + network dominates, not
   re-sending cached tokens. So neither the GO nor the tail risk depends on the
   cache.

Separately measured (a direct test, not in this run): **explicit cache CREATE
latency ~0.78s** (one-time per session). Informational; explicit deferred (jnjj.41).

CAVEAT -- model substitution (outage): at measurement time `gemini-2.5-flash-lite`
(the secretary's target) was in a sustained, widely-reported **503 UNAVAILABLE**
outage, so the probe's fallback chain measured on **`gemini-3.1-flash-lite`**
(`is_fallback_model: true` in the artifact) -- the newer same-tier lite model. For
the MEDIAN this is a sound proxy (both lite models median sub-second). For the TAIL
it is a CAVEAT: the 8.5s/20s spikes were measured on the fallback during a degraded
window for the model family, so part of the heavy tail may be service degradation
rather than intrinsic. Re-confirm the tail on a healthy 2.5-flash-lite -- but the
mitigation (timeout + filler, jnjj.43) is warranted regardless, because cheap-model
tails are heavy in general and outages recur (jnjj.42).

NOTE (resilience): this outage motivated a probe-level model fallback chain
(2.5-flash-lite -> 3.1-flash-lite -> flash-lite-latest, all within the Gemini BAA),
which is what produced this clean number. The same resilience for the PRODUCTION
secretary/validator path is filed as bd jnjj.42.
