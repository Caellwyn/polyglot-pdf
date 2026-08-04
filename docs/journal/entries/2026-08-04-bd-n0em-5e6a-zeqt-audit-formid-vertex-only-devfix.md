---
date: 2026-08-04
bead: polyglot-pdf-n0em
title: "Audit trail names the form, Vertex-only production, and Windows local dev works again"
tags: [security, hotfix, conventions]
---

## Trigger

Three small, independent fixes bundled because each was blocking something
concrete and none warranted its own review cycle.

**`polyglot-pdf-n0em` (P1)** -- found in PRODUCTION. The maintainer's first real
deployed W-7 voice run (form-session `fss_mse0bv3x_yzmqj4gz`, 2026-08-04) wrote
31 `field_confirmed` events to the durable Firestore sink, every one carrying
`form_id="unknown"` instead of `"W-7"`. Now that the sink is durable (bd
`polyglot-pdf-z2is`), every session was permanently recording a liability trail
that could not name the form.

**`polyglot-pdf-5e6a` (P1)** -- maintainer directive, post-merge of PR #536: AI
Studio is NEVER a production path. Only Vertex's privacy agreement prevents
Google from using client data for model training, and the product's privacy
promise rests on that. PR #536 had shipped a two-flag escape hatch
(`ALLOW_AI_STUDIO=true`) designed when flipping the demo to AI Studio for 3.1
was a documented path; the directive kills that path.

**`polyglot-pdf-zeqt` (P2)** -- filed by the PR #536 outer review. `dev-local.ps1`
never set `VFF_DISABLE_AUTH`, so once #536 gated the form-kit routes, Windows
local dev showed "Unable to load forms". The POSIX sibling `dev-local.sh` had
always set it; the two dev paths had silently diverged.

## What shipped

**form_id through the manifest-first handshake.** `FormFillingService.start_session`
derives `form_id` from `schema["form_metadata"]["form_number"]`, but on the
manifest-first (JIT) transport -- the SHIPPED DEFAULT, since `USE_DTI` /
`CONTINUOUS_SESSION` default true -- the handshake carries a manifest +
`first_field_schema`, not the full schema, so `form_metadata` was absent and the
`"unknown"` fallback fired. The client now sends `form_number` alongside the
existing `form_title` (`schemaFormState.getJITHandshakePayload`), and
`websocket_routes` threads it into the minimal schema's `form_metadata`. Two
design points: (1) `form_number` and `form_title` stay DISTINCT keys -- the
title is a human label, the number is the audit identifier, and collapsing them
would record prose where an identifier belongs; (2) the metadata dict is now
built when EITHER key is present (the old code keyed construction on the title
alone, so a title-less handshake lost the number even if sent).

Worth noting the same `form_id` feeds the token-cost logging context
(`set_session_context`), which is why the deployed cost summaries also showed
`form_id: "unknown"` -- one fix corrects both surfaces. Section switches and
reconnects re-enter `start_session`, so they inherit the fix with no extra
plumbing.

**Vertex-only production.** The `ALLOW_AI_STUDIO` field and its acknowledgment
branch are REMOVED. `Settings` now fails startup outright when `VERTEXAI=false`
and `K_SERVICE` is set (Cloud Run), with no override. Local dev, the voice
harness, and probes have no `K_SERVICE` and keep full AI Studio access -- the
one sanctioned use, for testing a model (e.g. 3.1) before it reaches Vertex GA.
Docs corrected in three places that still described flipping a DEPLOYED service
to AI Studio: `ai-models.md` (the canonical selection rule, plus the A/B section
now labelled local-only), `config-deployment.md`, and the `deploy-demo.sh`
comment block.

**Windows dev parity.** `dev-local.ps1` sets `VFF_DISABLE_AUTH` (default `true`,
per-run override via `$env:VFF_DISABLE_AUTH`), matching `dev-local.sh`, and the
startup banner now reports it.

**Fresh-eyes round 1 (Sonnet): GAPS-FOUND (3), all adopted.** Two were rubric
FAILs, which is the assess loop doing exactly its job:
1. ADOPTED (5e6a criterion 2 FAIL): `docs/technical_guide.md` still described
   `ALLOW_AI_STUDIO=true` as the live mechanism for a deployed
   `VERTEXAI=false` -- a file whose own `**Tracks:**` line names
   `backend/config.py`. My earlier sweep missed it because I filtered the grep
   output. Rewritten to the Vertex-only rule + stamp bumped.
2. ADOPTED (n0em criterion 2 FAIL): no test covered the RECONNECT case the
   criterion names, even though the production bug was found on a session that
   reconnected mid-form. Correctness across reconnect rested on reading the
   code, not on a test. Added
   `test_form_id_survives_reconnect_and_section_switch` (cold connect + two
   resume handshakes must all derive the real id).
3. ADOPTED: the FRONTEND half of the fix -- the one line that actually puts
   `form_number` on the wire -- had no test at all, despite the fixture already
   seeding `form_number: 'I-90'` and a sibling precedent in the same file. Added
   two tests (real value; null when the kit lacks one), both mutation-verified.
   Notable asymmetry worth remembering: the backend half had a deliberate
   source-parity guard while the frontend half, equally revertible, had nothing.

**Fresh-eyes round 2 (Opus clearing round): GAPS-FOUND (5), all adopted.** Two
were rubric FAILs that invalidated this bead's headline claim:
1. ADOPTED (n0em criterion 1 FAIL -- **the tests were vacuous**): the reviewer
   reverted the route to its exact pre-fix form and **6 of the 7 tests still
   passed**. The module tested a local REPRODUCTION of the route's schema
   construction, so it could not observe the route at all; only the
   `inspect.getsource` substring guard fired.
2. ADOPTED (n0em criterion 2 FAIL): worse, the reviewer defeated that guard with
   a realistic ONE-TOKEN mutation -- `if jit_form_title or jit_form_number:` ->
   `if jit_form_title:` -- which leaves both guarded substrings intact. All 7
   tests passed against a live bug matching a scenario one of them claimed to
   cover. The reviewer then demonstrated that a real route-level test costs ~20
   lines using the existing `TestLiveHandshakeFlow` TestClient harness.
   **Rewritten**: the module now drives the REAL `/ws/fill` route over a
   websocket and asserts the `form_id` the CallbackHandler is actually
   constructed with (the value `log_field_confirmation` writes), including the
   reconnect case as three sequential round-trips sharing one
   `form_session_id`. Re-verified against BOTH mutations: the subtle `or`
   removal now fails 1 test, the full revert fails 3 (the fourth, older-client
   degradation, correctly still passes).
3-4. ADOPTED (5e6a criterion 2 FAIL): two more stragglers recommending the
   forbidden flip -- `deploy-demo.sh:74` ("flipping BACK to AI Studio ... needs
   no stale pin cleared", in the same comment block whose next paragraph
   forbids it) and `config-deployment.md:80` ("reaching it still requires
   VERTEXAI=false" with no local-only qualifier, in a deployment doc).
5. ADOPTED (reviewer filed as out-of-scope; fixed inline as it is two lines the
   diff itself falsified): `form_filling_service.py:610` asserted the
   manifest-first handshake "carries no form_metadata and resolves to unknown"
   -- true before this change, false after.

**Lesson recorded against myself:** I reported these tests as
"mutation-verified" after checking exactly ONE mutation (renaming the dict key),
which the substring guard happened to catch. I never tested the mutation that
mattered. A source-substring guard proves a string is present, not that
behavior is correct -- it is a weak substitute for exercising the real code
path, and claiming verification on the strength of one convenient mutation is
how a vacuous test ships wearing a verified label.

**Fresh-eyes round 3 (Opus): GAPS-FOUND (3), all adopted.** The round
independently re-ran both mutations against the rewritten module and confirmed
it is now non-vacuous (full revert -> 3 of 4 fail; subtle `or` removal -> 1
fails), and verified the spy reads the real `CallbackHandler._form_id` with
exact-list-equality so a `None` from a renamed attribute cannot pass silently.
1. ADOPTED (5e6a criterion 2 FAIL): `README.md` -- the repo's most-read doc --
   still INSTRUCTED a deployed AI Studio flip in two places, including the
   Deployment Checklist ("for the AI Studio path (`VERTEXAI=false`) set
   `GEMINI_API_KEY` instead"). A maintainer following that checklist would get a
   container that crash-loops with no README-visible explanation. Rounds 1-2
   swept the deploy script and the tier-2 docs; nobody swept the README. Fixed
   in three spots (deploy section, checklist, feature-list qualifier).
2. ADOPTED (honest scoping): the reviewer traced `form_session_id` through the
   whole backend and found it is only ever THREADED -- nothing keys, caches, or
   branches on it -- so the reconnect test's three round-trips are three
   independent sessions carrying the same string. It scored the criterion PASS
   (the backend is stateless by design, so there is no cross-connect state a
   reconnect could break, and per-connect derivation was the real risk) but
   flagged the docstring as over-claiming. Docstring rewritten to state exactly
   what is and is not covered.
3. ADOPTED: this entry's own "Files touched" line still described the
   SUPERSEDED 7-test helper design, contradicting the rewrite narrated two
   paragraphs above it.

Reviewer also filed `polyglot-pdf-knmp` (out-of-scope): `VFF_DISABLE_AUTH` has
no `K_SERVICE` fail-closed guard, so unlike `VERTEXAI` a stray env var could
disable auth on a deployed service. Correct to file rather than fix here --
it is a distinct hardening, not part of these three beads.

**Fresh-eyes round 4 (Opus): GAPS-FOUND (1), adopted.** The round confirmed all
prior fixes hold (re-traced `form_session_id` across 68 backend sites to verify
the round-3 docstring is factually accurate rather than merely softened; counted
the test module; verified no executable line changed since the round-3 green
suite) and ran an exhaustive named sweep of README, DEPLOYMENT.md, every deploy
script, `.github/`, env examples, skills, and probes.

**The finding:** `USE_PREMIUM_MODEL=true` selects 3.1, which exists only on AI
Studio -- and the new startup guard CANNOT fail-closed on it, because
`_resolve_model` sets the premium id BEFORE the `VERTEXAI` branch. A deployed
service therefore starts cleanly and then `1008`s at connect time on every
session, a worse failure mode than the crash-loop the guard produces. Three docs
presented it as a plain opt-in (`ai-models.md:58`, `technical_guide.md:40`,
`config-deployment.md:52`); all now carry a LOCAL-ONLY qualifier naming the
silent-failure mechanism.

**Correction (round 5).** Round 4 framed this as "the AI-Studio flip under
another name," and the round-5 reviewer checked it and found that overstated:
with `VERTEXAI=true` the adapter builds a **Vertex** client
(`live_ai_gemini.py:329-336`), so the combination never reaches AI Studio. It is
a MODEL-AVAILABILITY failure (a Vertex 1008 for an id Vertex does not publish),
not a privacy-boundary breach. 5e6a criterion 1 therefore genuinely PASSES, and
deferring the guard to `llva` is correct rather than an evasion. The docs
qualifier is still right -- an operator must not deploy 3.1 -- but the reason is
"it will not run," not "it leaks to consumer terms."

Fixed here as docs (a warning); the GUARD gap is filed as
`polyglot-pdf-llva` (P2) -- extend the fail-closed check to refuse startup when
the RESOLVED model is unavailable on the active backend, keyed on model+backend
rather than on a flag name so a future AI-Studio-only model is covered
automatically. Deliberately not done in this PR: it is a distinct hardening with
its own exit criteria, and 5e6a's criteria are about the `VERTEXAI` flip and the
docs.

Deliberately left (reviewer's call, concurred): `scripts/spikes/*_findings.md`
is a dated experiment artifact, frozen like a journal entry; pre-existing emoji
in `deploy-demo.sh` echo lines are outside every changed hunk.

## Lessons

- **A durable sink makes every latent metadata defect permanent.** `form_id`
  had been `"unknown"` on the JIT path for as long as JIT has been the default,
  but it was invisible while the trail died with the container. Turning on
  durability is the moment to audit what the record actually CONTAINS, not just
  that it persists. The first real production session was the audit.
- **A guard covers a FLAG; enumerate the STATES that flag was standing in for.**
  The Vertex-only guard fires on `VERTEXAI=false`. `USE_PREMIUM_MODEL=true`
  produces a different bad deployed state (an unrunnable model) that slips past
  it entirely, failing at connect rather than at startup. Note the discipline
  this cuts both ways: my first framing called that "the AI-Studio flip under
  another name," and review corrected it -- with `VERTEXAI=true` the adapter
  still builds a Vertex client, so it is unavailability, not a privacy breach.
  Enumerate the bad states a guard should cover, and be equally precise about
  which bad state each one actually is.
- **Two transports means two places for schema-derived values to fall through.**
  The legacy full-schema handshake and the manifest-first one both build a
  `schema` dict, but only one carries `form_metadata`. Any value derived from
  `schema[...]` needs checking against BOTH shapes -- `form_title` had already
  been fixed this way (bd `jnjj.9`, gap O) and `form_number` was the same class
  of bug, missed because the two keys were added at different times.
- **Bash-tool file writes do not persist, and `grep` verification of them
  lies.** An attempt to edit 18 per-language translation blocks via a
  Python-through-Bash script silently wrote to a sandboxed copy three times;
  the `grep -c` checks in between read that same phantom copy and reported
  success while the real file was uncompilable. Only `tsc --noEmit` caught it.
  Repetitive multi-block edits still go through Write/Edit, and verification
  belongs to the toolchain (compiler/tests), never grep. Recorded in local
  memory; the pre-existing repo scar tissue covers the general rule.

## Doc freshness

Bumped with substance: `docs/standards/ai-models.md` (Vertex-only production
rule replacing the two-flag guard; A/B section marked local-only),
`docs/components/config-deployment.md` (`ALLOW_AI_STUDIO` removed from the
env-overridable list and its bullet rewritten as the Vertex-only rule), and
`docs/standards/ws-protocol.md` (the new `form_number` handshake key).

That last one was **not** volunteered -- the existing contract test
`test_every_code_read_handshake_key_is_documented` failed the full suite
because the route read a handshake key absent from the protocol doc's tables.
Exactly the guard working as designed: the wire contract cannot grow a key
silently. Worth noting as a pattern, since any future handshake key will hit
the same gate.

The `z2is` journal entry retains its `ALLOW_AI_STUDIO` references deliberately
-- it is the historical record of what shipped that day, and the journal is not
rewritten.

## Files touched

- frontend/src/schema-forms/state/schemaFormState.ts -- send form_number on the JIT handshake
- backend/routes/websocket_routes.py -- read form_number; build form_metadata from either key
- backend/config.py -- ALLOW_AI_STUDIO removed; deployed AI Studio path fails hard
- backend/services/form_filling_service.py -- corrected the cache-key comment this change falsified (review round 2)
- scripts/dev-local.ps1 -- VFF_DISABLE_AUTH wired with override + banner
- deploy-demo.sh -- 3.1 comment rewritten (local-only until Vertex GA)
- docs/standards/ai-models.md, docs/components/config-deployment.md -- Vertex-only rule
- docs/standards/ws-protocol.md -- documents the new form_number handshake key
- docs/technical_guide.md -- Vertex-only rule (fresh-eyes: stale ALLOW_AI_STUDIO row)
- backend/tests/unit/test_jit_handshake_form_id.py -- new (4 ROUTE-LEVEL tests over a TestClient websocket; the earlier 7-test helper-based cut, including its inspect.getsource parity guard, was proven vacuous in review round 2 and removed)
- README.md -- Vertex-only rule in the deploy section + checklist (review round 3)
- backend/tests/unit/test_vertexai_guard.py -- rewritten for the no-override policy
- frontend/src/schema-forms/state/schemaFormState.test.ts -- 2 new form_number handshake tests
