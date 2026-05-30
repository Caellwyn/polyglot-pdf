---
date: 2026-05-30
bead: polyglot-pdf-lky
title: "Fix pricing table + family-keyed cost calc"
tags: [refactor, testing]
---

## Trigger

`bd polyglot-pdf-lky` (child of the AI model + pricing refresh epic
`polyglot-pdf-9nl`; depended on the now-closed `polyglot-pdf-9dq` env-swappable
models). `backend/config.py`'s `GEMINI_PRICING` was a single flat dict
**mislabeled "Gemini 2.0 Flash"** over what were actually 2.5 rates, with a
vague "October 2025" stamp. With models now A/B-swappable (2.5 native vs 3.1
live), a flat table bills every model at one rate — a 2.5↔3.1 comparison would
be costed wrong.

## What shipped

**`backend/config.py`** — replaced the flat dict with `GEMINI_PRICING_BY_FAMILY`
keyed by family (`"2.5"`, `"3.1"`), each row carrying verified per-1M rates
divided to per-token:

| family | text_in | audio_in | text_out | audio_out |
|--------|---------|----------|----------|-----------|
| 2.5    | 0.50    | 3.00     | 2.00     | 12.00     |
| 3.1    | 0.75    | 3.00     | 4.50     | 12.00     |

Added `model_family(name)` (case-insensitive substring match on the version
token, falls back to `DEFAULT_PRICING_FAMILY="2.5"` for unknown/empty names so
cost tracking never crashes on a new preview model) and
`get_pricing_for_model(name)`. Kept `GEMINI_PRICING` as a **backward-compatible
alias** to the default family's row (the old flat values were the 2.5 rates, so
this is a no-op for any other importer). Corrected the comment + stamped
`Updated: 2026-05-30`.

**`backend/adapters/live_ai_gemini.py`** — the only consumer. Swapped
`from backend.config import GEMINI_PRICING` → `get_pricing_for_model`, and the
cost calc (formerly `GEMINI_PRICING["text_input"]` etc.) now selects the rate
row via `get_pricing_for_model(self._model_name)` — the active model's family.
`token_file_logger` needed no change (it only *receives* computed costs).

**`tests/test_pricing.py`** (new, 14 tests) — satisfies the acceptance
criterion: the same 1M-token-per-modality bundle costs **$17.50 at 2.5** and
**$20.25 at 3.1** (asserted distinct), plus family-mapping cases (known models,
case-insensitivity, unknown→default) and the legacy-alias guard.

Nothing deferred.

## Rate + model-name verification (independent research)

Before merge, verified the spec's rates and model names against Google's own
docs (`ai.google.dev/gemini-api/docs/pricing` and `/models`) on 2026-05-30 —
not the bead text — because third-party aggregators gave conflicting numbers:

- **Rates: confirmed exact.** 2.5 = 0.50/3.00/2.00/12.00, 3.1 = 0.75/3.00/4.50/12.00
  (per 1M, text-in/audio-in/text-out/audio-out) match the official pricing page.
- **Model names: confirmed real.** `gemini-3.1-flash-live-preview` is the current
  Live API model; `gemini-2.5-flash-native-audio-preview-12-2025` is the current
  2.5 native-audio preview. Both map correctly via `model_family()` — verified
  the `-preview-12-2025` date suffix does NOT false-match `2.5` against `12-2025`.
- **Edge note:** a bare `gemini-3-flash-preview` (no `.1`) is not a Live/native-
  audio model per Google, so it won't reach this adapter; if it ever did it bills
  at the 2.5 default. Documented in the config comment.
- Added the real Google model IDs as explicit test cases (24 pricing tests now).

**Out-of-scope finding filed:** the research surfaced a Google forum report that
`gemini-2.5-flash-native-audio-preview-12-2025` returns `code=1011` mid-turn at
~80% since 2026-05-27. Filed as **`polyglot-pdf-daa`** (P1 watch/investigate) —
our default model is the stable alias, not confirmed affected.

## Lessons

- Keeping a **backward-compatible alias** (`GEMINI_PRICING` → default family) let
  this be a drop-in: the one consumer was updated deliberately, and any future
  stray importer still gets sane (default-family) rates instead of an
  ImportError. Cheap insurance when refactoring a widely-importable constant.
- `model_family()` fails *open* (default family) rather than raising on an
  unknown model name — cost tracking is observability, not a correctness gate;
  better to mis-bill slightly at the default than crash the live session loop.

## Doc freshness

`check_doc_freshness.py`: "No docs to check" (components/ + standards/ are the
empty starter skeleton). The blocked bead `polyglot-pdf-2hy` (Update model +
pricing docs) is the home for documenting these rates — left for that bead,
now unblocked.

## Files touched

- `backend/config.py` — family-keyed pricing dict + `model_family` / `get_pricing_for_model` helpers + alias; fixed comment/stamp.
- `backend/adapters/live_ai_gemini.py` — cost calc selects rate row by active model family.
- `tests/test_pricing.py` — new; 14 tests covering rate selection + family mapping + alias.
- `docs/journal/entries/2026-05-30-bd-lky-fix-pricing-table-family-keyed-cost-calc.md` — this entry.
