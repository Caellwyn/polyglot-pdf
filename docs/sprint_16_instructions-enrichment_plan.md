# Sprint 16 -- Instructions enrichment: booklet-grounded field guidance from the extraction pipeline

**Status:** maintainer-approved 2026-07-25 (plan-mode session; two design rounds
plus an adversarial review round). This is the plan-of-record for the
instructions-enrichment epic; every bead in the epic carries a `plan:` pointer
here.

---

## Why (the problem)

Per-field `help.instructions` is the voice AI's only reference for guiding a
user through a field, and it is sub-par because **the extraction LLM is never
asked for it**: the extraction contract
(`scripts/bakeoff/schema_contract.py::_CONTRACT_TEMPLATE`, FIELD SHAPE) has no
`help`/`instructions` key. Everything shipped today comes from two
deterministic post-steps in `scripts/authoring/extract_form.py`:

- `/TU` tooltip copy (`_extract_instructions_from_dump`, fills blanks only), and
- an OPTIONAL shallow booklet match (`_enrich_instructions_from_pdf`: shortest
  paragraph containing the field name as a whitespace-collapsed substring,
  appended after /TU; deep ingestion explicitly deferred in bd s4dp.3).

Result: i-90 has 132/132 fields covered only because its acroform carries rich
/TU tooltips (median 75 chars, thin tail, at least one factual error -- the
`p3_line9_heightinches3` text says "weight in pounds"). w7 has **0/59** -- zero
/TU tooltips, and the booklet enrichment never ran despite
`form-kits/w7/w7-instructions.pdf` sitting in the kit dir. There is **no lint
rule, no judge, and no metric** for guidance quality anywhere.

The source material is ample: both booklets are in-repo, pure text, and small
(i-90instr 11 pp at `schema-editor/public/schemas/i-90/i-90instr.pdf`; W-7
16 pp). The goal is a pipeline that populates guidance well enough that the
voice AI can answer deep questions ("which reason box do I check?") and reduce
the meticulous human labor of correcting these fields -- for FUTURE
extractions, not a one-off content fix.

## Decision record (maintainer, 2026-07-25)

The hard call was the depth model, driven by the W-7 "Reason You're Submitting
Form W-7" case: one consolidated checkbox group whose booklet guidance (pp.
6-8) is ~3,400 tokens -- 8 lettered categories, 5 numbered Exceptions, and
cross-field obligations (a/f also require box h + an exception designation;
b forces a foreign address on line 3; d requires the citizen's SSN and
date-of-entry rules).

**Resolution: DECOUPLE STORAGE FROM DELIVERY.**

- **Storage -- extraction always emits BOTH artifacts per field:**
  - `help.instructions`: short synthesized overview, 2-4 sentences. The ONLY
    abstractive (rewritten) text; judged and human-reviewed.
  - `help.details` (new key): VERBATIM booklet excerpts under headings (per
    option letter for consolidated groups, per line for line-keyed content).
    Zero-trust channel: a deterministic booklet-containment lint verifies
    every paragraph.
- **Delivery -- a backend policy, v1 default = INLINE:**
  - The spoken ask-hint (the bo4m "Context to briefly convey when asking"
    tail) carries ONLY the short instructions -- never details.
  - The per-field guidance block (DTI) injects BOTH, labeled ("Instructions:
    ..." + "Official reference text: ..."). While the field is current the
    voice model holds the full verbatim section: full grounding, no hook to
    follow, no blocking secretary round-trip (median ~1s, tail 8-20s), no
    context starvation. Context compression reclaims it after moving on, so
    the inline cost is transient (low single-digit cents/session at w7 scale).
  - The secretary static catalog renders details too (flash-lite, cached
    prefix, ~1/10 input rate -- near-free), so cross-field and after-the-fact
    deep questions work through the EXISTING `ask_secretary` tool. No new
    tools in v1. One SI line: answer deep questions from the reference text;
    if you don't hold it, ask the secretary.
  - **Secretary booklet FLOOR (load-bearing review fix):** the deepest user
    questions are FORM-level ("am I eligible?", "what documents do I need?",
    "where do I mail this?") and much of the W-7 booklet (Who Is Eligible,
    Supporting Documentation Requirements, How/When/Where To Apply) attaches
    to NO field. Without a floor those passages have no home and the "ask the
    secretary" fallback is circular. Fix: the WHOLE booklet text goes into the
    secretary's cached prefix, plus a form-level details block in the catalog.
    Verbatim by construction, zero mapping risk, near-free at w7 scale.
- **Phase 2 (pre-designed, deferred):** per-field/per-form delivery flip to
  secretary-mediated depth -- a render-derived hook line (topic index derived
  from details headings + "ask the secretary rather than answering from
  memory") and a widened `ask_secretary` contract (third use: detailed
  requirements guidance on a field, KEEPING the bd-2af7 name/id prohibition).
  Activated by the step-2 measurement gate or by a giant-booklet form (f1040
  instructions ~100 pp, i-589 30+ pp). Config/threshold change; no schema or
  extraction change.

**Rejected alternatives** (stress-tested; do not reopen without new evidence):
dump-into-instructions-single-key (floods the spoken ask-hint; welds delivery
to schema); index-only pointers (the secretary never sees the booklet --
invites hallucination; also bad editor ergonomics and no git-diffable
content); secretary-first-by-default before measuring (risks starving the
voice model to save fractions of pennies); extending the main extraction
contract (perturbs a solved, graded, output-ceiling-constrained pass and loses
the standalone backfill CLI); runtime synthesis (per-session improvisation is
the corruption vector this design exists to avoid -- summarization happens at
bake time, as a reviewable artifact).

**Trust posture:** passage-to-field distribution = high trust (the booklets
are line-/option-keyed) plus judge-checked. Summarization = moderate trust,
confined to the smallest artifact (instructions), judged against details,
human-reviewed. The deep channel needs NO trust (verbatim + containment lint).
Nothing unreviewed ships in an immigration/tax product.

## Architecture: dedicated post-extraction enrichment stage

A new chunked LLM call, separate from field extraction:

- **Seam:** `scripts/bakeoff/llm_providers.py` (Claude CLI free locally /
  Gemini hosted; add an `INSTRUCTIONS_MODEL` env mirroring `EXTRACTOR_MODEL`;
  generalize the scratch-file output path to a `run_json` helper).
- **Inputs:** per-field digest (id, name, type, options, show_if, /TU) + the
  booklet TEXT + the form TEXT (extracted layout-aware -- see quality gate --
  provider-neutral, no multimodal dependency).
- **Outputs:** `{field_id: {instructions, details, format_hint}}` plus the
  form-level details block.
- **Runs two ways:** (i) inside `extract_form.py::extract()` post-repair,
  beside the option-translation bake, fail-open and credential/CLI-gated;
  (ii) as a standalone backfill CLI over an existing kit's schema.json
  (`--instructions-pdf` explicit, kit-dir glob fallback across the
  inconsistent booklet filenames). w7 backfill is the validation vehicle.
- The existing /TU baseline and naive booklet match remain the deterministic
  fail-open floor. `warning`/`example`/`legal_reference` stay unpopulated (no
  consumers; pure liability). `format_hint` IS emitted (three live consumers).
- Replacement, not append, for machine-provenanced fields; empty beats filler.

## Content contract (one module; consumed by the prompt, the judge, and lint)

- Grounding: every claim traceable to booklet/form//TU; no outside legal
  knowledge.
- instructions priority: where-to-find-value > applicability NOT already
  modeled as show_if > headline pitfalls/interlocks > format (only when
  format_hint cannot carry it). Speakable register: English, second person,
  no markdown, no "see page 7", no on-screen deixis. Soft <=280 chars, lint
  hard 500. Anti-restatement of label/options.
- details: faithful excerpting only; headings mandatory above a size
  threshold; no dangling cross-references; WARNING above ~3k words/field.

## Quality gate: born verified, stricter keep than translations

- **Deterministic lint** (native in `backend/services/schema_lint.py`, so it
  runs on every lint pass): instructions missing / label-restatement /
  too-long / screen-ref; details **booklet-containment** -- every paragraph
  must fuzzy-match into the booklet text. Containment spec pinned in the
  contract module (dehyphenation, reflow, curly-apostrophe folding, match
  threshold) and the lint RECORDS the matched source span. Extract booklet
  text layout-aware (`get_text("blocks")`/`"dict"`); evaluate the official
  IRS/USCIS HTML instructions (metadata `instructions_url`) as the canonical
  text source to dodge PyMuPDF column-interleave artifacts in the Exceptions
  Tables. Containment kills fabrication, NOT misleading-by-omission.
- **Bake-time judge** (chunked; tier reuses the translation-bake tiering):
  instructions -> {grounded, unsupported_claims[], useful_beyond_label};
  details -> scoping check PLUS an omission check (flag excerpts whose
  adjacent qualifying clauses -- "unless...", "except..." -- were dropped).
- Bounded rectify (max 2) with full-loop re-entry (re-lint, re-judge).
- **KEEP rule:** unresolved or judge-unavailable fields fall back to the
  deterministic baseline (/TU + no details). NEVER ship unverified LLM legal
  text. Enrichment is all-upside-or-status-quo.
- Flags persisted at `_bakeoff.authoring.instructions_enrich.flags`,
  re-emitted through the existing translation-flags pattern in `schema_lint`;
  all WARNING, never publish-blocking; ValidationPanel gets rule labels.

## Provenance / no-clobber

- `_bakeoff.authoring.instructions_enrich.provenance`:
  `{field_id: {source: tu|booklet-match|llm-verified, sha1}}` + top-level
  `booklet_sha1`. Hashes cover instructions AND format_hint AND details.
- Hash mismatch or no record => human-owned => skipped. Machine text is
  upgradeable (tu -> llm-verified always; llm-verified refresh on
  booklet_sha1 change or `--force-refresh`); human text only via `--force`.
- **Bootstrap pass (required -- without it the i-90 refresh is a no-op):**
  legacy kits have no records, so "no record => human-owned" would skip all
  132 i-90 fields. One-time mechanical pass: a field whose current
  instructions text EXACTLY matches its /TU entry in the acroform dump is
  marked machine-owned (source: tu); hand-edited fields fail the match and
  stay protected.
- Staleness: booklets revise annually; `booklet_sha1` paired with the form
  version metadata must flag a stale booklet loudly.

## Runtime wiring (v1)

- `backend/models/form_models.py` `FieldHelp` += `details` (+ TS mirrors:
  `frontend/src/schema-forms/types/schema.ts`, `schema-editor/src/types/
  schema.ts`, generated `backend/schemas/form_schema_types.ts`). The frontend
  must NOT render details -- extend the `instructions-not-rendered` guard test.
- Guidance render (`manifest_service.get_field_guidance` +
  `ai_context.render_field_guidance`): labeled "Official reference text:"
  block for the CURRENT field.
- Spoken ask-hint path (frontend `formatNextFieldHint` / bo4m tail): short
  instructions only, never details -- with a test proving it.
- `backend/services/secretary_context.py`: INCLUDE contract += help.details;
  whole-booklet floor + form-level details in the static catalog (byte-stable
  prefix preserved).
- Static SI: the one delegate-don't-improvise line. No new tools.
- schema-editor `FieldEditor`: Details textarea beside Instructions.
- **Transport decision (explicit, step 1, with payload sizes in hand):**
  help.* today rides client -> handshake manifest -> backend; details
  multiplies that payload (the reason field alone ~15KB; 1011-history
  reconnects re-send it) and ships never-rendered text to the browser.
  Alternative: server-side join from the kit copy (backend already reads
  kits) -- lean client payload, render guard satisfied structurally, but forks
  source of truth with the editor. Weigh and decide; do not inherit the
  client path by default.

## Staging (7 beads; measurement gate SECOND, before the engine is built)

1. **Schema + runtime plumbing (v1 delivery).** FieldHelp.details + mirrors +
   editor textarea + guard extension + secretary catalog render (incl. booklet
   floor + form-level block) + inline injection + short-only ask-hint + SI
   line + the transport decision.
   Exit: (a) details round-trips schema -> guidance block AND secretary
   catalog; (b) ask-hint provably excludes details (test); (c) guard test
   green; (d) transport decision recorded with sizes. Splitting this bead is
   the implementer's call.
2. **Attention/behavior measurement gate** (voice harness + experimentation
   skill). Needs only step-1 plumbing plus HAND-CRAFTED reason-field details
   from the booklet -- does NOT wait for the engine. With/without-details A/B
   on the w7 reason field: tool-call reliability, field_id fidelity, spoken
   discipline, deep-question accuracy; verify compression reclaims guidance
   blocks and never trims the CURRENT field's details; plus one non-English
   (e.g. Spanish) run -- a large English verbatim block is a language-lock
   contamination vector against the bar the i18n sprints raised.
   Exit: measured verdict recorded -- inline confirmed as the complex-field
   default OR the delivery policy flips to phase-2 secretary-mediated BEFORE
   the engine is built.
3. **Content contract module + deterministic lint + eval metrics.** Pinned
   containment normalization + matched-span recording; layout-aware/HTML
   source extraction; coverage/length/restatement columns in
   `scripts/authoring/eval_extraction.py`.
   Exit: lint fires on w7 (missing) + synthetic violation fixtures; eval
   table shows the new columns; human eyeball of table-region (Exceptions
   Tables) excerpts recorded.
4. **Enrichment engine, dry-run only.** Digest builder, prompt from the
   contract module, chunked `run_json` call, proposals JSON + diff report; no
   kit writes.
   Exit: w7 proposals >=80% field coverage, lint-clean incl. containment;
   both providers parse.
5. **Verify loop + provenance + kit write.** Judge incl. omission check,
   bounded rectify, KEEP rules, hash no-clobber over all three keys, legacy
   bootstrap pass, `--write`.
   Exit: w7 written born-verified with flags in ValidationPanel; a pre-edited
   field survives a re-run untouched (test); judge-unavailable leaves
   baseline behavior; bootstrap marks i-90 /TU-identical fields
   machine-owned.
6. **Pipeline integration in `extract()`.** Fail-open, credential/CLI-gated;
   naive booklet match demoted to in-stage fallback. NOTE: other sessions are
   actively changing the extractor -- this bead must coordinate/rebase.
   Exit: fresh w7 extraction populates both channels end-to-end;
   field-detection eval scores unchanged.
7. **Backfill + review.** w7 backfill + i-90 refresh (canary: the
   height/weight instruction error must be corrected or flagged -- reachable
   via the step-5 bootstrap); hand-review ~15-20 fields (the reason field is
   the designated hard case); journal the findings.
   Exit: both kits at target coverage, flags triaged, review recorded.

**Cross-link:** cross-field interlocks (a/f => box h + exception designation)
overlap the sprint-15 relationship-extraction epic (`polyglot-pdf-o2bs`,
`docs/sprint_15_relationship-extraction_plan.md`): machine-actionable
conditionality belongs THERE; spoken guidance belongs HERE.

## Out of scope / follow-ups

- i18n of instructions/details (non-English sessions get localized names +
  English guidance today) -- follow-up bead, not this epic.
- Booklets for f1040/i-589 kits -- acquire when those forms matter; their
  scale is what activates phase 2.
- Phase-2 hook + widened ask_secretary contract -- pre-designed above,
  activated by measurement or form scale.

## Prior art / key code pointers

- bd s4dp.3 (`docs/journal/entries/2026-06-29-bd-s4dp.3-help-from-instructions.md`)
  -- the existing /TU + shallow booklet merge and its defended decisions;
  merge-contract tests in `tests/test_extract_form_instructions.py`.
- bd 0x10.2 -- help.instructions is AI-guidance only, never rendered
  (`frontend/src/schema-forms/components/fields/instructions-not-rendered.test.tsx`).
- Consumers: `backend/services/manifest_service.py::get_field_guidance`,
  `backend/services/ai_context.py::render_field_guidance`,
  `backend/services/field_utils.py` (bo4m spoken tail),
  `backend/services/secretary_context.py`.
- Verify-loop shape to mirror: `backend/services/translation_verify.py`.
- Extraction-quality ground truth: `docs/research/2026-06-12-7a9.10-enrichment-signal-ablation-findings.md`
  (field detection is solved; do not perturb it).
