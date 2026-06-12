---
date: 2026-06-12
bead: polyglot-pdf-rlpq
title: "BUG: pr_review_watcher --close-on-clean does not fire on MERGED"
tags: [tooling, beads, closeout]
---

## Trigger

After PR #172 (polyglot-pdf-ipnr) was merged, the watcher exited MERGED (exit 0)
but the --close-on-clean hook did not fire -- the bead stayed open and required a
manual close. The condition in main() only checked CLEAN+review_verdict.

## What shipped

Extended the close condition in `pr_review_watcher.py` `main()` to also fire on
MERGED:

    should_close = args.close_on_clean and (
        (_LAST_STATE == "CLEAN" and _LAST_CLEAN_WAS_REVIEW)
        or _LAST_STATE == "MERGED"
    )

The merge is the ultimate success signal -- the review verdict is moot once the
maintainer merged. Updated the --close-on-clean help text, `_close_beads_on_clean`
docstring, and the module-level MERGED state description to match.

COMMENTS/ERROR/TIMEOUT remain excluded.

## Lessons

When a watcher has two "success" exit paths (CLEAN and MERGED), the close hook
should fire on both. Exit code alone (both exit 0) is not a sufficient gate --
the state must be checked directly.

## Doc freshness

`docs/components/beads-remote-bootstrap.md` flagged due to `bd_prime.py` mtime
from the ipnr fix (same pre-existing flag, already reviewed in that journal
entry). No change needed.

`docs/components/pdf-filling.md` flagged due to unrelated frontend file mtime.
This PR touches only `scripts/pr_review_watcher.py`. Reviewed, no update needed.

## Files touched

- `scripts/pr_review_watcher.py` -- extend close condition to fire on MERGED
