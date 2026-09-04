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

## The outer review: presence, then binding, then SEVERITY

Fixing the corrupted call made the test assert that arguments BIND. The outer
review showed that still was not enough: dropping the trailing `warn` left every
test green while flipping the editor's gate from WARN to FATAL. With
`severity="${4:-fatal}"`, a 3-arg call aborts -- and under `set -e` that blocks
EVERY editor deploy over a pre-existing backend's IAM state, the exact
"gate crying wolf" outcome warn mode exists to prevent.

Three rounds on one assertion, each a strictly larger claim:

1. the function NAME appears -> matched the definition;
2. a CALL exists -> matched a corrupted call;
3. the arguments BIND -> missed the severity;
4. and now the severity COUNT per script.

My first severity map was itself wrong -- it asserted `warn` for every call in
`deploy-all.sh`, which reddened on the backend stage's correctly-fatal call. The
map is now `{script: (n_warn, n_fatal)}`, because `deploy-all.sh` legitimately has
one of each and a single expected value cannot express that.

Also pinned: the editor's call must be a BARE command. The sibling subshell guard
is parametrized on `GATED_DEPLOY_SCRIPTS`, so `deploy-editor.sh` escaped it
entirely -- latent while severity is `warn`, live the moment it is not.

## A doc falsified by a file the diff never opened

`config-deployment.md` said "the two copies are pinned identical" and described
one completeness set. There are now three copies and two sets. Its reassurance
that "a third such script cannot ship ungated" was precisely the belief that let
`deploy-editor.sh` through, so it now spells out both sets in a table, why each
script is absent from the one it is absent from, and that severity differs by
call site.

Second time in two PRs that a change falsified a tier-2 doc in a file the diff
did not touch. The `Tracks:` line is the signal for this and I did not consult it
either time.

## A doc sentence that was false, and the hole behind it

Round two caught that my new sentence "the counts are pinned per script" was
false for `backend/deploy-new.sh`: appending `warn` to its call downgraded the
abort with every test green.

The tempting fix was to soften the sentence. The right one was to make it true --
because that script is the WORST place to lose the abort. Its entire job is
standing up a NEW service, and the refused-binding bug fires only on new
services. It was the highest-value of the three call sites and the only
unguarded one.

`test_service_creating_script_takes_the_fatal_default` now covers every script in
`GATED_DEPLOY_SCRIPTS` -- i.e. exactly those that create a public service -- so a
fourth inherits the pin automatically. Mutation-verified against the mutation
that was green before.

Worth noting the reviewer classed this as pre-existing (it reproduces on `dev`)
and filed it rather than blocking. That was the correct call on its own terms;
fixing it here was still right, because leaving it open would have left this
PR's own doc sentence lying.

## "At least one" was not what the sentence promised

Round three caught that my fix asserted a LOWER BOUND (at least one fatal call)
while the doc said "counts" -- exact. The reviewer defeated the lower bound with
an opt-in-strict shape:

```sh
if [ "$STRICT" = "1" ]; then verify_... "$S" "$R" "$P"
else                         verify_... "$S" "$R" "$P" warn; fi
```

The DEFAULT path warns, a decoy fatal call satisfies "at least one", suite green.
Only reachable once a script gains a second call site -- but the sentence claimed
a property the test did not hold, which is the same over-claim in miniature that
this whole bead has been about.

Two fixes were on offer: soften the doc, or strengthen the test. Took the second.
`GATED_DEPLOY_SEVERITY = {script: (n_warn, n_fatal)}` now mirrors
`URL_BAKING_SEVERITY`, and both the decoy shape and a plain `warn` append redden.

Three rounds, three strictly larger claims about the same assertion: it exists ->
it is called correctly -> its severity is exactly right. Each round the weaker
version had looked sufficient.

## Round four: the classifier read the wrong thing entirely

Two more evasions, both in tests written in round three.

**Severity read from OUTPUT, not source.** The probe driver stubs only the
variables the real scripts use, so any OTHER variable in the severity position
expanded to empty and was classified "fatal". Routing severity through one --

```sh
SEV=warn verify_service_publicly_reachable "$S" "$R" "$P" "$SEV"
```

-- flipped `deploy-new.sh` to warn mode with all 32 tests green. Now classified
from the SOURCE TOKEN, and a `$` in that position is refused outright: an
indirected severity cannot be read by inspection, which is exactly the problem.

**A dead filter that widened the attack surface.** My `"_gate_" not in ln` clause
matched zero real lines (the helpers live inside the function body, already
excluded) but let a trailing `# _gate_` comment hide a live call -- which, paired
with a decoy in an `if false` branch, satisfied the exact counts. Removed; the
remaining filters do the job.

Both were found on the same script and the same test the previous round had just
hardened.

## What this bead actually cost, and what it bought

Four review rounds on one call site. The trajectory:

| round | finding |
|---|---|
| 1 | the gate call was CORRUPTED -- a literal `
` -- so it queried a service named `n` and could never fire |
| 2 | severity unpinned; dropping `warn` flipped the editor to FATAL, green |
| 3 | the pin was a LOWER BOUND while the doc claimed exact counts |
| 4 | the classifier read stdout, so an indirected severity read as fatal, green |

Every round found something the previous round's fix had left open, and every
round I believed the work was finished. The one constant: **each assertion was
weaker than the sentence I had written about it.** Presence, then invocation,
then binding, then exact severity, then severity that cannot be indirected.

The gate itself was correct from round one. What took four rounds was proving it
would stay correct -- and the reason is that a guard is not verified by writing
it, only by trying to defeat it. Three of the four rounds were caught by a
reviewer trying mutations I had not thought of, not by my own testing.

## Testing

Full suite: 4466 passed, 126 skipped, exit 0. Three mutations, each confirmed applied: a new ungated
URL-baking script (caught by the new set test), a new real public-deploy script
(caught by the re-scoped old one, proving the narrowing did not weaken it), and
removing the editor's gate call (caught only after the presence-vs-call fix).
