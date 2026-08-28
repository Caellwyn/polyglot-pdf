# Sprint 13 -- Multilingual voice UX fixes

**Source assessment:** bd `polyglot-pdf-6mzi` (CLOSED; findings:
[`scripts/spikes/multilingual_ux_findings.md`](../scripts/spikes/multilingual_ux_findings.md))
| **Epics:** `polyglot-pdf-66ek` (A: deterministic field focus),
`polyglot-pdf-tupu` (B: translated spoken names) |
**Status: APPROVED 2026-07-22 (maintainer, in-chat; plan reviewed pre-approval
by an adversarial Opus pass, 10 findings folded in) -- beads filed**

## Why

The 6mzi assessment ran one scripted in-language voice session each in
Spanish, Chinese, French, Hindi, and Russian and found: English field jargon
read aloud to non-English speakers plus per-field secretary spam (fr: 14/14
questions), a Chinese session that filled the name block one field behind
(9/14 accuracy), a Hindi session that invented a field id AND a value and
propagated it over the user's real answer, spell-back verification collapsing
into Cyrillic letter names, inconsistent decline handling (zh wrote literal
"N/A"), uncontrolled register (French courteous, Russian telegraphic), and
Russian missing from the app entirely despite the model speaking it fluently.
Maintainer triage (2026-07-22): ship the easy fixes now (Bundle C), probe the
unclear ones (D), and commit to two structural epics -- the voice model stops
handling field ids (A), and field spoken names get translated like option
labels already are (B).

## Bundle C -- immediate small fixes (1-2 PRs, then a rerun sweep)

`polyglot-pdf-mccl` (add Russian, code-backed ru-RU -- FIRST, so Epic B's
backfill covers it), `nb2c` (declines always leave the field empty, never
literal "N/A"), `s39z` (spell Latin-alphabet values with English letter names
in every session language), `djnk` (unknown-field-id feedback hardening --
interim; epic A supersedes), `lo37` (harness: localize confirm/decline
fixtures). Then one multilingual rerun sweep (~$3) to confirm the observed
bugs don't recur.

## Epic A -- Deterministic field focus (`polyglot-pdf-66ek`)

The voice model loses `field_id` entirely: `update_form_fields` /
`confirm_field` / `skip_field` operate on the backend's `_current_field_id`
pointer; `get_form_status` returns whole-form compact status;
`switch_to_field` (already free-text + client-resolved + secretary fallback)
is the only navigation affordance. Ids do NOT leave the backend<->client wire
-- only their SOURCE changes (backend pointer instead of model echo).

Ground truth (verified 2026-07-22): focus is already tracked deterministically
on both sides (`form_filling_service.py:101` backend pointer;
`navigation.ts:125-264` client `computeNextField` + pin); multi-field fills
already don't exist (single-field only, `config.py:391-392`); the h1bn
coercion (`form_filling_service.py:1310-1347`) already re-points unresolvable
ids but treats a RESOLVABLE-but-wrong id as an authoritative correction (bd
8vy3) -- the exact zh wrong-field gap. A large fraction of the DTI SI exists
only to make id-echoing reliable (`config.py:777-822`).

Design commitments (adversarial-review-hardened):
1. Model-side removal only; the backend keeps sending its resolved id to the
   client (webFormConnection handlers key on it).
2. The two-pointer invariant is explicit: client acks carry the field id
   acted on; backend asserts equality, logs `focus_desync` telemetry, and
   resyncs FROM the client (client owns state); reconnect re-seeds the
   pointer from the handshake (test-pinned).
3. The 8vy3 late-correction reroute (switch-first) is PROBED, not assumed --
   A1 runs a scripted "confirm N, correct N-2, continue" scenario; fallback
   is a narrow resolvable-id affordance behind the flag, decided at the A1
   readout.
4. get_form_status goes id-less too, so ids leave the model's vocabulary
   entirely; secretary answers + switch candidate lists stop echoing raw ids.

Beads: `66ek.1` A/B probe + r5m7 reproduction (THE GATE -- Epic A proceeds
only if the wrong-field class is attributable to model-side id handling and
reliability is non-regressed; ~$8, n>=3 per arm per language) -> `66ek.2`
backend contract behind `TOOLS_IDLESS` default-off -> `66ek.3` SI rewrite
(blocked by B2's SI rule landing first) -> `66ek.4` test migration + flag
flip + old-path removal.

Exit rubric: (1) correction scenario lands every value in the right real
field 3/3; (2) fill+confirm+advance reliability >= the A1 baseline arm,
n>=3/language; (3) zero `focus_desync` events in the verification sweep;
(4) suites green with the new contract pinned. ("Zero invented-id fills" is
structurally guaranteed by the design and deliberately NOT a criterion.)

## Epic B -- Translated spoken field names (`polyglot-pdf-tupu`)

Mirror the proven option-label pipeline (ow1e runtime + 2h9j extraction-time
bake) for per-field `spoken_name_translations` (lowercase language-name keys,
same convention as option `label_translations`). Supersedes bd 37le (closed).

Threading map (re-verified against current code, symbol-anchored so it
survives line drift): override hook `_apply_label_overrides` in
`manifest_service.py`; `render_field_guidance`'s `Spoken:` line in
`ai_context.py`; the option-override call sites (`form_filling_service.py`'s
`get_option_label_overrides` injection and its `option_label_overrides=`
call into `render_field_guidance`; `callback_handler.py`'s
`_option_overrides`/`_spoken_overrides` helpers and their three call sites)
PLUS the channels the option list misses: switch success message
(`callback_handler.py`'s `_switch_success_response`), switch
candidate/clarify lists (`_switch_degrade_response`), ask_secretary `fields`
arrays (`_handle_ask_secretary_tool`'s `response["fields"]` assembly),
backend-side hint substitution (`FormFillingService._resolve_hint_field_schema`
in `form_filling_service.py`), and `previous_spoken_names`
(`ai_context.py`'s `render_section_metadata` and `build_form_context`
parameters). The runtime build change is a NAMED contract change to
`option_translation.py`'s `get_translation_overrides` (returns one
`TranslationOverrides` dataclass with `.option_labels` / `.spoken_names`
dicts, pinned in `test_option_translation.py`): one overrides object, one
batched call over the UNION of missing strings. Editor: stale-drop on
spoken_name rename in `FieldEditor.tsx`'s spoken-name `onChange` handler
(`delete edited.spoken_name_translations` alongside the edit).

Out of scope: the legacy non-DTI SI FIELDS block stays English; visual
on-screen form translation stays parked (maintainer decision 2026-07-17).

Beads: `tupu.1` schema+bake+backfill (blocked by mccl so Russian rides the
pass) -> `tupu.2` runtime+threading+SI rule -> `tupu.3` editor support ->
`tupu.4` verification sweep (n>=3 x es/zh/hi/fr, ~$9).

Exit rubric: (1) all 4 kits fully covered for every code-backed language;
(2) in-language field names, zero raw-English field-name readouts, n>=3 per
language; (3) zero spoken-name secretary queries (overall secretary volume
tracked as a diagnostic metric only); (4) English sessions byte-identical.

## D -- probes + standalone beads

- `polyglot-pdf-m1lg`: `speech_config.language_code` acceptance probe on
  native-audio Vertex (<$0.05), then n>=3 output-language-adherence reruns if
  accepted. Explicitly NOT aimed at ww9y (that was mis-generation with
  correct input transcription).
- `polyglot-pdf-zmlo`: register-guidance A/B (general language-agnostic tone
  rule + title translation; per-language register controls only if it fails).
  h1me closes on its outcome.
- `polyglot-pdf-3x87`: es-ES vs Latin American Spanish modal disambiguation.
- `ww9y` + `r5m7` resolve through the A1 gate (`66ek.1`); `djnk` is interim.

## Sequencing

Bundle C -> D probes in parallel -> Epic B (tupu.1-.4) -> Epic A (66ek,
gated on the A1 readout; its SI bead 66ek.3 lands after B2's SI rule).
Estimated live-model spend across all probes/verification: ~$25-30.

## Verification

Per-PR: unit/contract pins named above + full suites. Behavioral: the 6mzi
harness per-language 14q slices with `--debug` transcripts, n>=3, compared
against the committed 2026-07-22 baselines
(`scripts/spikes/data/costs_i90-full_2.5_dti_cont_happy_20260722T17*`).
Program success = a repeat 5-language assessment showing no wrong-field
fills, no invented ids, in-language field names, consistent declines,
register per guidance, and Russian first-class.
