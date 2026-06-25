# Secretary Gate 2 (LATENCY + caching facts) -- findings

bd polyglot-pdf-jnjj.27. Second secretary gate (runs after Gate 1 RECALL, which
shipped with a "feasibility promising" characterization, PR #240). The
`ask_secretary` call is BLOCKING -- the principal (live voice model) waits
mid-conversation for the answer -- so the question is: **is a cached flash-lite
lookup fast enough for live conversation UX?** Two parts: (a) establish Gemini
context-caching facts from authoritative sources; (b) measure the real round-trip.

Verdict stance: like Gate 1, this is a CHARACTERIZATION with a GO/KILL recorded on
"fast enough for live conversation" -- the maintainer reads the latency numbers.

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
best-effort implicit hits. This feeds Gate 3 (cost, jnjj.28); recorded here as a
fact, decided there.

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
against live Gemini in three arms over the I-90 static catalog (~9.5k tokens) + a
battery of prose queries (reused from the Gate-1 corpus):
- **uncached** -- full catalog sent fresh each call (the no-caching floor);
- **implicit** -- stable catalog prefix repeated; Gemini's automatic implicit cache
  may fire (a warm-up call primes it; `cached_content_token_count` confirms hits);
- **explicit** -- `caches.create()` the catalog once (creation timed separately),
  then `cached_content=` calls (guaranteed hit).

SCOPING (decided, not a deploy ask): the gate's real question is whether the
blocking flash-lite `generate_content` round-trip is fast enough. That is
measurable directly against live Gemini WITHOUT building the `ask_secretary` tool or
deploying the demo (same as the Gate-1 recall probe). The in-session WS tool-call
hop (principal->backend->secretary->back) is additive and small, already
characterized by the cost harness's per-turn latency. CAVEAT recorded: these are
API round-trip numbers, not full in-session tool-call numbers.

### Measured so far

- **Explicit cache CREATE latency: ~0.78s** (live, one-time per session, ~3k-token
  payload). Confirms flash-lite supports `caches.create()` and that cache creation
  is sub-second -- a one-time cost amortized across all session lookups.

### BLOCKED: live generation latency pending flash-lite availability

At measurement time (2026-06-19) `gemini-2.5-flash-lite` `generate_content` was
returning **503 UNAVAILABLE** persistently (sustained model-demand outage, not
transient -- exhausted 5 backoff retries + the SDK's own tenacity layer; 0/3 on a
bare availability probe). DIAGNOSTIC: the sibling `gemini-2.5-flash` answered
normally (~0.67s) and `caches.create()` on flash-lite itself worked (0.78s) -- so
the outage is **flash-lite-generation-specific**, not an account/key/region issue.

The probe is built, validated (dry-run + a working explicit-cache-create live), and
RETRY-RESILIENT; only the live generation numbers are blocked, purely by Gemini-side
availability. A re-run is scheduled for when flash-lite recovers. The GO/KILL on
"fast enough for live conversation" is recorded once those numbers land. (Early
indication, NOT the verdict: the working sibling flash at sub-second and the 0.78s
cache-create both point toward a comfortable GO, but the real flash-lite round-trip
must be measured before recording it.)
