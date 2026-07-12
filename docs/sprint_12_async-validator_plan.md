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

**Trigger (client).** A page-boundary crossing detected on the next-field
path: previous field page P, next field page P' != P => "page P ended". Also
fires on `form_complete` (the terminal boundary, existing emission kept).
Skip-driven and manual-edit-driven crossings ride the same seam (all funnel
through the next-field hint). Backward jumps (switch_to_field to an earlier
page) do NOT re-trigger -- only first-time forward crossings, tracked by a
persisted high-water page number.

**Windowing (client builds, backend validates).** On a page-end trigger the
client forms the maintainer-specified overlapping windows -- size ~20, stride
~10, over the schema field order -- covering fields up to the crossed
boundary, EXCLUDING windows already sent (persisted validated-window
high-water mark). Each window's contract-2 payload (field_id, name, value,
steered) rides ONE `validate_windows` message. Values-only fields as today;
window size/stride are config knobs (defaults 20/10).

**Async backend.** The WS handler acks immediately and runs the validation in
a background task (`asyncio.create_task`), one flash-lite call per window
(concurrent), fail-open per window, hard per-window timeout (existing
VALIDATOR_TIMEOUT_SEC). Conflicts from all windows in the batch are DEDUPED by
field-id set (overlap makes duplicates structural, not exceptional), then
suppressed by the steered markers exactly as today, then pushed to the client
as a `validation_result`. Nothing in the voice path waits on any of this.

**Queue + surfacing (client).** Findings land in a new persisted
`validatorFindingsQueue` on SchemaFormState. They surface at the NEXT
page-end trigger (or form_complete, the terminal drain): the client sends a
`drain_findings` message carrying the queued conflicts; the backend composes
ONE steer via the SHIPPED oiok composer (`_compose_validator_steer` --
navigate/read-back/correct, one finding at a time) and injects it. In
practice a window's verdict (~1-4s) lands long before the next page ends, so
findings for page P typically steer right when page P+1 ends -- one page of
latency at most, versus end-of-form today. Fields steered from the queue get
their `steered` markers on injection delivery, exactly as today.

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
is recorded with the data and far-pair coverage explicitly deferred.

**What this deletes/replaces.** The inline receive-loop await goes; the
section_complete trigger machinery (already dead in continuous mode) is C7's
(55jg) deletion; the form_complete emission survives as the terminal
drain + (if GO) the pro-pass trigger. The client 6s validator gate
(VALIDATOR_GATE_TIMEOUT_MS) and pendingSectionSwitch parking lose their
purpose once nothing blocks; removed with the legacy path.

## Exit rubric (build epic)

| # | Criterion | Verify |
|---|-----------|--------|
| 1 | During a continuous multi-page fill, validator windows run in the background and the voice flow is never blocked: no validation await in the WS receive loop, and a deliberately slow/hung validator does not delay any voice turn or ack | Code: websocket_routes has no inline validation await (grep). Behavior: a unit/integration test with a slow validator stub shows acks/turns proceed; harness run shows no added turn latency |
| 2 | A contradiction planted on page P of a multi-page form is steered at a page boundary BEFORE form completion, and the live model corrects it via the rail (navigate -> read-back -> correct) | Extend probe_validator_rail (or the harness): plant a page-1 contradiction, fill past a page boundary, observe queued finding -> page-end steer -> switch_to_field -> corrected write, all pre-form-complete |
| 3 | Overlapping windows never yield duplicate steers for one conflict, and a user-CORRECTED value re-enters the net while a user-CONFIRMED-intentional pair is never re-flagged | Unit tests: dedupe by field-id set across windows; re-arm-on-value-change clears steered on edit; the existing max-resteer/override tests still pass |
| 4 | The end-of-form pro pass is either wired with MEASURED far-pair recall recorded, or explicitly recorded NO-GO with the measurement data committed | Findings doc + committed run artifacts for the pro measurement; the wiring (or its absence) matches the verdict |

## Implementation beads (filed on approval; ordering edges in parens)

| Bead | Scope | Surfaces | Inherits |
|------|-------|----------|----------|
| W1 async backend | Move validation off the receive loop (create_task, immediate ack, result push); per-window fail-open/timeout; window-batch dedupe by field-id set | backend/routes/websocket_routes.py, backend/services/form_filling_service.py, backend/services/validator_service.py, backend/tests/ | #1, #3 (dedupe half) |
| W2 page-end trigger + windows | Page-crossing detection on the next-field seam; persisted high-water marks (page + validated windows); window builder 20/10 (config knobs); `validate_windows` emission | frontend/src/webFormConnection.ts, frontend/src/schema-forms/state/schemaFormState.ts, frontend tests | #2 (trigger half) |
| W3 queue + drain (after W1, W2) | Persisted validatorFindingsQueue; `drain_findings` at page-end/form-complete; backend drain handler -> the oiok steer composer; E2E with a planted page-1 contradiction | frontend/src/webFormConnection.ts, backend ws route + service, tests, probe extension | #2 |
| W4 re-arm on value change (parallel) | Clear `steered` in the updateField write path on value change; pin the confirmed-intentional-never-re-flagged case | frontend/src/schema-forms/state/schemaFormState.ts, tests | #3 (re-arm half) |
| W5 pro-pass measurement (parallel; gated spend ~$0.30-0.50) | Extend the 6cfu.5 instrument to 2.5-pro whole-form far-pair recall on the 132-field corpus, thinking bounded; findings doc + verdict | backend/scripts/ or scripts/spikes/, data artifacts | #4 |
| W6 pro-pass wiring (after W5, only on GO) | form_complete runs the pro pass alongside the terminal drain; findings ride the same queue/steer path | backend service + tests | #4 |

Out of scope: any mid-utterance interruption UX (steers surface between
fields, at boundaries, as today); Preview-mode visual page tracking (no such
event exists; the fill-order seam covers both views); the legacy
section-machinery deletion (C7/55jg owns it, sequenced after this lands).

## Open item folded into this approval

Approving this plan also approves: (a) the W5 measurement spend
(~$0.30-0.50 on Vertex pro-tier with bounded thinking); (b) the re-arm
design change to the steered-marker lifecycle (W4).
