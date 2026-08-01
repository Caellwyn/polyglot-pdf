---
date: 2026-08-01
bead: polyglot-pdf-ball
title: "Run extraction could overwrite a different copy of a kit, invisibly"
tags: [schema-editor, extractor, security, testing]
---

## Trigger

Filed by the Opus reviewer during bd `polyglot-pdf-s2bf` closeout. That bead put a
same-folder handshake in front of the three **backend** server-side actions
(Repair all, Regenerate divisions, Rewrite guidance), because the editor reads and
writes the folder the human picked while the backend resolves the same kit id
against its own `FORM_KITS_LOCAL_ROOT`. "Run extraction" is the same bug class and
was left ungated -- deliberately out of scope there (s2bf's exit criterion named
the three backend actions), and filed as this bead.

## The bug

Open a copy of `form-kits/` somewhere else via the folder picker, pick a kit whose
id also exists under the Vite host's `FORM_KITS_ROOT`, press **Run extraction** --
and the extractor runs against, and overwrites `schema.json` in, the **host's**
copy, not the one on screen. `FormCatalogue` then refreshes the picked folder and
shows no change, so the destructive write leaves no trace in the UI. Hand-reviewed
work in a kit the human was not even looking at is silently replaced.

The client's own docstring had admitted the precondition for years without
enforcing it: "this works when the editor's open folder is the server's form-kits
root."

There is a second-order half. The instructions PDF (bd `s4dp.3`) is written by the
browser into the **picked** kit dir, then read by the endpoint from
`path.join(kitDir, instructionsPdfFile)` under the **host's** root -- so on a
mismatched folder the file is written to one place and looked for in another, and
the request 400s with "instructions PDF not found" for a file the browser had just
successfully written.

## Why s2bf's guard could not simply be reused

This is the part worth remembering. Extraction is served by the **Vite dev
server**, not the FastAPI backend, and the two have **separate roots**:

| Channel | Root setting |
|---|---|
| Backend server-side actions | `FORM_KITS_LOCAL_ROOT` (`backend/config.py`) |
| Vite extraction endpoint | `FORM_KITS_ROOT` (`extractEndpoint.ts`) |

So `serverActionsOk` -- proof that the editor agrees with the *backend* -- says
nothing about where the *extractor* writes. Both roots can be set independently,
and only one of them is what `schema.json` lands under. The gate needed its own
nonce channel.

## The fix

The same proof-by-shared-observation s2bf used, because the same constraint
applies: a path comparison is impossible (the browser cannot read a filesystem
path out of a directory handle, by design).

```
POST /api/extract/handshake  {nonce} -> {sameFolder, extractorRoot, reason}
```

The browser writes a fresh nonce into the picked folder; the Vite host reads it
back from the root it would actually resolve kit ids against; a match means both
are looking at one directory. `verifySameFolder()` was already parameterized on
its asker, so it is reused verbatim and both channels share one marker-lifecycle
implementation (including the `.editor-store-check.json` name and its gitignore
entry).

Design points carried over deliberately from s2bf, since the failure mode is
identical:

- **Checked at the moment of the write**, inside `handleRunExtraction`, not once
  per folder -- it is the last thing before any file is touched.
- **The instructions PDF is written only after the gate passes**, which is what
  closes the second-order half above.
- **Fail-closed everywhere.** A network error, a non-OK response, a non-JSON body,
  or a merely-truthy `sameFolder` all read as UNPROVEN. `sameFolder` must be
  exactly `true`. The gated action is a destructive overwrite; a refused button is
  not.
- **Read-only on the host side.** It never creates or deletes the marker, so a
  read-only root degrades to `sameFolder=false` rather than failing.
- **Per-check nonce**, so a leftover marker from an earlier session in a different
  folder reads as *stale* rather than as a false match.
- Behind the existing same-origin guard, since the response reveals the host's
  form-kits root.

## Verification

End to end against a running dev server, all six paths: matching nonce ->
`sameFolder true`; no marker -> `mismatch`; wrong nonce -> `stale`; the marker
survives the read; cross-origin -> 403; missing nonce -> 400.

Then the bead's exact scenario: `w7` copied to a temp dir with its marker written
**there**, the gate refuses, and the host's own `form-kits/w7/schema.json` is
byte-identical afterwards (sha256 `93bc4083...` before and after -- that is the
hash of the file ON DISK, which is what the extractor would have rewritten; the
git blob hashes differently because of line-ending normalization, so do not
expect `git show HEAD:...` to reproduce it) -- while an
ungated POST for that same id demonstrably resolves to the host's copy, which is
what makes the refusal load-bearing rather than decorative.

25 new tests (12 endpoint, 8 client asker, 5 component -- one of the 5 pins the
fresh-nonce/cleanup contract rather than the refusal itself). Both gates were
**mutation-verified rather than assumed**: forcing the endpoint to report
`sameFolder=true` fails 4 endpoint tests, and removing the UI gate fails 5
component tests.

The two UI mutations differ, and the distinction is the point: removing the WHOLE
gate (the `verifySameFolder` call included) fails 5 -- the 4 refusal tests plus
the nonce test, which stops observing a handshake once none is run. Removing only
the REFUSAL (`if (!folder.ok)`) fails 4, because the handshake still happens and
the nonce test is still satisfied. Both were run; quote whichever you mean.

## A refusal message that was a dead end (bd polyglot-pdf-6pzs, folded in)

The Opus outer review caught that the `unwritable` branch had inherited s2bf's
advice verbatim -- "make a copy somewhere writable and open that" -- which is
right for that channel and **wrong for this one**. Saving targets whatever folder
you picked, so any writable copy fixes it; extraction always writes under the
host's `FORM_KITS_ROOT`, so a copy made anywhere else is by construction not the
host root and the next click just fails the *mismatch* branch instead. The advice
could not reach a working state.

Now it directs the user at the host's own root (make it writable, or point
`FORM_KITS_ROOT` at a writable folder and restart). Note the `unwritable` branch
short-circuits *before* the handshake is asked (`formKitDirectory.ts` returns
early on the failed marker write), so `backendRoot` is undefined there and the
message cannot name the root -- it says what to do without naming it.

Worth recording because it is a general hazard when mirroring a guard onto a new
channel: the *mechanism* transfers, but the remediation advice may not, because
the two channels write to different places. A test now pins the new wording and
asserts the copy-elsewhere text is gone.

A later review round found the **same defect class one branch over**, which is
the more useful lesson. `verifyExtractorFolder` collapsed four outcomes into one
bare `sameFolder: false` -- fetch rejection, non-OK, unreadable body, and a real
mismatch -- and `verifySameFolder` labels every one of them `mismatch`. So a dev
server that had simply died rendered "the folder you opened is not the one the
extractor uses ... it would rewrite a different copy", confidently misdiagnosing a
transport failure as a wrong folder and sending the user to change configuration
that was already correct. Worse, the test I wrote for that case *asserted* the
wrong wording, entrenching it.

The verdict was never wrong -- all four outcomes must refuse, and did. Only the
explanation was. The asker now reports unreachability out-of-band (its return
shape is shared with the backend channel, so widening it was not an option) and
that case gets its own message. The general form: **fail-closed is a property of
the verdict, not of the message**, and a guard that refuses correctly can still
send someone down a dead end.

And then a THIRD time, in the docs written to explain the first two. The
remediation "point the dev server at your folder with `FORM_KITS_ROOT`" fixes
extraction and **silently breaks the backend gate**, because the launcher starts
two servers that resolve kit ids from two different variables -- so the user
follows the advice, extraction starts working, and Repair all / Regenerate /
Rewrite guidance / the widget picker all quietly switch off behind the s2bf
mismatch modal. Both docs now name `FORM_KITS_ROOT` **and**
`FORM_KITS_LOCAL_ROOT` and say why; the in-app message recommends simply opening
the server's folder (always correct) and defers the env-var route to the README,
rather than half-specifying it in a toast.

And a FOURTH time, in the fix for the first one. The rewritten unwritable message
said "open a writable **copy** of the folder the dev server uses" -- a copy of the
host root is still not the host root, so it was the identical dead end in new
words, directly contradicting the comment sitting above it that spells out why a
copy cannot work.

**The test I had written to prevent exactly this did not catch it**, and that is
the part worth keeping. It asserted the *literal s2bf phrase* was absent
(`/make a copy somewhere writable and open that/`), so a reworded copy-elsewhere
sailed through untouched. It pinned a string, not a rule.

So I banned the word `copy` -- and the NEXT review defeated that too, with
"**duplicate** it somewhere writable and open that duplicate". 38 of 38 green.
I had written "banning the word is what actually holds" in this very entry, and
it did not: a blacklist is always one synonym from being defeated, and the
demonstration cost one reviewer one mutation.

What holds is an **allowlist**. This branch has exactly two remedies that reach a
working state -- make this folder writable, or open the server's own folder -- so
the test now asserts both are present, strips them plus the framing, and requires
that **no further instruction survives**. A third remedy fails it regardless of
wording. Verified against four bypasses, including one containing no copy-word at
all ("set FORM_KITS_ROOT to this folder"), which every blacklist version would
have missed.

Four rounds, four instances of the same shape. Two lessons, both general:

1. **When you add a guard, the remediation path is part of the deliverable, and
   it has to be verified like code.** Every recommendation here was ultimately
   checked by running it -- including the two-variable one, confirmed by pointing
   the real backend at a temp root and watching `get_form_kit_store().root`
   follow.
2. **Allowlist the correct advice; do not blacklist the wrong advice.** Three
   versions of one test failed here, and the first two failed the same way: they
   described what the message must NOT say (a literal sentence, then a single
   word), and each was beaten by a rewording. You cannot enumerate the wrong
   answers -- there are infinitely many, and only one has to slip through. You
   can enumerate the RIGHT ones, because a branch that offers two working
   remedies offers exactly two. Assert those, then assert nothing else remains.

   The generalization: when a test guards *prose*, blacklists rot and allowlists
   hold. Worth remembering the next time a message needs pinning, because the
   blacklist is always the one that comes to mind first.

## A harness trap that cost real time

Twice during this work a suite ran green against code that no longer contained
the change under test, and once a test failed on a string (`moveitsomewhere
writable`) that exists in no file and no commit. Both are the same cause, which
an Opus reviewer diagnosed independently after hitting it themselves:
`schema-editor/node_modules` is a junction into the MAIN checkout, so the vitest
transform cache under `node_modules/.vite/vitest` is SHARED across every worktree
and every concurrent run. A reviewer mutating a file for their own mutation test
can therefore serve a stale (or foreign) module to a run happening in parallel.

Practical rule: **verify an edit is on disk before trusting a green suite**, and
treat a failure quoting text you cannot find in the tree as cache contamination
rather than as a real defect. Re-run in the foreground, alone, before chasing it.

## One thing worth flagging for the next person

Five existing run-extraction component tests started failing the moment the gate
landed -- their fetch mock routed *every* POST through one handler, so the new
handshake POST received the extraction payload and read as a refusal. That is the
mock being too coarse, not a product defect, and the fix belonged in the mock: it
now routes by URL and **defaults to agreement**, so those tests keep testing what
they were written to test rather than accidentally testing the refusal.

Worth noting because the failure looked like a regression at first glance. The
tell was that the failures were the tests that *complete* an extraction, and none
of the ones that merely show or hide the button.

Note the count is five, not six, even though six tests in that block POST. The
sixth ("disables folder controls ... WHILE extraction is in flight") holds its
POST promise open, which satisfies the handshake and the extraction alike, so it
survives the coarse mock. Recording the exact signature because the *shape* of
the failure set is the diagnostic -- "every test that finishes an extraction, and
only those" is what tells you the mock is at fault rather than the gate.
