# Context-window compression eviction: re-probe findings (SDK 2.8.0)

*Date: 2026-06-12. Bead: polyglot-pdf-eycd. Prior dead-end: bd polyglot-pdf-l3a.1 (SDK 1.38.0).*

## Summary verdict

**Eviction is confirmed and reliable at 20 turns on SDK 2.8.0.**

At 10 turns, eviction was intermittent (2/3 runs fired). At 20 turns, eviction fired
in all three runs -- consistently 3-4 evictions per session. The server needs a few
turns past the trigger before compression fires; 10 turns was borderline, 20 turns is
well past the reliable threshold.

The OFF baseline grew unbounded (4,945-5,729 prompt tokens by turn 20). The ON sessions
stayed bounded, with the prompt repeatedly resetting toward the 800-token window target
after each eviction. This definitively overturns the l3a.1 dead-end. Compression works.

---

## Exact experimental setup

**Script:** `scripts/spikes/diag_compression_usage.py`

**Exact command used:**
```
cd <repo-root>
backend/.venv/Scripts/python.exe scripts/spikes/diag_compression_usage.py \
    --trigger 1500 --window 800 --turns 20 \
    --json scripts/spikes/eycd_20turn_runN.json
```

**Full configuration:**
- Model: `gemini-3.1-flash-live-preview`
- SDK: `google-genai 2.8.0`
- API version: default `v1beta` (no `http_options` override)
- Compression: `trigger_tokens=1500`, `sliding_window.target_tokens=800`
- Turns: 20 synthetic audio turns, gTTS-synthesized PCM16 at 16 kHz
- System instruction: `"You are a form-filling assistant. Keep spoken replies very short."`
- Tools: none (fallback tools only, no `function_declarations`)
- VAD: native (no manual `UNSPECIFIED` override)
- Audio prompts (cycled over 20 turns from this list):
    1. "Hi, I'd like to start filling out the form."
    2. "My first name is Alex."
    3. "My last name is Rivera."
    4. "I was born on January second, nineteen ninety."
    5. "I currently live in Austin, Texas."
    6. "My phone number is five five five, zero one four two."
    7. "I am applying to replace a lost card."
    8. "I have lived at my current address for three years."
    9. "I do not have a middle name."
   10. "Can you read back what you have so far?"
   11. "That all looks correct."
   12. "Thank you, I think that's everything for now."
   (turns 13-20 cycle back from prompt 1)

Each session: compression OFF first (baseline), then compression ON, same clips in same
order. `usage_metadata` captured per turn via `_on_raw_usage` diagnostic hook.

**Eviction signal:** a turn-over-turn DROP in `prompt_token_count` with compression ON.
`cached_content_token_count` is `None` in every turn of every run -- the prompt drop
is the sole observable eviction signal with this model.

**Raw JSON dumps:** `scripts/spikes/eycd_20turn_run{1,2,3}.json`

---

## Run 1 -- full per-turn token counts

**Config:** trigger=1500, window=800, turns=20, model=gemini-3.1-flash-live-preview

### OFF (baseline)

| turn | prompt | prompt_text | prompt_audio | resp | resp_audio | total | cached | eviction |
|-----:|-------:|------------:|-------------:|-----:|-----------:|------:|-------:|:---------|
|    1 |    272 |         158 |           79 |   76 |         76 |   348 |   None |          |
|    2 |    449 |         177 |          209 |   73 |         73 |   522 |   None |          |
|    3 |    613 |         195 |          333 |   80 |         80 |   693 |   None |          |
|    4 |    830 |         220 |          503 |  142 |        142 |   972 |   None |          |
|    5 |  1,105 |         255 |          709 |  113 |        113 | 1,218 |   None |          |
|    6 |  1,392 |         287 |          934 |   -- |         -- | 1,392 |   None |          |
|    7 |  1,480 |         296 |        1,006 |  220 |        220 | 1,700 |   None |          |
|    8 |  1,875 |         347 |        1,307 |   92 |         92 | 1,967 |   None |          |
|    9 |  2,069 |         371 |        1,449 |  102 |        102 | 2,171 |   None |          |
|   10 |  2,292 |         399 |        1,616 |  418 |        418 | 2,710 |   None |          |
|   11 |  2,878 |         463 |        2,072 |   81 |         81 | 2,959 |   None |          |
|   12 |  3,079 |         488 |        2,224 |   80 |         80 | 3,159 |   None |          |
|   13 |  3,295 |         518 |        2,382 |   79 |         79 | 3,374 |   None |          |
|   14 |  3,474 |         537 |        2,514 |   59 |         59 | 3,533 |   None |          |
|   15 |  3,628 |         556 |        2,627 |   76 |         76 | 3,704 |   None |          |
|   16 |  3,843 |         581 |        2,795 |  134 |        134 | 3,977 |   None |          |
|   17 |  4,112 |         616 |        2,995 |  112 |        112 | 4,224 |   None |          |
|   18 |  4,398 |         648 |        3,219 |  165 |        165 | 4,563 |   None |          |
|   19 |  4,702 |         686 |        3,451 |  105 |        105 | 4,807 |   None |          |
|   20 |  4,945 |         715 |        3,637 |   96 |         96 | 5,041 |   None |          |

Turn 20 prompt: **4,945** (18.2x turn-1 baseline). Audio fraction at turn 20: 73.5%.

### ON (trigger=1500, window=800)

| turn | prompt | prompt_text | prompt_audio | resp | resp_audio | total | cached | eviction        |
|-----:|-------:|------------:|-------------:|-----:|-----------:|------:|-------:|:----------------|
|    1 |    272 |         158 |           79 |  157 |        157 |   429 |   None |                 |
|    2 |    545 |         185 |          287 |   67 |         67 |   612 |   None |                 |
|    3 |    703 |         202 |          406 |   76 |         76 |   779 |   None |                 |
|    4 |    913 |         224 |          572 |  193 |        193 | 1,106 |   None |                 |
|    5 |  1,259 |         262 |          830 |  161 |        161 | 1,420 |   None |                 |
|    6 |  1,606 |         300 |        1,101 |  141 |        141 | 1,747 |   None |                 |
|    7 |  1,872 |         331 |        1,312 |  152 |        152 | 2,024 |   None |                 |
|    8 |  2,179 |         368 |        1,542 |  156 |        156 | 2,335 |   None |                 |
|    9 |  1,021 |         244 |          645 |   92 |         92 | 1,113 |   None | **-1158 (EVICT)**|
|   10 |  2,468 |         542 |        1,600 |  226 |        218 | 2,694 |   None |                 |
|   11 |  1,598 |         318 |        1,064 |  135 |        135 | 1,733 |   None | **-870 (EVICT)** |
|   12 |  1,865 |         349 |        1,268 |  168 |        168 | 2,033 |   None |                 |
|   13 |  2,188 |         390 |        1,508 |   83 |         83 | 2,271 |   None |                 |
|   14 |  1,004 |         243 |          626 |   61 |         61 | 1,065 |   None | **-1184 (EVICT)**|
|   15 |  1,156 |         259 |          742 |   76 |         76 | 1,232 |   None |                 |
|   16 |  1,369 |         282 |          908 |   59 |         59 | 1,428 |   None |                 |
|   17 |  1,532 |         298 |        1,035 |   92 |         92 | 1,624 |   None |                 |
|   18 |  1,792 |         327 |        1,240 |   64 |         64 | 1,856 |   None |                 |
|   19 |  1,967 |         346 |        1,376 |  141 |        141 | 2,108 |   None |                 |
|   20 |  2,254 |         379 |        1,598 |  133 |        133 | 2,387 |   None |                 |

Evictions: turn 9 (2179->1021, -1158), turn 11 (2468->1598, -870), turn 14 (2188->1004, -1184)
Turn 20 prompt: **2,254** vs OFF **4,945** -- 54% lower.

---

## Run 2 -- full per-turn token counts

### OFF (baseline)

| turn | prompt | prompt_text | prompt_audio | resp | resp_audio | total | cached | eviction |
|-----:|-------:|------------:|-------------:|-----:|-----------:|------:|-------:|:---------|
|    1 |    272 |         158 |           79 |   62 |         62 |   334 |   None |          |
|    2 |    420 |         173 |          194 |   39 |         39 |   459 |   None |          |
|    3 |    543 |         185 |          287 |   89 |         89 |   632 |   None |          |
|    4 |    774 |         210 |          467 |  137 |        137 |   911 |   None |          |
|    5 |  1,042 |         239 |          670 |  147 |        147 | 1,189 |   None |          |
|    6 |  1,374 |         274 |          929 |  130 |        130 | 1,504 |   None |          |
|    7 |  1,638 |         303 |        1,130 |  149 |        149 | 1,787 |   None |          |
|    8 |  1,938 |         339 |        1,358 |  152 |        152 | 2,090 |   None |          |
|    9 |  2,213 |         374 |        1,558 |  148 |        148 | 2,361 |   None |          |
|   10 |  2,499 |         410 |        1,768 |  490 |        490 | 2,989 |   None |          |
|   11 |  3,205 |         493 |        2,303 |   84 |         84 | 3,289 |   None |          |
|   12 |  3,406 |         516 |        2,457 |  214 |        214 | 3,620 |   None |          |
|   13 |  3,792 |         567 |        2,738 |  125 |        125 | 3,917 |   None |          |
|   14 |  4,027 |         593 |        2,915 |  134 |        134 | 4,161 |   None |          |
|   15 |  4,272 |         620 |        3,099 |  136 |        136 | 4,408 |   None |          |
|   16 |  4,561 |         651 |        3,321 |  123 |        123 | 4,684 |   None |          |
|   17 |  4,812 |         681 |        3,510 |  155 |        155 | 4,967 |   None |          |
|   18 |  5,151 |         719 |        3,775 |  151 |        151 | 5,302 |   None |          |
|   19 |  5,443 |         752 |        3,996 |  137 |        137 | 5,580 |   None |          |
|   20 |  5,729 |         787 |        4,213 |  151 |        151 | 5,880 |   None |          |

Turn 20 prompt: **5,729** (21.1x). Audio fraction at turn 20: 73.5%.

### ON (trigger=1500, window=800)

| turn | prompt | prompt_text | prompt_audio | resp | resp_audio | total | cached | eviction        |
|-----:|-------:|------------:|-------------:|-----:|-----------:|------:|-------:|:----------------|
|    1 |    272 |         158 |           79 |   65 |         65 |   337 |   None |                 |
|    2 |    434 |         177 |          198 |   73 |         73 |   507 |   None |                 |
|    3 |    606 |         197 |          326 |   61 |         61 |   667 |   None |                 |
|    4 |    800 |         220 |          477 |   60 |         60 |   860 |   None |                 |
|    5 |    965 |         238 |          604 |  193 |        193 | 1,158 |   None |                 |
|    6 |  1,355 |         281 |          905 |  191 |        191 | 1,546 |   None |                 |
|    7 |  1,709 |         327 |        1,167 |  130 |        130 | 1,839 |   None |                 |
|    8 |  1,988 |         362 |        1,377 |  161 |        161 | 2,149 |   None |                 |
|    9 |  2,267 |         393 |        1,585 |  272 |        272 | 2,539 |   None |                 |
|   10 |  2,046 |         498 |        1,260 |  346 |        338 | 2,392 |   None | **-221 (EVICT)** |
|   11 |  1,544 |         312 |        1,013 |  193 |        193 | 1,737 |   None | **-502 (EVICT)** |
|   12 |  1,886 |         354 |        1,267 |  132 |        132 | 2,018 |   None |                 |
|   13 |  2,171 |         392 |        1,472 |  187 |        187 | 2,358 |   None |                 |
|   14 |  1,119 |         261 |          694 |   96 |         96 | 1,215 |   None | **-1052 (EVICT)**|
|   15 |  1,315 |         283 |          840 |  181 |        181 | 1,496 |   None |                 |
|   16 |  1,656 |         319 |        1,107 |  185 |        185 | 1,841 |   None |                 |
|   17 |  1,990 |         360 |        1,356 |  214 |        214 | 2,204 |   None |                 |
|   18 |  1,005 |         241 |          637 |  110 |        110 | 1,115 |   None | **-985 (EVICT)** |
|   19 |  1,247 |         270 |          818 |  135 |        135 | 1,382 |   None |                 |
|   20 |  1,528 |         304 |        1,033 |  264 |        264 | 1,792 |   None |                 |

Evictions: turn 10 (2267->2046, -221), turn 11 (2046->1544, -502), turn 14 (2171->1119, -1052),
           turn 18 (1990->1005, -985)
Turn 20 prompt: **1,528** vs OFF **5,729** -- 73% lower.
Note: turns 10-11 show incremental two-step compression (server spread the eviction across
two consecutive turns rather than one large drop).

---

## Run 3 -- full per-turn token counts

### OFF (baseline)

| turn | prompt | prompt_text | prompt_audio | resp | resp_audio | total | cached | eviction |
|-----:|-------:|------------:|-------------:|-----:|-----------:|------:|-------:|:---------|
|    1 |    272 |         158 |           79 |  134 |        134 |   406 |   None |          |
|    2 |    526 |         187 |          264 |  145 |        145 |   671 |   None |          |
|    3 |    785 |         217 |          457 |  115 |        115 |   900 |   None |          |
|    4 |  1,048 |         248 |          661 |   81 |         81 | 1,129 |   None |          |
|    5 |  1,243 |         272 |          808 |  130 |        130 | 1,373 |   None |          |
|    6 |  1,560 |         308 |        1,053 |  102 |        102 | 1,662 |   None |          |
|    7 |  1,789 |         333 |        1,227 |   96 |         96 | 1,885 |   None |          |
|    8 |  2,019 |         358 |        1,404 |  164 |        164 | 2,183 |   None |          |
|    9 |  2,317 |         397 |        1,615 |   93 |         93 | 2,410 |   None |          |
|   10 |  2,527 |         422 |        1,772 |  450 |        450 | 2,977 |   None |          |
|   11 |  3,166 |         494 |        2,257 |   88 |         88 | 3,254 |   None |          |
|   12 |  3,379 |         521 |        2,415 |   80 |         80 | 3,459 |   None |          |
|   13 |  3,591 |         550 |        2,570 |  134 |        134 | 3,725 |   None |          |
|   14 |  3,846 |         579 |        2,756 |  139 |        139 | 3,985 |   None |          |
|   15 |  4,103 |         610 |        2,946 |  115 |        115 | 4,218 |   None |          |
|   16 |  4,366 |         641 |        3,150 |   84 |         84 | 4,450 |   None |          |
|   17 |  4,564 |         665 |        3,300 |  105 |        105 | 4,669 |   None |          |
|   18 |  4,844 |         695 |        3,520 |  104 |        104 | 4,948 |   None |          |
|   19 |  5,072 |         720 |        3,695 |  102 |        102 | 5,174 |   None |          |
|   20 |  5,307 |         745 |        3,877 |  197 |        197 | 5,504 |   None |          |

Turn 20 prompt: **5,307** (19.5x). Audio fraction at turn 20: 73.1%.

### ON (trigger=1500, window=800)

| turn | prompt | prompt_text | prompt_audio | resp | resp_audio | total | cached | eviction        |
|-----:|-------:|------------:|-------------:|-----:|-----------:|------:|-------:|:----------------|
|    1 |    272 |         158 |           79 |   54 |         54 |   326 |   None |                 |
|    2 |    413 |         173 |          187 |   62 |         62 |   475 |   None |                 |
|    3 |    565 |         189 |          303 |   60 |         60 |   625 |   None |                 |
|    4 |    758 |         210 |          455 |  177 |        177 |   935 |   None |                 |
|    5 |  1,080 |         249 |          692 |  145 |        145 | 1,225 |   None |                 |
|    6 |  1,409 |         284 |          948 |  143 |        143 | 1,552 |   None |                 |
|    7 |  1,693 |         317 |        1,161 |  165 |        165 | 1,858 |   None |                 |
|    8 |  2,010 |         355 |        1,404 |  162 |        162 | 2,172 |   None |                 |
|    9 |  1,060 |         253 |          665 |  145 |        145 | 1,205 |   None | **-950 (EVICT)** |
|   10 |  1,342 |         287 |          875 |  328 |        328 | 1,670 |   None |                 |
|   11 |  1,846 |         349 |        1,245 |  142 |        142 | 1,988 |   None |                 |
|   12 |  2,124 |         383 |        1,455 |  144 |        144 | 2,268 |   None |                 |
|   13 |  1,616 |         448 |          952 |  109 |        101 | 1,725 |   None | **-508 (EVICT)** |
|   14 |  1,022 |         250 |          631 |   63 |         63 | 1,085 |   None | **-594 (EVICT)** |
|   15 |  1,176 |         266 |          749 |   85 |         85 | 1,261 |   None |                 |
|   16 |  1,399 |         291 |          923 |  141 |        141 | 1,540 |   None |                 |
|   17 |  1,671 |         322 |        1,130 |  153 |        153 | 1,824 |   None |                 |
|   18 |  2,004 |         356 |        1,393 |  144 |        144 | 2,148 |   None |                 |
|   19 |  1,060 |         242 |          684 |  188 |        188 | 1,248 |   None | **-944 (EVICT)** |
|   20 |  1,402 |         281 |          945 |  187 |        187 | 1,589 |   None |                 |

Evictions: turn 9 (2010->1060, -950), turn 13 (2124->1616, -508), turn 14 (1616->1022, -594),
           turn 19 (2004->1060, -944)
Turn 20 prompt: **1,402** vs OFF **5,307** -- 74% lower.
Note: turns 13-14 show consecutive partial evictions (same pattern as run 2 turns 10-11).

---

## Aggregate observations

| Run | OFF turn-20 prompt | ON turn-20 prompt | Reduction | Evictions | First eviction |
|-----|--------------------|-------------------|-----------|-----------|----------------|
| 1   | 4,945              | 2,254             | 54%       | 3         | turn 9         |
| 2   | 5,729              | 1,528             | 73%       | 4         | turn 10        |
| 3   | 5,307              | 1,402             | 74%       | 4         | turn 9         |

**Audio fraction of prompt tokens (OFF, turn 20):** ~73% across all three runs. This
confirms audio is the dominant and fastest-growing component of context cost.

**Eviction landing zone:** post-eviction prompt lands in the range 1,000-1,600 tokens,
somewhat above the configured 800 window target. The server appears to target the window
size but does not hit it exactly, possibly due to turn-boundary granularity.

**Incremental eviction:** in 2/3 runs, one eviction pair spanned two consecutive turns
(run 2 turns 10-11: -221 then -502; run 3 turns 13-14: -508 then -594). Total tokens
removed across the pair matches a single large eviction. Server may spread compression
when the gap is large.

**`cached_content_token_count`:** `None` in every turn of every run. The prompt drop
is the sole observable eviction signal for this model.

**`thoughts_token_count`:** `None` in every turn -- model is not reporting thinking tokens
(consistent with native-audio mode).

---

## Why 10-turn runs were inconsistent

First eviction fires at turn 9-10. In the one 10-turn miss (run 2 of the earlier series),
the server simply had not fired yet within the window. At 20 turns, every run gets
multiple evictions well before the end. The compression mechanism works; 10 turns was
just an unlucky probe length.

---

## What changed since l3a.1

l3a.1 was run on **google-genai SDK 1.38.0** in June 2026. The SDK was upgraded to
**2.8.0** in PR #156. Config and model string are unchanged. Most likely: a server-side
change on Google's end, either shipped alongside or exposed by the SDK upgrade.

---

## Status on gemini-2.5-flash-native-audio-preview-12-2025

Untested due to internal server errors. Crashes with `1011 Internal error` after the
first audio turn. Pre-existing instability (bd daa), unrelated to compression. Whether
2.5 also evicts is unknown; worth re-testing if server-side stability improves.

---

## Next steps (bead polyglot-pdf-eycd)

1. **Window-size research:** run with realistic form-fill prompts (longer answers,
   confirmations, corrections, section transitions) to measure real-session token growth
   and choose a production (trigger, window) pair. The synthetic gTTS prompts here are
   short; real user audio will accrue tokens faster.
2. **Plan the epic** via `/plan-epic` once window-size data is in hand.
3. **Do not enable yet** (`CONTEXT_COMPRESSION_ENABLED=False` in `backend/config.py`).
   Parameter tuning and coherence regression testing come first.
