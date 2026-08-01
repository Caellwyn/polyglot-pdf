---
date: 2026-08-01
bead: polyglot-pdf-bagn
title: "Two same-folder handshakes shared one marker file, and nothing pinned its name across languages"
tags: [schema-editor, testing, conventions]
---

## Trigger

Both filed by Opus reviewers during bd `polyglot-pdf-ball` closeout, and both
deliberately scoped out of it. Three separate reviewers independently filed the
`bagn` half, which is a decent signal it was real.

## bagn -- the two channels could void each other

There are now two same-folder handshakes, each proving the editor and one server
are looking at the same directory:

| Channel | Reader | Root setting |
|---|---|---|
| backend (bd `s2bf`) | FastAPI | `FORM_KITS_LOCAL_ROOT` |
| extractor (bd `ball`) | Vite dev host | `FORM_KITS_ROOT` |

Both run against the folder the human picked, and **they are not serialized**:
`handlePickFolder` bars a folder *switch* during an extraction, but the App-level
backend check is already in flight from the pick itself. Both wrote and then
deleted the *same fixed filename*, so either channel's cleanup could delete the
other's in-flight marker. The reader then observed nothing and refused -- telling
the user "the folder you opened is not the one the extractor uses" about a folder
that genuinely agrees.

Fail-closed, so never a safety hole (a per-check nonce makes a cross-channel
false *pass* impossible -- channel A's marker can never satisfy channel B's
nonce). But it is the misdiagnosis class `ball` spent four rounds eliminating: it
sends the user to change configuration that is already correct.

**Fix:** a separate marker filename per channel. Considered and rejected: putting
the nonce *in* the filename, which would also make interference impossible but
changes the wire contract for three components in two languages and turns both
readers from a fixed-path read into a directory glob. Separate names buy the same
structural guarantee for a one-line change on each side.

## kesf -- the name had no cross-language pin

The marker filename is declared in three production files across two languages,
coupled only by comments. **The failure mode is silent:** a reader that cannot
find the marker treats it as "nothing observed", which is indistinguishable from
a genuinely wrong folder.

So the *natural, self-consistent* refactor -- rename the Python constant and
update the four hardcoded literals in its own test file -- leaves the Python
suite green, leaves the TS suite green, and permanently switches off Repair all,
Regenerate divisions, Rewrite guidance and the widget picker behind the s2bf
mismatch modal. Nothing fails; the feature just stops.

`markerNames.contract.test.ts` now reads all three declarations as **source
text** and pins both pairings. It scrapes rather than imports because that is
precisely the problem it exists to solve: the Python is unimportable from vitest,
and the Vite plugin sits outside the `src/` tsconfig scope (`"include": ["src"]`),
which is why neither type system could ever have caught this.

The old TS-only coupling test was **removed, not kept**. Keyed on the bare name
`HANDSHAKE_FILE`, it would now match the *backend* channel's constant in
`formKitDirectory.ts` and silently compare the wrong pair -- a test that looks
like coverage while asserting nothing useful is worse than no test.

## Verification

Both by mutation, not by inspection:

- **bagn:** giving both channels the same marker again fails 4 tests, including
  the interference reproduction -- a held-open backend check released to complete
  *during* an extraction check, with the asker reading what is actually on disk
  at ask time.
- **kesf:** running the bead's exact recipe (rename `_HANDSHAKE_FILE` **and** all
  four Python test literals) leaves the Python suite GREEN -- 5 passed -- and
  turns the contract test RED with the drift named: `expected
  '.editor-renamed-check.json' to be '.editor-store-check.json'`. That is exit
  criterion 1 verbatim, including its "today it is green" precondition.

## The general lesson

A constant duplicated across a language boundary has no compiler holding it
together, and when the consumer's failure mode is "treat absence as a negative
answer", drift is invisible rather than loud. Both conditions were true here.
When they are, the pin has to live *outside* both languages -- reading the
sources as text is ugly, but it is the only thing that can see across the seam.

Related: [[2026-08-01-bd-ball-extraction-same-folder-gate]] (the extractor
channel this splits off from), and bd `s2bf` (the backend channel).
