---
date: 2026-11-17
bead: polyglot-pdf-o40eo
title: "Deployed telemetry: gemini-3.8-live vs 2.5 native audio cost/latency/reliability (logs only)"
tags: [performance]
---

## Trigger

`gemini-3.8-live` replaced 2.5 native audio on 2026-10-21. The investor
materials (`pitch/i90-stress-test`, `pitch/naive-vs-mitigated-cost`) needed
current cost and latency numbers. Local-harness latency must not be quoted as
product latency, so deployed telemetry was the only honest source.

A sibling session ran the local scripted benchmarks. This bead did the free,
logs-only half: compare deployed 3.8 sessions against deployed 2.5 sessions.

## What shipped

`scripts/spikes/3p8_deployed_telemetry.py` is a read-only, in-process pull
from four sources, all through google-auth `AuthorizedSession` and
`google-cloud-bigquery`, with no gcloud or bq subprocess:

- Cloud Logging `jsonPayload`;
- Monitoring log-based metrics;
- the BigQuery telemetry sink;
- the BigQuery billing export.

It writes `data/3p8_deployed_telemetry_aggregates.json`, which contains no
PII. The findings are in `3p8_deployed_telemetry_findings.md`.

Headline: **3.8 has run deployed exactly once.** That was one staging
post-deploy test drive on 2026-10-22, with 7 turns and 3 tool calls. The demo
service was last deployed 2026-09-23 and has never served 3.8. No deployed 2.5
latency baseline survives the 30-day log retention. Telemetry cost reconciles
with Vertex billing: to the cent on both clean 2.5 days, and +3.1% on the 3.8
day.

On that 3.8 day, Vertex billed text output of 137 tokens. That is close to
logged text output *minus* thoughts (119). The 1,022 logged thought tokens
appear on no billing line.

Follow-ups filed:

- `polyglot-pdf-beeoh`: deployed `timing_*` events die at 30 days, because
  the BQ sink does not carry them.
- `polyglot-pdf-qv3jp`: one 3.8 intro-instance close with code 1007 after an
  empty activity bracket, n = 1.
- `polyglot-pdf-1lks4` (filed by the cross-surface reviewer): verify whether
  Vertex bills 3.8 Live thought tokens before trusting either pricing story.

## Lessons

- **Log retention silently decides which comparisons are possible.** The
  `_Default` bucket keeps 30 days, so a model cutover more than about 4 weeks
  old has no deployed latency baseline. Cost survives because the usage rows
  are sinked to BQ. Timing does not survive. Check retention before promising
  a before/after comparison.
- **The billing export is a cheap independent check on the cost
  telemetry**, but only on days with no local-harness Live traffic, since it
  is project-wide. Matching token counts per SKU (audio-in exact) is the tell
  that a day is clean.
- **Check the service's last-deploy time before reasoning about which model
  a channel serves.** The `model=` field on demo said 2.5 a fortnight after
  the "cutover", because demo was never redeployed.

## Doc freshness

No tier-1/2 docs changed. This bead touched only `scripts/spikes/` (spike
artifacts) and this journal entry. `docs/standards/logging-and-cost.md` was
reviewed and left as-is. Its timing-checkpoint list matches the emitted
events. Where deployed latency lives, and for how long, is now bead
`polyglot-pdf-beeoh`.

`check_doc_freshness.py` flags 25 tier-2 docs as stale, along with stacked
stamps in 7 of them. None of those docs tracks a file this branch touched,
so all of it predates this branch and was left alone.

The beads audit flagged one stale `in_progress` bead, `polyglot-pdf-h06sv`
(beads GCS-remote cutover, 55 days). It is another workstream and was not
transitioned here.

## Files touched

- `scripts/spikes/3p8_deployed_telemetry.py` (new): the read-only telemetry
  pull.
- `scripts/spikes/3p8_deployed_telemetry_findings.md` (new): method, query
  text, numbers, n and caveats.
- `scripts/spikes/data/3p8_deployed_telemetry_aggregates.json` (new): raw
  aggregates, no PII.
- `docs/journal/entries/2026-11-17-bd-o40eo-deployed-3p8-telemetry.md` (this
  entry).
