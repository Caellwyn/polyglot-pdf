# Sprint 5 -- The I-90 authoring loop: good-enough auto-pass + joyful editor

**Epic:** polyglot-pdf-7a9 (PDF -> JSON FormSchema authoring -- cut the human-labor
cost), continued. **Planned:** 2026-06-13 via `/plan-epic`. **Status:** approved
(maintainer, 2026-06-13).

> Sprint plan = current state + the approved rubric/tree. The chronological record
> (why we pivoted off I-589, the research arc) lives in the journal
> (`docs/journal/entries/2026-06-12-bd-7a9.10-*`, `2026-06-13-bd-7a9.11-*`).

---

## Why (L1 -- the maintainer owns this)

Going from a raw PDF to a usable FormSchema is painful enough today that it
bottlenecks adding new forms. The research arc (7a9.9/10/11) proved the model
cannot fully autonomously author a schema, and chasing the hardest forms (I-589) is
a dead end for years. The leverage is the **human-in-the-loop**: a "good enough"
automated first pass on I-90-grade forms, plus a schema-editor that makes the human
finish **fast and pleasant enough that the maintainer will actually do it**. The
test set then grows as a *byproduct* of doing touch-ups -- each hand-finished form
both ships and becomes a gold fixture. This sprint builds that loop and exercises
it once end-to-end.

**Explicitly NOT this sprint:** big-form / table-heavy authoring (I-589 class). The
7a9.11 finding (the enriched bundle regresses on big-form tables vs the plain
claude-hybrid prompt; start from claude-hybrid there) is **parked as a future
note**, not a task. Complexity != field count; we target simple-to-medium forms.

## How (L2 -- challenged + agreed)

Two course-corrections surfaced at planning and were adopted:

1. **Within the editor, universal wins first; field merge/split is demand-gated.**
   The survey's top friction was field consolidation (merge/split), but how much
   that matters depends on what the auto-pass leaves behind. So we build the
   friction-on-every-form wins first (undo, search, controls_fields UI,
   frictionless save) and build merge/split only after a real I-90-grade touch-up
   pass shows it is needed -- avoiding polishing a corner the good-enough pipeline
   may make rare.
2. **The I-90 pipeline picks its prompt empirically, not by architectural
   loyalty.** The 7a9.11 finding (enrichment can REGRESS) applies to I-90 too (the
   7a9.10 trim cost ~1.5pp). So B1 bakes plain claude-hybrid vs the enriched bundle
   ON I-90 and ships whichever is best for the human-touch-up goal.

## Exit rubric (approved)

| # | Criterion | Verify |
|---|-----------|--------|
| 1 | **One-command auto-pass:** a single command takes `form-kits/i-90/form.pdf` -> a draft FormSchema file, using whichever prompt (plain claude-hybrid vs enriched bundle) scores best on I-90, with the choice recorded. | Run the command on I-90; a schema-format-valid draft is produced; the prompt pick + its I-90 score is recorded in a findings/journal note. |
| 2 | **Good-enough quality bar on I-90:** the auto-pass draft scores at or above the best existing I-90 bake-off arm on type accuracy + pdf_field_name fidelity + field-detection F1 (the metrics that drive human-touch-up effort). | `scripts/schema_score.py` on the draft vs `form-kits/i-90/schema.json` meets/beats the recorded best-arm numbers. |
| 3 | **Frictionless finish:** from the editor, a human saves a corrected schema to a chosen file in one step (File System Access API -- no manual download+copy) and reloads it cleanly with the edit present. | Open a draft in the editor, edit a field, save to a file via the API, reload it; the edit is present. |
| 4 | **Joyful editing -- the universal wins:** the editor has undo/redo, field search/filter, and a `controls_fields` editing UI; a human can find, edit, and revert any field and author a controls_fields relationship without leaving the tool or hand-editing JSON. | Drive the editor: search a field by name, edit it, undo, then add a controls_fields relationship -- all via UI. |
| 5 | **(maintainer-gated) The loop is exercised once, end-to-end:** at least one NEW (non-I-90) simple-to-medium form goes PDF -> auto-pass -> human touch-up -> saved gold, proving the loop and adding a fixture. | A new form-kit exists with a hand-finished schema produced via the loop, recorded as a new gold pair. (Gated on the maintainer sourcing the form; the epic substantially completes on 1-4.) |

**Rubric notes:** criteria 1-4 are code this sprint. Criterion 5 is the loop-proof
and depends on the maintainer supplying a form; it may land after 1-4. Any rubric
change is logged on the epic bead.

## Bead tree (MECE; surfaces disjoint)

### Track A -- Editor joy (universal wins; A1-A4 fully parallelizable, disjoint surfaces)

| bead | title | surfaces | inherits |
|------|-------|----------|----------|
| A1 | One-step save via File System Access API (replace download-only export) | `schema-editor/src/` (save path + a fs-access hook) | crit 3 |
| A2 | Undo/redo (edit-history stack) | `schema-editor/src/App.tsx`, `schema-editor/src/hooks/` | crit 4 |
| A3 | Field search/filter in the field list | `schema-editor/src/components/FieldList.tsx` | crit 4 |
| A4 | controls_fields editing UI (the missing logic surface) | `schema-editor/src/components/FieldEditor.tsx` | crit 4 |

### Track B -- I-90 good-enough pipeline

| bead | title | surfaces | inherits |
|------|-------|----------|----------|
| B1 (rescoped 7a9.12) | Pick the best-on-I-90 prompt + ship the one-command PDF->draft auto-pass (defer big-form/table work; park the claude-hybrid finding) | `scripts/bakeoff/`, a new pipeline entry script | crit 1, 2 |

### Track C -- Loop proof (maintainer-gated)

| bead | title | surfaces | inherits |
|------|-------|----------|----------|
| C1 | Run a NEW simple-to-medium form through the loop -> new gold pair | a new `form-kits/<form>/` | crit 5 |

**Parallelism:** A1-A4 have disjoint surfaces and no ordering edge -> all
concurrently executable. B1 is independent of Track A. C1 gates on B1 + the
maintainer sourcing a form. A field-merge/split bead is intentionally NOT filed yet
(demand-gated -- file it after the first real touch-up pass if the pipeline leaves
merge work behind).

### Track D -- Form catalogue + onboarding (added 2026-06-13, maintainer)

The editor's missing FRONT DOOR: today there is no way to onboard a new form (the
editor reads a hardcoded `AVAILABLE_FORMS` list from its own `public/schemas/`
static copy, disconnected from `form-kits/` and GCS). The maintainer needs to
drag-drop an AcroForm PDF to add it to the catalogue, see all forms at a glance,
and track review progress.

**Storage model (maintainer decision, 2026-06-13):** in-progress forms live LOCALLY
in `form-kits/<id>/` (the editor reads/writes them via the File System Access
**directory** API) AND are COMMITTED TO GIT for off-machine durability (the
"coffee-spill" clause -- a dead laptop must not lose work). Completed forms reach
the voice app via the EXISTING deploy -> GCS flow; "complete" = a `status` marker
in `metadata.json` that gates the deploy. This avoids browser<->GCS auth entirely
(no new backend API for the MVP): local files + git for durability + the existing
deploy for the complete-gate. Single source of truth: `form-kits/<id>/` holds both
draft and complete forms, distinguished by `metadata.json` `status`.

**Two corrections from the Codex review of this plan (2026-06-14), both adopted:**

1. **The draft-leak window is closed by folding the MINIMAL deploy gate INTO D1
   (not deferring it to D2).** The moment D1 can write draft kits into
   `form-kits/`, an unfiltered deploy would upload them to GCS / the voice app --
   so the `status != complete` skip in the deploy MUST land in the same bead that
   introduces drafts. D1 therefore includes the minimal gate; D2 is now only the
   *editor-side* status UI + richer gating, no longer the thing standing between
   drafts and production.
2. **The deploy upload+manifest loop lives in `deploy-all.sh` (~lines 192-237),
   not `deploy-demo.sh`/`scripts/deploy-form-kit.sh`.** `deploy-demo.sh` delegates
   to `./deploy-all.sh`; both demo and prod (and a direct `deploy-all.sh
   --form-kits`) run that loop, which today uploads EVERY `form-kits/*/` with a
   `schema.json` and writes it into the manifest with no status filter. The gate
   must go in `deploy-all.sh` to actually hold. Surfaces corrected below.

| bead | title | surfaces | inherits |
|------|-------|----------|----------|
| D1 (MVP) | Form catalogue + drag-drop onboarding (editor lists all `form-kits/` forms via the FS-access **directory** API + drag-drop a PDF to add `form-kits/<id>/`, git-backed) **+ the minimal deploy gate** (`deploy-all.sh` skips any kit whose `metadata.json` `status` != `complete`, defaulting absent/`draft` to NOT-deployed) | `schema-editor/src/`, `form-kits/`, `deploy-all.sh` | crit 3 (the loop's front door) |
| D2 | Editor-side status UI + richer complete-gate: view/set a form's `status` from the editor; confirm the deploy filter (D1) against demo + prod + `deploy-all.sh --form-kits` | `form-kits/`, `schema-editor/src/`, `deploy-all.sh` | (epic 7a9, new) |
| D3 | Catalogue dashboard: per-form progress (has-extraction / in-progress / complete, % human-review done), multi-form completion counts | `schema-editor/src/` | (epic 7a9, new) |

**D1 is the MVP** the maintainer asked to build now -- now INCLUDING the minimal
deploy gate so drafts can never reach production (Codex finding adopted). D2
(editor status UI + richer gating) and D3 (progress dashboard) are the
"expand later" children, filed but not yet scheduled. D1 depends on nothing new;
D2/D3 build on D1. The progress-metric signal D3 needs does not exist yet -- D3's
first task is defining how "review progress" is
measured.

## Bead housekeeping (approved)

- **7a9.12** rescoped to B1 (I-90 good-enough; big-form/table work deferred).
- **7a9.8** closed as SUPERSEDED by B1 (same "fused pipeline" idea; B1 replaces it
  with the empirical-prompt-pick framing).
- **hid** repurposed as the Track-A editor umbrella (its "assess + file enhancement
  beads" deliverable is now concretely A1-A4).
- **7a9.13** (section_id metric DECISION) left as-is -- still a relevant scoring
  decision, independent of this tree.

## Out of scope (this sprint)

- Big-form / table-heavy authoring (I-589 class), table/multi_entry detection,
  supplement-overflow wiring, the chunked pass. Parked.
- Field merge/split editor UI (demand-gated; not filed until observed need).
- A backend REST API / browser<->GCS auth for form onboarding -- explicitly
  avoided: Track D uses local `form-kits/` + git for durability + the existing
  `deploy-demo.sh` for the complete-gate, so no backend write endpoint is needed
  for the MVP. (A backend API would only return if multi-user / multi-device
  onboarding is ever required -- not now, single maintainer.)
- The catalogue progress dashboard (D3) and the explicit complete-gate (D2) are
  FILED but deferred -- D1 (onboarding MVP) is the scheduled Track-D work.
- Batch operations, keyboard-nav polish, virtual scrolling (survey's
  medium/low-priority items) -- candidates for a later editor pass, not this one.
