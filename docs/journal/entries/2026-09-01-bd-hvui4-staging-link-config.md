---
date: 2026-09-01
bead: polyglot-pdf-hvui4
title: "deploy: staging could not mint links, --set-secrets was never passed -- and nine rounds spent on a guard that kept asking the wrong question"
tags: [deploy, staging, secrets, iam, testing, review-rounds]
---

## Trigger

The maintainer stood up a staging channel and mentioned it in passing. Checking
what it did with the client-link config turned up three gaps, all verified
against the LIVE Cloud Run services rather than inferred from the scripts.

## What was wrong

**1. Staging could not mint links at all.** `deploy-staging.sh` states its own
contract -- *"Backend env MIRRORS deploy-demo.sh exactly. That is the whole
point of a staging channel: a config difference between the two would mean
staging stops predicting demo behavior, and the deploy-only bugs this
environment exists to catch are precisely the config-shaped ones."* It carried
none of the `LINK_*` vars: it was written from a pre-#693 copy. So the channel
could not exercise the one feature the pilot depends on.

**2. `--set-secrets` was documented and never passed.** Two scripts said the
signing key "is injected separately via Secret Manager (--set-secrets)". Grep
across every `deploy-*.sh`: the flag appeared ONLY in those sentences. The
secret existed; nothing bound it; the mint route 503'd.

**3. Live drift.** The demo service carried two hand-applied secret bindings
for a retired gate. `--set-secrets` REPLACES the whole block, so the next
deploy drops them -- flagged in the PR rather than silently changed.

## One dependency, three providers, three rounds

The thing worth remembering. Wiring `--set-secrets` created a runtime
dependency, and I satisfied it one provider at a time, each round fixing
exactly where the reviewer pointed:

1. Passed the flag. Missed that the runtime SA needs
   `roles/secretmanager.secretAccessor`.
2. Granted the role in `setup-gcp-project.sh`. Missed that
   `add-iam-policy-binding` is **not API-gated** -- the script exits 0 while
   `secretmanager.googleapis.com` is off and the deploy still fails.
3. Enabled the API in `setup-gcp-project.sh`. Missed that `deploy-all.sh` keeps
   its OWN enable list -- and THAT is the one that runs on every deploy and
   self-heals, while the bootstrap is a one-time script nobody re-runs.

So the script that actually guarantees the APIs was the one still missing it.
Recorded as `satisfy-a-dependency-in-every-provider`: grep for every site that
PROVIDES that class of thing, and ask which script the operator actually runs,
and how often.

**A reviewer finding can be wrong.** Round 4 claimed the SA lacked the role and
the deploy would fail. It doesn't -- the live IAM policy has it, granted out of
band. The reviewer couldn't check (no `gcloud` in its sandbox) so it reasoned
from the script, which was right about the gap and wrong about the consequence.
I had been treating those findings as authoritative; querying the live system
is what separated them.

## Six defeats of one guard

The test was defeated six times, each by a shape the previous fix did not
anticipate:

| # | The defeat | What I had pinned |
|---|---|---|
| 1 | commented-out line, token alive in the comment | whole-file substring |
| 2 | hard-coded provider list | two files by name |
| 3 | argv slice overran the invocation by ~14 lines | "to the next blank line" |
| 4 | paren-unaware extractor | a lazy regex |
| 5 | renamed the variable in the GUARD | the assignment literal |
| 6 | a second `SECRETS_FLAG=()` after the conditional | membership of lines |

**The through-line: I kept asking "does this text exist?" when the question is
"does this value reach its destination?"** Existence is cheap to check and easy
to satisfy by accident. Defeats 3-6 are all the same error -- containment
versus proximity, membership versus position, presence versus last-write.

Two general fixes came out of it: check LIVE lines (strip comments,
quote-aware, because `deploy-all.sh` has a quoted `#`), and DISCOVER the set
rather than listing it -- a hand-written list is the same bug one level up.

## Three verifications that silently did not run

Worth its own note. Three times a mutation reported something that looked like
a result and was not:

- `\n` anchors against CRLF files: **SKIP**, printed as clean output.
- A heredoc ate an escaped backslash: **SyntaxError**, and 13 tests passed
  immediately after, which said nothing about the check that never ran.
- My own discovery filter excluded any path containing `.claude` -- and this
  repo lives under `.claude/worktrees/`, so it filtered out every file and
  returned nothing. The `>= 2 providers` floor caught it; without that floor
  the test would have passed while checking nothing.

A skip and a pass look alike in a terminal and mean opposite things.

## Left for the maintainer

**bd `polyglot-pdf-3q9qn` -- and it should be decided BEFORE staging deploys
with minting on.** Both channels sign with the same `LINK_TOKEN_SECRET` and
tokens carry no channel or audience claim, so a staging-minted link **verifies
on the demo backend**. `link_redemptions` is keyed by `jti` alone, so a staging
test-drive burns a real link's single redemption. And `record_mint` increments
the same `firms/{id}/link_usage/{YYYY-MM}` counter the per-link pricing bills
against. Now written into `promotion-tiers.md` item 5, which is what someone
reads before deploying staging.

Also open: `nxrds` and `v6sfh` (guard completeness -- the sixth defeat and an
anchor that can fail a correct script), and `136l7`/`q278f` folded in here.
