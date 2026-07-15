---
date: 2026-07-14
bead: polyglot-pdf-7d19
tags: [docs, readme, onboarding, vertex, vision]
---

# README accuracy pass + immigration-first vision (polyglot-pdf-7d19)

Maintainer asked to bring `README.md` back in line with the current build state,
then to reframe the vision so immigration is the first target ("Immigration is
our first stop").

## What drifted (verified against code, not docs)

- **Credential path.** The README documented `GOOGLE_API_KEY`/`GEMINI_API_KEY`
  as the required credential in setup, Cloud Run deploy, the deployment
  checklist, and troubleshooting. Ground truth: `backend/config.py` defaults
  `VERTEXAI=true`, so the default backend authenticates to Gemini via **Vertex
  AI + ADC + `GOOGLE_CLOUD_PROJECT`**, no API key. `backend/deploy-new.sh` sets
  only `GOOGLE_CLOUD_PROJECT`. Rewrote all four spots to make Vertex the primary
  path and the API key the explicit AI-Studio-only alternative (`VERTEXAI=false`,
  for the premium 3.1 model that is not yet on Vertex).
- **`GEMINI_API_KEY` is canonical, not interchangeable with `GOOGLE_API_KEY`.**
  Fresh-eyes traced that `Settings.GEMINI_API_KEY` reads only `GEMINI_API_KEY`,
  and `/health` + the startup misconfig warning key off that name. `GOOGLE_API_KEY`
  works only via the SDK's implicit fallback and leaves `/health` reporting the
  key as absent -- confusing to debug. README now tells operators to use
  `GEMINI_API_KEY` specifically, with a one-line note about the fallback.
- **Tool count 5 -> 7.** The architecture diagram said "5 tools"; the live
  `TOOL_DECLARATIONS` list carries 7 (update_form_fields, get_form_status,
  switch_section, confirm_field, ask_secretary, skip_field, switch_to_field).
- **Continuous-DTI is the production default.** The "section navigation" framing
  predated it. Noted `CONTINUOUS_SESSION` + `USE_DTI` as the default single-session
  flow, section-reset as the env-flippable fallback.
- **Small fixes.** Last Updated June -> July 2026; editor deploys via
  `deploy-editor.sh`; Prerequisites credential line points at Environment Variables.

## Vision reframe

Project Vision now LEADS with immigration/legal intake (USCIS I-90, IRS W-7) as
the first target; the generic "transform form-filling" mission is the second
paragraph, framed as the broader goal the form-agnostic architecture generalizes
to. Primary Use Cases reordered (Immigration & Legal Intake #1, Medical #3).
Broadened the HIPAA-only privacy bullet to "Zero PII/PHI Storage" -- the stateless
guarantee applies as much to immigration data as medical.

## Out of scope, deliberately not touched

The live-session prompts in `backend/config.py` (`SYSTEM_INSTRUCTION`,
`DTI_SYSTEM_INSTRUCTION`) still say "medical-form assistant". That is a code
change (prompt wording, product-behavior consequence), not a docs fix, and it is
outside a docs-only README bead. Flagged here for a future bead if the maintainer
wants the runtime persona wording to match the immigration-first framing.

Docs-only change; no code touched. Full backend suite green (1075 passed) at prep.
