---
date: 2026-08-24
bead: polyglot-pdf-75nmm
title: "test(firm-telemetry): 'all three record types' docstring is stale -- there are four firm_id-carrying events"
tags: [testing]
---

## Trigger

`test_firm_telemetry.py`'s module docstring, and two of its tests'
docstrings/mutation-comments, claimed "three record types carry firm_id".
Since bd `polyglot-pdf-0dsv4` a fourth event kind, `disclaimer_accepted`
(`confirmation_logger.log_disclaimer_acceptance`), also carries a
`firm_id` key. The test suite still passed (each test only writes the
events it names), but the stated invariant read as a complete
enumeration it no longer was.

## What shipped

Enumerated the full set of stale "three" claims mechanically (grep, not
recall) rather than fixing only the one site the bead named -- found
three sites total, only one of which the bead itself cited: the module
docstring and two test docstrings/mutation-comments. Rewrote the module
docstring to name all four event kinds and `disclaimer_accepted`'s
distinct always-`None` `firm_id`. Renamed
`test_all_three_record_types_share_the_firm_key` to
`test_all_three_firm_carrying_record_types_share_the_firm_key` and
clarified its scope rather than folding the fourth event in (it asserts
`{d["firm_id"] for d in docs} == {"firm-b"}`, which would be false for an
event whose `firm_id` is never a real firm). Added a new, separate test,
`test_disclaimer_accepted_carries_the_firm_key_always_none`, pinning the
correct, distinct invariant for that event: the key is present, always
`None`.

## Lessons

**A fix scoped to exactly the one location a bead cites can still miss
the set.** The bead named line 90's docstring; grepping the whole file
found two more instances of the same stale claim it didn't name (the
module docstring, and a second test's mutation-comment). Both would have
shipped stale under a narrower fix.

**Not every "extend the test" fix belongs in the existing test.**
`disclaimer_accepted`'s `firm_id` is permanently `None` by design (the
route is unauthenticated) -- a fundamentally different invariant from
the other three events' "carries the CALLER'S real firm claim." Folding
it into the shared-firm-key test would have meant asserting something
false. The right fix was a new test pinning the correct, different
property, not a bigger version of the old one.

## Files touched

- `backend/tests/unit/test_firm_telemetry.py` -- module docstring, two
  test docstrings, one new test
