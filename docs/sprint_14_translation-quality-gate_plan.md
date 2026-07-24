# Sprint 14 -- Translation quality gate (context-first translation + verify/rectify)

Commissioned 2026-07-23; maintainer-approved same day after THREE review
rounds (research input + adversarial Opus review + a third feedback round,
folded in as "review round 3" below). Epic: `polyglot-pdf-sekc`.

## Why (L1)

Every translated string the app ships -- field spoken names, checkbox option
labels, section titles, across 17 non-English languages in all 4 form kits
(~643 unique strings x 17 = ~10,900 translations) -- was produced by a SINGLE
model call checked by nothing but itself. `TextAIGemini.translate_labels`
(`backend/adapters/text_ai_gemini.py:346`) validates the response for JSON
SHAPE only; a fluent-but-wrong translation ships. Worse, the call carries ZERO
context: bare deduped strings, no form name, no field, no sibling options --
the known worst case for short-string translation ("State"? "Single"?
"Present"?). This is a hole in the project's "second opinion on everything"
policy -- and the maintainer cannot manually verify 16+ languages.

The maintainer already named the underlying blocker when parking the full
display-translation path (bd memory `visual-translation-path-deliberately-
parked`, 2026-07-17): translated output creates "a real obligation to
native-speaker review per language," with no contacts or funds yet. **This
epic is the automated substitute for that review, with the funded human
review filed as a funding-gated bead (maintainer directive 2026-07-23).**

Maintainer decisions (2026-07-23, in-chat):
- Warn-only is useless to an editor who doesn't speak the language: the gate
  must RECTIFY -- a model pass that, given the original + current translation
  + back-translation + drift reason, produces a FIXED translation.
- Verification is OPT-OUT (default on), not opt-in.
- Judge drift verdict is `{drift, reason}` (house validator shape).
- Still-drifting after bounded retries: KEEP best attempt, FLAG UNRESOLVED
  for human review, never silently trust.
- From the research pass: adopt context-carrying translation, temperature 0,
  pro-tier where it matters; avoid over-engineering (no TMS, no multi-vendor
  ensemble, no human spend now).

## Design principles (ordered)

**Prevention > detection > correction > human escalation.** Context is a
bigger quality lever than any checker -- a checker cannot recover information
the translator never had. So the epic FIRST upgrades the forward translation,
THEN verifies it.

### Part A -- Make the forward translation right (prevention)

1. **Context-carrying translation payload.** Replace the bare string list
   with structured items: `{text, kind (field-name | option-label |
   section-title), form (name+number), parent_question (for options),
   sibling_options (translated AS A SET so options stay mutually
   distinguishable and grammatically parallel -- the current union-dedupe
   actively breaks this for sets like filing status)}`. New adapter method
   (`translate_items`) beside `translate_labels`; the bake builds the
   structured payload from data it already holds. Dedupe stays (same text +
   same kind translates once); option sets group by parent.
2. **Per-language glossary + style file, seeded from the government's own
   translations.** A committed UTF-8 data file (`form-kits/_translation/
   glossary.json` -- data, not .py, per scar #6) with: (a) pinned terms from
   IRS Pub 850 (EN-ES, EN-ZH) and USCIS's own multilingual renderings --
   HONEST COVERAGE SCOPE: real term pins exist for ~2-3 languages (es, zh);
   the other ~14 languages get only (b)-(e); (b) a per-language REGISTER line
   (es: usted; de: Sie; fr: vous...) mirroring the zmlo voice-register
   decision, all 17 languages; (c) a do-not-translate list (form numbers,
   USCIS, ITIN, agency names), language-independent; (d) an explicit DIGITS
   line (review round 3): ASCII digits are PINNED in every language --
   locales that conventionally use native numerals (ur: Arabic-Indic) still
   emit ASCII, because this text guides entry into a US form; (e) the
   expected-script table (ru Cyrillic, zh Han, hi Devanagari, ur Arabic...).
   Injected into the translate, judge, AND rectify prompts. Defensibility
   bonus (es/zh): "we match the agency's own terminology" beats "our LLM
   chose this word".
3. **Temperature 0.0** (from 0.1) on the translate path -- deterministic
   legal translation; translate-path-only (the validator/secretary
   byte-stability is untouched).
4. **Ambiguity self-flag.** The translator's output schema gains an optional
   per-item `ambiguous` flag ("source under-determined") -- nearly free,
   catches the "State/Single" class at the source; ambiguous items flow into
   the same report channel as drift flags.
5. **The RUNTIME translation path is unified, not silently diverged**
   (adversarial-review blocker B1). `build_translation_overrides` -- the live
   session-start fallback for unbaked strings -- switches to the SAME
   context-carrying `translate_items` call (it holds the full schema, so the
   context payload is free). HONEST RESIDUAL, stated not hidden: runtime
   translations remain UNVERIFIED (no judge loop at session start --
   latency). After the V5 re-bake all shipped kits are fully baked, so the
   runtime path fires only for new/edited kits before their next bake -- and
   those get verified at that bake.

### Part B -- The verify/rectify loop (detection + correction)

Runs inside the ONE shared bake (`bake_label_translations`,
`backend/services/option_translation.py`), after the fan-out loops, on the
just-baked strings per language. All three call sites (CLI, extraction step
3f, editor route) consume the returned `report` dict, so flags reach every
surface with zero per-site plumbing. **Batch per LANGUAGE, never per string.**

0. **Deterministic mechanical lint (NO model, runs first).** Regex/rule
   checks on every translated string: do-not-translate terms present and
   unmangled; digits ASCII and format masks byte-exact (ASCII digits pinned
   in ALL languages incl. native-numeral locales -- the glossary line
   A.2(d)); the EXPECTED Unicode script PRESENT (dominant after stripping
   DNT terms and masks) -- **NEVER "no Latin present"** (review round 3:
   correct translations legitimately keep "I-90", "USCIS", "mm/dd/yyyy"
   verbatim inside Cyrillic and Devanagari strings alike); non-empty;
   glossary pins honored where they exist. **Pin-check caveat (review round
   3):** exact-substring matching is sound for today's pins (zh doesn't
   inflect, es only mildly) but will false-positive on inflecting languages
   -- when pins expand to ru/ur/pl-class languages the check needs
   normalization or demotion to advisory there. A mechanical failure is
   PROOF of wrongness -- it skips the judge ON THE WAY IN and feeds rectify
   directly, but the rectified string **re-enters the FULL loop** (re-lint +
   back-translate + re-judge; review round 3 disambiguation): a rectify pass
   that restores "USCIS" can simultaneously drift the meaning. This also
   makes exit criterion 2 checkable BY SCRIPT.
1. **Back-translate** (INDEPENDENT lite call, `get_text_ai` chain): baked
   foreign strings -> English. Evidence for the judge, NOT the sole signal.
   (High V1 false-positive rate? Suspect THIS layer first; the targeted fix
   is bumping only flagged-string re-verification one tier.)
2. **Bilingual judge** (pro, bounded thinking): batched per language but
   CHUNKED to ~25-50 items per call (per-item judgment quality degrades with
   batch size; V1 A/Bs two chunk sizes and pins the number empirically).
   Each item: {original English + its context, the FOREIGN translation
   itself, the back-translation, the glossary + register line}. Verdict
   `{drift: bool, reason}`. Judging the foreign string directly (round-trip
   as supporting evidence) addresses both round-trip failure modes: a wrong
   translation that round-trips clean, and a good idiomatic translation that
   round-trips non-literally. Prompt is a byte-stable module constant with
   an anti-over-flag precision block (the W5/g1c lesson: enumerate what is
   NOT drift) -- and REGISTER CONFORMANCE as an explicitly checked
   criterion.
3. **Rectify** (pro, flagged strings only): batched per language; given
   {original + context, current translation, back-translation, drift reason,
   glossary} -> corrected translation. The correction RE-ENTERS the loop
   (fresh back-translate + re-judge; the judge never sees provenance).
   Bounded to 2 rectify attempts. **Keep rule:** first attempt that
   re-judges clean REPLACES the translation; if neither clears, keep the
   ORIGINAL baked translation -- it came from the same pro tier with
   glossary, whereas a twice-rejected rectify attempt may be appeasement
   drift. **Known collision, decided on V1 evidence (review round 3):** for
   MECHANICAL-origin flags the original is PROVEN wrong, so a rectify
   attempt that passes the lint but gets judge-flagged is plausibly the
   better keep. **DECIDED by V1's readout (2026-07-24, bd i36i,
   `scripts/spikes/translation_gate_findings.md`): mechanical-origin
   unresolved keeps the latest LINT-CLEAN rectify attempt when one exists
   (the collision materialized live -- keep-original would have shipped a
   provably wrong digit); judge-origin unresolved keeps the ORIGINAL.**
   Both still flag UNRESOLVED. V3 also inherits: a flip-flop detector
   keyed on REJECTION RECURRENCE (the judge re-flags a value already
   flagged earlier in the item's trace -> UNRESOLVED early; never value
   identity alone -- the ur trace converged on a re-proposed value),
   judge-prompt hardening against back-translation anchoring and
   never-flag-your-own-proposal, and chunk size 50.
4. **Fail-open throughout**: missing client / failed back-translate / judge
   or rectify error leaves the original baked translation in place with a
   "verification unavailable" note -- the gate can never make a kit worse
   than today's unverified state.
5. **Prompt hygiene** (review N1): source strings -- including author-typed
   labels from the editor route -- enter judge/rectify prompts as DATA,
   `json.dumps`-delimited, never as instruction text.

### Flag taxonomy (one report channel, four kinds)

LintFinding-shaped (`severity/rule/path/message`), ALL severity=WARNING --
never ERROR, so no flag can block kit publish (publish-blocking would
contradict fail-open; shipping decisions on flags stay human). Path
convention carries the parent in the exact shape
`schema_lint.field_id_of()` parses, so `field_id` derivation works
(V2 build note -- the plan's original prettier format parsed to None):
`fields[<idx>] (id=<field_id>).spoken_name_translations.<lang>` /
`fields[<idx>] (id=<field_id>).options[<value>].label_translations.<lang>` /
`sections[<section_id>].label_translations.<lang>` (sections carry no
`(id=...)` -- no field to focus).
- `translation-drift-rectified`: judge flagged it, rectify cleared it on
  re-judge; message = drift reason + old->new note. Informational.
- `translation-drift-unresolved`: no attempt cleared; ORIGINAL kept; message
  = drift reason + the rejected attempts. The human-review worklist.
- `translation-ambiguous-source`: the translator's self-flag. Usually fixed
  by enriching context/glossary, not the string.
- `translation-mechanical`: the deterministic lint's kind (DNT violated /
  format mask broken / non-ASCII digits / wrong script / empty / glossary
  pin missed). Feeds rectify directly (no judge on the way IN); the
  rectified string re-enters the full lint+judge loop; if no attempt clears,
  it joins the UNRESOLVED worklist (keep rule pending V1 measure (c)).

**Default-ON, opt-out** (`--no-verify` / `TRANSLATION_VERIFY_ENABLED`).
This does NOT contradict the wire-pro-passes-dark pattern
(`FORM_COMPLETE_PRO_VALIDATOR` default-false): that guards RUNTIME
per-session cost; this gate runs at AUTHORING time only -- a deliberate,
per-bake spend of ~cents.

### Explicitly rejected as over-engineering at current scale (recorded)

- **TMS / translation-memory platform** (Crowdin etc.): 4 kits, 64 calls;
  the glossary file IS the mini-termbase, and confirmed-good translations
  get promoted into it. Revisit when form count reaches dozens.
- **N-way translation across model families + adjudicator**: violates the
  single-provider Vertex posture, 3x cost; the bilingual judge + glossary
  covers the same failure classes at this scale. The valid kernel
  (self-preference bias) is handled by provenance-stripped judging.
- **Context caching / few-shot cache infrastructure**: 64 calls total.
- **Native-PDF translation path**: different pipeline, out of scope.
- **`response_schema` structured-output hardening**: noted, not a bead.

## Tiers + reuse (verified in exploration)

- Forward translate + rectify + judge -> pro (`OPTION_TRANSLATION_MODEL`
  gemini-2.5-pro already; judge/rectify mirror the `get_text_ai_pro` factory
  pattern: empty fallback chain = fail loud, `VALIDATOR_PRO_THINKING_BUDGET`
  512). W5 measured pro recall 1.000 vs flash 0.50 / lite 0.33 on
  comparison-judgment at ~$0.009/call. Back-translate -> lite chain
  (`get_text_ai`) for independence from the pro forward path.
- Service/verdict shape mirrors `ValidatorService`; adapter methods mirror
  `validate()`: JSON-mime, shape-validate, fail-open, counts-only logging.
- Flag list mirrors `schema_lint.LintFinding` so it rides the editor
  `ValidationPanel` UI and the `_bakeoff.authoring` provenance slot.

## Cost estimate (Gate 2)

Per kit-language: base = 1 back-translate (lite) + judge calls CHUNKED at
~25-50 items (2-6 judge calls for a large kit). Each rectify attempt adds
rectify (pro) + fresh back-translate (lite) + chunked re-judge (pro), max 2
attempts. The mechanical lint is free. Across 4 kits x 17 languages = 68
kit-languages:
- Full re-bake (context+glossary+temp0 forward pass): 68 pro calls, ~$2-3.
- Verify worst case with chunking: ~1,100 calls (~700 pro) ~= **$7-8**;
  realistic: ~350 calls ~= **$3**.
- The combined V5 re-bake+audit is ONE maintainer ask (~$10-11 worst case
  all-in). The V1 pilot (1 kit x 3 languages, ~$0.25) needs no separate
  go-ahead (pre-authorized at plan approval).

## Exit rubric (epic `polyglot-pdf-sekc`)

Criterion (1) is the DETECTION-QUALITY anchor -- (3) and (4) are plumbing
checks a never-flagging judge could pass vacuously, which is exactly why (1)
gates the build (review N3).

| # | Criterion | Verify |
|---|-----------|--------|
| 1 | V1: planted mistranslations caught (incl. the clean-round-trip trap) AND official/idiomatic renderings not flagged | probe report table |
| 2 | Translations are context-carrying and mechanically valid: option sets translate as units; the deterministic lint passes SCRIPT-CHECKED over the re-baked kits (DNT intact, format masks byte-exact, ASCII digits, expected script present, glossary pins incl. es "head of household" == Pub 850) | unit pins + a lint run over the kits, no diff-reading |
| 3 | Default-ON, fail-open, bounded: a verify outage leaves the kit byte-untouched; an unresolved string keeps the ORIGINAL + is flagged, never silently trusted | unit pins |
| 4 | The V5 re-bake ran THROUGH the verify loop and yields the per-language flag list | V5 findings + kit diff |

## Bead tree

Order: V2 -> V1 -> V3 -> V4 -> V5. (V1 runs after V2 so the probe exercises
the real glossary + lint module; V1 gates V3 -- the epic's one probe gate.)

| Bead | Scope | Surfaces | Inherits |
|------|-------|----------|----------|
| `polyglot-pdf-ch7j` (V2) | `translate_items` context payload + glossary/style file (pins es/zh; register + script + ASCII-digit lines all 17; DNT list) + temp 0.0 + ambiguity self-flag + the MECHANICAL LINT module (pure functions, zero live calls). NO re-bake (review S1). | `backend/adapters/text_ai_gemini.py`, `backend/services/translation_lint.py`, `form-kits/_translation/`, unit tests | 2 |
| `polyglot-pdf-i36i` (V1) | Standalone spike: full loop on 1 kit x es/zh/ur (ur over af, review round 3). Planted errors = mechanical corruptions of Pub 850 gold. Measures (a)-(e) incl. the mechanical half-success keep-rule plant. GATE for V3. | `scripts/spikes/translation_gate_probe.py` + data + findings | 1 |
| `polyglot-pdf-9ikj` (V3) | The loop in `bake_label_translations` (lint -> back-translate -> judge -> bounded rectify, full-loop re-entry, provenance-stripped re-judge) behind default-ON `TRANSLATION_VERIFY_ENABLED`; runtime fallback onto `translate_items`; flag taxonomy into report; test migration. | `backend/services/option_translation.py`, `backend/dependencies.py`, `backend/config.py`, bake tests | 3 |
| `polyglot-pdf-9djc` (V4) | Flag surfacing: CLI FLAGS block + `--flags-out` + `--no-verify`; extraction provenance + console count; editor route `flags` -> ValidationPanel. | CLI script, `extract_form.py`, `editor_kit_routes.py`, `schema-editor/src/` | 3+4 (surfacing half) |
| `polyglot-pdf-hif1` (V5) | Pre-re-bake git tag; re-bake 4 kits x 17 languages THROUGH the pipeline; per-language UNRESOLVED+ambiguous flag list (low-resource first) + findings; cross-family judge comparison via Claude subagent (once, spike-only). THE one maintainer-ask spend. | `form-kits/` | 2+4 |

- **V6 (risk-tiered vignette check): deliberately NOT filed** -- file only if
  V5's flag rates suggest residual risk (plan decision).
- **`polyglot-pdf-6mji` (funding-gated, STANDALONE):** human/native review
  program (marketplace review, legal-aid outreach, in-app feedback button).
  Not an epic child so the epic can close at V5; blocked on V5 + explicit
  maintainer funding confirmation.

## Out of scope

- Visual/on-screen form translation (parked, maintainer 2026-07-17).
- Native-PDF translation path.
- TMS platforms, multi-vendor ensembles, caching infra (rejected above).
- The legacy (non-DTI) SI FIELDS block stays English.

## Verification (end-to-end)

- V1 probe = behavioral proof of judge discrimination in both directions,
  run under the experimentation skill gates (standalone spike).
- Unit tests pin every stage with stubbed adapters (no live calls): loop
  bound, keep rule(s), flag taxonomy, fail-open paths, runtime unification.
- V5's re-bake-through-the-pipeline is the program-level proof; the es slice
  of its diff is directly checkable against Pub 850, and its UNRESOLVED list
  is the standing artifact the funded human review inherits.
