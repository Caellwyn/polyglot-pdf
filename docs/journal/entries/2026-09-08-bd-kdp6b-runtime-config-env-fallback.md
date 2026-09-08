---
date: 2026-09-08
bead: polyglot-pdf-kdp6b
title: "fix(runtime-config): legacy env fallback must be a live os.getenv read, not a compiled constant"
sprint: 22
tags: [hotfix, testing]
---

## Trigger

Bead 1.5 (`polyglot-pdf-bg313`, PR #735) moved `LINK_MINTING_ENABLED`,
`LINK_COST_CEILING_USD` and `LINK_FIRM_CAP` to the Firestore runtime-config
document with a fallback chain. Its finisher noticed, after both reviews had
cleared, that the final fallback was a set of compiled-in constants, so the
deploy scripts' `LINK_MINTING_ENABLED=true` had become inert: the next deploy
of either channel would have turned link minting off until an operator
seeded `app_config/{channel}`. The fix was written and re-reviewed on the
bead branch (fresh-eyes two rounds, Opus cross-surface one round, all clean)
but the push was rejected because the maintainer had merged dev into the
branch and then merged the PR in the meantime, so dev carried the defect.

## What shipped

The reviewed fix, cherry-picked onto dev under its own bead.
`backend/services/runtime_config.py` gains `_legacy_env_default(key)`: for
the three legacy keys it reads the deploy-time environment variable live,
parsed exactly as the pre-bg313 call sites parsed it, and uses the compiled
constant only when the variable is unset or unparsable. `CREDITS_ENFORCED`
stays compiled `False` and never reads env. The fallback order is
Firestore document, then last-known-good, then the env variable, then the
constant. Tests pin that `runtime_config.py` itself reads the three names
from env (so the fallback cannot be dropped silently again), the on/off
behaviour with an unreachable store, and that a lowered ceiling survives a
broken read even when env holds a higher value. The prose in
`config-deployment.md`, `auth.md`, `technical_guide.md` and the bead 1.5
journal entry that described the env line as inert is corrected.

Review outcomes for this PR are recorded in the closeout ping.

## Lessons

- **A merge by a human between review and push is a race the finisher
  cannot win.** The finisher correctly refused to force-push, but the PR was
  merged before anyone read its "hold" note. When a fix is ready and
  reviewed, push it immediately and let the PR show it; do not hold a
  reviewed commit locally waiting for a later pipeline stage.
- **"Env default" in a plan means the deploy-time variable, not a constant.**
  The plan's fallback wording was read two ways by two builders; the
  reviewers only caught it by tracing the deploy scripts. Name the concrete
  read (`os.getenv`) in the bead when a fallback is load-bearing.

## Doc freshness

`docs/components/config-deployment.md` and `docs/components/auth.md` stamped
2026-09-08; `docs/technical_guide.md` prose updated (no stamp by design).
Other STALE flags from the freshness checker track files this bead did not
touch and were left.

## Files touched

- `backend/services/runtime_config.py`
- `backend/tests/unit/test_runtime_config.py`
- `docs/components/config-deployment.md`
- `docs/components/auth.md`
- `docs/technical_guide.md`
- `docs/journal/entries/2026-09-04-bd-bg313-runtime-config.md`
- `docs/journal/entries/2026-09-08-bd-kdp6b-runtime-config-env-fallback.md` (this entry)
