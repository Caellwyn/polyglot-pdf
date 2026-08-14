---
tags: [cost, legal-posture, docs, recovery, si-reduction, scar-tissue]
beads: [polyglot-pdf-77j0d, polyglot-pdf-rtyia]
surfaces: [docs/standards, CLAUDE.md, backend/config]
---

# Two tier-1 invariants: one obsolete and being quoted, one nowhere and violable

Both beads are about the same failure class from opposite directions. An
invariant that lives in tier-1 gets read into EVERY session, so a wrong one
is not inert -- agents quote it back as current and plan against it. An
invariant that lives nowhere authoritative can be silently violated by
someone who never had reason to look.

## bd 77j0d -- recovering a measurement without inheriting its errors

The maintainer's report was blunt: *"'text is a greater cost than audio' ...
I keep getting quoted by agents, but which is obsolete."*

The bead's instruction was RECOVER, do not re-measure -- bd 89mt had
measured this properly and expensively, and the doc correction was stranded
on an abandoned local branch when the maintainer declined the spike
artifacts. Cherry-pick the three doc hunks from commit `7b35c227`.

Doing exactly that would have shipped numbers the author had already
retracted.

### Two layers of staleness, neither in the bead

**First:** a LATER commit on the same abandoned branch (`5888cda7`, "carry
the unshipped-SI caveat into the standards docs") corrected the one the
bead named. Its own fresh-eyes review had caught that the 56%/66% audio-in
split was measured on a SLIMMED system instruction that was not shipped;
re-weighted for the deployed SI, audio-in was nearer ~49%. The bead cited
only the first commit. Applying it alone would have landed a figure its
author already knew was wrong.

**Second, and the reason this needed more than careful cherry-picking:**
that caveat is ITSELF now stale. It assumed the deployed SI was ~4,388 tok
pending bd `6a79`. But 6a79 SHIPPED (PR #565, 2026-08-08), after the branch
was abandoned. Measuring `Settings().DTI_SYSTEM_INSTRUCTION` today gives
**~3,363 tok** -- neither the ~2,485 the split was measured on, nor the
~4,388 the caveat assumed. The SI was cut, then grew back partway.

So there was no version of the recovered text that was correct: the
original figures assumed a smaller SI than ships, the caveat assumed a
larger one. The numbers had to be re-weighted against a value MEASURED FROM
TODAY'S CODE rather than copied from either.

The general lesson, and it generalizes past this bead: **a recovered commit
is a claim about the world at the time it was written, and the world
includes commits that came after it -- including later commits on the same
abandoned branch.** The bead's own warning ("treat the recovered prose as
stale-by-default") was right and still understated it, because it framed
staleness as prose drift against `dev`. The real drift was that a
DEPENDENCY of the numbers had shipped in the interim.

This is also why the doc now states the ORDERING as the durable finding and
the percentages as approximate, names the configuration they hold on, and
says what would invalidate them. A number with no provenance invites
exactly this: silent re-quoting long after its premise moved.

### The set was twice what the bead named

The bead named three files. A grep found **six** live sites:

- `CLAUDE.md`, `logging-and-cost.md`, `si-reduction.md` -- the three named.
- `schema-key-visibility.md` -- a comparison table asserting "per-turn
  text-in = **95-98% of session cost**" as current fact.
- `sprint_20_sol-intro-tts_plan.md` -- an ACTIVE plan using the stale claim
  to argue AGAINST a cost justification ("Not a cost saving ... audio is
  negligible"). Now doubly wrong: audio leads, so moving speech off the
  Live model onto deterministic TTS is plausibly a cost WIN. Flagged rather
  than re-argued, and pointed at bd `n1y9h`, which owns re-checking that
  exact premise.
- `secretary-agent-research-plan.md` -- cites `logging-and-cost.md` as
  current justification, so a reader following the pointer would hit a
  contradiction. Annotated, argument left intact.

`docs/archive/sliding-window-go-no-go-brief.md` was deliberately left: it
is explicitly a point-in-time record ("What we now know (measured)"), and
rewriting it would destroy the historical account rather than correct it.
That line -- annotate a doc that POINTS at current state, leave one that
RECORDS a past decision -- is the useful distinction.

### The docs were only half the fix: a bd MEMORY still asserted the old number

The reported symptom was *"I keep getting quoted"* by agents. Correcting the
docs does not fix that on its own, because `bd remember` memories are loaded
into EVERY session's context the same way tier-1 docs are -- and
`cost-invariant-moved-audio-now-dominates` still asserted the raw 56%/66%
split, the pre-caveat figures measured on the unshipped slim SI.

Fixing six markdown files while leaving that memory in place would have
shipped a PR that looked complete and left the actual complaint intact,
because the wrong number would still have been in every agent's context
window at turn zero.

Updated in place, with the SI-size dependency stated explicitly so the next
reader can tell whether it still holds. Also annotated a SECOND memory,
`sliding-window-shelved-pivot-to-si-diet`, which reasons from the same
obsolete premise -- and which is doubly stale, since compression was
un-shelved and now ships by default. That one is a dated DECISION RECORD, so
it keeps its original text and gains a superseded-by note rather than being
rewritten; same distinction applied to `docs/archive/`.

**The transferable lesson: "where does this claim live?" is a bigger question
than "which docs mention it."** For a claim that agents quote, the set
includes bd memories and bead bodies, not just markdown -- and memories are
the highest-leverage members of that set, since they load unconditionally.

## bd rtyia -- an invariant with real consequences, recorded only in a prompt

The app produces a DRAFT, is never used for self-filing, and depends on an
outside qualified human reviewing before filing. Before this, that lived in
`backend/config.py`'s prompt text, a test docstring, and tier-3 journal
entries. Nothing authoritative.

It is not a nicety -- shipped behavior rests on it. The hedge-and-defer
answer policy (bd `rdsl`) closes by deferring to "the firm or professional
reviewing their form." **Opened to self-filers, demoed to a prospect with
no reviewing staff, or sold direct-to-consumer, that deferral points at a
person who does not exist -- in every supported language -- and a careful
hedge becomes a dead end.** Nothing in the codebase would object, and the
person making that business call has no reason to grep prompt strings.

### The register distinction is the thing most likely to get re-broken

Internally, review is REQUIRED (contracts). To the applicant, review is
ADVISED, never guaranteed. Those are different statements on purpose.

Verified against shipped text rather than the bead's description:
`DisclaimerModal.tsx` says *"We strongly advise you to have a qualified
professional check your final form before you submit it"*, and the SI
already carries *"Do not promise the user that a review WILL happen -- the
disclaimer they accepted advises it rather than guaranteeing it."*

The bead flags this because it has already been broken once: in rdsl the SI
wrongly PROMISED review ("Every form drafted here is reviewed...") where the
disclaimer only advises it. That survived the author, the tests, and two
review rounds -- caught only because one reviewer happened to open the
disclaimer and read it beside the prompt. A stated invariant makes the next
"tightening" wrong on its face instead of dependent on someone noticing.

### The legal invariant had THREE registers, and my first test pinned the wrong clause

Writing rtyia's doc required reading what actually ships, and the shipped
surfaces disagree more than the bead described.

There are **three** registers, not two: contracts REQUIRE review; the spoken
`intro_script.json` has the applicant UNDERTAKE it ("you agree to review the
completed document ... with a certified professional"); `DisclaimerModal.tsx`
merely ADVISES it. Three speech acts by three parties -- *we advise*, *they
agree*, *contracts require* -- and the SI deliberately sits at the weakest,
which is correct and must stay, since the model cannot know whether a review
actually happened.

Two self-inflicted errors along the way, both worth recording:

**The doc overclaimed.** I wrote that the undertaking lives in the spoken
script "and the modal that renders the same paragraphs." It does not:
`DisclaimerModal.tsx` has zero occurrences of "agree to review", and no
frontend component reads those paragraphs at all -- the one-source wiring is
unshipped (bd `s1iex.5`). `intro_script.json` and `intro_tts.py` BOTH assert a
HARD INVARIANT that the modal renders exactly those paragraphs, and that
invariant is simply false today. I had documented the intended end state as
current -- exactly the failure the current-state-only rule exists to prevent,
committed in the doc written to prevent it.

**The test pinned the wrong clause.** The undertaking paragraph is two
clauses: agree-to-review, and absolve-the-brand. My structural proxy (one
paragraph carrying both the agree-placeholder and the brand, over 80 chars) is
satisfied by the RELEASE alone. Proved it: keeping both markers, keeping the
release, staying 235 chars, and dropping only the review undertaking left the
suite fully green -- while the docstring claimed the undertaking was pinned.

The reason my first mutation missed it is the transferable part: **I mutated
toward an obviously-broken value (a short stub) rather than the plausible one
a translation sweep would actually produce.** A mutation that is too crude
tests the guard you wrote, not the failure you fear. The fix is an
English-anchored assertion -- English is the source language and untranslated,
so the clause is assertable verbatim -- and the exact mutation that defeated
v1 now reddens that test alone.

**A third correction, and the one that inverted the claim.** I then wrote that
which register an applicant accepted depends on whether they LISTENED or READ.
The outer review traced the spoken path and showed that is also wrong -- in the
opposite direction from my first error.

The intro clip has no frontend player at all (bd `s1iex.5` is open; `grep -rn
"tts/intro" frontend/src` returns nothing) and `INTRO_TTS_ENABLED` defaults
false, so the route 503s. What the Live model actually reads aloud is
`DISCLAIMER_TRANSLATIONS[lang].fullText` -- **the modal's own advisory text** --
via `readDisclaimer` and the `read_disclaimer` WS message. So both user-facing
surfaces are advisory and IDENTICAL today. There is no live undertaking
register, and no listened-vs-read split.

I had made the same class of error twice in one section: describing a STAGED
surface as shipped. The first time I said the modal renders the spoken
paragraphs (it does not); the second time I said the spoken clip carries a
stronger register (it is not wired). Both came from reading `intro_script.json`
and `intro_tts.py`, which each assert a HARD INVARIANT that "the modal renders
exactly these paragraphs -- one source, no separate fullText" -- **an invariant
that describes the intended end state and is simply not true today.** Trusting
a file's own stated invariant is exactly the move that
[[verify-claims-against-code-not-brief]] warns against; the producing file is a
brief like any other.

The section now carries an explicit STATUS column (live / staged), so the
distinction cannot be lost again, and states that shipping `s1iex.5` is what
would CREATE the register split -- which is precisely why bd `nsb4y` (settling
whether the modal adopts the undertaking) should be decided BEFORE the player
ships, not after. That is a legal/product call, and `intro_script.json` notes a
counsel pass is still pending.

## Process notes

- The `config.py` change is a COMMENT only. Verified
  `DTI_SYSTEM_INSTRUCTION` is byte-identical at 13,451 chars, so there is
  no prompt change and no cost impact -- worth checking explicitly on a
  file where an accidental string edit would silently alter every session's
  behavior and bill.
- Confirms bd `teizj` (filed round 8) is real: `schema-key-visibility.md`
  has no `Tracks:` line, so the freshness gate skips it entirely -- which
  is part of why a stale current-state claim survived there.
- Two bd memories corrected and pushed to dolt (so the fix reaches web and
  cloud sessions, which never see this worktree).
- The fresh-eyes review caught me introducing `Prior:`/`Earlier:` stamp
  chains, which `doc-architecture.md` bans by PATTERN while
  `check_doc_freshness.py` only greps the literal `Previously:` -- so all
  three of my edits passed the checker while violating the rule. I inherited
  the shape from the recovered commit without checking it against doctrine.
  Collapsed; bd `polyglot-pdf-cqyke` owns the sweep of the two pre-existing
  offenders plus broadening the regex so the rule stops depending on authors
  remembering it.
- Backend + scripts: 3330 passed, 3 skipped (exit 0) -- the +18 are the new
  per-language undertaking cases.
- Two outer-review passes died to a transport stall (no verdict returned).
  Per doctrine that is never read as clean; both were re-run rather than
  assumed. The second stall correctly flagged an uncommitted tree -- I had
  been editing while a review was in flight, which is my process error, not
  the reviewer's.
