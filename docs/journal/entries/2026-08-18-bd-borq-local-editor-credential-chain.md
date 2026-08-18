---
tags: [editor, local-dev, testing, stale-bead, enumerate-the-set, scar-tissue]
beads: [polyglot-pdf-borq]
surfaces: [tests, scripts, schema-editor]
---

# A P1 bug that was already fixed, and the guard that was missing instead

bd `borq` said the local schema editor was unusable: the launcher started
uvicorn with no editor token, so every `/api/editor` call 503'd. It was a
detailed, well-evidenced bead -- line numbers, a TestClient reproduction, both
halves of the failure traced.

It was also stale. bd `cpiw` (PR #522) rewrote the launcher months later and
fixed both halves.

## Checking before building

The bead's evidence was specific enough to be worth trusting, which is exactly
why it was worth checking. Reading `run-schema-editor.sh` took a minute:

```sh
if [ -z "$SCHEMA_AUTHOR_TOKEN" ]; then
    SCHEMA_AUTHOR_TOKEN="$(... secrets.token_urlsafe(24) ...)"
fi
```

...then handed to the backend, and the SAME value baked into the vite bundle
as `VITE_EDITOR_TOKEN`. Both halves the bead called broken.

Confirmed by execution rather than by reading, since that is the standard this
repo keeps re-learning: TestClient with the launcher's env shape returns 401
without the token and 200 with it.

Had I started from the bead's instructions I would have "fixed" a working
launcher -- and the diff would have looked plausible.

## The real gap was criterion 2, which nobody had done

The bead's second exit criterion asked for a test pinning that the launcher's
two sides agree. That was genuinely missing, and it is the more valuable half,
because the credential crosses FOUR links in three languages:

    run-schema-editor.sh   mints + exports SCHEMA_AUTHOR_TOKEN
      -> exports the same value as VITE_EDITOR_TOKEN
        -> remoteKitStore.ts reads import.meta.env.VITE_EDITOR_TOKEN
          -> sends it as the X-Editor-Token header
            -> require_editor_role reads that header

**The failure mode is what makes it worth a test.** Break any link and local
mode does not error -- the editor loads, the panel renders, and lint returns
nothing. To an author that reads as "no problems found", not "auth failed".
There is no toast and no red state. A findings-free panel and a clean schema
look identical.

## Testing the guard found two holes in the guard

Both are the same mistake wearing different clothes, and both were found by
mutating rather than trusting.

**Hole 1: I asserted against prose.** The first cut checked that
`VITE_EDITOR_TOKEN` appeared anywhere in `remoteKitStore.ts`. Renaming the live
read left the suite green, because two DOC COMMENTS still spell the old name.
A guard whose whole job is catching drift between code and its description was
itself reading the description. Fixed by stripping comment lines.

**Hole 2: my mutation was too gentle.** I renamed
`VITE_EDITOR_TOKEN` -> `VITE_EDITOR_TOKEN_V2`, which is the friendliest
possible version of that edit -- and the old name is a PREFIX of the new one,
so a substring check matches it. The guard passed again. Fixed with a word
boundary, then verified against BOTH a suffixed and a clean rename.

The second hole is the more interesting one. A mutation that is too polite
does not just fail to prove the guard works -- it actively certifies a guard
that does not. I would have shipped hole 2 believing hole 1 was the whole
story, because the mutation I chose could not tell the difference.

**The rule that generalizes:** pick the mutation a real author would make, and
when a guard survives, ask whether the mutation was strong enough before
concluding the guard is.

## And a THIRD instance of the same hole, one language over

The review found the comment-vs-code bug still open on the PYTHON side. I had
fixed it in TypeScript and moved on -- while my docstring said "Two files, two
languages, one string", claiming a symmetry that did not exist.

FastAPI derives the wire header from the parameter NAME
(`x_editor_token` -> `X-Editor-Token`), so that identifier is the contract.
The docstrings also spell `X-Editor-Token`, and my assertion searched the raw
file. Measured: renaming the parameter -- which changes the real header the
backend expects -- left all six tests green.

So the sequence across this one small test file was:

1. assert against prose (TypeScript)      -> caught by my own mutation
2. mutation too gentle to expose a prefix -> caught on re-mutation
3. assert against prose (Python)          -> caught by the reviewer

Three rounds, one root cause, three surfaces. I fixed each instance as I found
it instead of asking, after the first, *where else does this shape live?* The
answer was: every place the guard reads a file, which is four files in three
languages. That question was cheap and I did not ask it.

**The reviewer's mitigating finding is worth recording too**, because it
changes what the defect actually was: the system did NOT silently degrade,
because the pre-existing `test_editor_kit_routes.py` fails 152 tests on that
mutation. Criterion 2's real bar -- fails loudly -- already held. What was
wrong was my FILE's *claim* to pin that link.

That is a specific kind of harm worth naming: **a guard that claims coverage
it does not have is worse than an absent guard**, because it stops the next
person from looking. An absent guard leaves a visible hole; a lying one closes
the hole on paper.

## Four versions of one assertion, and the lesson underneath them

The Python-side header check went through four versions. Every wrong one was
found by mutation, never by reading:

| # | assertion | defeated by |
|---|---|---|
| 1 | `"x-editor-token" in py.lower()` on raw text | the DOCSTRINGS satisfied it -- renaming the parameter changed the real header, test stayed green |
| 2 | word-bounded parameter NAME | rejected `Header(alias="X-Editor-Token")` -- a VALID refactor, verified 200 |
| 3 | name OR literal alias | rejected `Header(alias=_HDR)` from a constant -- also valid, also 200 |
| 4 | walk FastAPI's dependant graph | nothing yet |

Versions 1-3 all failed the same way, and it took three tries to see it: each
**pattern-matched SOURCE TEXT for something the framework computes.** Every
patch bought one more spelling and left the next one open, because the target
was never really "does this text appear" -- it was "which header does the app
bind?"

FastAPI answers that directly:

```python
for route in app.routes:
    for param in route.dependant.header_params:
        declared.add(param.alias.lower())
```

That is immune to all three defeats at once, and to ones I had not thought of:
comments are not in the graph, and neither are string literals or constants.
It also cannot over-constrain, because it asks about behavior rather than
spelling -- version 2 and 3's failure mode is structurally impossible.

**The transferable rule: when a guard needs three patches to cover three
spellings, the spelling is not the thing to assert.** Ask the system that owns
the answer. Text-matching is a fallback for when nothing owns it -- which is
why the TypeScript half of this same test still reads source: a string literal
in a fetch call has no framework to interrogate.

A pass-3 review independently reached the same conclusion, having reproduced
version 3's hole with a stale comment (`# renamed from x_editor_token:`) that
satisfied the regex while the real header was `X-Wrong-Header`. Verified that
exact probe fails against the graph version, along with the constant-alias
case it flagged but could not test.

## The pattern I could not see from inside: my prose kept outrunning my code

Four review rounds on a test-only diff. The code was defensible every time.
What kept failing was the sentence describing it:

| I wrote | What the code did |
|---|---|
| "Two files, two languages, one string" | stripped comments on ONE of them |
| "should not depend on which comment style a file prefers" | three styles unhandled |
| "pins the FastAPI PARAMETER" | matched the docstring too |
| asked about "this dependency" | asked about the whole app |

Every one is the same shape: **a claim slightly wider than the implementation.**
Not one was a lie I would have caught by rereading, because each felt true when
written -- I described what I MEANT the code to do.

That is the specific harm worth carrying forward. A missing guard leaves a
visible hole; a guard whose docstring overclaims closes the hole *on paper* and
stops the next reader looking. The overclaiming sentence is more dangerous than
the gap it describes, because it is what survives into the next person's
understanding.

Concretely, the habit that would have caught all four: after writing the
sentence, read it back as a STRANGER'S SPECIFICATION and ask what test would
falsify it. "Two languages" -> is there an assertion per language? "Style
independent" -> which styles did I try? "This dependency" -> does the code
name that dependency, or a set containing it? Each takes seconds and each
would have failed.

## The tree is shared while a reviewer runs

Two process facts, both learned the hard way in this round:

- A **false negative**: one mutation "passed" only because the review subagent
  was mid-mutation on the same file. Re-run on a settled tree, it failed
  correctly. A test result taken while another agent is editing the same file
  is not evidence.
- The reviewer's cleanup **reverted my uncommitted edit** along with its own
  mutation. Uncommitted work is not safe in a tree another agent is restoring.
  Commit promptly, or expect to redo it.

## Process notes

- The bead is RESCOPED, not closed-as-invalid. Criterion 1 was met by shipped
  code; criterion 2 is what this delivers. Both findings are recorded on the
  bead so the next reader sees why a P1 "bug" produced a test-only diff.
- No production file is touched. That is the honest shape of the work: the
  code was right and the safety net was missing.
