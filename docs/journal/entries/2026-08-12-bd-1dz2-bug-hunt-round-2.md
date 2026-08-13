---
date: 2026-08-12
bead: polyglot-pdf-1dz2
title: "Bug-hunt round 2: validation fallback, health-probe coalescing, strict retrieval, scratch sweep, dev-local.ps1 parity"
sprint: null
tags: [testing, concurrency, conventions]
---

## Trigger

Second maintainer-requested bug-hunt roundup (round 1: bd oqqxj/ioe8d, 5xhbb,
eh2i, PR #573). Same brief: find easy, single-surface beads, bundle a few,
close them.

## What shipped

1. **bd polyglot-pdf-1dz2**: `backend/utils/field_validator.py`'s
   `_resolve_constraint` only tried the camelCase top-level key
   (`maxLength`) as its final fallback. Real on-disk kits carry the
   constraint as a top-level snake_case key (`max_length`) with no nested
   `validation` block. Widened the fallback to try both.
2. **bd polyglot-pdf-fzwp**: `confirmation_sink_status` (surfaced on the
   unauthenticated `/health` route) did the actual Firestore probe outside
   any lock, so N concurrent `/health` polls on a cold cache each did
   their own round trip against the collection holding the legal audit
   trail. Added Event-based coalescing.
3. **bd polyglot-pdf-k3v7**: `read_confirmation_log`'s `strict=True` only
   raised on a FAILED query when the sink was enabled -- an operator who
   forgot `--firestore` (the normal laptop case) got "no events found"
   having never checked the durable trail at all. Now also raises when
   the sink isn't enabled.
4. **bd polyglot-pdf-xlvba**: the bakeoff CLI's uuid4-per-call scratch
   path made a fresh collision impossible but also removed the old
   pid-keyed path's incidental self-healing -- a hard-killed call's
   scratch file was orphaned forever. Added a best-effort age-based
   sweep.
5. **bd polyglot-pdf-cgeh**: `scripts/dev-local.ps1` (Windows local-dev
   runner) omitted `DISABLE_GEMINI_VAD` and `SEND_TRANSCRIPT`, which its
   POSIX sibling sets -- a Windows dev-local run silently got a weaker
   debug log (no audio transcription) than a POSIX one.

Also investigated and **released unfixed**: bd polyglot-pdf-9oae. Its
described `widget.text_maxlen = 0` line does not exist anywhere in the
current codebase (`git log -S` on the file returns zero commits ever
introducing that string). The bead's premise appears superseded by an
unrelated commit that landed the same day the bead was filed. Left a note
rather than forcing a fix onto code without the described defect.

## Scar tissue

**1. A bead's premise can go stale between filing and pickup, and the
mechanical proof is cheap.** Before touching `9oae`, a plain grep for the
described line found nothing. `git log -S "text_maxlen = 0"` on the file
(the "did this string ever exist" query) returned zero commits -- not
"was removed," never EXISTED. That is a five-second check that saves
writing a fix for a bug that was never real, and it is strictly more
reliable than re-reading the bead's prose and trusting its own citations.
Every bead in a roundup like this deserves that check before claiming it,
not just the ones that look suspicious on read-through.

**2. A correct, tested fix can still be inert on the path that matters.**
The outer cross-surface review found that `1dz2`'s fix -- while genuinely
correct and tested against the real on-disk w7 schema -- does not change
LIVE voice-path behavior today: `ValidationHandler`'s allowlist (a
separate, pre-existing gate) strips the `max_length` key before the
validator function this bead fixed ever sees it. The fix is real (it
changes `validate_field_value`'s direct-caller behavior, e.g.
`/api/fill-pdf`), but the review correctly traced it one hop further than
the bead's own description went, and found the wiring gap was PRE-EXISTING
(reproduces unchanged on `origin/dev`) rather than introduced by this
diff. Filed separately (`polyglot-pdf-lzk82`) rather than expanded into
this PR's scope -- a bug-hunt roundup fixes what it found, not everything
adjacent to it.

**3. A concurrency fix's own safety margin needs a caller-aware bound, not
a round number.** The health-probe coalescing fix's first draft used a 30s
wait for a coalesced caller with no real justification beyond "long enough
to be safe." The inner fresh-eyes reviewer found the actual caller
(`/health`) wraps the whole thing in a 3s `asyncio.wait_for` -- and that
`wait_for` does NOT cancel the underlying `asyncio.to_thread` worker on
timeout, so the 30s wait just left worker threads pinned well past the
point they could usefully help anyone, specifically during the kind of
sustained Firestore outage this probe exists to detect. The fix: bound
the wait relative to the ACTUAL caller's own budget (2s, under the 3s
ceiling), not a number that felt conservative in isolation. A defensive
timeout is only as good as its relationship to what's actually waiting on
it.

## Review record

Two inner fresh-eyes rounds (NO-GAPS both times, with one non-blocking
finding surfaced and fixed between them -- the 30s-vs-3s timeout mismatch
above) and one outer Opus cross-surface round (NO-GAPS, with two
PRE-EXISTING findings filed separately rather than folded in). The outer
review's contract trace went beyond the diff's own docstring claims: it
enumerated all 96 real shipped-kit fields the `1dz2` widening actually
touches (the bead's description named only one), and traced the fix one
hop further into `ValidationHandler`'s allowlist to find the inert-on-the-
voice-path gap. Both extra steps were the review doing its job -- following
a contract OUT past where the diff's own description stopped.
