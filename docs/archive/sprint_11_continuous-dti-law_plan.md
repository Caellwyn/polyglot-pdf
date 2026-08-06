# Sprint 11 -- Continuous-DTI law of the land

> **ARCHIVED (2026-08-05, docs audit bd polyglot-pdf-2zk3).** Epic
> `polyglot-pdf-fc7t` is closed. Kept verbatim as the sprint's plan of record --
> read it as history, not as current direction. Current behavior lives in
> [`../components/context-compression.md`](../components/context-compression.md)
> and [`../standards/section-reset-deprecation.md`](../standards/section-reset-deprecation.md).

**Epic:** `polyglot-pdf-fc7t` | **Planning bead:** `polyglot-pdf-s9xh` (closed by
this plan's PR) | **Approved:** 2026-07-11 (maintainer, via the /plan-epic
Step-5 gate)

## Why

Maintainer direction (2026-07-11): continuous-DTI -- one Gemini Live session for
the whole form, with DTI, context-window compression, the secretary
(`ask_secretary`) for recall, and the validator for second-pass correctness --
is the ONLY supported product path. The legacy section-reset flow (fresh session
per section) is retired as a product matter, but the code doesn't say so:
defaults still boot the retired path (`USE_DTI` / `CONTINUOUS_SESSION` /
`CONTEXT_COMPRESSION_ENABLED` all default false; only `deploy-demo.sh` flips
them), recall tooling is half-broken in continuous mode, the validator net
silently collapsed to a single end-of-form pass, the mobile overlay was never
gated for continuous mode, and docs/tests still describe the old world. This
epic makes code, tooling, UI, docs, and tests state the law, wires the missing
validator-correction rail, and deletes the obsolete machinery last, gated on
everything else being green plus a demo test-drive.

## Decisions resolved at planning (maintainer-approved)

- **D1 -- `get_field_value` is RETIRED** in favor of `ask_secretary` (whole-form
  recall) + `switch_to_field` (navigate + read-back). It is broken in continuous
  mode (section-1-pinned lookup), overlaps the secretary, and the DTI SI diet
  wants a smaller tool catalog. Fallback recorded on the bead: widen-lookup
  revert (lt9z option a) if recall quality degrades.
- **D2 -- the validator->`switch_to_field` correction rail is BUILT,
  prompt-level**: the steer text instructs the model to navigate to the flagged
  field, read the value back with the validator's reason, and take the fix. No
  client-side auto-navigation (the model stays the actor). The rail is
  orthogonal to WHEN steers fire, so it lands before wt6w's async redesign and
  is reused by it.
- **Named limitation (accepted):** in continuous mode the validator currently
  fires only at `form_complete` (the `section_complete` trigger never fires).
  This epic does NOT build interim mid-form triggers -- that is wt6w's page-end
  design. Until wt6w ships, demo runs with an end-of-form-only validator net.

## Exit rubric

| # | Criterion | Verify |
|---|-----------|--------|
| 1 | A no-env-var backend boots continuous-DTI (defaults flipped) and BOTH full suites are green with the flipped defaults | Backend pytest + FE vitest with no env overrides; Settings-defaults test pins the three flags true |
| 2 | In continuous mode there is exactly ONE recall path and it works whole-form: `get_field_value` gone (tool catalog, dispatch, SI prose); `ask_secretary` answers a cross-section recall correctly | Grep `config.py` TOOL_DECLARATIONS + `ai_context.py` SI text; harness/probe recall query for a section-2+ field |
| 3 | A validator conflict in continuous mode drives the correction rail end-to-end: steer -> `switch_to_field` on the flagged field -> read-back with reason -> fix accepted. Scope: verified at `form_complete` (the only continuous-mode trigger until wt6w) -- proves the RAIL, not mid-form correction | Harness/probe run with a seeded contradiction: observe steer injection, `switch_to_field` call, UI focus, corrected value written |
| 4 | No user-facing surface shows section-session state in continuous mode (desktop label, mobile parity, disclaimer start-trigger) while pagination still works | Drive the local stack in continuous mode, desktop + mobile widths |
| 5 | Docs and code agree continuous-DTI is the law and the legacy production path is deleted: tier-2 docs updated, legacy tests updated or legacy-marked, section-reset production machinery removed with the harness baseline arm still runnable AND continuous reconnect surviving | `check_doc_freshness.py` green; `measure_form_session_costs.py --arm section-reset` starts; harness continuous reconnect leg + FE reconnect tests pass; demo test-drive (maintainer-authorized deploy) |

## Bead tree

| Bead | Role | Surfaces (write) | Inherits | Order |
|------|------|------------------|----------|-------|
| `polyglot-pdf-7872` (C1) | Flip the three defaults to production values; simplify deploy-demo.sh; residue inventory feeds C7 | backend/config.py, deploy-demo.sh, backend/tests/ | #1 | FIRST |
| `polyglot-pdf-p5h2` (C2) | Retire `get_field_value` (decl, dispatch, handler, FE handler, `getFieldBySpokenName`); rewrite SI recall prose to `ask_secretary`. Subsumes `lt9z` | backend config/callback_handler/form_filling_service/ai_context, FE webFormConnection + schemaFormState, tests | #2 | after C1 |
| `polyglot-pdf-whid` (C3) | Validator-loop journal map (audit legwork done at planning) + residual gap beads | docs/journal/ | #3 | parallel-safe |
| `polyglot-pdf-oiok` (C4, marquee) | Validator->`switch_to_field` rail in `_compose_validator_steer`; E2E seeded-contradiction verification | backend/services/form_filling_service.py, backend/tests/, harness probe | #3 | after C2, C3 |
| `polyglot-pdf-wt6w` (C5) | SPEAR plan for the async validator + page-end queue (planning gate only) | docs/ | #3 (trigger half) | after C3/C4 |
| `polyglot-pdf-4l7p` (C6) | UI sweep: desktop label, mobile gating parity, disclaimer trigger semantics. Subsumes `944q` | frontend/src/demo/VoiceOverlay*.tsx, overlay tests | #4 | parallel with C2-C4 |
| `polyglot-pdf-55jg` (C7) | Legacy deletion (LAST): section-reset production path out; `switch_to_section` + legacy-SI renderer kept as documented harness-only internals | backend + frontend legacy paths, tests, voice-harness | #5 | blocked on C1,C2,C3,C4,C6 + demo test-drive; NOT on C5 |
| `polyglot-pdf-ft47` (C8) | Docs alignment (context-compression, si-reduction, terminology, voice-ai, tool-call-flow, schema-forms, websocket-routing, technical_guide, INDEX) to post-deletion truth | docs/ | #5 | after C7 |

Ordering edges are wired in beads (`blocks`): C1->C2->C4, C3->C4, C4->C5,
{C1,C2,C3,C4,C6}->C7, C7->C8. C6 runs parallel to C2-C4 (disjoint FE surfaces).

**Riders (NOT epic children):** `yipc` (late-session tool stall), `ipw7`
(computeNextField alias blindness), `hc4b` (soft-refresh re-greet -- apply the
continuous lens when picked up), `mhyt` (bakeoff section-grouping metric).
`944q` and `lt9z` close as superseded when C6/C2 land.

## Out of scope

- Mid-form validator triggers in continuous mode (wt6w's page-end design owns
  this; no interim shim on soon-deleted section machinery).
- Building wt6w's async validator (C5 is the planning gate only).
- The riders above; harness fidelity upgrades beyond the C2/C4 verification
  probes; any prod-channel work (no active prod).
- Renaming the backend-internal manifest_service/ai_context "part" SI-text path
  (standing deferral, CLAUDE.md scar #5).

## Verification (epic-level)

1. After C1: full backend + FE suites green with no env overrides.
2. After C2/C4: voice-harness (or targeted WS probe) in continuous mode --
   cross-section recall via `ask_secretary`; seeded contradiction at
   `form_complete` produces steer -> `switch_to_field` -> read-back -> fix.
3. After C6: local stack, desktop + mobile widths -- no section-session UX;
   pagination + disclaimer flow work.
4. Before C7 merges: demo test-drive (`deploy-demo.sh` is a per-instance
   maintainer ASK); post-deletion, `--arm section-reset` re-run plus the
   continuous reconnect leg + FE reconnect tests.
5. `check_doc_freshness.py` green after C8.
