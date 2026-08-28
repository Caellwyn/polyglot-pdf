---
date: 2026-08-27
bead: polyglot-pdf-nlbck
title: "test(check-doc-freshness): count-free the _SITE_ANCHORS start anchor + pin the lead-sentence count word"
tags: [doc-freshness]
---

## Trigger

bd `polyglot-pdf-82rzp` made `scripts/check_doc_freshness.py`'s "Why every
check lives in one script" paragraph count-free, so adding a fifth check
would never require updating that paragraph. But two count-bearing sites
were left unfixed: a test anchor (`_SITE_ANCHORS[0]`) hard-coded the exact
stale "four" text, and the module docstring's LEAD SENTENCE itself still
said "four" with no test reading it at all.

## What shipped

- `_SITE_ANCHORS[0]`'s start anchor shortened to a count-free substring.
- The module docstring's lead sentence rewritten to be count-free.
- A new test, `test_lead_sentence_names_no_count_word`, scanning the whole
  docstring for a count word immediately before "check(s)".

## Lessons

**A test that extracts a "lead sentence" by positional index is the exact
failure mode this file has already paid for twice.** The first draft of
the new test used `freshness.__doc__.split("\n\n")[1]` to isolate the lead
sentence -- a future paragraph inserted before it would silently shift the
index, and the test would then check unrelated text while still passing.
This is the same shape as bd `polyglot-pdf-u3miz`'s vacuous `count() >= 2`
and bd `polyglot-pdf-uquqs`'s swallowed-window bug, both in this same test
file. Fixed by scanning the WHOLE docstring instead of an extracted
substring -- no position to shift.

**A reviewer that reasons about a regex instead of running it can produce
a confident false positive.** A Haiku docs-reviewer pass flagged that
"adding a fifth check" (elsewhere in the docstring) should match the new
count-word pattern and break the test -- a plausible-sounding claim from
reading the regex. Running the test directly showed it passes: the
regex's word list is cardinal numbers only ("four", not "fourth"), and
"fifth" is an ordinal referring to a hypothetical future check, not a
claim about the current total. The fix was not to change the code but to
ask the reviewer to re-verify by executing the test rather than reasoning
about it -- which it then did, and correctly reversed itself.

## Files touched

- `scripts/check_doc_freshness.py` -- lead sentence made count-free
- `tests/test_doc_freshness.py` -- anchor fixed, new test added
