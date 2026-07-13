# Sprint 12 -- Decoupled async validator (page-end queue)

**Planning bead:** `polyglot-pdf-wt6w` (sprint-11 epic fc7t child C5, CLOSED on
approval) | **Build epic:** `polyglot-pdf-09da` (6 children W1-W6 filed) |
**Status: APPROVED 2026-07-12 -- implementation beads filed**

## Why

Maintainer direction (2026-07-10): the validator no longer needs to align with
the presented sections and no longer needs to block the voice flow. Today the
whole net is ONE synchronous end-of-form pass: `handle_validation_boundary` is
awaited inline in the WS receive loop (websocket_routes.py:692/:713), the
per-section trigger is dead in continuous mode, and a contradiction made on
page 1 of a 7-page form is not caught until the entire form is confirmed.
Target shape (maintainer's picks, recorded on the bead): validator runs async
in the background; findings are QUEUED and surfaced at PAGE END; flash-lite
only (flash excluded on thinking-cost + latency); ~20-field windows overlapping
at stride ~10; far-pair coverage via one end-of-form pro pass IF measurement
supports it.

## Ground truth the design rests on (researched, file:line verified)

- Sections are page-ALIGNED but finer than pages (I-90: 28 sections over 7
  pages); every field carries `pdf_position.page` and every derived section a
  `page_number` (derive_sections.py invariant: a section never spans pages).
- In continuous mode NO page/section-advance event exists: currentSectionId
  stays pinned, the section display is frozen, Preview renders all pages
  stacked with no page-change event. The one observable boundary crossing is
  the next-field path (`onNextField` / `handleNextField`, frontend/src/schema-forms/components/SchemaForm.tsx:249):
  when the AI's next field's `pdf_position.page` differs from the previous
  field's, the fill has crossed a page.
- The client owns all state (sessionStorage `SchemaFormState`); a findings
  queue is a new persisted key following the `completedSections` serialization
  pattern; `steered` markers live per-FieldValue.
- The oiok correction rail (shipped, live-verified 4/4) is trigger-agnostic:
  whatever injects a steer gets navigate -> read-back -> correct behavior.

## The design

> **Report-cadence revision (maintainer, 2026-07-13).** The original design had
> two clocks fused into the page boundary: it VALIDATED windows at page end AND
> REPORTED (drained findings to the voice model) at page end. Reporting costs a
> voice turn, so page-end reporting meant one turn per page whether or not
> anything was wrong. The revised design SEPARATES the two clocks and makes
> reporting FINDING-DRIVEN, for paginated AND non-paginated forms alike:
> - **Validation runs on a page-agnostic field-count stride** (not page
>   crossings). Windows are built + sent as fields get confirmed; this is cheap,
>   async, and produces no voice turn. Decoupling from pages also removes the
>   no-pagination gap entirely (`source: "web"` forms, unplaced PDF fields --
>   which carry no `pdf_position.page` -- validate on the same stride as any
>   other form; there is no page trigger to miss).
> - **Reporting happens ONLY when a surviving finding exists.** A clean window
>   produces NO steer and NO turn -- no "all is well" chatter. A window that
>   surfaces a real contradiction (post-dedupe, post-steered-suppression) drains
>   to the voice model right then (findings batch into one steer), so a mistake
>   is corrected as soon as it is detected, not held to a boundary.
> - **No `form_complete` drain.** The end-of-form report is redundant with the
>   whole-form pro pass (W5/W6), which runs on a stronger model at
>   form_complete. Instead of re-reporting, the mid-form findings already
>   surfaced/adjudicated FEED FORWARD into the pro pass's context so it does not
>   re-flag them and can reason with them.
>
> The paragraphs below are the ORIGINAL page-boundary design; the bead bodies
> (W2 kxkw, W3 pr3i, W6 gbus) carry the revised finding-driven shape and are the
> build contract. This block is the current-state summary of the change.

**Trigger (client).** ORIGINAL: a page-boundary crossing on the next-field
path. REVISED: a page-agnostic field-count stride -- as fields are confirmed,
the client builds + sends the windows that newly became coverable, EXCLUDING
windows already sent (persisted validated-window high-water mark). No page
comparison; `pdf_position.page` is not required. `form_complete` no longer
drives a validator report (the pro pass owns end-of-form).

**Windowing (client builds, backend validates).** The client forms the
overlapping windows -- size ~20, stride ~10, over the schema field order --
covering the confirmed fields not yet in a sent window (persisted
validated-window high-water mark). Each window's contract-2 payload (field_id,
name, value, steered) rides ONE `validate_windows` message. Values-only fields
as today; window size/stride are config knobs (defaults 20/10). The stride is
the VALIDATION clock only -- it produces no voice turn.

**Async backend.** The WS handler acks immediately and runs the validation in
a background task (`asyncio.create_task`), one flash-lite call per window
(concurrent), fail-open per window, hard per-window timeout (existing
VALIDATOR_TIMEOUT_SEC). Conflicts from all windows in the batch are DEDUPED by
field-id set (overlap makes duplicates structural, not exceptional), then
suppressed by the steered markers exactly as today, then pushed to the client
as a `validation_result`. Nothing in the voice path waits on any of this.

**Queue + surfacing (client) -- FINDING-DRIVEN.** Findings land in a new
persisted `validatorFindingsQueue` on SchemaFormState. A `validation_result`
carrying surviving conflicts drains IMMEDIATELY (not at a boundary): the client
sends a `drain_findings` message with the queued conflicts and the backend
composes ONE steer via the SHIPPED oiok composer (`_compose_validator_steer` --
navigate/read-back/correct, one finding at a time) and injects it. A CLEAN
`validation_result` enqueues nothing and triggers no drain -- no turn is spent
on an all-clear. Fields steered from the queue get their `steered` markers on
injection delivery, exactly as today. Latency: a window verdict (~1-4s) lands
mid-fill and steers as soon as it arrives -- correction happens right after the
conflicting field is entered, not one page later. The queue exists to BATCH
concurrent findings into one steer and to survive a reconnect; it is not a
boundary buffer.

**Re-arm on value change (the maintainer's PR-#413 question, now designed
in).** `steered` currently sets at steer delivery and never clears, so a
CORRECTED value is never re-validated (a correction that introduces a new
contradiction slips the net) and a genuinely new conflict on a steered field
is suppressed forever. Change: clearing a field's `steered` flag when its
VALUE changes (in the updateField write path). The no-nagging guarantee is
preserved where it matters: a user who confirms "both are intentional" changed
no value, so the marker stays and they are never re-asked; only a field whose
value actually moved re-enters the net.

**End-of-form pro pass (measure BEFORE wiring).** Far pairs (cross-page
contradictions) are outside lite's 20-field windows. The maintainer's pick is
one whole-form pro-tier pass at form_complete -- but it is UNMEASURED (even
2.5-flash whole-form caught only 0.50 of far pairs). A measurement child runs
first (extends the 6cfu.5 instrument to gemini-2.5-pro on the 132-field
corpus, thinking budget BOUNDED, ~42 calls, estimated $0.30-0.50 -- spend
approval is part of approving this plan). Wire the pass only on a GO; a NO-GO
is recorded with the data and far-pair coverage explicitly deferred. **The pro
pass is now the SOLE end-of-form report** (there is no separate form_complete
validator drain -- report-cadence revision above). To avoid re-flagging what
the mid-form lite windows already surfaced, the pro pass is fed the
already-surfaced/adjudicated findings (the `steered`-marked fields + their
conflict reasons) as CONTEXT, so its whole-form pass reasons WITH them rather
than re-reporting them.

**What this deletes/replaces.** The inline receive-loop await goes; the
section_complete trigger machinery (already dead in continuous mode) is C7's
(55jg) deletion. The page-boundary REPORT trigger and the `form_complete`
validator drain are replaced by finding-driven reporting (revision above) --
`form_complete` now drives ONLY the pro pass (if GO), not a lite-findings
drain. The client 6s validator gate (VALIDATOR_GATE_TIMEOUT_MS) and
pendingSectionSwitch parking lose their purpose once nothing blocks; removed
with the legacy path.

## Exit rubric (build epic)

| # | Criterion | Verify |
|---|-----------|--------|
| 1 | During a continuous multi-page fill, validator windows run in the background and the voice flow is never blocked: no validation await in the WS receive loop, and a deliberately slow/hung validator does not delay any voice turn or ack | Code: websocket_routes has no inline validation await (grep). Behavior: a unit/integration test with a slow validator stub shows acks/turns proceed; harness run shows no added turn latency |
| 2 | A contradiction surfaced by a mid-form lite window is steered AS SOON AS THE WINDOW VERDICT LANDS (finding-driven, not at a boundary) and BEFORE form completion, and the live model corrects it via the rail (navigate -> read-back -> correct). A CLEAN window produces no steer/turn. Applies to paginated AND non-paginated (`source: "web"`) forms (report-cadence revision 2026-07-13) | Extend probe_validator_rail (or the harness): plant an early contradiction, fill until its window's verdict lands, observe queued finding -> immediate steer -> switch_to_field -> corrected write, pre-form-complete; and a clean fill emits no steer |
| 3 | Overlapping windows never yield duplicate steers for one conflict, and a user-CORRECTED value re-enters the net while a user-CONFIRMED-intentional pair is never re-flagged | Unit tests: dedupe by field-id set across windows; re-arm-on-value-change clears steered on edit; the existing max-resteer/override tests still pass |
| 4 | The end-of-form pro pass is either wired with MEASURED far-pair recall recorded, or explicitly recorded NO-GO with the measurement data committed | Findings doc + committed run artifacts for the pro measurement; the wiring (or its absence) matches the verdict |

## Implementation beads (filed on approval; ordering edges in parens)

| Bead | Scope | Surfaces | Inherits |
|------|-------|----------|----------|
| W1 async backend | Move validation off the receive loop (create_task, immediate ack, result push); per-window fail-open/timeout; window-batch dedupe by field-id set | backend/routes/websocket_routes.py, backend/services/form_filling_service.py, backend/services/validator_service.py, backend/tests/ | #1, #3 (dedupe half) |
| W2 stride window builder + emit (REVISED 2026-07-13) | Page-AGNOSTIC field-count stride on the confirm/next-field seam (no `pdf_position.page` dependency); persisted validated-window high-water mark; window builder 20/10 (config knobs); `validate_windows` emission. (Was page-crossing detection; the report-cadence revision made validation stride-based.) | frontend/src/webFormConnection.ts, frontend/src/schema-forms/state/schemaFormState.ts, frontend tests | #2 (trigger half) |
| W3 queue + FINDING-DRIVEN drain (after W1, W2; REVISED 2026-07-13) | Persisted validatorFindingsQueue; `drain_findings` fires IMMEDIATELY on a non-empty `validation_result` (not at a boundary; a clean result drains nothing); backend drain handler -> the oiok steer composer; E2E with a planted early contradiction + a clean-fill no-steer case | frontend/src/webFormConnection.ts, backend ws route + service, tests, probe extension | #2 |
| W4 re-arm on value change (parallel) | Clear `steered` in the updateField write path on value change; pin the confirmed-intentional-never-re-flagged case | frontend/src/schema-forms/state/schemaFormState.ts, tests | #3 (re-arm half) |
| W5 pro-pass measurement (parallel; gated spend ~$0.30-0.50) | Extend the 6cfu.5 instrument to 2.5-pro whole-form far-pair recall on the 132-field corpus, thinking bounded; findings doc + verdict | backend/scripts/ or scripts/spikes/, data artifacts | #4 |
| W6 pro-pass wiring (after W5, only on GO; REVISED 2026-07-13) | form_complete runs the pro pass as the SOLE end-of-form report (no separate lite drain); the already-surfaced mid-form findings (steered fields + reasons) are FED to the pro pass as context so it does not re-flag them; its NEW conflicts ride the same finding-driven queue/steer path | backend service + tests | #4 |

Out of scope: any mid-utterance interruption UX (steers surface between
fields, as today); Preview-mode visual page tracking (no such event exists;
the fill-order seam covers both views); the legacy section-machinery deletion
(C7/55jg owns it, sequenced after this lands).

## Open item folded into this approval

Approving this plan also approves: (a) the W5 measurement spend
(~$0.30-0.50 on Vertex pro-tier with bounded thinking); (b) the re-arm
design change to the steered-marker lifecycle (W4).
