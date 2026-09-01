---
date: 2026-08-31
bead: polyglot-pdf-see5j
title: "perf(tts): /api/tts/notice caches synthesis and honors If-None-Match"
tags: [backend, tts]
---

## Trigger

`POST /api/tts/notice` (`synthesize_notice`) called the metered Google TTS
API on every request, unlike its sibling `/api/tts/intro`, which caches
synthesized audio in a process-lifetime dict and honors `If-None-Match`
with a 304. The notice text set is tiny and fully static (2 keys x ~18
languages today), ideal for exactly the same cache -- and because the
route is `require_auth`, not `require_paid_client_work`, nothing else
bounds call volume: any holder of a valid link token could drive unbounded
paid synthesis by re-POSTing.

Not a correctness break (the route is keyed with server-side text, so it
cannot become an open TTS service) -- a cost/abuse-hardening item.

## What shipped

- `notice_tts.py`: added a `(language, notice_key) -> (audio, etag)`
  process-lifetime cache, mirroring `intro_tts.py`'s cache shape exactly
  (same lock discipline, same first-writer-wins race handling, same
  cache-hit-size-in-the-log-line detail).
- `tts_routes.py`'s `notice_tts` route: added the `http_request: Request`
  parameter and the `If-None-Match` check, mirroring the intro route's
  304 handling verbatim.

## A real regression found by the Opus cross-surface review

The initial cache implementation resolved the language for the cache key
via `intro_tts.resolve_intro_language` (matching against `intro_tts`'s own
`_LANGUAGES` table, case-insensitively), but looked up the notice TEXT via
a case-SENSITIVE `NOTICE_TEXT.get(language_name)` on the raw, unresolved
name. The two could disagree: a request for `"spanish"` (lowercase) would
synthesize the ENGLISH fallback text (case-sensitive lookup miss), but
cache it under the resolved key `("Spanish", "save_early")` -- the SAME
key a properly-cased `"Spanish"` request would hit. Once cached, every
subsequent genuinely-cased Spanish request served the English clip for
the rest of the process lifetime.

This was pre-existing and inert on `origin/dev` (every request
re-synthesized its own text, so a lowercase caller only ever got English
for itself) -- the cache this bead adds is what turns a private,
per-request fallback into persistent cross-request contamination. Fixed
by adding `resolve_notice_language` (a case-insensitive resolver against
`NOTICE_TEXT`'s OWN key set, deliberately NOT `intro_tts`'s table) and
resolving ONCE per request, feeding that single resolved value into both
the text lookup and the cache key. This also fully resolves a second,
related concern the review raised (filed as `polyglot-pdf-8v8ee`, closed
as a side effect): the two tables (`NOTICE_TEXT` and `intro_tts`'s
`_LANGUAGES`) are no longer coupled at all, so a language present in one
but not the other can no longer cause a text/cache-key mismatch, by
construction.

New test reproduces the exact regression end-to-end through the real
route (a lowercase then a properly-cased request for the same language),
asserting exactly one synthesis call and that the synthesized text is the
CORRECT language's text, not the English fallback. Mutation-verified:
reverting to the original (raw-name-for-text, resolved-name-for-key) shape
reddens exactly this new test.

## Testing

New file `test_notice_route.py` (5 tests), mirroring `test_intro_route.py`'s
fixture pattern: a repeat request for the same (language, notice) is served
from the cache with exactly one synthesis call, and is genuinely re-keyed
on either dimension changing (different notice, different language); a
case-mismatched language request resolves to the SAME cache entry as the
properly-cased one, with the correct language's text (the regression
test for the fix above); `If-None-Match` gets a bodiless 304 without a
second synthesis call; unknown notice keys still 400 before synthesis; a
synthesis failure is still a 502.

Mutation-verified: removing the cache lookup reddened both the cache test
and the 304 test (the 304 path is cache-only, per the intro route's own
comment); removing the `If-None-Match` check reddened only the 304 test;
reverting the case-mismatch fix reddened only its own regression test.
Restored all three, ran the full related suite (`test_notice_route.py`,
`test_intro_route.py`, `test_notice_tts_parity.py`, `test_http_route_auth.py`)
green (133 tests total across the touched files).

## Files touched

- `backend/services/notice_tts.py` -- process cache added; language
  resolution fixed to a single, self-consistent source (see above).
- `backend/routes/tts_routes.py` -- 304 revalidation added to the notice
  route.
- `backend/tests/unit/test_notice_route.py` -- new, 5 tests.

## Follow-ups filed (out of scope for this bead)

- `polyglot-pdf-uow0s` -- the sole frontend caller of `/api/tts/notice`
  (`noticeSpeech.ts`) never sends `If-None-Match`, so the 304 path added
  here is currently unreachable in production; worse, if a future caller
  starts sending it, the existing `!response.ok` guard would silently
  swallow a 304 as a failure. Filed rather than fixed here since it's a
  separate surface (frontend) from this bead's backend scope.
