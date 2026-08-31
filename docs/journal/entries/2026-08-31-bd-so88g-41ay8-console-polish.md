---
date: 2026-08-31
bead: polyglot-pdf-so88g, polyglot-pdf-41ay8, polyglot-pdf-l25zi
title: "console: two resolvers because the tiers want opposite precedence -- and a mutation that was a no-op wearing a mutation's clothes"
tags: [console, client-links, auth, frontend, css, testing]
---

## Trigger

Two loose ends from bd `gob8l` (the mint page, PR #693), bundled because each
is small and both stand between the maintainer and using the page this week.

## so88g: the console sent the client's credential

Mint a link, open it in the same tab to check it, come back and mint another
-- the second mint was refused. `/f` stashes the client-link token in
`sessionStorage`, `resolveSessionToken` prefers it, and the backend resolves
that to a caller with no `uid`. The operator saw "your account is not attached
to a firm": wrong, and unfixable by them.

**The fix is not a precedence flip**, which is what I assumed before reading
the code. Client-link-wins is deliberate and load-bearing on the FILL path: it
keeps a session attributed to the link rather than to a staffer who happened
to open it, and the one-time-use accounting and telemetry both rest on that.
Flipping it globally would have broken exactly what it exists to protect,
while fixing a staff-tooling annoyance.

The two paths want opposite precedence. So: one resolver each, named for the
tier it serves -- `resolveSessionToken` (fill: link wins) and
`resolveStaffToken` (console: the Firebase user wins, a stashed link token is
ignored outright).

**The enumeration question**: of ten call sites, does only the mint page move?
I claimed yes; the reviewer DERIVED it rather than trusting me, and the
derivation is better than my reasoning was. `grep -rn 'user.get("uid")'
backend/routes/*.py` returns exactly one hit -- `link_routes.py`. A client-link
credential resolves to `uid: None`, so `/api/links/mint` is the only route in
the app that structurally rejects a link token. Every other site targets
`require_signin`/`require_auth`, which accept link tokens BY DESIGN because a
client must be able to do those things (catalogue, schema, PDF bytes, filled
preview, archive). `ArchivedVersionsLink` reads like a second candidate --
its docstring says "a firm user" -- but it is mounted inside the form-filling
surface and its route accepts links.

That is the right shape for this question: not "which sites feel staff-only?"
but "which backend route can a link token structurally never satisfy?"

## 41ay8: the page rendered unstyled

It emitted three class names no stylesheet defined. Values are LIFTED from
`schema-form.css` -- same system font stack, `#333` body text, 1px `#ccc`
4px-radius input, `#4CAF50` focus ring -- so the console reads as the same
product rather than a second design. That file is plain CSS with BEM-ish names
and no custom properties, so this one is too; a token system for one page is a
bigger commitment than the bead authorizes.

Imported by the PAGE, not the entry point. A stylesheet wired elsewhere can be
mounted without it, which is the shape of the original bug.

The reviewer checked the leak risk harder than I did and was right to: because
`MintLinkPage` is a STATIC import, `console.css` ships in the same bundle as
everything else and its rules are live on `/f` too. The element/attribute
selectors (`.mint-page > p`, `.mint-page [role="alert"]`) are therefore a real
question, not a theoretical one -- they are safe only because every one is
ancestor-scoped to a class exactly one component emits, and the 14 other
`[role="alert"]` emitters all sit under `.schema-form` or `.client-link-entry`.

## The mutation that was a no-op

My first verification of the so88g fix reported **GREEN**, which should have
meant the test was vacuous. It was worse than that: the mutation itself was
fake. I "reverted" the page by aliasing the import --
`resolveStaffToken as resolveSessionToken` -- which renamed the symbol while
still calling the staff function. Nothing changed, so nothing failed.

Re-run as a genuine revert (import both, call the session one -- the code that
actually shipped in `gob8l`), it goes red on exactly the right test.

The repo memory already says *confirm the mutation actually applied*. This is a
sharper version: a mutation can APPLY -- the file changes, the diff is real,
tsc still passes -- and still be semantically inert. **The check is not "did the
text change" but "can this code still do the wrong thing?"** A no-op mutation
reporting green is indistinguishable from a vacuous test, and I nearly filed it
as the latter.

## Also

- The reviewer caught me reporting the frontend suite as "408 files". That is
  `numTotalTestSuites` in the vitest JSON, which counts something else; the
  real number is **122 files / 1778 tests**. I had been repeating 406-408 all
  session. The test count was always right, which is why it never showed up.
- `resolveStaffToken`'s docstring claimed its union return type was for
  `resolveSessionToken`'s microtask reason. It is not -- that race is specific
  to the other function's synchronous `readToken()` early return; this one can
  never return synchronously. Corrected in the same PR (bd `l25zi`), because a
  false justification in shipped code propagates.
- Filed `hlqy2`: the new class guard only matches `className="..."` literals,
  so a template-literal class would be invisible to it. Not defective today
  (the page has zero dynamic classNames) but it is a latent version of the very
  bug it guards.
