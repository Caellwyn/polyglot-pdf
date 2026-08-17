# System-instruction (SI) reduction -- frozen contract

**Tracks:** backend/config.py backend/services/ai_context.py backend/services/manifest_service.py

*Last updated: 2026-08-14 (bd polyglot-pdf-77j0d: the cost rationale pointer no
longer asserts the obsolete "text-in is 95-98%" premise -- this epic plus
compression capped text-in, so audio-in now leads).*

Continuous-DTI is the production default (`USE_DTI` defaults true, bd
polyglot-pdf-7872); the legacy full-SI is the deprecated section-reset fallback (bd
polyglot-pdf-55jg). The JIT manifest SI mode was removed (bd polyglot-pdf-en2j); the
two surviving SI modes are DTI (shipped) and legacy full-SI (fallback). The
ADDRESS CONSISTENCY prose stays permanently in both templates as the primary check
(bead B1 / polyglot-pdf-jnjj.13 is CLOSED WON'T-DO after the G1 gate came back
NO-GO) -- it is not pending removal. Both templates' CONSTRAINTS direct the model to
briefly convey a field's Note / hint-carried context while asking (bd
polyglot-pdf-bo4m); the per-turn `{next_field_hint}` string built by the frontend
(`formatNextFieldHint`) appends `help.instructions` as "Context to briefly convey
when asking: ...". See
[../journal/entries/2026-07-05-bd-bo4m-field-fine-print-reaches-voice-ai.md](../journal/entries/2026-07-05-bd-bo4m-field-fine-print-reaches-voice-ai.md).
The legacy SI renders the canonical nested `help` block
(`help.instructions`/`help.format_hint`) (bd polyglot-pdf-jnjj.23). Created as the F1
foundation contract (bd polyglot-pdf-jnjj.2).

This is the interface the SI templates and their placeholder sets build against, so
work touching the system instruction does not collide on the `config.py` templates.
It pins: the SI template shapes, the surviving placeholder set, and the status of
the ADDRESS-CONSISTENCY prose (permanent, not pending removal). The cost rationale
(why SI size matters at all, and how much) lives in
[logging-and-cost.md](logging-and-cost.md) (MANDATORY read before SI/cost work) --
note that the invariant MOVED: the "text-in is 95-98% of 2.5 cost, and it's the
per-turn SI" figure that motivated this epic is OBSOLETE. This epic plus context
compression capped text-in, so AUDIO-IN now leads and SI size is no longer the
single dominant lever. That is this work succeeding, not being invalidated -- but
plan new cost work against the current split, not this epic's founding premise;
the model-selection rule lives in [ai-models.md](ai-models.md); this doc owns the
**SI shape** contract.

## Current state: two SI modes, one builder

`backend/services/ai_context.py::build_form_context()` builds the SI on every
(re)connect (the backend is stateless -- it rebuilds from the WS handshake each
time) and branches on the `USE_DTI` flag (`backend/config.py`, **default
`true`** -- continuous-DTI is the production law of the land, bd
polyglot-pdf-7872; set `USE_DTI=false` for the deprecated legacy fallback):

| Mode | Template (`config.py`) | The cost driver |
|------|------------------------|-----------------|
| **DTI** (`USE_DTI=true`, the default/shipped mode) | `DTI_SYSTEM_INSTRUCTION` | Nothing form-specific. The SI is a FULLY STATIC behavioral backbone with NO field data and NO form/session state (byte-identical across every form/section). The CURRENT field's guidance rides the initiating message; each next field's guidance rides the `confirm_field` tool response. See "DTI: guidance injection" below. |
| **Legacy** (`USE_DTI=false`, deprecated fallback) | `SYSTEM_INSTRUCTION` | `{fields_json}` -- the CURRENT SECTION's fields dumped as text. The legacy handshake builder sends `extractSectionFields(currentSectionId)` as `schema`, so the dump is the active section, NOT the whole form. Each field's line carries its authored guidance: the canonical nested `help.instructions` -> `Note:` and `help.format_hint` -> `Format:` (flat `description`/`format` as fallback; bd polyglot-pdf-jnjj.23). |

> **The legacy SI is per-section, not whole-form** -- and it belongs to the
> DEPRECATED section-reset fallback (bd polyglot-pdf-55jg; see
> [section-reset-deprecation.md](section-reset-deprecation.md)). In that flow the
> live model only ever sees the current section's fields, because each section switch
> restarts the Live session with a fresh section SI. The DTI default carries the whole
> form as one session; cross-section recall comes from the exploration tools
> (`ask_secretary`), not from carrying other sections in the SI.

`build_form_context()` selects exactly one template per build: `DTI_SYSTEM_INSTRUCTION`
when `USE_DTI` is set (returned byte-identically, no `.format(...)` -- it carries no
placeholders), else `SYSTEM_INSTRUCTION.format(...)` with the placeholder set below.

## DTI: guidance injection (the shipped path)

DTI (Dynamic Turn Injection, bd polyglot-pdf-jnjj.22; epic polyglot-pdf-13w7) moves
everything form-specific OFF the SI and onto the per-turn injection:

- **Per-field guidance** -- `render_field_guidance` (`ai_context.py`) renders one
  field's guidance (from `manifest_service.get_field_guidance`, incl. `fill_language`).
  When the field has options, the `Options` segment carries the option COUNT and a
  per-turn ask-style marker (bd polyglot-pdf-6bq8 + s503 + cqx6 + 41fi). The gate
  names the ASK-DIRECTLY side (`ai_context.ASK_DIRECTLY_OPTION_TYPES = {select}`):
  a `select`/dropdown renders
  `Options (N -- standard list; ask directly and offer to read all N aloud): [...]`
  at every count (the 50-state lists, height feet/inches). EVERY other
  option-bearing type -- radio/checkbox groups, and any unrecognized or absent
  type (the accessibility-safe default direction, bd cqx6) -- renders by count:
  exactly 2 options ->
  `Options (2 -- ask ONE natural question that makes both choices clear; do not
  recite the labels as a list): [...]` (bd 41fi -- yes/no fields are one natural
  question, not a recital); 3..`LONG_OPTION_LIST_THRESHOLD` (20) ->
  `Options (N -- read ALL N aloud when asking; the user cannot see them): [...]`;
  above the threshold -> `Options (N total -- long standard list; ...)`. Two marker
  phrases key the SI/template carve-outs: "standard list" (a substring of the
  select AND long-list markers) keys the ask-directly-and-offer carve-out, and the
  TWO-option marker is keyed by its own separate `the guidance marks ... TWO
  options` clause in the SI's PRESENTING OPTIONS block, WORKFLOW step 1, and both
  initiating templates -- it is NOT covered by the standard-list phrase. Those
  clauses key on the MARKER, never on a bare option count, because two n==2 cases
  deliberately take the recital branch instead (bd polyglot-pdf-575i + 9tuu): a
  MULTI-select (`MULTI_SELECT_OPTION_TYPES` -- which includes a `checkbox` that
  CARRIES options, the legacy v1 group idiom; a v2 standalone checkbox has none
  and never reaches this branch), where the user may want BOTH options
  and an exclusive either/or ask would foreclose that, and a pair whose labels
  exceed `TWO_OPTION_MAX_LABEL_WORDS` (20), which cannot fold into one natural
  question without dropping substance. That word count is measured on the ENGLISH
  label even in a translated session: `_apply_label_overrides` substitutes the
  session language into `opt["label"]` before the render sees it, and word count
  is not translation-invariant, so the render reads the pre-override English label
  POSITIONALLY from the raw field -- `guidance["options"]` is index-aligned with
  the raw options (sourced by the same `options or allowed_values` rule
  `get_field_guidance` uses), so index i's label is the English one. Measuring
  the translated text made the branch language-dependent and flipped both
  calibration fields on shipped kits. A reverse lookup over the override map was
  tried and rejected: the map is keyed by English label but would be applied to
  labels that may never have been translated, so an untranslated option could
  inherit an unrelated long label's word count. An SI rule keyed on the count would
  contradict the render on exactly those fields. The SI's SPEAK-THE-SUBSTANCE rule
  also carves out the inverse case -- an option whose label is ONLY a line/box
  reference ("1 Line 3a"), where stripping the navigation would leave nothing
  speakable, so the reference is spoken as the option's only identity. All options
  always ride the injection in every branch; only the ask style changes. The
  frontend-built `{next_field_hint}` resolves its `options: [...]` labels through
  the kit-baked `label_translations` for the session language (bd
  polyglot-pdf-0rm1; `formatNextFieldHint`'s `language` param), so the hint and
  the guidance block speak the SAME language. That resolver MIRRORS the backend's
  (`option_translation.py` `_kit_translation_keys`/`_kit_translation`, via
  `kitTranslationKeys` in `frontend/src/shared/languages.ts`): the canonical
  lowercase language name plus the BCP-47 code and its stem, case-insensitive on
  the kit's own keys, with a whitespace-only value treated as a miss (bd
  polyglot-pdf-thun). Legacy bare-string options (`options: ["A","B"]`) render as
  the strings themselves, and a dict option missing `label` falls back to its
  `value` -- both previously spoke a literal "undefined" (bd polyglot-pdf-5419).
  NOT mirrored on the client: the backend's rung-2 secretary `translate_items`
  fallback, which exists only server-side, so an UNBAKED kit's hint stays English
  by design while its guidance block is translated. The session language is read
  through to the persisted state at format time
  (`WebFormConnection.sessionLanguage`), so a producer that has not yet synced
  cannot emit labels in a language the session no longer holds (bd
  polyglot-pdf-pjws). NOT a mid-session switch: the spoken language is PINNED for
  the whole form (bd polyglot-pdf-87a9,
  [voice-and-vad.md](voice-and-vad.md)); this is the general read-stale-state
  guard, and pjws was originally written up in the switching framing.
  Option labels render pre-translated into the session language when the runtime
  option-translation overrides are available (bd polyglot-pdf-ow1e:
  `option_label_overrides` substitutes the label and omits `spoken_label` on
  overridden options; option VALUES stay English for tool-call matching, and the
  DTI SI's MATCHING block scopes its translate-aloud rule to the English-fallback
  window). No overrides -> byte-identical English render.
  When the field carries `help.details` (verbatim official-booklet excerpts, bd
  polyglot-pdf-wsao.1), the render appends an `Official reference text:` segment --
  inline v1 delivery per the sprint-16 plan; a no-details render is byte-identical
  to the pre-wsao.1 output. The spoken ask-hint path (`formatNextFieldHint` ->
  `strip_field_id_from_hint`) carries only `help.instructions`, never details.
  The SAME text delivers field 1 via the initiating message
  (`FormFillingService.send_initiating_message`) and fields 2..N via the `confirm_field`
  tool response (`response["next_field_guidance"]`), so the model sees identical
  guidance whichever path delivers it. The next field's guidance is CLIENT-SUPPLIED on
  the `next_field_hint_response` and rendered into the `confirm_field` response by
  `callback_handler.py`, honoring the stateless / client-owns-state invariant.
- **Form/section metadata** -- `render_section_metadata` (`ai_context.py`) renders the
  form title, section n/total, label, previous spoken names, and confirmation policy
  onto the initiating message at session/section start (bd polyglot-pdf-uogm). The
  static DTI SI carries none of it.

DTI is carried over the **manifest-first handshake transport** (`handshake_jit` WS
message type, `schema["jit_mode"]`, the `jit_mode_enabled` session-ready signal
`= settings.USE_DTI`, and the frontend's `jitModeEnabled` state). That transport
survived the JIT-mode purge (bd polyglot-pdf-en2j) as DTI's carrier -- it is documented
in [../components/websocket-routing.md](../components/websocket-routing.md) and
[../components/schema-forms.md](../components/schema-forms.md).

## Placeholder set (the legacy full-SI interface)

The DTI template carries NO placeholders (it is static). The legacy `SYSTEM_INSTRUCTION`
template is the only one `build_form_context()` calls `.format(...)` on; its placeholder
set is:

`{form_title}`, `{section_number}`, `{total_sections}`, `{section_label}`,
`{section_list}`, `{filled_count}`, `{total_fields}`, `{unfilled_count}`,
`{fill_language}`, `{previous_spoken_names}`, `{next_field_hint}`,
`{confirmation_policy}`, and `{fields_json}` (the full current-section field dump).

> **`fields_json` is a placeholder NAME, not JSON.** It carries pipe-separated field
> text (the comment at `config.py` notes this -- kept for compatibility). Do not "fix"
> it to JSON.

## ADDRESS CONSISTENCY prose: stays permanently, in both templates

Both SI templates carry an `ADDRESS CONSISTENCY:` block instructing the LIVE model to
cross-check address fields (zip-vs-state, etc.) itself.

- **Bead B1 (polyglot-pdf-jnjj.13), which would have deleted this prose, is CLOSED
  WON'T-DO.** The G1 detection gate (jnjj.5) came back NO-GO -- the flash-lite
  validator's contradiction recall (0.853) is below the in-SI check's measured 1.000 --
  so the maintainer rescoped the epic (2026-06-17): the prose stays as the PRIMARY
  contradiction check; a cheap-model validator (pillar B), if it ships, is additive
  defense-in-depth, not a replacement, and nothing gates the prose's removal.
- The verdict/payload/steering shapes the validator uses are owned by the
  validation-delegation standard (F3, bd polyglot-pdf-jnjj.4), not here.

## Editing the SI: REWRITE the block, never bolt a rule on

**The SI is one document the model reads whole. Edit it that way.** The failure
mode below is not hypothetical -- it is how the shipped SI reached 4,388 tokens,
and it recurred during the v4 slimming work until it was measured and stopped.

**1. A CONTRADICTION BREAKS AS HARD AS AN OMISSION, and is far harder to see.**
Two individually-correct rules that collide on the same text make the model pick
one -- differently on different turns. Measured on the W-7 `reason` field: the SI
said "read each option VERBATIM AND IN ITS ENTIRETY... every qualifier,
parenthetical, and condition" AND "never read a label's printed-form NAVIGATION
aloud -- item/line/BOX NUMBERS". Option (a)'s
"(you must also check and complete box h)" is a **parenthetical naming a box**
that is also a **binding obligation**. Result: the clause was spoken in 1 of 3
runs. The shipped SI spoke it 2 of 2 -- it carries the SAME two rules but spends
more words holding them apart, and the compression had cut exactly that
connective tissue.
  - **A substring harness cannot catch this.** Every rule was present and every
    check passed while the behaviour was broken. Only a live listen found it.
  - **The fix is to make the test FUNCTIONAL, not lexical:** ask what a clause
    DOES (obligation/condition -> speak; pointer with no obligation -> omit;
    cannot tell -> speak), never what it looks like. That scored 3/3.

**2. REDUNDANCY IS PAID EVERY TURN.** The SI is re-sent per turn on the dominant
cost line, so a duplicated rule is a permanent tax. Bolting each fix on top of
the last -- add a sentence, leave the sentence it supersedes -- accumulates
silently: by the end of one slimming pass the options block said "do not
shorten" in FOUR phrasings and the names block warned against guessing a
spelling THREE times. Rewriting those two blocks from scratch, losing no rule,
moved the cut from 19.3% to 32.4% (31.7% as shipped, after a later review round
added back a write-vs-read carve-out). **When a fix supersedes existing prose,
DELETE the prose it supersedes in the same edit.**

**3. So: read the WHOLE SI before and after any edit.** Not the block you are
changing -- the whole thing, in one pass, looking for rules that now collide or
now say the same thing twice. Per-section review structurally cannot find either
class of defect.

**4. But NOT all duplication is waste -- check the tests before deleting any.**
WORKFLOW step 1 deliberately restates the PRESENTING OPTIONS carve-outs, and
`test_dti_si_forbids_one_by_one_yes_no_option_walk` slices
`SI[WORKFLOW:..TOOL PROTOCOL:]` to pin exactly that: an unqualified step-1
imperative contradicted the two-option rule on every confirm-path turn. That
repetition IS a fix. The repo's pinning tests are the record of which
duplications are load-bearing; consult them before "cleaning up" one.

**5. Verify behaviourally, and never on a single run.** The live model is
stochastic (see the baseline audio/text divergence in
`scripts/spikes/0rpu_desync_attribution_findings.md`). A prompt fix that scores
1-of-2 is not a fix -- one of the fixes above looked confirmed on its first run
and failed the repeat. Run the same probe on the SHIPPED SI too: several
"regressions" found during this work reproduced identically on the baseline and
were pre-existing model behaviour, not candidate defects.

## What changes this contract

Any edit that adds/removes a legacy placeholder, changes the DTI guidance-injection
shape, or changes the ADDRESS-CONSISTENCY prose's status updates THIS doc first
(current-state only -- the journal holds the history), then the code.
