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
byte-identical afterwards (sha256 `93bc4083...` before and after) -- while an
ungated POST for that same id demonstrably resolves to the host's copy, which is
what makes the refusal load-bearing rather than decorative.

23 new tests. Both gates were **mutation-verified rather than assumed**: forcing
the endpoint to report `sameFolder=true` fails 4 endpoint tests, and removing the
UI refusal fails the 4 component tests.

## One thing worth flagging for the next person

The six existing run-extraction component tests started failing the moment the
gate landed -- their fetch mock routed *every* POST through one handler, so the
new handshake POST received the extraction payload and read as a refusal. That is
the mock being too coarse, not a product defect, and the fix belonged in the mock:
it now routes by URL and **defaults to agreement**, so those tests keep testing
what they were written to test rather than accidentally testing the refusal.

Worth noting because the failure looked like a regression at first glance. The
tell was that all six failures were exactly the tests that *run* an extraction,
and none of the ones that merely show or hide the button.
