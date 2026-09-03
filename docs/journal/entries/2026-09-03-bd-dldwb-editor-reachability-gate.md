---
date: 2026-09-03
bead: polyglot-pdf-dldwb
title: "fix(deploy): the editor deploy had the same blind spot -- third instance of one bug"
tags: [doctrine, testing]
---

## Trigger

`deploy-editor.sh` resolved the hosted editor's backend with
`gcloud run services describe --format 'value(status.url)'` and injected it as
`VITE_API_BASE_URL`, with no reachability check. Same blind spot bd
`polyglot-pdf-816te` closed in `deploy-all.sh`'s frontend stage: **`describe`
answers for a service that EXISTS, whether or not anyone may invoke it.**

It matters more here than the name suggests. `remoteKitStore.ts` treats
`VITE_API_BASE_URL` as THE hosted contract, so every editor action -- kit list,
draft save, publish, the editing lock -- goes through that URL. A contractor
hitting 403s sees what looks like an access-code failure and reports an auth
problem, sending the operator to debug the wrong layer. That is the same wild
goose chase bd `emm7` and bd `pidtg` were both filed for.

## Why it escaped twice

The guard added for `816te` keys on `--allow-unauthenticated`, i.e. "who DEPLOYS
a public Cloud Run service". That is the right set for the abort-on-create gate,
and it correctly excludes `deploy-editor.sh`, which deploys only Hosting.

But it is the wrong set for THIS failure. The set that matters is "who resolves a
backend URL and bakes it into a frontend build" -- and it has two members,
`deploy-all.sh` and `deploy-editor.sh`. One set was pinned; the other did not
exist. Third instance of one bug in three scripts (scar #8), and the guard I
wrote for the second instance is what let the third through.

Both sets are now derived mechanically and pinned separately:

- `GATED_DEPLOY_SCRIPTS` -- passes `--allow-unauthenticated` (2 members).
- `URL_BAKING_SCRIPTS` -- calls `services describe` AND exports a `VITE_*`
  (2 members). `backend/deploy-new.sh` resolves a URL but exports no `VITE_*`,
  so it is correctly absent: it deploys a service, it does not build a frontend.

## Two of my own guards misfired, in opposite directions

**A false POSITIVE, immediately.** Adding the gate to `deploy-editor.sh` broke
`test_allow_unauthenticated_set_is_complete` -- because the gate's own comment
block and error text both contain the string `--allow-unauthenticated`, and the
detector was a whole-file substring search. It declared a Hosting-only script a
public-deploy script. Scoped to non-comment, non-message lines; verified a REAL
invocation is still caught.

**A false NEGATIVE, found by mutation.** My first assertion was
`"verify_service_publicly_reachable" in body`, which matches the function
DEFINITION. Deleting the editor's gate CALL left all 30 tests green. Now it joins
line continuations and requires a line that actually invokes the function.

Both are the same underlying error in mirror image: **the evidence I checked was
not the claim I meant.** Once too wide (any mention of a flag), once too narrow
in the wrong dimension (presence rather than use).

## What shipped

`deploy-editor.sh` carries a byte-identical copy of
`verify_service_publicly_reachable` -- now three copies, all pinned identical --
and calls it in WARN mode after resolving the URL. Warn, not abort, for the same
reason as `deploy-all.sh`'s frontend stage: that backend is PRE-EXISTING and
possibly mid-fix by someone else, whereas the backend stage aborts because the
deploy had just created the service itself.

## The escaping bug reached SHIPPED CODE this time

The review found the gate call I had just added was corrupted:

```
verify_service_publicly_reachable 
            "$BACKEND..."
```

`
` is two literal characters, not a line continuation. So bash bound
`svc="n"`, `region=$BACKEND_SERVICE_NAME`, `project=$REGION`,
`severity=$PROJECT`. The gate queried a service named `n`, that query failed, and
the `__QUERY_FAILED__` fallback warned-and-skipped. **A gate that could never
fire, with every test green.**

Fourth occurrence of this escaping bug in this arc, and the first to reach
shipped code rather than a test. The cause each time is the same: writing shell
through a heredoc, where `\
` collapses.

**And my test passed over it.** The assertion checked the function name appeared
on a non-comment, non-definition line -- which a corrupted call satisfies
perfectly. Presence had already proved too little once here (it first matched the
DEFINITION); this was the same lesson one level deeper.

The fix is to stop asserting on text: the test now EXECUTES each call site
against a probe function that reports its arguments, and asserts they bind to the
script's own service/region/project variables. Re-applying the exact corruption
now reddens it. Only running the shell can tell a working call from a
well-spelled one.

## A filter wide enough to hide a false positive hid a true one

Adding the gate to `deploy-editor.sh` tripped
`test_allow_unauthenticated_set_is_complete`, because the gate's own comment and
error text contain `--allow-unauthenticated` and the detector was a whole-file
substring search. My first fix excluded any line containing `echo` -- which also
excludes `gcloud run deploy ... --allow-unauthenticated || { echo fail; }`, a
genuine public deploy. Removed: the comment and `_gate_error` filters already
cover the real false positive, and verified a real invocation with `echo` on the
line is now caught.

## Testing

Full suite: 4464 passed, 126 skipped, exit 0. Three mutations, each confirmed applied: a new ungated
URL-baking script (caught by the new set test), a new real public-deploy script
(caught by the re-scoped old one, proving the narrowing did not weaken it), and
removing the editor's gate call (caught only after the presence-vs-call fix).
