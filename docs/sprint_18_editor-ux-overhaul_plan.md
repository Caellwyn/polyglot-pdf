# Sprint 18 -- Schema-editor UX overhaul: embedded findings, honest gates, review-last

Epic: polyglot-pdf-4qul (maintainer-approved 2026-08-03; plan v13 after
10 Opus fresh-eyes rounds / 67 findings and two maintainer hands-on
rounds)
Source audit: `planning_documents/schema-editor-ux-audit-2026-08-02.md`
Prototype: branch commits 1df099ef + 670a5aec (reference only, not a merge
candidate; the maintainer drove it and this v10 encodes their feedback).
Reviews: Opus fresh-eyes rounds 1-7 on v1-v9 (52 findings, all folded --
change log retained at bottom); maintainer directives round 1 (5) and round 2
(the hands-on session: 15 walkthrough items + 8 design responses + 2
follow-ups).

## Why (L1)

The maintainer is the editor's primary user and its model for future staff
(authors = trusted staff; editors = lower-trust contractors working a backlog
of forms). The audit + two hands-on sessions surfaced the core failures: a
warnings pane whose counts ignored the maintainer's ~50 acknowledgments; a
publish lock invisible until save time; buried, blocking, per-field
regeneration; and -- decisive, from driving the v1 prototype -- the insight
that a SEPARATE warnings surface is itself the bug: it eats workspace, holds
a second copy of per-field truth that drifts from the field statuses ("0 need
review" beside "7 to review"), and invites bulk shortcuts that defeat review.
Directives now in force: findings live IN the fields they are about; ONE
count line derived from field statuses; Mark-complete gates hard on 100%;
review is the last touch; no bulk quality approvals; editors finish a form
completely and move on; the workspace -- not the chrome -- gets the screen.

## Product model (maintainer-set, 2026-08-03)

- **Tiers:** authors (trusted staff) gate forms in and out: onboarding,
  extraction, unlock/revert of published kits, deploy, and every
  model-calling action. Editors (contractors) do the manual review work and
  may mark a form complete (the work-is-done signal) but cannot publish to
  the store, revert published kits, or spend model tokens.
- **Editor request flags:** where an editor needs a model action (rewrite,
  re-translate), they set a zero-cost "requested" flag on the field; the
  author's final pass triggers the actual calls, batched, with their eyes on
  the diffs. Cost control by construction -- no quota infrastructure. (Bulk
  here is fine: it is the AUTHOR working a queue of explicit per-field human
  requests, not a blanket approval.)
- **A form is complete when the joint linter+editor ability is exhausted:**
  every field reviewed, every finding fixed or explicitly confirmed at its
  field, every ignore deliberate. Publishing anything less is refused, and
  the refusal is visible BEFORE the click (the gated button).
- **Completion is FREE; the bake belongs to the author's final pass.**
  Verified contradiction (Opus round 9): today the editor-role complete
  transition SPENDS model tokens (the drift sweep bakes translations
  inside /status, by documented design), which would falsify the
  cost-control-by-construction claim. Resolution (the maintainer's own
  tiered-review model): editor Mark-complete runs ONLY the free readiness
  gate and flips status; the bundled translation bake moves OUT of the
  complete transition into the AUTHOR's deploy-prep step, and deploy
  eligibility = complete + translation coverage. Editors finish a form
  alone at zero token cost; authors trigger the one bake per form in
  their final eyes-on pass, alongside the queued rewrite requests. (C8
  reshaped accordingly; the sweep leaves /status.) **The coverage CHECK
  stays in the editor's complete gate** (Opus round 10): checking
  coverage is free -- `translation_coverage_summary` is pure schema
  inspection, no model call -- and removing it with the bake would
  silently delete the only blocking translation gate on the hosted path
  (the per-kit deploy surface exists only under vite dev; hosted has
  none, and the coverage lint rule is WARNING-severity). So /status
  complete still REFUSES on incomplete coverage, with the refusal
  wording pointing at the request-flag flow ("translations are not baked
  yet -- ask an author to run the translation pass"); only the
  token-spending bake moves to the author. Completion stays token-free
  AND honest. Absorbed here too: the
  earlier spun-off edit-loss task (silent discard on revert-to-draft
  refetch) is owned by C2, not a parallel bead -- same surfaces, same
  chain.

## Load-bearing design decisions

1. **The warnings pane is removed; findings render at their fields; the
   strip COMPONENT keeps the plumbing.** The field list flags findings;
   the field editor shows them anchored to the PROPERTY they concern (the
   finding paths already name it -- clicking a count/flag scrolls to the
   Instructions box, the option row, etc.). Form-level findings
   (schema-wide coverage, kit-level flags) get one pinned "Form" row at
   the top of the field list, counted once; they are the ONLY place a
   standalone dismiss exists (no field review can cover them). **The
   strip lints with the SAME inputs as the gate:** for an open kit the
   dumpless POST /lint is replaced by a kit-scoped lint that loads the
   AcroForm dump exactly as the publish gate does -- otherwise the two
   dump-gated ERROR rules are structurally invisible to the strip and a
   confident 100% button can still 409 (Opus round 9). One small backend
   addition, owned by C1 (its former "NO backend changes" claim is
   retired). The pane's
   four non-display responsibilities are explicitly REASSIGNED, not
   deleted: the strip component retains (a) the lint round-trip itself
   (fetch, monotonic staleness guard, auth-error surfacing,
   keep-last-report-on-blip), (b) the onReport mirror App's field list
   and overlay feed from, (c) the Repair-all button (a sanctioned
   mechanical bulk action, errors-only, right end of the strip), and
   (d) the limited-checking / checks-did-not-run notices -- which matter
   MORE under status-derived counts (a failed lint must never render as
   "reviewed and clean"; it also puts the gate button into its explicit
   "not fully checked" state, decision 4). The strip additionally owns a
   refusal/error line from birth: server refusal details (publish gate,
   translation coverage) render there with field links, so no mid-chain
   state exists where a refusal has no home (C2 later upgrades this line
   into the guided-flow staging).
2. **One count line, one definition -- and the predicate is pinned.** The
   bottom strip becomes a single line: progress bar + `N reviewed - M to
   review - T total` + the gated Mark-complete state. The count predicate
   is EXACTLY: `_review.status == reviewed_correct`, not demoted by the
   ack gate or the timeliness rule, and no lint ERROR anchored to the
   field -- inputs the client and server both possess (`_review` + lint
   findings), so both compute the identical number. `checkFieldComplete`
   LEAVES the count: it remains the advisory WHY-list and icon input, but
   its client-only error band no longer excludes fields from `complete`
   (its genuinely structural checks are covered by, or in C12 promoted
   into, backend lint rules -- enumerated there). This closes the
   client-only-derivation seam (Opus round 9): strip, stamp, button, and
   gate all evaluate one predicate over one input set.
   "M to review" is a CONTROL: clicking it jumps to the next review target
   (and a long-press/secondary action filters the field list to flagged
   fields -- the overview that used to justify a pane). No "resolved" count.
3. **Findings gate through field review, with a timeliness rule.** A field
   with any unresolved finding is not green; marking it reviewed-correct is
   the human's sign-off that they saw its notices (informational ones
   included). Drift additionally requires its explicit confirm/rewrite
   action first (the existing ack gate). **A finding whose fingerprint is
   new since the field's last review demotes the field back to
   needs-review** -- the general mechanism that keeps warnings timely.
   Storage is pinned: signing off writes the field's current finding
   fingerprints into a fourth `_review` slot, `seen_fingerprints`
   (fingerprint = rule + field + content hash); the demotion is an
   EFFECTIVE-status derivation (like the ack gate), never a silent stored
   write; every `_review` writer explicitly carries the fourth slot (the
   three-slot rebuild silently dropping unknown keys is a recorded past
   bug, so a shared helper + test pin preservation). This IS a per-field
   fingerprint snapshot -- the difference from the deleted dismissals list
   is that it has exactly one writer (the sign-off) and no standalone
   action. Owned once, in `reviewStatus.ts`, shared by C1 and C7.
   **Fingerprint stability is load-bearing:** the fingerprint is
   `rule + field + path-sans-identity-suffix` and EXCLUDES the message --
   messages are prose the C12 copy pass deliberately rewrites, and a
   message-keyed fingerprint would demote every reviewed field on every
   kit the moment C12 ships (a mass re-review wave, the exact failure
   this epic exists to end). Residual accepted and named: a message-only
   content change does not re-raise (rule+path shifts cover the real
   cases; C3's per-field flag replacement handles rectification
   recurrence). C12 is ordered BEFORE C1 (blocks edge) so messages are
   stable before any fingerprint is written.
4. **Mark-complete is a progress meter that becomes a button, and ONE
   backend function defines readiness.** `publish_readiness(schema,
   lint_findings)` (new, backend) computes: every non-ignored field
   `reviewed_correct`; no lint ERROR; no un-acked drift -- computed
   NATIVELY (the server calls `guidance_contract.identity_sha1(field)`
   directly and compares to `_review.guidance_ack_sha1`; the same function
   that emits the hash, so no cross-language copy and no path parsing);
   no finding newer than the field's `seen_fingerprints`. The /status
   complete transition refuses on that function's verdict, naming the
   fields. The SAME function's counts are what C4 stamps into
   `metadata.json` at save, and the stamped counts are what the gated
   button displays ("Mark complete -- 82% reviewed", grey; primary-active
   at 100%) -- so the button and the gate cannot disagree about a saved
   kit (the button is dirty-gated anyway, with its reason inline). The
   client's live strip may lead the stamp mid-edit; the gate reads the
   store. This deliberately promotes `_review` into a backend publish
   input (reverses v9's soft-gate deferral, maintainer-directed);
   consequence: kits hand-marked complete outside the editor cannot
   re-publish until actually reviewed. **Ignore is not a silent bypass:**
   quarantined fields leave the denominator, so the publish confirmation,
   the complete notice, and the catalogue card all state the ignored
   count ("53 reviewed, 7 ignored") -- an author's final pass sees at a
   glance if a gate was cleared by ignoring (named consequence; the grey
   overlay treatment is the second tripwire). The translation bake (C8)
   runs inside the same guided transition with staged in-place progress.
   When lint could not run (degraded/no-backend), readiness is UNKNOWN:
   the button renders an explicit "not fully checked" state, never a
   confident 100%.
5. **Disabled primary actions always show their reason inline** -- never
   tooltip-only (the "Mark complete did nothing" session bug: a dirty-gate
   disable with a hover-only explanation).
6. **Drift resolution is amber, symmetric, and settles on blur.** The box
   is amber (amber = human judgment needed; red = structurally broken --
   blocking-ness is expressed by the gate, not the color). Two equal
   actions: "Confirm instructions are correct" / "Instructions not correct,
   attempt auto-rewrite" (no "booklet" -- sources vary: booklet, tooltips,
   form text, nothing). Identity-drift evaluation keys on settled edits
   (blur/commit), never per keystroke. For editor tier the rewrite action
   becomes "Request rewrite" (sets the flag; no model call).
7. **Rewrite calls keep a two-level liveness promise.** Client: animated
   working indicator (growing/shrinking ellipsis) with escalating status
   text -- no wall-clock predictions. Server: a hard deadline on the
   route's model work; on expiry the server aborts, writes nothing, and
   returns an explicit failure the client renders (could not connect /
   model did not respond / timed out). The client never declares failure
   while the server might still write (the deadline is server-owned), and
   nobody waits ten minutes on a hang.
8. **Diff acceptance is per channel.** The propose/apply pair (server-side
   dry-run propose; apply re-verifies hashes, re-stamps provenance,
   preserves other fields' flags, replaces the field's own flags) accepts
   instructions and details INDEPENDENTLY. No accept-all.
9. **No bulk quality approvals, anywhere.** Bulk-confirm is deleted (the
   maintainer bulk-confirmed a real rename during the session -- exactly
   the laziness it invites). The review cycle (Next-to-review / the strip
   count) is the sanctioned path. The only bulk-ish surfaces are
   author-triggered batches of EXPLICIT per-field editor requests (model
   actions), and mechanical non-quality operations (repair-all).
10. **Ignore is individual, deliberate, and stays visible.** No
    section-level bulk ignore (session evidence: acceptance-agent fields
    had slipped into Sign Here and vice versa; a bulk ignore would have
    silently swept mis-filed required fields). To ignore a field the
    editor must first clear its Required flag (existing backend rule,
    surfaced as a guided two-step, not a refusal dead-end); and ignored
    fields REMAIN RENDERED on the PDF overlay with a distinct dark-grey
    treatment -- the visual tripwire ("a field in a required section just
    turned grey"). **This deliberately re-opens the quarantine design's
    invisibility premise** (ignoreField.ts chose relocation out of
    `fields[]` precisely so every downstream reader stays blind with zero
    changes): the overlay becomes the ONE sanctioned reader of
    `_ignored_fields`, via a dedicated ignored-field rendering branch in
    PDFViewer/FieldOverlay -- NOT by widening the closed `EffectiveStatus`
    union (whose consumers stay untouched). The premise amendment is
    recorded in ignoreField.ts's doc comment.
11. **The chrome shrinks; the workspace rules.** One thin header row
    (title, form picker + status, save cluster); the catalogue moves behind
    the picker/a drawer; the Fields panel is collapsible (the PDF overlay
    with field-ids is the primary navigation; the panel's irreplaceable
    jobs -- reordering, re-sectioning, ignoring -- move to an explicit
    curation view, C11); panes are user-resizable; the layout target is a
    1366x768 laptop, where the three work panes get the overwhelming
    majority of the viewport.
12. **Every lint message is written for the reviewer.** Plain language (no
    "deixis"), states the consequence (verified against the actual runtime
    behavior -- e.g. what really happens to over-500-char instructions on
    the voice path), and names the action ("shorten it", "confirm or
    rewrite", "pick the excerpt from the booklet pane"). One copy pass over
    the rule catalogue with the RULE_LABELS parity contract maintained.

## Verified constraints carried forward from v9 (unchanged)

- The client staleness machinery needs the drift finding EMITTED (the
  identity hash lives only in its path); acked-filtering is client-side;
  backend lint emission is untouched by presentation work.
- The identity hash excludes guidance text; only the server-side apply
  re-stamps provenance (machine-ownership preserved); propose must be a
  true dry-run; apply merges per-field and clears the kit-level
  judge-unavailable flag; a second regeneration never grows the count.
- gnb0 (regenerate concurrency) is a wired prerequisite of C3.
- The publish gate currently blocks on lint ERRORs only; the hard review
  gate is NEW server behavior (decision 4).
- The extract route needs the complete-kit lock (C2); local Mark-complete
  routes server-side since 4ae1320b (stamp ownership three-case rule);
  Save-As never stamps (`savingToKit`); lint-report-less local saves stamp
  `verified: false`; quarantined fields sit outside `total` by
  construction; `getCompletionStats` gains an `errors` bucket (named API
  change, ~8 consumers).
- The review flip classifies TAGGED COMMIT CALL SITES (a channel can carry
  oppositely-classified behaviors); rename retargets and mechanical/server
  operations never flip; accepted rewrites preserve review (the acceptance
  IS the review of that change).
- 13 native `window.confirm` sites; RULE_LABELS parity test regex;
  translation force-selector is string-keyed with intended twin fan-out;
  incremental bake retry via key-presence.

## Exit rubric

| # | Criterion | Verify |
|---|-----------|--------|
| 1 | The warnings pane is gone and nothing is lost: findings render at their fields (property-anchored in the field editor; flagged in the field list; form-level findings on one pinned Form row), and the bottom strip is a single line whose counts (`reviewed / to review / total`) derive from effective field statuses only -- the catalogue % (both modes, via stamps) and the strip can never disagree; "to review" jumps to the next target; resolving or confirming a finding moves the count in the same render pass; a finding newer than the field's review flips it back to needs-review. | Fixture walk: no pane element renders; counts match a hand-computed status tally; click-to-jump works; inject a fresh finding on a reviewed field -> flips; catalogue-vs-strip equality test in hosted AND local mode. |
| 2 | Publishing is honestly gated: Mark-complete renders disabled-grey with the live % below 100 and primary-active at 100; the server refuses complete below 100% reviewed or with unresolved findings, naming the fields; disabled states show their reason inline (never tooltip-only); the guided complete transition runs save -> readiness gate (incl. the FREE translation-coverage refusal, whose message points at the author request flow) -> complete with NO model calls (token-free for editors); the AUTHOR "Run translation pass" action performs the one bundled bake (missing + flagged strings) with staged in-place progress and incremental retry, on hosted and local alike; `metadata.json` status values stay byte-identical. | Fixture with 2 unreviewed fields: button grey with "%", inline reason; force-complete via API refused with field list; review all -> button activates -> complete succeeds with zero model calls in the log; author deploy-prep runs the bake with staged progress; failure-retry re-runs only the remainder; status-key test. |
| 3 | Roles match trust: unlock/revert of a published kit, deploy, extraction, and every model-calling action are author-only (editor sees a disabled control with the reason, or a "Request" flag action); an editor can mark complete but their token cannot trigger a model call or a draft-revert at all (server-enforced -- NOTE the /status route carries BOTH transitions, so the role check is per transition inside the handler, not per route); editor rewrite-requests queue for the author, who runs them batched with per-request progress and per-channel diff acceptance. | Role-matrix test enumerating (route, action) PAIRS -- specifically /status with body complete (editor: allowed) and body draft on a published kit (editor: 403); editor token -> 403 on model routes; UI walk at editor tier (request flag sets, no call fires; lock banner says "ask an author"); author batch over 2 requested fields with an accept and a decline. |
| 4 | Drift resolution is calm and safe: the box is amber with two symmetric equal-weight actions; drift evaluation fires on settled edits only (typing in a field never flags mid-keystroke); rewrite shows the animated working indicator, a server-owned deadline kills a hung run and surfaces an explicit failure, and a successful rewrite is reviewed per channel (instructions/details accepted independently); decline writes nothing (byte-identical store); accepted fields stay machine-owned; repeated re-authoring never increases the kit's warning count. | Component tests (blur-settled, amber, symmetric labels); kill-switch test (server deadline -> explicit error, store untouched); per-channel accept test; byte-compare on decline; second-regeneration count test. |
| 5 | Review is the last touch and ignore is deliberate: content edits and new findings flip reviewed-correct (undo restores; tagged call sites exhaustive -- an unclassified commit site fails a test); the review section runs Notes -> status dropdown -> sign-off button LAST (green; needs-follow-up yellow); ignoring requires Required cleared first via a guided step and is per-field only (no section bulk); ignored fields render dark-grey on the PDF overlay. | Component tests: edit->flip, new-finding->flip, undo->restore, rename-dependent->no-flip, repair-all->no-flip; visual order/color check; ignore a required field -> guided two-step; overlay shows the grey box for an ignored field. |
| 6 | The workspace wins the screen: one-row header; catalogue behind the picker/drawer; Fields panel collapsible with reorder/re-section/ignore moved to a dedicated curation view; panes resizable; at 1366x768 with a form open and a field selected, the three work panes visibly dominate the viewport (no warnings pane, no second header row). | STRUCTURAL tests (jsdom cannot measure CSS layout): exactly one header-row element, no warnings-pane element, the work-pane container carries the flex-grow class, collapse/resize handlers wired; plus a MANUAL 1366x768 check recorded in the closeout journal with a screenshot (the target: work panes >= ~75% of viewport height). |

(Six criteria -- one over the 2-5 guideline; retained deliberately: merging
any two reproduces unscoreable conjunctions, per review round 3. Logged.)

## Bead tree

| Child | Bead | Child | Bead |
|---|---|---|---|
| C12 | polyglot-pdf-xfdb | C8 | polyglot-pdf-moxm |
| C1 | polyglot-pdf-o7y9 | C9 | polyglot-pdf-3v13 |
| C4 | polyglot-pdf-g687 | C10 | polyglot-pdf-x4tm |
| C2 | polyglot-pdf-apmo | C11 | polyglot-pdf-hlz3 |
| C3 | polyglot-pdf-05k9 | C5 | polyglot-pdf-cff9 |
| C7 | polyglot-pdf-jxkl | C6 | polyglot-pdf-cf6v |

Chain C12 -> C1 -> C4 -> C2 -> C3 -> C7 -> C8 -> C10 -> C11 -> C5
(blocks edges; one SPA, shared hub files serialize; each child names its
slice). C12 leads so lint messages are stable before fingerprints ship
(decision 3). C6 and C9 parallelizable. C3 blocked additionally by bd
polyglot-pdf-gnb0.

- **C1 (polyglot-pdf-o7y9) Embedded findings + one-truth strip** (rubric 1).
  Surfaces: `ValidationPanel.tsx` (becomes the thin strip; RULE_LABELS
  contract + parity test migrate), `FieldEditor.tsx` (property-anchored
  finding placement), `FieldList.tsx` (pinned Form row), `guidanceStaleness.ts`,
  `reviewStatus.ts` (new-finding-flips-review timeliness rule +
  fingerprints), App.tsx (count/nav wiring), tests + fixture. NO backend
  changes. Deletes the v1-prototype grouped pane, bulk-confirm, and
  field-level dismissals.
- **C4 (polyglot-pdf-g687) One truth for progress, both modes** (rubric 1's catalogue half).
  As v9 (stamps, three-case ownership, `savingToKit` gate, verified:false
  downgrade, errors bucket API change, display-language pass, closes bd
  2onl), with the stamp computed by the SAME `publish_readiness` function
  the gate uses (decision 4) so strip, stamp, button, and gate share one
  definition.
- **C2 (polyglot-pdf-apmo) Publish gates + lock + roles' UI half** (rubric 2 + 3's UI).
  Surfaces: App.tsx (lock banner -- red, author-only unlock; 409 inline
  action; guided save->gates->bake->complete; dirty-buffer fix;
  disabled-shows-why rule), `RemoteCatalogue.tsx`/`FormCatalogue.tsx`
  (gated grey-%->active Mark-complete, dirty-gated with inline reason,
  in-card staged progress -- absorbs bd 6udf), `backend/routes/
  editor_kit_routes.py` + new `backend/services/publish_readiness.py`
  (extract route complete-lock; the HARD gate refuses on
  publish_readiness's verdict, naming fields -- decision 4), tests.
- **C3 (polyglot-pdf-05k9) Drift + rewrite machinery** (rubric 4; blocked by gnb0).
  Surfaces: `FieldEditor.tsx` (amber symmetric two-action; blur-settled
  evaluation; working indicator), diff-review component (per-channel
  accept), `backend/routes/editor_kit_routes.py` (propose dry-run + apply
  modes; server-owned deadline with explicit abort semantics),
  `scripts/authoring/enrich_instructions.py` (per-field-merging apply,
  kit-level flag clear), App.tsx (author batch driver over requested
  fields), tests.
- **C7 (polyglot-pdf-jxkl) Review-last integrity** (rubric 5's review half).
  Surfaces: `FieldEditor.tsx` (bottom section order Notes -> dropdown ->
  green sign-off button; yellow needs-follow-up), App.tsx commit-channel
  classification + `fieldRename.ts` handler, `reviewStatus.ts`
  (new-finding flip shared with C1), tests incl. exhaustiveness.
- **C9 (polyglot-pdf-3v13) Roles + request flags, server half** (rubric 3; parallelizable
  after C2's gate lands).
  Surfaces: `backend/routes/editor_kit_routes.py` (model-calling routes
  already author-only -- verified; add: the /status handler's role check
  becomes PER-TRANSITION -- body complete stays editor-allowed, body
  draft on a published kit becomes author-only -- one handler, two rules;
  deploy-adjacent author-only; request-flag storage acceptance),
  `FieldEditor.tsx`/catalogues (editor-tier "Request rewrite"/"Request
  re-translate" flags -- stored as `_review` request slots carried by the
  same writer-preservation helper as `seen_fingerprints`; author's
  requested-work queue view; C2's unlock button renders author-only, the
  editor-tier lock banner says "ask an author to unlock"), tests (the
  (route, action)-pair role matrix).
- **C8 (polyglot-pdf-moxm) Translate once, by the AUTHOR** (rubric 2's bake half).
  As v9 mechanically (extraction default-off, force-string selector,
  incremental retry), but the BAKE moves out of the /status complete
  transition (which becomes token-free) into an author-tier "Run
  translation pass" action on the kit (hosted AND local -- it does not
  ride the dev-only deploy endpoint, which exists only under vite dev);
  the /status gate KEEPS the free coverage refusal, so an un-baked kit
  cannot reach complete on any path and the editor's refusal points at
  the author request flow. Deploy tooling is untouched.
- **C10 (polyglot-pdf-x4tm) Layout: thin chrome, resizable workspace** (rubric 6).
  Surfaces: App.tsx header/layout, catalogue drawer/picker integration,
  pane resize + Fields-panel collapse, CSS. The 1366x768 target.
- **C11 (polyglot-pdf-hlz3) Field curation view + visible ignore** (rubric 5's ignore half +
  rubric 6's curation walk).
  Surfaces: new curation view (supersedes the SectionManager modal --
  whose Regenerate-divisions button moves with it, staying reachable:
  reorder, re-section, per-field ignore with the guided Required step),
  `FieldOverlay.tsx`/`PDFViewer.tsx` (the overlay gains a SECOND
  iteration source -- `getIgnoredFields(schema)` -- alongside
  schema.fields, rendered by the dedicated dark-grey branch),
  `ignoreField.ts` + `fieldGrouping.ts` (the `_ignored_fields` stash is
  now load-bearing for RENDERING, not just restore -- a round-trip test
  pins that every save path preserves it), tests.
- **C5 (polyglot-pdf-cff9) Polish bundle** (supports all). Styled confirms (13 sites), a11y
  labels, card action consistency.
- **C6 (polyglot-pdf-cf6v) Investigation: identity-drift wave root cause** (parallelizable).
  As v9.
- **C12 (polyglot-pdf-xfdb) Lint message copy pass** (decision 12; parallelizable).
  Surfaces: `backend/services/schema_lint.py` messages (+ the enrich/
  translation flag writers' message templates), RULE_LABELS + remedies,
  parity test, a verification note per rule pinning its stated consequence
  to actual runtime behavior (starting with the 500-char instructions
  bound).

MECE check: chain order is the collision guard for shared hub files with
named slices; every criterion inherited (1->C1+C4, 2->C2+C8, 3->C9+C2,
4->C3, 5->C7+C11, 6->C10+C11); no "etc." items; C6/C9/C12 parallelizable
where noted; prerequisite gnb0 wired; absorbed beads (6udf, 2onl) named;
l7u0 superseded by C1's overlay/status work.

## Out of scope

- Voice-app changes; the voice-delivery schema contract; `metadata.json`
  status values byte-stable (test-pinned).
- Editor-tier self-serve model calls and quota/rate-limit infrastructure
  (the request-flag model removes the need; revisit only if authors become
  a bottleneck).
- Merging the two catalogue components; a guidance-history store; undo
  across server operations (decline + per-channel accept are the
  controls); deployment mechanics beyond the author-only gating.
- (Moved from kept-scope to a NAMED CHANGE:) the local no-backend
  UNCHECKED completion path is RETIRED by the hard gate -- with no
  backend there is no gate, so that branch may still save drafts but can
  no longer flip a kit to complete (an ungated completion would be the
  epic's own loophole). Breaking change to the offline flow, stated for
  the approval record; local dev runs the backend via
  run-schema-editor.sh as standard.

## Change log

Rounds 1-7 (v1-v9): 52 Opus findings folded -- server-side propose/apply;
chunk-cost pinning; gnb0 prerequisite; stamp mechanism + three-case
ownership; lock scope = the backend's locked routes + extract; blocking as
rule-class with consumers named; to-review-pending misconception corrected;
C8 sweep force-selector; flip call-site classification; flag-replacement
lifecycle; parity contracts; no-backend degraded modes. (Full per-round log
in v9, superseded here for brevity; v9 is in git history.)

**Opus round 8 (v10, 8):** the hard gate pinned to ONE backend function
(`publish_readiness`) computing ack-matching NATIVELY via
guidance_contract.identity_sha1 (no cross-language copy, no path parsing),
with the C4 stamp and the gate reading the same function so the button and
server cannot disagree about a saved kit, and a degraded-lint UNKNOWN state
on the button; the ignore-as-gate-bypass consequence named with the
ignored-count accountability rail (publish confirmation, notice, card);
grey ignored-overlay authorized as a dedicated rendering branch reading
`_ignored_fields` (EffectiveStatus union untouched; ignoreField's
invisibility premise formally amended); `seen_fingerprints` pinned as the
fourth `_review` slot with single-writer semantics and
writer-preservation helper + test (the three-slot-rebuild drop hazard is a
recorded past bug); the ValidationPanel's four non-display
responsibilities (lint round-trip, onReport mirror, Repair-all,
degraded-mode notices) explicitly reassigned to the strip component, plus
a strip refusal/error line from birth (closes the C1->C2 mid-chain
no-renderer window); rubric 6 restated as structural tests + a recorded
manual 1366x768 check (jsdom cannot measure layout); the /status role
split specified per-transition inside the one handler with a
(route, action)-pair test matrix.

**Opus round 9 (v11, 6):** the editor-token-spends-tokens contradiction
resolved by the maintainer's tiered model -- complete becomes a free
readiness gate, the bake moves to author deploy-prep with deploy
eligibility = complete + coverage (C8 reshaped; the sweep leaves
/status); the count predicate pinned to review-status + lint only
(checkFieldComplete leaves the count, stays advisory; its structural
checks promoted to lint rules via C12 where missing); kit-scoped lint so
the strip and gate share dump-loaded inputs (C1's no-backend-changes
claim retired); C11 gains the fieldGrouping.ts stash-round-trip coupling
and the second overlay iteration source, and keeps Regenerate-divisions
reachable; the no-backend completion branch retired under the hard gate
(named breaking change); fingerprints exclude message text and C12 is
ordered before C1 so the copy pass cannot mass-demote reviewed fields.
Also absorbed: the spun-off edit-loss task is C2's, not a parallel bead.

**Opus round 10 (v12, 1):** the author-bake fold had silently deleted the
only blocking translation gate on the hosted path (the per-kit deploy
surface is vite-dev-only; the coverage lint rule is WARNING). Fix as the
reviewer specified: the FREE coverage check stays in the /status complete
refusal (pure schema inspection, no tokens) with request-flow wording;
only the bake moves to an author-tier "Run translation pass" action that
exists on hosted and local alike; deploy tooling untouched.

**Maintainer hands-on round (v10 restructure):** warnings pane removed in
favor of embedded findings + one-truth strip with clickable counts (the
session's "0 need review vs 7 to review" contradiction is structurally
impossible under one definition); hard 100% gate with the grey-%->active
Mark-complete button (reverses v9's soft gate, maintainer-directed);
disabled-shows-why rule (the "nothing happened" session bug);
new-finding-flips-review timeliness rule replaces field-level dismissals;
bulk-confirm deleted; drift box amber + symmetric + blur-settled +
no-"booklet" wording; two-level timeout promise (client indicator, server
deadline, explicit failures); per-channel diff acceptance; author/editor
trust split with zero-cost request flags instead of editor model calls;
unlock red + author-only; review section reordered (Notes -> dropdown ->
button, green/yellow); per-field-only ignore with guided Required step and
dark-grey overlay visibility (bulk section ignore rejected -- session
evidence of mis-sectioned required fields); thin one-row header, collapsible
Fields panel, resizable panes, 1366x768 target; field curation view (C11);
lint-message plain-language/consequence/remedy pass (C12); "resolved" count
dropped from the strip.
