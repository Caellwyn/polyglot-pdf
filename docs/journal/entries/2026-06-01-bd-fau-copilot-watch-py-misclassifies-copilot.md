---
date: 2026-06-01
bead: polyglot-pdf-fau
title: "copilot_watch.py misclassifies Copilot approval issue-comments as findings"
tags: [conventions]
---

## Trigger

`bd polyglot-pdf-fau`, bumped P3→P2 after recurring on **three** consecutive PRs
(#41, #42, #43): each multi-round closeout paid a spurious extra re-watch cycle
because `copilot_watch.py` reported `COMMENTS` on a Copilot *approval* issue-comment
(no actual finding). Folded into PR #43 (the `5ys` watcher change) since both touch
`copilot_watch.py`.

## What shipped

The watcher already routed issue-comment classification through
`_is_approval_comment()` (→ CLEAN when an approval phrase is present and no change-ask
signal is). The bug was that **`_APPROVAL_PATTERNS` was too narrow** — it had 5 phrases
("no further changes", etc.) that didn't cover Copilot's actual approval vocabulary.
Verified against the real comment bodies from this session:

- #43: *"no outstanding findings … Nothing further to address"* → did NOT match → COMMENTS.
- #42: *"I don't see any new blocking issues"* → did NOT match → COMMENTS.
- #43 (other round): *"No further changes needed"* → DID match (so it was the
  "no outstanding findings" phrasing that slipped through and caused the loop).

Broadened `_APPROVAL_PATTERNS` with the observed phrasings ("no outstanding
findings/issues", "no blocking issues", "nothing further to address", etc.), keeping
the conservative `_CHANGE_ASK_SIGNALS` guard untouched so a **mixed** comment
("no findings, *but please* fix X") still classifies COMMENTS — the module's core
invariant ("never read ambiguity as CLEAN") is preserved.

Verified by replaying the real bodies + negative controls against
`_is_approval_comment`: the two #43 phrasings now read APPROVAL; mixed-comment and
real-finding controls stay COMMENTS; the original 5 patterns and the change-ask
guards (`should`, `missing`, `but`, …) don't regress.

**Scoped miss (intentional):** #42's *"don't see any new blocking issues"* still reads
COMMENTS — matching its exact verb phrasing would need a loose `blocking issues`
substring, which could false-positive on a comment *describing* a blocking issue.
Erring toward COMMENTS there is the safe direction; the dominant failure mode (the
#43 phrasings) is fixed.

### Review triage (PR #43)

Round 3 (this review) raised three findings, all adopted:
1. `_pr_closed_state` docstring referenced "timeline" — reworded to reflect the PR
   payload fields (`merged` / `merged_at`) actually used.
2. Comment overstated "observed verbatim" for `"no new blocking issues"` (the verbatim
   #42 phrase was *not* matched) — reworded to clarify it broadens the #42 pattern.
3. This placeholder itself — filled (you're reading it).

## Lessons

`_is_approval_comment` is a phrase **allowlist** — it only ever gets more accurate by
observing real Copilot approval vocabulary and adding the misses (the change-ask guard
keeps the broadening safe). The asymmetry is deliberate: a false COMMENTS costs one
re-watch; a false CLEAN could merge past a real finding. So widen approvals only with
verbatim-observed phrasings, never speculatively. This bug *couldn't* have been the
`5ys` merge-fix (different code path) — confirming that a recurring symptom can have
two unrelated root causes (here: merge-not-reported AND approval-misread).

## Doc freshness

- No tier-1/tier-2 doc tracks `scripts/copilot_watch.py` — no doc updates triggered.
- STALE docs reported by the checker track `live_ai_gemini.py` / `config.py` /
  schema-forms TS — files this branch did NOT touch (pre-existing). Left as-is.

## Files touched

- `scripts/copilot_watch.py` — broadened `_APPROVAL_PATTERNS` (+ rationale comment).
- `docs/journal/entries/2026-06-01-bd-fau-copilot-watch-py-misclassifies-copilot.md` — this entry.
