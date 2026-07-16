---
date: 2026-07-15
bead: polyglot-pdf-6les
title: "fix(dev-local): default local backend to Vertex, not AI Studio (single billing account)"
tags: [hotfix, doctrine]
---

## Trigger

While live-verifying the continuous-mode section-paging fix (bd polyglot-pdf-gz20),
the local voice session showed "disconnected / Connection failed" -- the local
runner forces AI Studio, whose credits are depleted. The maintainer restated the
standing directive: ALL sessions, local OR remote, must run on Vertex all the time,
so spend lands on ONE billing account. Splitting across the AI Studio account is
unreliable (fails when Studio credits deplete -> 1011) and complicates the
maintainer's accounting. This reaffirms + extends the 2026-07-12
all-live-model-work-on-vertex rule to the local dev runners specifically.

## What shipped

Both `scripts/dev-local.sh` and `scripts/dev-local.ps1` HARDCODED `VERTEXAI=false`,
forcing the local backend onto AI Studio even for the DEFAULT (2.5) arm -- whose
native-audio model IS available on Vertex. `backend/config.py` already defaults
`VERTEXAI=true`; only the runners overrode it.

The change: the DEFAULT arm now runs `VERTEXAI=true` +
`GOOGLE_CLOUD_PROJECT=polyglot-demo-aa709` (local ADC present). The premium (3.1)
arm remains `VERTEXAI=false` + `GEMINI_API_KEY` -- the SOLE exception, because 3.1 is
AI-Studio-only for now (a model-availability constraint documented in config.py,
NOT a billing choice) -- and it now warns loudly that it bills to the AI Studio
account. The credential preflight in both runners is now arm-aware: the default
(Vertex) arm warns on missing ADC; the premium (Studio) arm warns on missing
`GEMINI_API_KEY`. `GOOGLE_CLOUD_PROJECT` respects an already-set value so a
different project can be used per run. The `run-local` SKILL.md (the doc-of-record
for these runners) was updated to match.

Scoping check: the only other `VERTEXAI=false` occurrences in scripts/ are the
bakeoff/spike scripts, which already DEFAULT to Vertex (their `false` mentions are
opt-in overrides for deliberate experiments); the remaining conversions there are
tracked by bd eztf/w6en. So the runners were the only place hardcoding Studio for
normal sessions.

Decisions (mine; the WHAT was the maintainer's explicit directive, only the HOW was
mine): (1) escalated ONE thing -- which GCP project local sessions bill to -- because
it directly affects the maintainer's billing; they chose polyglot-demo-aa709.
(2) Kept the premium arm on Studio rather than dropping premium support, because 3.1
genuinely has no Vertex id yet -- removing it would lose the A/B arm. (3) Fixed BOTH
runners (bash + PowerShell), not just the bash one the agent can run, so a human
using the .ps1 isn't left on Studio.

Fresh-eyes (Step 5.5.b): 1 round on Opus (the final clearing tier), NO-GAPS -- it
traced the env-var contract into the adapter (Vertex client ignores api_key) and
confirmed the .ps1 mirrors bash + ASCII compliance. No gaps, nothing deferred.

Outer review (Step 5.6): 2 rounds. Round 1 (Opus primary) returned NO-GAPS but
noted two warn-only preflight edges: the bash ADC check was Windows-path-only (a
valid POSIX ~/.config/gcloud ADC would trip a spurious warning every launch), and
the ps1 Join-Path $env:APPDATA could throw if %APPDATA% were unset. Both fixed
inline (bash checks both OS ADC locations honoring CLOUDSDK_CONFIG; ps1 guards the
base path with a CLOUDSDK_CONFIG/APPDATA/$HOME fallback) and re-verified live (no
spurious ADC warning). Round 2: TWO independent Opus passes (primary re-run +
second independent) both NO-GAPS on the identical fixed diff.

Verification: booted `./scripts/dev-local.sh backend` and confirmed `/health`
reports `vertexai:true` and the Vertex model id
(`gemini-live-2.5-flash-native-audio`), `use_premium_model:false`. Could not
execute the .ps1 (pwsh blocked in this environment) -- verified it by inspection,
mirroring the bash logic exactly. Full backend suite green via closeout prep.

## Lessons

A config default being correct (`config.py` VERTEXAI=true) does NOT mean every
entry point honors it -- a runner script can silently override the right default.
When a billing/infra directive says "always X", grep for every place that could
set the opposite, including dev tooling and both OS runners, not just the app
config.

## Doc freshness

Updated `.claude/skills/run-local/SKILL.md` (the runners' doc-of-record): the
backend description + preflight notes said "forces VERTEXAI=false (AI Studio)",
now corrected to Vertex-default with the premium exception.
`docs/components/config-deployment.md` was reviewed and left as-is: it documents
the `VERTEXAI` env semantics (default true, demo runs Vertex) accurately and never
claimed local dev used Studio. Other prep-flagged STALE docs track backend files
this branch did not touch (pre-existing staleness from other sprints).

## Files touched

- `scripts/dev-local.sh` -- Vertex-default backend selection + arm-aware preflight
  + GOOGLE_CLOUD_PROJECT export + header comment.
- `scripts/dev-local.ps1` -- same, PowerShell.
- `.claude/skills/run-local/SKILL.md` -- corrected backend/preflight description.
