---
date: 2026-07-02
bead: polyglot-pdf-fyq4
title: "fix(extract): hosted extraction uses Vertex/ADC auth on Cloud Run (no GEMINI_API_KEY on the service)"
tags: [ai-models, conventions]
---

## Trigger

During the live-deploy prep for the hosted-editor epic (bd 92qe), a pre-flight
of the demo Cloud Run backend showed it runs `VERTEXAI=true` with a service
account and NO `GEMINI_API_KEY` attached. The maintainer asked the right
question: can hosted extraction attach to Vertex instead of needing a key, and
are the extractor's models even available on Vertex (the ids don't always
overlap AI Studio)?

## What was wrong

`scripts/bakeoff/llm_providers.py`'s `GeminiProvider.run()` -- the provider the
hosted author-tier "Run extraction" path invokes via `extract_form.py` --
hardcoded `genai.Client(api_key=os.environ["GEMINI_API_KEY"])`. On the deployed
backend that key does not exist, so extraction would `KeyError` (the route
catches it as a 503). The feature had never actually worked on Cloud Run; only
the local/dev path (which does set a key) did.

## The fix

When `VERTEXAI` is set, build a Vertex client (`vertexai=True`, project +
location from `GOOGLE_CLOUD_*` env, ADC / service-account auth, no key),
mirroring the live voice adapter (`backend/adapters/live_ai_gemini.py:292-298`)
which already runs on Vertex in production. The AI-Studio `api_key` path is
preserved for local dev and the offline bakeoff harness. The parse is
`os.getenv("VERTEXAI","").strip().lower() == "true"` -- deliberately identical
to how `backend/config.py` reads VERTEXAI (and every other bool flag: `.lower()
== "true"`), so the backend's notion of "am I on Vertex" and the extractor's can
never diverge. (The first draft accepted `1`/`yes` too; fresh-eyes prep flagged
that as a latent backend-vs-extractor split, tightened to match config.)

## Verification (against the live demo Vertex endpoint)

Model availability first, because Vertex ids do not always match AI Studio:
probed the demo project's ADC -- `gemini-2.5-pro` (the `EXTRACTOR_MODEL`
default), `gemini-2.5-flash`, and `-flash-lite` all resolve and respond on
Vertex. No remap needed for the 2.5 family.

Then the full path: `VERTEXAI=true`, no `GEMINI_API_KEY` in env,
`extract_form.py` on F1040 -> authenticated via ADC and extracted 147 fields.
The extractor's schema-contract validation then flagged a few multi-entry
fields for polish -- normal first-pass draft behavior, identical on either auth
path, not an auth failure.

## Lessons

The "extractor uses a different SDK auth than the request-serving backend" split
is a real footgun: the voice path went Vertex long ago, but the bakeoff-derived
extraction provider stayed key-only, so a backend that looked fully Vertex-
configured still had one code path silently requiring a key. When a service
authenticates via ADC/service account, EVERY google-genai client it spawns
(including subprocess/vendored ones) has to opt into Vertex too.

Bool-flag parsing must be uniform across a codebase. A single flag read two
ways (`== "true"` in config vs. `in ("1","true","yes")` here) is invisible until
someone sets the off-convention value and two subsystems disagree.

## Files touched

- scripts/bakeoff/llm_providers.py -- Vertex-vs-key client construction in
  GeminiProvider.run(), gated on VERTEXAI with the config-matching parse.
