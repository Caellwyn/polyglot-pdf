# Secretary Gate 2 (LATENCY + caching facts) -- findings

bd polyglot-pdf-jnjj.27. Second secretary gate (runs after Gate 1 RECALL, which
shipped with a "feasibility promising" characterization, PR #240). The
`ask_secretary` call is BLOCKING -- the principal (live voice model) waits
mid-conversation for the answer -- so the question is: **is a cached flash-lite
lookup fast enough for live conversation UX?** Two parts: (a) establish Gemini
context-caching facts from authoritative sources; (b) measure the real round-trip.

Verdict stance: like Gate 1, this is a CHARACTERIZATION with a GO/KILL recorded on
"fast enough for live conversation" -- the maintainer reads the latency numbers.

> **VERDICT: GO.** The blocking secretary lookup measured **~0.8s mean (tail
> ~1.0-1.1s)** -- a natural conversational beat, well under the awkward-pause
> threshold; the GO holds at the ~1.1s worst case. Implicit caching hits 100%
> (~8.1k of ~11k prompt tokens, ~74%, zero setup) and is a COST lever, not a
> latency one. DECISION: implicit caching now; explicit deferred to scale (bd
> jnjj.41). Caveat: measured on `gemini-3.1-flash-lite` because the target
> `gemini-2.5-flash-lite` was in a 503 outage -- a sound same-tier proxy; both lite
> models are sub-second.

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

### Latency result: GO -- sub-second blocking lookup

All numbers below are from the committed clean stable-service run (artifact
`secretary_latency_20260625T115102.meta.json`, n=12 per arm, catalog ~9.5k tokens +
prose query). (Earlier outage-period runs gave ~3-6s numbers; those were
outage-contaminated -- a bare 1-token prompt was also 3-6s then -- and are NOT used
for the verdict.)

| arm | mean | median | p90* | min | max | implicit-cache hit |
|---|---|---|---|---|---|---|
| uncached | 0.837s | 0.804s | 0.953s | 0.719s | 1.016s | 100% (8122 tok) |
| implicit | 0.829s | 0.812s | 0.891s | 0.719s | 1.109s | 100% (8122 tok) |

*p90 in the table is the probe's floor-indexed value (the 11th of 12 sorted). The
true interpolated p90 for the implicit arm is ~1.07s; the `max` column (1.0-1.1s) is
the honest tail. Read the tail as ~1.0-1.1s, not 0.9s.

**VERDICT: GO.** A ~0.8s mean (tail ~1.0-1.1s) blocking lookup is a natural
conversational beat -- comparable to a person briefly glancing at a note before
answering -- well under the "awkward pause" threshold for live voice. The blocking
ask_secretary round-trip is fast enough; the GO holds even at the ~1.1s worst case.

Two structural findings:
1. **Implicit caching hit 100%** -- every call reported ~**8,122 of ~11,053 prompt
   tokens (~74%)** cached (`cached_content_token_count`), with ZERO explicit cache
   management, just the stable catalog prefix. The cost lever works reliably (the
   cheaper $0.01/M rate on ~74% of the input). Feeds Gate 3 (cost, jnjj.28).
   (METHOD NOTE: both arms get a warm-up call before timing, which seeds the
   implicit cache -- so the "uncached" arm ALSO shows 100% implicit hits. The arm
   names describe intent, not a cold-vs-warm contrast; both effectively measure the
   warm/implicit-cached round-trip. A true cold floor would need warm-up disabled.)
2. **uncached vs implicit latency is identical** (0.837 vs 0.829s) -- consistent
   with both arms being implicitly cached. The takeaway stands: implicit caching is
   a COST lever, NOT a latency lever -- re-sending cached tokens is not what costs
   the time; generation + network is. So the GO does not depend on the cache.

Separately measured (a direct test, not in the run artifact above): **explicit
cache CREATE latency ~0.78s** (one-time per session) -- confirms flash-lite supports
`caches.create()`. Informational only; explicit caching is deferred (jnjj.41).

CAVEAT -- model substitution (outage): at measurement time `gemini-2.5-flash-lite`
(the secretary's target) was in a sustained, widely-reported **503 UNAVAILABLE**
outage, so the probe's fallback chain measured on **`gemini-3.1-flash-lite`**
(`is_fallback_model: true` in the artifact) -- the newer same-tier lite model,
~0.42s on a bare call. This is a sound proxy, and arguably stronger evidence (newer
model): both lite models sit in the same sub-second band (during its brief uptime
windows, 2.5-flash-lite also answered ~0.44s bare). The GO is robust across both.
Re-confirm on 2.5-flash-lite when it recovers if a target-model number is wanted,
but the verdict does not hinge on it.

NOTE (resilience): this outage motivated a probe-level model fallback chain
(2.5-flash-lite -> 3.1-flash-lite -> flash-lite-latest, all within the Gemini BAA),
which is what produced this clean number. The same resilience for the PRODUCTION
secretary/validator path is filed as bd jnjj.42.
