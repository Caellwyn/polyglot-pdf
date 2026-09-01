---
date: 2026-08-31
bead: polyglot-pdf-gob8l
title: "console: a staff page to mint client links -- and five review rounds spent on one enumeration I kept keying wrong"
tags: [console, client-links, frontend, deploy, review-rounds, enumeration]
---

## Trigger

The maintainer had testers waiting and no way to put them on the deployed app:
"I have folks that want to try out the app, and I don't have a good way to let
them do that." Minting existed as an API call and nothing else -- bd `ugm6`
built the tier, bd `ik7e` bounded its spend, and neither shipped a UI.

The immediate need was a page. The decision taken was to build it as the FIRST
SLICE OF THE CONSOLE rather than a throwaway script, so it grows into link
tracking and firm-admin management instead of being deleted.

## What shipped

- `frontend/src/console/MintLinkPage.tsx` -- pick a form, click, copy a link.
  Mounted at `/console/links` behind `ProtectedRoute`.
- `LINK_MINTING_ENABLED=true`, `LINK_REDEMPTIONS_FIRESTORE_ENABLED=true` and
  `LINK_BASE_URL` declared in `deploy-demo.sh` (maintainer authorised the first
  two directly; the third is required for the links to resolve).
- `link_cost_ceiling_usd: 3` on the two shipped kits (w7, i-90).

## The bug the tests could not see

The page read `user` from a PROP. The route element passes none. So
`resolveSessionToken(undefined)` returned undefined, `authHeaders()` yielded
`{}`, and every request went out unauthenticated: an empty form picker and a
401 on every mint.

**All nine tests passed.** They inject `fetchImpl` and none asserted a header.
`VFF_DISABLE_AUTH` masks it locally. The feature would have been dead on
arrival on the one deployment it was built for, and nothing in the suite,
the typecheck, or a local run would have said so.

The fix is one line (`useAuth()` like `SchemaFormDemo`). The lesson is not the
fix: **a test that supplies the transport cannot observe the credential.** The
new test asserts `Authorization: Bearer` on both calls and is mutation-verified
against the original defect.

The Opus reviewer then verified the fix STRUCTURALLY rather than by its test --
`AuthProvider` renders nothing while loading and `ProtectedRoute` renders
`Login` for a null user, so the page cannot mount with no user and its
catalogue effect cannot fire unauthenticated. That was the residual doubt I had
flagged, and it was closed by upstream structure, not by the mock.

## Five rounds on ONE set, because I kept keying the enumeration wrong

Enabling minting falsified a family of claims scattered across docs and source:
"minting is off until the ceiling ships", "nothing sets that key". Scar #7 says
enumerate the set before fixing any of it. I did that FOUR TIMES and got it
wrong three:

| Round | What I searched | What it missed |
|---|---|---|
| 1 | the claims I happened to recall | a fourth doc |
| 2 | `grep` over `docs/` | three `.py` restatements |
| 3 | `grep ik7e` over all file types | the member citing no bead at all |
| 4 | the claim, in one phrasing | (closed -- reviewer confirmed) |

Round 3 is the instructive one. I widened the file types and still missed a
member, because I keyed on the BEAD ID. The survivor -- `technical_guide.md`'s
"a feature no kit uses yet" -- states the claim without citing its source, so
no identifier-keyed grep can ever find it. It was word-for-word the same
sentence as the `websocket_routes.py` comment I had already fixed, in a
different file.

**The rule, now in `bd remember` (`enumerate-by-claim-not-by-identifier`):**
derive the grep key from the PROPOSITION your change falsified, not from the
ticket that introduced it. Ask "what sentence is now false?" and grep the
semantic content -- then grep again for the same claim in different words. The
reviewer found every survivor by asking what was false; my greps found only
what was labelled.

## Counts rot; properties do not

Three claims in this repo went stale mid-branch purely by being numbers:
`"All NINE backend-calling sites"`, `"the page's own 9 tests"`, and a
prediction that `"a TENTH site fails CI"` -- falsified by the mint page, which
IS the tenth and passes correctly.

The CI guard asserts the offender list is **empty**, at any ordinal. So the
prose was pinned to a value while the guard checked a property, and nothing
could catch the drift. All three now state the property. Same failure as the
enumeration above, one level down: pin the rule, not the instance.

## Deliberately not fixed

- **Per-form ceilings are declared but INERT.** Both kits carry $3;
  `websocket_routes` calls `check_budget(jti)` with no kit metadata, so the
  global $10 is what binds. Fails safe -- higher ceiling, never absent.
  Threading it costs a kit load on every client connect, so it is bd `4tjt7`.
  Real per-link demo exposure is $10, not $3, and the deploy comment now says
  so; my first version of that comment claimed the $3 shipped, which was false.
- **The picker can offer a form minting will refuse.** `/api/form-kits` lists
  every PUBLIC kit; mint requires the kit in the firm's explicit allowlist
  (`get_allowed_kits` returns kits *beyond* public ones), enforced at mint AND
  re-checked at open. That is deliberate entitlement policy, so the page now
  reports WHICH 404 it hit instead of blaming `LINK_MINTING_ENABLED`; changing
  the rule is a product call -- bd `boq04`.
- **A staff tab that has opened a client link mints with the CLIENT token** and
  403s, reported as "not attached to a firm". Fails closed. It is exactly the
  mint-test-mint-again flow, so: test links in a private window. bd `so88g`.
- **`firestore.rules` has no explicit deny for `link_redemptions`**, which this
  change activates. Safe today (Admin SDK only, default-deny), but the sibling
  `/firms` block exists for defence in depth. Security-surface change beyond
  this bead: bd `8f8gt`.

## Also

A `SchemaForm.previewEdit` failure appeared in one full-suite run of six. I
concluded "unrelated" partly from my diff's shape -- the reasoning this repo
explicitly warns against. The reviewer did it properly: ran the suspect files
in ONE invocation (21/21), confirmed vitest's fork pool isolates per file so
the new `AuthContext` mock cannot leak, and identified the actual mechanism --
`PreviewPane` is `React.lazy` and its chunk can exceed the bare 1000ms
`findByTestId` under load. bd `d6qep` carries that, replacing my misleading
"suggests leaked state" note.

Separately: I had been reading vitest JSON with the platform default encoding
and it threw on a non-ASCII byte. Re-read every prior run with explicit utf-8 --
all were genuinely clean, so the counts reported earlier were accurate. One
byte from reporting green without knowing it.

## Still needs the maintainer

`LINK_TOKEN_SECRET` (>=32 chars) must be provisioned via Secret Manager, never
a plaintext env var -- the same rule this repo states for `GEMINI_API_KEY`.
Without it minting 503s. And none of this is live until `deploy-demo.sh` runs,
which is a per-instance ask.
