---
date: 2026-09-02
bead: polyglot-pdf-816te
title: "sweep: the nine deploy follow-ups left by the staging-channel reviews"
tags: [doctrine, testing]
---

## Trigger

The staging-channel work (`9qn64`, `pidtg`, `6oi9s`) generated nine follow-up
beads across its review rounds. The maintainer batched them and deferred
`q64tv` (the schema-editor backend split) as real debt that does not move
toward pilot-ready.

Closed here: `816te`, `7aez9`, `yz244`, `cq0at`, `xsp5b`, `20940`, `py7nc`,
`l7afe`, `t7drr`.

## The one real bug: 816te

`deploy-all.sh --frontend` resolved the backend's Cloud Run URL and baked it
into `VITE_WS_URL` with no reachability check, because `pidtg`'s gate sits
inside the BACKEND stage. **`gcloud run services describe` returns a URL for a
service that EXISTS whether or not anyone may invoke it** -- existence and
reachability are independent -- so a frontend-only deploy could publish against a
403ing backend and report success. Both channel wrappers run the frontend as a
separate `deploy-all.sh --frontend` process, which the code's own comment calls
"the usual path".

Fixed by calling the same gate from the frontend stage. **It WARNS there rather
than aborting**, and the asymmetry is deliberate: in the backend stage the deploy
just created the service, so an unreachable one is that run's own doing; in the
frontend stage the backend is pre-existing, possibly mid-fix by someone else or
deliberately private, and refusing to ship a frontend over someone else's IAM
state is the gate crying wolf.

That required a severity switch, `VERIFY_FAIL_IS_FATAL`, which **defaults to
fatal**. Leniency has to be opted into, never inherited by forgetting a flag --
otherwise the backend stage's abort could be silently downgraded.

## t7drr had mostly solved itself

Filed as "three shared-state surfaces have no channel marker", with all three
inert at the time. Two were closed since by bd `3q9qn`, which shipped
`LINK_CHANNEL`: every link token now carries an `aud` claim naming the channel
that may open it, and each channel keeps its own redemption ledger. Checking
before writing was the whole job here -- the bead's own description was stale.

The genuinely open item was its exit criterion 1 for surface 3, the form-kit
editing lock, which is shared and **correct that way**: the lock is uid-scoped
and preemption IS the stale-lock release, so two backends contending behave
exactly as two editors on one backend already do. Making it per-channel would
let one person hold two locks on the same kit and edit from both -- worse than
the contention it removes. Recorded in `promotion-tiers.md` as a decision rather
than left as an open question.

## yz244: my own defeatable guard

The dead-prod doc check I wrote during `9qn64` banned three literal phrasings and
then, as a catch-all, searched the WHOLE FILE for a death word. Both halves were
weak: a blacklist is one synonym from defeat, and the file-wide fallback was
satisfied permanently by unrelated prose -- README.md's existing "Production site
(inactive)" hundreds of lines away. The reviewer rewrote the death paragraph into
"To deploy production, run ./deploy-production.sh" and every test stayed green.

Replaced with a PROPERTY per mention, scoped to the mention's own line plus two
either side. Repo scar tissue almost verbatim: *a checker that infers a claim
from text must scope the evidence region to exactly the claim.*

Two things fell out of the stricter check immediately:

- It **found a real gap on its first run** -- a `config-deployment.md` mention
  outside any death-marked neighbourhood.
- That turned out to be the doc's `**Tracks:**` header, a FILE LIST rather than
  prose offering a deploy path. Demanding a death marker inside a filename list
  is a false positive, so it is exempted explicitly. Worth noting the stricter
  check earned its keep in both directions on day one.

## The rest

- **7aez9** -- neither channel wrapper had a `*)` arm, so `--front-end` matched
  nothing, every `DEPLOY_*` stayed false, and the script deployed NOTHING while
  printing its success banner and exiting 0. On staging that is exactly the false
  confidence the tier exists to remove. Now fatal, matching `deploy-all.sh`.
- **xsp5b** -- `.firebaserc`'s `default`/`prod` aliases named the dead project.
  **Removed rather than repointed:** pointing `default` at the demo would make a
  bare `firebase deploy` hit the live investor site, which is worse than failing.
  Verified first that no executable path relies on the alias -- every scripted
  `firebase` call passes `--project`.
- **20940** -- the form-kit hint named one Cloud Run service; there are two.
  Now names both, pinned as a SET so a third fails CI.
- **cq0at** -- `subprocess.run(..., text=True)` without `encoding=` decodes the
  child with the LOCALE codec, so Windows cp1252 raises `UnicodeDecodeError` the
  moment a deploy script prints an emoji. Fixed in the two shell harnesses.
- **py7nc / l7afe** -- comment-only. The usage header omitted an argument the
  script reads; the byte-identical gate block referred to `backend/deploy-new.sh`
  by name from inside that file, so it told the reader to match itself. Reworded
  symmetrically, since byte-identity means any file-specific reference reads
  correctly in exactly one copy.

## A guard I had to widen, carefully

The frontend call is `VERIFY_FAIL_IS_FATAL=false verify_service_publicly_reachable
...`, and `test_gate_is_called_as_a_bare_command` rejected it -- correctly, by its
own rules. Rather than loosen it, I **verified in a shell** that an env-var prefix
does not create a subshell and `exit` still propagates, then narrowed the guard to
allow exactly that shape. Confirmed it still rejects pipes, command substitution,
`&&`/`||` guards, backgrounding, and an env prefix COMBINED with a pipe.

## What the review caught in my own fixes

Three findings, all in work done for THIS sweep:

- **The `**Tracks:**` exemption was itself smugglable.** I exempted lines
  starting with that marker so a filename list would not need a death marker --
  but a bare `startswith` waves through
  `**Tracks:** Run ./deploy-production.sh to go live.`, which is the same class
  of evasion the blacklist had. Now every token after the marker must LOOK LIKE
  A PATH (contain a `/` or an extension), which prose words never do. My first
  attempt at tightening was too strict (it rejected `Dockerfile`,
  `.gcloudignore`, `.firebaserc`) and my second too loose (it re-accepted the
  smuggled line, because `Run`/`to`/`go` are made of path characters). The
  third is checked against all four shapes.
- **`t7drr` exit criterion 1 names `LINK_TOKEN_SECRET` explicitly**, and I had
  documented the other two surfaces without it. Now recorded: both channels
  deliberately bind the SAME secret, because the signing key is not what
  separates them -- the `aud` claim is, checked on every redemption. Per-channel
  keys would add nothing and create a real failure mode, since rotating one
  would silently invalidate the other's links.
- **Warn mode was pinned only by TEXT.** The tests asserted the flag string
  appeared in the frontend stage, which would still pass if the branches inside
  the function were swapped. This file already has an execution harness, so
  there was no excuse: warn mode is now EXECUTED, and deleting its early
  `return 0` reddens it (verified).

## The outer review: an env var cannot express "just this call"

Two more, both in this sweep's own work:

- **`.firebaserc`'s alias removal falsified a doc I never touched.**
  `config-deployment.md` said the dead project was "(still the `.firebaserc`
  `default`/`prod` alias)" -- true on `dev`, false the moment `xsp5b` deleted
  them. A tier-2 current-state doc, broken by a change in a different file. The
  lesson is not "update the doc" but that a `Tracks:` list is a hint about which
  docs a change can falsify, and I did not consult it.
- **`VERIFY_FAIL_IS_FATAL` was the wrong mechanism.** An env var cannot
  distinguish "the frontend stage set this for one call" from "it was ambient in
  the operator's shell", so an exported `VERIFY_FAIL_IS_FATAL=false` silently
  disarmed the BACKEND stage's abort -- on the one path where an unreachable
  service is definitely that run's own doing. Reproduced, then fixed by making
  severity a positional ARGUMENT (`$4`, default `fatal`), which only a real call
  site can pass. `test_ambient_env_cannot_disarm_the_fatal_default` exports the
  old variable and asserts the abort still fires.

The second is the more interesting error: I reached for the cheapest way to add
a per-call option and picked one whose scope was wrong. A flag that can arrive
from anywhere is not a per-call flag.

## And the same no-op join, a third time

Round two of the outer review noted the argument form created an opportunity the
fix had not taken: nothing pinned that the BACKEND call omits `warn`. Appending
it there silently downgrades the abort, and the suite stayed green.

Writing that guard, I hit the identical `
`-vs-backslash-newline no-op AGAIN --
a heredoc collapsed the escape, the join matched nothing, and the test failed
with a nonsense message. Third occurrence of one bug in this bead's lineage. The
line is now written as an explicit concatenation with a comment naming the trap,
which is the only form that survives being pasted through a shell.

The lesson generalises past this bug: when a test transforms text before
asserting on it, the transformation is code that can be silently wrong, and a
test whose *setup* is broken fails in ways that look like the subject is broken.

## Testing

Full suite: 4431 passed, 126 skipped, exit 0. Three behavioural mutations, each confirmed to apply before
being trusted: removing the frontend gate call, removing the unknown-arg arm, and
reverting the hint to one service. One mutation silently no-op'd on an escaping
failure and was redone from a file -- the count assertion caught it, which is why
every mutation script here asserts before writing.
