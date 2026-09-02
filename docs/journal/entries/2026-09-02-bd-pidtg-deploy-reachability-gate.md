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

## Testing

Three tests in `test_deploy_channel_isolation.py`, each mutation-verified
against the mutation that matters (scar #9):

| mutation | caught by |
|---|---|
| remove the gate entirely (the original bug) | all 3 |
| downgrade the fatal branch to a warning | fatality test |
| make the inconclusive branch fatal too (false-alarm regression) | warn test |
| check `run.invoker` instead of `allUsers` (defeats the real check) | 2 of 3 |

The tests pin the fatality and the warn/fail split as PROPERTIES, not merely the
presence of a check -- a check that only warned would have let the original bug
through unchanged.

Also verified against the live services before shipping: the gate PASSES on both
`polyglot-backend` and `polyglot-backend-staging` as they exist today, so it is
not a false alarm that would block every future deploy.

Full backend suite: 3094 passed, 76 skipped, exit 0.

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
