---
date: 2026-09-02
bead: polyglot-pdf-pidtg
title: "fix(deploy): a deploy that leaves an unreachable service must not exit 0"
tags: [doctrine, testing]
---

## Trigger

The first-ever deploy of `polyglot-backend-staging` (bd `polyglot-pdf-9qn64`)
reported SUCCESS and produced a service that 403'd every request.

`deploy-all.sh` passes `--allow-unauthenticated`, which REQUESTS the `allUsers`
invoker binding. The domain-restricted-sharing org policy
(`constraints/iam.allowedPolicyMemberDomains`, inherited, allowing only customer
id `C03we4ddv`) REFUSED it. gcloud created the service anyway, printed a
non-fatal warning, and exited 0.

Measured at the time:

```
polyglot-backend          roles/run.invoker = ['allUsers']   -> /health 200
polyglot-backend-staging  (no bindings at all)               -> /health 403
```

The 403 comes from Cloud Run's own gate, BEFORE any application code runs, so
FastAPI never sees the request. In the browser it surfaced as the app's
*"Not authorized to load form kits (sign in again?)"* -- an auth message with
nothing to do with Firebase auth, which sent the maintainer to debug the wrong
layer entirely. Roughly an hour went into checking Firebase tokens, the runtime
service account's roles, env parity and secret access before the Cloud Run log
line `The request was not authorized to invoke this service` identified the
actual layer.

**Why it had never been seen:** an EXISTING service's binding predates the policy
and is not retroactively stripped. The demo has been coasting on a permission it
could no longer be granted today. The failure is therefore invisible until
someone stands up a NEW service -- exactly the moment they are least equipped to
tell a config bug from a code bug.

## This is scar #7 one layer out

CLAUDE.md scar #7: a mock cannot tell you the real dependency is FORBIDDEN --
check the IAM envelope. That scar is about the RUNTIME SA lacking a permission it
needs. This is the same shape applied to the SERVICE'S OWN INGRESS: we asked for
an IAM grant, were refused, and reported success. Neither the test suite nor the
deploy output could have caught it, because the deploy genuinely succeeded --
the service simply was not reachable.

## What shipped

A reachability gate in `deploy-all.sh`, immediately after `gcloud run deploy`:

- Reads the service's IAM policy and looks for an `allUsers` invoker binding.
- **Missing binding -> `exit 1`**, with the exact `add-iam-policy-binding`
  remedy and a note that the org policy may need relaxing first. A deploy that
  leaves an unreachable service must not exit 0.
- **IAM read itself fails** (no permission, transient API error) -> **WARN and
  continue.** Being unable to check is not proof the service is broken, and a
  gate that cries wolf gets disabled -- taking the real check with it.

**Why the binding and not `curl /health`.** A health probe conflates this bug
with ordinary startup failures and adds cold-start latency to every deploy. That
distinction is not hypothetical: the morning after this bug, the DEMO went down
with 500s from containers failing their startup probes -- a completely unrelated
platform-level issue that a health-probe gate would have blamed on the deploy.
The binding is the exact thing that silently fails here, and reading it is fast
and deterministic.

## The review caught a FALSE PASS in the first version of this gate

The first cut grepped the raw IAM policy text for the bare string `allUsers`.
The pre-PR review showed that a policy like

```
roles/run.viewer   -> allUsers
roles/run.invoker  -> serviceAccount:...
```

**satisfies that check while the service is still completely un-invokable** --
the exact bug the gate exists to catch, passing cleanly. My own mutation testing
missed it because every mutation I tried was in the *fail-closed* direction
(remove the gate, downgrade it, break the branch); I never tried a mutation that
made it fail OPEN.

That is the worse direction. A gate that fails open does not merely miss the bug
-- it reports a GREEN check over it, which is more misleading than having no gate
at all, and this whole bead exists because a green signal over a broken service
cost an hour of debugging.

The fix asks gcloud to do the pairing rather than doing it in text: filter to
bindings whose MEMBERS include `allUsers`, return their ROLES, and require
`roles/run.invoker` with an EXACT line match (`grep -qx`, so a lookalike role
like `roles/run.invoker.custom` cannot satisfy it either). stderr is no longer
merged into the captured value, so gcloud nags cannot satisfy a text match on
their own.

## ...and then the fix had the OPPOSITE bug

The outer cross-surface review caught that adding `--filter` **without**
`--flatten` introduced a FALSE FAIL. `--filter` on `get-iam-policy` is evaluated
against the whole policy resource, not per binding, and `value(bindings.role)`
emits every role `;`-joined on ONE line:

```
roles/run.invoker;roles/run.admin        <- one line, so grep -qx never matches
```

So the gate would have refused to deploy the moment a service had a SECOND
binding -- an operator's `roles/run.admin`, a service-to-service invoker, a
Cloud Scheduler SA. Both live services happen to carry exactly one binding
today, so it passed every check I ran and would have surfaced later, blocking a
perfectly reachable demo deploy at the worst possible moment.

`--flatten='bindings[].members'` makes each member/role pair its own record, so
the filter really is per-binding and each surviving role prints on its own line.
Verified in both directions against gcloud's real output.

**The lesson across the two rounds:** I wrote a check with a false PASS, fixed it
into a check with a false FAIL, and needed two independent reviewers to land on
one that is correct in both directions. Both failure modes are bad for different
reasons -- failing open hides the bug behind a green check; failing closed blocks
good deploys, and a gate that cries wolf gets deleted, taking the real check with
it. A guard is not done when it catches the bug; it is done when it *only*
catches the bug.

## And the test that pinned the bug

Removing `--flatten` from the query left all 30 tests GREEN, because the
assertion looked for the flag anywhere in `deploy-all.sh` -- and the comment
block above the query names every flag it uses. The prose satisfied the test.

Fixed by extracting a `_reachability_query()` helper that returns only the
gcloud invocation, and asserting the flags against THAT. Re-running the same
mutation now reddens 2 tests. (Repo scar tissue, stated almost exactly: *a
checker that infers a claim from text must scope the evidence region to exactly
the claim* -- widening it turns nearby prose into evidence.)

## Testing

Six tests in `test_deploy_channel_isolation.py`, each mutation-verified against
the mutation that matters (scar #9):

| mutation | caught |
|---|---|
| remove the gate entirely (the original bug) | yes (3 tests) |
| downgrade the fatal branch to a warning | yes |
| make the inconclusive branch fatal too (false-alarm regression) | yes |
| check `run.invoker` instead of `allUsers` | yes (2 tests) |
| **revert to the loose `allUsers` text grep (the false pass)** | **yes (3 tests)** |
| loosen `grep -qx` to a substring match (lookalike role) | yes (2 tests) |
| re-merge stderr into the captured value | yes |
| **remove `--flatten` from the query (the false fail)** | **yes (2 tests)** -- but only AFTER the assertion was scoped to the query; it was green before |

The tests pin the fatality, the warn/fail split, and the role-specificity as
PROPERTIES, not merely the presence of a check.

Also verified against the live services before shipping: the gate PASSES on both
`polyglot-backend` and `polyglot-backend-staging` as they exist today, so it is
not a false alarm that would block every future deploy.

Full backend suite: 3096 passed, 76 skipped, exit 0.

## Status of the underlying policy

DRS was **disabled** for `polyglot-demo-aa709` on 2026-09-01 (maintainer's call,
after the tradeoff was laid out: it removes the guardrail that would block an
accidental public binding anywhere in the project, in exchange for staging being
able to serve the voice path at all -- the Hosting-rewrite-only alternative
cannot carry WebSockets). So the specific refusal that caused this should no
longer occur.

The gate stays regardless: the policy can be re-enabled, other causes of a
missing binding exist, and the failure mode it prevents -- a green deploy of an
unreachable service -- is expensive to diagnose from the symptom.
