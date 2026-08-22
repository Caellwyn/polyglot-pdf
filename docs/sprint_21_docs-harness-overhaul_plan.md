# Epic plan: docs-harness overhaul -- fresh, lean, conflict-free

**Status: FINAL (v3). Survey-informed; adversarial Opus review round applied
(2 blockers + 5 majors found and integrated -- summary at bottom).**

## Context

The docs-freshness system has never worked: **21 of the 28 freshness-tracked
tier-2 docs (75%) are stale right now** (6 more tier-2 docs have no `Tracks:`
line and are invisible to the checker entirely), sessions blind-append to docs
(the 22-line stamp changelog PR #622 removed), docs contradict code and each
other, and parallel sessions merge-conflict in shared doc files. PR #622
(bd abn4o, merged 2026-08-22) fixed one file and produced the diagnosis; this
epic generalizes the fix to the whole harness: scripts, tests, skills, agent
prompts, and doc formats.

### Diagnosis (verified evidence, 2026-08-20..22)

1. **Alarm fatigue killed the freshness signal.** The checker prints the same
   ~21 stale docs at every closeout; unactionable in the moment, and closeout
   Step 2's "note that in the journal entry" escape hatch dismisses the whole
   list in one sentence.
2. **No cheap "reviewed, still accurate" path.** Clearing a stale flag today
   requires a stamp bump (merge conflict) or a doc commit (noise). Honest
   review leaves the flag on, so everyone learns to ignore the flag.
3. **Enforcement level predicts compliance (measured, same script).** The
   warn-only staleness half: 21 stale docs. The CI-gated current-state
   convention half: corpus clean. Advisory signals die here; gates bind.
   COROLLARY (from the adversarial review): any new gate's cheapest
   satisfying action WILL become the ritual -- so the cheap path must be the
   honest path, structurally.
4. **Instructions taught transcription, not verification.** Closeout
   instructed re-adding the deleted stamp; the checker docstring (:53) and
   doc-architecture.md both describe a pre-commit hook that HAS NEVER EXISTED
   (no .pre-commit-config.yaml, no .git/hooks entry, no settings.json hook).
5. **Blind insertion + no format pins = accretion.**
6. **Set-pins work and are an established house pattern** (3 precedents:
   test_websocket_protocol.py pins ws-protocol.md's tables both directions;
   test_technical_guide_routes_table.py; test_http_route_auth.py's set pin).

### Ground truth the design is anchored on (adversarial-review verified)

- **dev is LINEAR: every PR squash-merges** (last true merge commit
  2026-07-05; PR #622's branch commits are provably not ancestors of dev).
  Consequences: commit-ANCESTRY carries no information across a merge; any
  branch SHA recorded anywhere dies at squash; doc+code edits in one PR
  collapse into ONE dev commit (equal timestamps -> the existing strict
  `file_ct > doc_ct` compare already treats that as fresh, correctly).
  Therefore: **keep the timestamp compare** (it produced the accurate 21);
  do NOT rebuild on ancestry. The freshness anchor for acks must be a
  git-tracked FILE (whose own commit time survives squash), never a SHA.
- check_doc_freshness.py facts: always exits 0; `--staged` mode is the
  branch-gate template (staged_files() :206, check_doc() :318-377, compare
  :373, doc_ct sources :343-345); `--all` is a no-op flag; DOC_DIRS :88,
  TIER1_DOCS :147, CONVENTION_ONLY_DOCS :163; no-Tracks docs silently
  skipped (:336). Suite: tests/test_doc_freshness.py (1,146 lines, 59 tests).
- Closeout SKILL.md: Step 2 stamp instruction (:183) + abn4o carve-out
  (:185); worktree $WT-not-$R hazard documented (bd 9pe); Step 0 requires a
  clean tree; trivial-diff arm skips adversarial review (:408-411);
  push-time is `git pull --rebase origin dev` (:597, :647).
- 39 files still carry stamps (9hdt4/w3btc say "44" -- stale, correct when
  updating those beads). doc-architecture.md's own stamp interacts with the
  TRACKS_RE first-match hazard documented at checker :151-163.
- Tool docs: voice-ai.md :302-341 documents tool SEMANTICS; technical_guide
  contract-4 table :344-353 is a COUPLING map. Same nouns, different facts --
  NOT duplicates (review-verified: switch_to_field appears only in the
  table). Neither is pinned against Settings.TOOL_DECLARATIONS
  (backend/config.py:588) + SPELLBACK_TOOL_DECLARATION (:832).
- Env-var table (technical_guide :38-52, 13 rows) is NOT cleanly enumerable
  (2 rows are getenv-not-Settings; 1 glob row; 1 derived row; 55/68 Settings
  fields deliberately undocumented; Settings holds non-env prompt blobs).
- deploy-all.sh's BACKEND_ENV enumerates the vars deployments actually set;
  tests/test_deploy_form_kit_hints.py already pins against deploy config
  (the honest, code-owned source for "load-bearing").

## Epic structure

**Extend epic w3btc** (update its description to the broadened scope, point
`plan:` at this file, correct its "44 stamps" to 39). No second docs epic.
Existing children unchanged unless named below: jqgpl, m2j14 (conditional),
m1ulw (measure-first). vjdcn is implemented AS WRITTEN (merge replaces the
:597 rebase -- the plan adds nothing to it; an earlier draft misread it).

## Beads

### B1a = polyglot-pdf-fytzi (new, P1): the ack mechanism + freshness rule, mechanism-only
**No doc files touched. First PR of the epic.**
- Keep the existing timestamp compare. Add ONE new doc_ct source: a per-doc
  ack file `docs/freshness/<slug>.ack` (NOT dot-prefixed -- avoids gitignore
  shadowing and hidden-dir invisibility; test asserts the path is not
  ignored). **The freshness anchor is the ack file's own git commit time**
  (`git_commit_time(ack_file)`), which survives squash by construction and is
  topology-robust (works under true merges too). Rule:
  `stale iff file_ct > max(doc_ct, ack_file_ct)`.
- Ack file CONTENT is for reviewers, not for the math:
  `verified: <tracked files checked>` + `because: <one line>` + the SHA at
  ack time (informational). Written by `check_doc_freshness.py --ack <doc>
  --because "<reason>"`; the tool auto-fills `verified:` with the tracked
  files that triggered staleness. **Structural anti-gaming** (diagnosis-3
  corollary): the reason + file list land in reviewable diff surface; a bare
  ack is impossible; and any PR whose diff contains a `.ack` is routed to at
  least the Haiku docs-review arm regardless of the trivial-diff skip
  (closes the ack-laundering path).
- Uncommitted-ack semantics defined: the gate reads the WORKING TREE (so
  Step-2 triage acks count immediately); acks must be committed before
  closeout_finish.py runs; all invocations via $WT per the documented bd-9pe
  hazard.
- Soft rate signal: >3 acks in one branch prints a pointer to the audit bead
  (B7) -- bulk acking is audit work, not closeout work.
- Exit criteria: (1) ack->green->code-moves->red cycle mutation-verified,
  incl. the squash case (ack + code landing in one commit stays fresh) and
  the not-gitignored assertion; (2) a doc-first-then-code SEPARATE-commit
  pair is fresh once the ack (or doc touch) postdates the code commit;
  (3) no doc file modified in the PR.

### B1b = polyglot-pdf-xheli (new, P2, after B1a+B1c): delete the 39 stamps
**Mechanical, docs-only PR (Haiku arm), no logic change.** Sequenced LAST of
the B1 family deliberately: it is the maximally conflict-prone diff (39 hot
files), so it ships alone, after the mechanism and instructions are stable,
timed for a quiet moment (check open PRs first). Care: doc-architecture.md's
stamp + the TRACKS_RE first-match hazard (:151-163). Exit: zero
`*Last updated:*` lines in tier-1/2 docs; checker + full suite green.

### B1c = polyglot-pdf-olphy (new, P1, right after B1a): instruction sites
**Small PR.** Rewrite closeout Step 2 (:183) to "update the prose, then ack
what you verified" (the stale-doc "leave it" carve-out SURVIVES -- see B2);
delete the two fictional pre-commit-hook claims (checker :53,
doc-architecture.md setup item); give the 6 no-Tracks tier-2 docs either a
real `Tracks:` line or membership in an explicit no-tracks allowlist in the
checker (silent skip becomes a deliberate, visible list -- pinned by a test).
Exit: (1) no instruction anywhere tells a session to bump/add a stamp
(allowlist-style test, B6 finishes the sweep); (2) the no-tracks set is
explicit and pinned.

### B1d = polyglot-pdf-hzntv (new, P2, independent): format pins on the CONVENTION (CI-gated) half
**Separate from B1a-c because it touches the half that reddens CI.** Widen
PREVIOUSLY_CHAIN_RE for the observed accretion grammar ("Same day,/Same
week, bd ..." in tier-1/2 prose); pin the `Tracks:` line shape. Exit: each
new pattern mutation-verified red on a synthetic violation AND green on the
current corpus (no false positives on the 34 real docs).

### B2 = polyglot-pdf-rooqt (new, P1, after B1a): branch-scoped staleness gate at closeout
- New checker mode `--branch [BASE=origin/dev]`: the gated set is docs whose
  tracked files changed IN THIS BRANCH (`git diff BASE...HEAD`), minus docs
  touched in the branch (non-whitespace diff -- `git diff -w` empty check),
  minus docs with an ack committed/working-tree in the branch. **Staleness
  that predates the branch NEVER enters the gate** -- the current "it was
  already stale before you; leave it" carve-out is preserved mechanically
  (this is what keeps day-one usable: a PR touching backend/config.py is
  gated only on ITS OWN doc debt, not on three docs stale since before it).
- closeout_prep.py surfaces the set as a first-class RESULT item and refuses
  "ready" until it is empty. Hard gate, deterministic, in prep.
  [MAINTAINER APPROVE-POINT -- recommended: hard. With the newly-caused-only
  scoping, the gate only ever asks a session to document its own change;
  reversible in one line if it over-blocks.]
- Corpus-wide output leaves closeout: one summary line + pointer to B7.
- Defined no-ops: journal-only and docs-only PRs (no tracked code changed).
- Exit: (1) branch with tracked-code change + no doc/ack -> prep refuses;
  ack or real doc edit -> passes; whitespace-only doc edit -> still refuses;
  (2) a doc stale at BASE for unrelated reasons never blocks; (3) closeout
  no longer prints the corpus-wide list.

### B3 = polyglot-pdf-j5gt2 (new, P2, independent): set-pins for tool names + env vars
- **Tool names, three-way set pin**: the same tool-name set must appear in
  code (TOOL_DECLARATIONS + SPELLBACK_TOOL_DECLARATION), voice-ai.md's
  semantics list, and technical_guide's coupling table. BOTH docs stay --
  they document different facts about the same nouns (review finding); the
  pin is set-membership only. Fix the current real gaps the pin will expose
  (e.g. switch_to_field missing from voice-ai's list).
- **Env vars**: phantom direction only from the table (every documented var
  exists in Settings or a named getenv site, with a documented exception
  shape for the glob/derived rows) + completeness derived from a CODE-OWNED
  source: deploy-all.sh's BACKEND_ENV (precedent:
  test_deploy_form_kit_hints.py). NO test-curated allowlist (self-curated
  pins are the pin-the-label trap).
- Doctrine line in doc-architecture.md: "a doc that enumerates code facts
  gets a set-pin" + name the precedents.
- Exit: (1) both pins mutation-verified both directions with the
  adversarial-shaped mutation; (2) no test-curated completeness list exists.

### B4 = polyglot-pdf-6v6sc (new, P2, independent): doc-edit discipline doctrine
Docs-only PR. New "Editing discipline" section in doc-architecture.md
(canonical home; CLAUDE.md gets a one-line pointer):
1. READ the whole doc before editing.
2. REPLACE, don't accrete -- insertion into existing prose without any
   deletion is the bloat signature the reviewer now flags (B5).
3. Before editing a tier-1/2 doc: `git fetch && git diff origin/dev -- <doc>`;
   if it moved upstream, merge first.
4. One home per FACT (not per noun -- the voice-ai/technical_guide tool docs
   are the worked example of the distinction).
5. Size guidance: at ~500 lines consider splitting on the next substantive
   edit (advisory; m2j14 owns the known monster).
Plus workflow.md "Bead lifecycle": sync worktree to origin/dev at bead start.
Exit: sections exist, convention scan green, no rule stated in two homes.

### B5 = polyglot-pdf-fe3jh (new, P2, independent): reviewer hunt-list upgrades
Agent prompts (review infrastructure -- Opus arm). docs-reviewer.md gains,
each with a worked example AND stated negative space: (a) net-additive edit
to a current-state doc (a genuinely new section is fine; insertion into
existing prose without deletion is the flag); (b) restatement of a rule whose
home is elsewhere (extends class :22 from contradiction to duplication);
(c) an ack whose `because:`/`verified:` content does not plausibly match the
diff (the ack-quality check -- note honestly: this is advisory; the
STRUCTURAL defenses live in B1a/B2). fresh-eyes-reviewer.md mirrors (a)+(b).
Exit: classes present with examples + negative space; a synthetic
net-additive diff draws the flag in a spot-check run.

### B6 = polyglot-pdf-wnso6 (new, P2, after B1c): instruction audit -- verification, not transcription
Grep-driven sweep of .claude/skills/, .claude/agents/, docs/doctrine/,
CLAUDE.md for transcription-shaped instructions -> rewrite to
derive-from-code. Exit: (1) enumeration listed in the commit (grep, not
recall); (2) the allowlist test from B1c extended to pin "no stamp/ack
mechanics instructions outside the sanctioned set".

### B7 = polyglot-pdf-sqexi (new, P2, after B1a+B2): the 21-doc content audit
Sequenced after the ack mechanism EXISTS so "reviewed, accurate" has
somewhere durable to go. One bead, batched by surface (components/ 8,
standards/ 13), sonnet execution; per-doc outcome = fixed or acked-with-
reason; every claim verified against code (verify-claims-against-code
memory). Agent labor, not maintainer labor -- scheduled by default;
maintainer can reprioritize. Exit: corpus stale count <= 2 at completion;
every ack carries a real reason.

## Sequencing

```
B1a (mechanism)          -> B1c (instructions) -> B1b (39 stamp deletions)
                         -> B2  (branch gate)  -> B7 (content audit)
                                               -> B6 (instruction audit)
B1d (format pins)   independent
B3  (set-pins)      independent
B4  (doctrine)      independent   (vjdcn implemented as written, unchanged)
B5  (reviewers)     independent
```

## Success metrics (gate-independent -- a metric the gate can manufacture is
not a metric)
- **Corpus stale count**: 21 today -> <=2 after B7, staying <5 at +4 weeks.
- **Ack:fix ratio** per month: mostly-fixes healthy; ack-heavy is the
  ack-spam tell (this number falsifies the anti-gaming design if it goes
  wrong). Both computable from git by a scheduled check.
- **Conflict recurrence**: m1ulw's hunk-header method re-run at +3 weeks.
- Owner: bd polyglot-pdf-l5rli (the measurement bead, filed with the epic) (runs the three
  numbers, reports to the maintainer; created at epic update, fired ~3 weeks
  after B2 lands).

## Deliberately out of scope
- Journal (tier 3) quality -- per-file append-only design is already right.
- Routes-table generator (m1ulw measures first); contracts split (m2j14
  conditional); hard doc-size caps; any CI-blocking staleness (staleness
  reddens closeout, never CI); no pre-commit hook (the fictional claims get
  deleted; a real hook is a later bead only if closeout-time proves too late).
- Full mechanical duplicate-rule detection (semantic; honest answer is
  set-pins per class + B5's advisory hunt + the saxh rule: when duplication
  is found, enumerate and pin the set).

## Critical files
- scripts/check_doc_freshness.py (+ tests/test_doc_freshness.py -- the home
  suite, extend not fork)
- scripts/closeout_prep.py; .claude/skills/closeout/SKILL.md (Step 2, Step 0
  preconditions, trivial-diff arm :408, push-time rebase :597 -- vjdcn)
- .claude/agents/docs-reviewer.md, fresh-eyes-reviewer.md
- docs/doc-architecture.md; docs/doctrine/workflow.md; CLAUDE.md (pointer)
- backend/config.py (read-only source for B3); deploy-all.sh (read-only
  source for B3)
- Reuse: test_technical_guide_routes_table.py + test_websocket_protocol.py
  as set-pin patterns; test_deploy_form_kit_hints.py as deploy-config-pin
  pattern; the existing --staged plumbing as the --branch template.

## Verification (epic-level)
- Every gate/pin mutation-verified per scar #8, with the ADVERSARIAL-shaped
  mutation (checker-evidence-region memory), files restored by hash.
- B1a end-to-end incl. the squash-collapse case; B2 end-to-end incl. the
  pre-existing-staleness non-block; B1d green on the live corpus.
- The three success metrics computed at +3 weeks by the scheduled bead.

## Execution notes
- Every bead gets its exit criteria (above) written into the bead body at
  creation, per planning.md.
- Each PR through /closeout as usual; B1b timed for a quiet PR window.

---
## Adversarial review round -- what changed (for the maintainer's audit)
The Opus reviewer found 2 BLOCKERS + 5 MAJORS; all integrated:
1. BLOCKER: the commit-ancestry rule + branch-SHA acks are invalid in this
   repo -- dev is squash-merged, so branch commits never join dev's history
   (verified on PR #622's own commits). REDESIGNED: keep the working
   timestamp compare; anchor acks on the ack FILE's git commit time, which
   survives squash and is topology-robust.
2. BLOCKER: B1 was 4-5 PRs in one bead and maximally conflict-prone. SPLIT
   into B1a/B1b/B1c/B1d with the 39-file deletion isolated and sequenced
   last.
3. MAJOR: ack-spam is the cheapest exit under a hard gate (the plan's own
   enforcement corollary). Acks now carry mandatory reason + verified-files
   in reviewable diff; ack-bearing PRs can never take the trivial-diff skip;
   >3 acks/branch redirects to the audit bead.
4. MAJOR: the gate would have blocked sessions on pre-existing staleness
   (any config.py PR inherits 3 stale docs). RESCOPED to newly-caused
   staleness only; the "leave it" carve-out is preserved mechanically;
   whitespace-touch defined away.
5. MAJOR: ack read-path/worktree/clean-tree timing was undefined; defined
   (working tree, committed before finish, $WT, not-gitignored test,
   non-dotted directory).
6. MAJOR: the voice-ai tool list and technical_guide table are NOT
   duplicates (different facts, same nouns) -- the demotion is dropped;
   three-way name-set pin instead.
7. MAJOR: the env-var allowlist was a self-curated pin; completeness now
   derives from deploy-all.sh's BACKEND_ENV (code-owned).
Plus: success metrics made gate-independent (ack:fix ratio catches gaming);
75% is the true stale rate (denominator 28, not 34); the 6 invisible
no-Tracks docs get an explicit fate (B1c); vjdcn is implemented as written,
not amended; "44 stamps" corrected to 39 in the beads being updated.
