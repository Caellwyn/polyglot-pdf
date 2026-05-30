## Review behaviour

After finishing a review on a PR targeting the `dev` branch, you **MUST always
post a top-level review summary comment — every time, on every round, with no
exceptions** — even when you have zero findings and even when a prior round's
findings have all been addressed.

**Why this is non-negotiable:** the PR author runs an automated agent that polls
for your review events. A silent finish (no comment, no state change) is
**indistinguishable from "I never reviewed it"** from the author's side, so the
agent waits indefinitely for a signal that never comes. Your top-level comment
IS the "review finished" signal. Skipping it — even when the code is perfect and
there is genuinely nothing to say — is the single most disruptive thing you can
do on this repo. When in doubt, post the comment.

### When you have one or more findings

- Post your usual file-level review comments **AND** a top-level summary comment.
- Assign the PR to `@caellwynai-josh` so the automated follow-up agent picks it up.
- Do NOT commit changes yourself. Make suggestions in comments — the author's
  code agent will read them and apply fixes.

### When you have zero findings (the code is satisfactory / LGTM)

This is the case you have historically skipped. **Do not skip it.** A satisfied
review still REQUIRES a top-level comment:

1. Submit an **Approve** review if the platform allows it.
2. **ALWAYS** post a top-level comment whose **first line** is exactly one of
   these literal phrases (nothing else on that line), so the author's polling
   agent has a deterministic, greppable signal:
   - `LGTM`
   - `No further suggestions`
   - `Approved`
3. Do NOT assign the PR — there's nothing for the follow-up agent to respond to.

"The work is satisfactory" is **not** a reason to stay silent — it is precisely
the case the LGTM signal exists for. If you reviewed and have nothing to add,
that is a *result* the author needs reported, not an excuse to finish quietly.

### Round 2 and later

Even when the previous round had findings and they have **all** been addressed,
you must still post the LGTM-style top-level comment (per the zero-findings rule
above). A silent "I looked again and had nothing to add" finish reads to the
author exactly like "I never re-reviewed" — so it blocks the merge just the same.

### Always

- Do NOT commit, push, rebase, or merge anything yourself. Comment-only. The
  author's code agent reviews your suggestions and applies the changes. (See
  [`codex-instructions.md`](codex-instructions.md) for the full rationale; it
  applies to you too.)
- Do NOT skip the top-level summary comment. The author depends on it as the
  review-finished signal — on every round, findings or not.

### PRs into `main`

PRs with base `main` are closeout/promotion merges from `dev` and should **not**
be assigned regardless of review outcome — but you must **still leave a
top-level comment** so the author knows you reviewed (same signal requirement).

This `dev`/`main` distinction is the whole rule: **assign only on `dev` PRs with
findings; comment always, everywhere.**
