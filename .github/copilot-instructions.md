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

### When you have zero findings (the code is satisfactory)

This is the case you have historically skipped or paraphrased. **Do not skip it,
and do not reword it.** A satisfied review still REQUIRES a top-level comment, and
that comment's body must be **EXACTLY** this, with nothing before or after it:

```
LGTM
```

That is the entire body: the four characters `LGTM`, on their own, no preamble, no
summary, no "I checked the branch and…", no restating what changed, no mention of
commit SHAs. One word. The author's polling agent greps for a body that is exactly
`LGTM`; any extra prose ("already addressed", "looks good but…", a summary
paragraph) defeats the deterministic match and stalls the merge.

- If the platform lets you submit an **Approve** review, put `LGTM` in that
  review's summary body. Otherwise post `LGTM` as a top-level issue comment.
- Do NOT add a second comment in addition to the `LGTM`.
- Do NOT assign the PR — there's nothing for the follow-up agent to respond to.

Why a single fixed word and not a phrase of your choosing: you have, on prior
rounds, invented new approval wordings the author's matcher did not recognize
(e.g. "the prior findings are already addressed in <sha>"). Each novel phrasing
forced a code change on the author's side. `LGTM` — exact, alone — is the contract
that ends that. "The work is satisfactory" is **not** a reason to stay silent or
to editorialize; it is precisely the case this one-word signal exists for.

### Round 2 and later

Even when the previous round had findings and they have **all** been addressed,
you must still post the exact `LGTM` body (per the zero-findings rule above) —
**not** a sentence describing that the findings were addressed. "The prior
findings are now resolved" is exactly the paraphrase that breaks the matcher; the
correct response to "all findings addressed, nothing new" is the single word
`LGTM`. A silent "I looked again and had nothing to add" finish reads to the
author exactly like "I never re-reviewed" — so it blocks the merge just the same.

### Always

- Do NOT commit, push, rebase, or merge anything yourself — not even an
  "obvious" one-line fix. Comment-only. The author's code agent reviews your
  suggestions and applies the changes. Committing directly breaks the author's
  ability to rebase/amend cleanly, can conflict with their in-progress local
  work, muddies the review history, and turns a reviewable finding into a silent
  fix nobody checks. (The Codex reviewer carries the same rule in its
  "If you are reviewing a PR" section of [`AGENTS.md`](../AGENTS.md).)
- Do NOT skip the top-level summary comment. The author depends on it as the
  review-finished signal — on every round, findings or not.

### PRs into `main`

PRs with base `main` are closeout/promotion merges from `dev` and should **not**
be assigned regardless of review outcome — but you must **still leave a
top-level comment** so the author knows you reviewed (same signal requirement).

This `dev`/`main` distinction is the whole rule: **assign only on `dev` PRs with
findings; comment always, everywhere.**
