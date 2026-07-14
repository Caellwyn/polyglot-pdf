# Secretary implicit-cache in-session miss -- diagnosis (bd polyglot-pdf-2af7)

**Date:** 2026-07-14. **SDK:** google-genai 2.8.x (post-cutover; not stale).
**Status:** diagnosis complete (code-only, no live spend); the per-field
metadata `ask_secretary` waste is fixed in the same bead by SI/guidance changes.

## The two observations (from stress-run costs_i90-full_..._20260714T055241Z)

1. In a clean 10-question continuous-DTI run the model called `ask_secretary`
   10 times, unprompted, once per field, each asking "what is the spoken name
   for field <id>" -- a blocking lookup per field for metadata it already holds.
2. The secretary implicit-cache hit rate was **1/10 in-session**, vs the 96-98%
   the offline probe (`probe_secretary_latency.py`) reports.

## Cause of (1): the guidance framed the secretary as a field-metadata source

The reported symptom is a per-field ask for the CURRENT field's spoken name
("what is the spoken name for field <id>"), one per field across the run. Three
places in the model's context invited that, in order of how much each drove the
per-CURRENT-field symptom:

1. **The `ask_secretary` tool DESCRIPTION** (`backend/config.py`, shared by DTI +
   legacy) advertised "which field covers a topic" + "the secretary holds the
   whole form" + "instead of trying to remember other fields yourself" -- readable
   as a general field-metadata lookup path. Tool descriptions are weighted heavily
   by the model, so this is the strongest driver of the per-CURRENT-field symptom.
2. **The DTI SI** had no line telling the model NOT to fetch field metadata from
   the secretary.
3. **`render_section_metadata`** (`ai_context.py`) told the model "Available
   fields from completed sections (**use ask_secretary to recall these exact
   names**)". Note this only concerns names of ALREADY-COMPLETED sections, so it
   is a lesser driver of the per-CURRENT-field symptom -- but it still framed the
   secretary as the name source and is worth correcting.

But the current field's `ID | Spoken | Type | ...` guidance block ALWAYS carries
its spoken name (`render_field_guidance`), delivered on the initiating message
(field 1) and every `confirm_field` response (fields 2..N). So the per-field asks
were fully redundant.

**Fix (shipped in this bead, code-only), addressing all three:**
1. Narrowed the `ask_secretary` tool description to the user's ANSWERS and added
   "Do NOT use it to look up a field's spoken name or id -- that metadata is
   already in your guidance block" (the strongest lever, per the fresh-eyes
   review that caught the tool-desc-vs-SI contradiction).
2. Added a DTI SI line: "Do NOT call ask_secretary to look up a field's spoken
   name or id ... ask_secretary is ONLY for recalling the user's past
   ANSWERS/values."
3. Reworded `render_section_metadata` so the completed-field names are listed
   inline (not framed as secretary-fetched).
Static tests pin (2) and (3); (1) is pinned structurally by the tool-declaration.

## Cause of (2): NOT a byte-instability bug -- TTL + model-mixing

The offline 96-98% number and the in-session 1/10 are not contradictory once the
two run shapes are compared:

- **The byte-stable prefix is intact in production.** The secretary prefix is
  `SECRETARY_SI + "\n\n" + render_static_catalog(schema)` (a value-free,
  session-invariant string). `schema` is `_full_schema` set once at handshake and
  never mutated by `merge_field_schema` (that uses a separate `_dti_extra_fields`
  dict), and `render_static_catalog` iterates in deterministic order with no
  timestamps. So the prefix bytes ARE identical call-to-call.
- **The misses come from cache WARMTH, not prefix bytes.** Google's implicit
  cache has a short TTL. The offline probe fires all asks back-to-back in a tight
  loop, so every ask after the first hits a warm prefix. In a real voice session
  the 10 asks are spread one-per-field across the whole conversation, seconds to
  minutes apart -- the warm prefix expires between them, so each is a cold miss.
- **The lite fallback chain mixes cache namespaces.** The secretary lite chain is
  `gemini-2.5-flash-lite -> gemini-3.1-flash-lite` (`text_ai_gemini.py`). Any ask
  served by the fallback model lands in a different cache namespace -> guaranteed
  miss for that call.

`cached_content_token_count` is logged per call (`_log_usage`), so a future live
run can confirm which asks missed and whether they correlate with the fallback
model.

**Net:** eliminating the redundant per-field metadata asks (the fix above) removes
almost all of the secretary hot-path exposure, which is the real cost/latency win.
If the secretary stays on a hot, widely-spaced path, the durable
warmth-and-model-independent fix is EXPLICIT caching (`client.caches.create`,
already scaffolded + measured as the probe's `explicit` arm) -- deferred, not in
scope for 2af7.

## Verification still pending (a gated live-harness spend)

Exit criterion 1 ("a clean >=10-field continuous run makes ZERO ask_secretary
calls for field metadata, verified by seam_tool_records") requires re-running the
live stress harness (`measure_form_session_costs.py`, real Gemini) with the new
SI. That is a per-instance-approved live-model run and is NOT claimed here; the
code fix + static SI pins are complete.
