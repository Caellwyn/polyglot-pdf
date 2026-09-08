---
date: 2026-09-04
bead: polyglot-pdf-bg313
title: "feat(backend): 1.5 runtime config app_config/{channel} with TTL + last-known-good; swap the three os.getenv reads"
sprint: 22
tags: [refactor, security, testing]
---

## Trigger

Epic 1 child 1.5 of the admin-console program
(`docs/sprint_22_admin-console_plan.md`, "Runtime config"). Three settings
that gate paid, unauthenticated client-link minting -- `LINK_MINTING_ENABLED`,
`LINK_COST_CEILING_USD`, `LINK_FIRM_CAP` -- lived in deploy-time env, so
retuning any of them meant a redeploy. The admin console (later beads) needs
somewhere to write these without a code change, and Epic 2 needs a fourth,
brand-new key (`CREDITS_ENFORCED`) with no env history at all.

## What shipped

New `backend/services/runtime_config.py`: one Firestore doc per channel,
`app_config/{channel}`, read through a `RUNTIME_CONFIG_KEYS` frozenset. The
fallback order on any read failure is LAST-KNOWN-GOOD (this process's own
previous successful read of that key) first, then -- only when nothing was
ever read -- the env-shaped default. Env-first would have been wrong: a
console that just lowered the ceiling must not see the old, higher default
reappear during a Firestore blip. A per-channel TTL cache (45s, inside the
bead's 30-60s bound) keeps this off the request hot path while still letting
a console flip land within the TTL with no redeploy. Deliberately NOT
`get_settings()` (`backend/config.py`'s pydantic `Settings`), which is
`lru_cached` for the whole process lifetime and would never see a change.

The three existing call sites were swapped: `link_routes.py`'s
`_minting_enabled()` and `link_budget.py`'s `firm_link_cap()` /
`default_cost_ceiling_usd()` now call into `runtime_config` instead of
`os.getenv`. `CREDITS_ENFORCED` has no call site to swap (Epic 2 bead A3 is
its first and only reader) but ships in the module now so that bead needs no
runtime_config change of its own.

`scripts/set_runtime_config.py` is the operator CLI: `get` reads a channel's
doc, `set` validates a key against `RUNTIME_CONFIG_KEYS` and a value against
the SAME coercion the reader applies (via a new public `coerce_value`
wrapper) before writing with `merge=True`. It exists so exit criterion 3
(flipping `LINK_MINTING_ENABLED` on staging changes `/api/links/mint` inside
the TTL with no redeploy) is verifiable before the admin console's own
`PUT /admin/config/{channel}` route ships (bd `polyglot-pdf-li9x0`).

**A consequence flagged in round 1, then corrected in round 2 below:**
`deploy-demo.sh` and `deploy-staging.sh` still set
`LINK_MINTING_ENABLED=true` in `BACKEND_EXTRA_ENV` (predating this bead).
Round 1 shipped `_ENV_DEFAULTS` as compiled-in Python constants, which made
that env line dead text the moment `runtime_config.py` existed -- see
"Review round 2" below for why that was wrong and how it was fixed before
merge.

## Lessons

Swapping a value's SOURCE (env -> a resolver module) breaks every test that
patches the OLD source directly, even when the two are meant to be
behaviorally identical. `os.getenv`/`monkeypatch.setenv` patches at the
process level and works no matter how many modules re-import a function; a
resolver-module swap does not, because `from module import name` binds a
name at import time -- patching the resolver module's attribute after that
import has no effect on the importer's own copy. Every test in
`test_link_budget.py`, `test_link_metering.py`, and `test_link_spend.py` that
retuned a cap via `monkeypatch.setenv` needed patching at whichever module
actually CALLS the resolver (its own `_rc_*` bound name, or the caller's
directly-imported function), not at `runtime_config`'s own module attribute.
The tell was "assert 30 == 75" style failures where the patch visibly took
effect on the object graph. No standards doc needed; this is standard
Python re-import-by-value behavior, not a project-specific rule.

## Doc freshness

- `docs/technical_guide.md` (no stamp by design): corrected the
  `/api/links/mint` route-table entry and the client-magic-links narrative
  section, both of which described `LINK_MINTING_ENABLED` as a live
  deploy-time flag "both channels now enable" -- no longer true. Added
  Surface contract 14 documenting the new producer/consumer/fallback shape.
- `docs/components/config-deployment.md` (Tracks `deploy-demo.sh`,
  `deploy-staging.sh`, among others): its client-magic-links bullet made the
  same now-false claim about the env line configuring anything for these
  three keys; corrected and stamp bumped with a parenthetical under
  2026-09-04.
- No other tier-2 doc's Tracks line covers `backend/services/runtime_config.py`,
  `backend/routes/link_routes.py`, or `backend/services/link_budget.py` by
  name; `scripts/check_doc_freshness.py` confirms both touched docs are OK
  and lists no newly-stale doc caused by this change (the STALE entries it
  reports are pre-existing drift from unrelated files this bead did not
  touch).

## Review round 1 (Opus cross-surface)

**Adopted (blocker, fixed in the worktree):** `link_routes.py`'s `mint_link`
called the new `_minting_enabled()` synchronously on the event loop.
Pre-swap this was a free `os.getenv`; post-swap a TTL-expiry cache miss makes
it a sync Admin-SDK Firestore read, which -- unwrapped -- blocks the shared
Cloud Run loop for every concurrent request on that instance, in-flight
client audio included. This is exactly the hazard `services/auth.py`'s
`require_auth` already documents in a comment, and the same file's other two
Firestore touches (`get_allowed_kits`, `enforce_link_redemption`) already
wrap in `asyncio.to_thread`. Fixed: `if not await asyncio.to_thread(_minting_enabled):`.
Added `test_the_minting_flag_check_runs_OFF_the_event_loop`
(`backend/tests/unit/test_link_routes.py`), which spies on `asyncio.to_thread`
rather than comparing thread identities -- `TestClient` runs the whole ASGI
app in its own worker thread regardless of what the route does internally,
so an identity comparison against the pytest thread is not a reliable
signal; asserting the resolver was actually dispatched through `to_thread`
is. Mutation-verified: reverting to a direct `_minting_enabled()` call turns
the new test red (`AssertionError: _minting_enabled was not dispatched via
asyncio.to_thread`); restoring the fix turns it green, and the full
`test_link_routes.py` + `test_runtime_config.py` suites (54 tests) still pass.

**Deferred (bead already filed by the reviewer, not fixed here):**
- `polyglot-pdf-b42qp` -- `record_mint()` at `link_routes.py:196` is the SAME
  hazard on the mint path, but it PRE-EXISTS on `origin/dev` (unchanged by
  this bead beyond making it marginally worse: `record_mint` now also calls
  `firm_link_cap()`, a second TTL-cached Firestore read). Out of this bead's
  scope; fix tracked separately.
- `polyglot-pdf-43eup` (nit) -- `MintLinkPage.tsx`'s "minting is off" operator
  message still names `LINK_MINTING_ENABLED` as something to set on the
  backend (i.e. via env/redeploy), which is now inert guidance post-swap. The
  key name is still correct; only the mechanism described is stale.
- `polyglot-pdf-uidpu` (nit) -- `link_budget.py`'s `_positive_int` helper is
  dead code: its only caller, `firm_link_cap()`, was rewritten in this bead to
  delegate to `runtime_config.link_firm_cap()`. `_positive_float` is still
  live (used by `cost_ceiling_usd_for_kit`).

**Refuted / no action (reviewer's own non-findings, restated for the
record):** the missing explicit `firestore.rules` deny block for
`app_config/**` is deferred by design to `polyglot-pdf-li9x0` per the plan
(`docs/sprint_22_admin-console_plan.md:359-360`); `_last_known_good`
cannot leak (at most 4 entries, one channel per process); the module-global
cache is safe under the GIL for this access pattern.

**Missed in round 1, caught by the finisher after review (see "Review round
2" below):** round 1 treated the demo/staging minting turn-off on the next
deploy as an intended, already-documented operational trap rather than a
gap. It was actually a real defect -- see round 2.

STATUS after round 1: the blocker is fixed; both nits and the pre-existing
finding are tracked as separate beads per the reviewer's filing. Round 1
believed no further gaps were outstanding; round 2 (below) found one.

## Review round 2 (finisher, post-review)

**Adopted (blocker, fixed before merge):** round 1's `_ENV_DEFAULTS` for the
three legacy keys (`LINK_MINTING_ENABLED`, `LINK_COST_CEILING_USD`,
`LINK_FIRM_CAP`) were compiled-in Python constants, not the deploy-time
environment variable the plan's "env default" language meant
(`docs/sprint_22_admin-console_plan.md`, "Runtime config": "the env default
only when nothing was ever read"). That made `deploy-staging.sh` /
`deploy-demo.sh`'s `LINK_MINTING_ENABLED=true` (`BACKEND_EXTRA_ENV`) dead
text the moment this bead shipped: a fresh process on either channel, before
anyone seeded `app_config/{channel}`, would silently mint OFF instead of ON
-- exactly the "minting silently goes dark on the next deploy" consequence
round 1 flagged as intended and by-design, when it was in fact an
unauthorized behavior change the plan never called for.

Fixed: `runtime_config.py` now reads `os.getenv` for the three legacy keys
ITSELF, inside a new `_legacy_env_default()`, parsed exactly as the pre-bg313
call sites parsed them (`LINK_MINTING_ENABLED`: case-insensitive `"true"`;
`LINK_COST_CEILING_USD`: positive float; `LINK_FIRM_CAP`: positive int),
falling back to the compiled constant only when the variable is unset or
fails to parse. `CREDITS_ENFORCED` is unchanged -- brand new, no pre-bg313
call site, stays compiled `false` with no env read at all (still pinned by
`test_credits_enforced_has_no_env_read_anywhere`). Fallback order is
unchanged: last-known-good still beats the env var, which still beats the
compiled constant -- a console that lowers the ceiling must not see a higher
value from EITHER source reappear during a blip.

`test_no_shipped_source_reads_this_key_from_env_outside_runtime_config`
(exit criterion 2) still passes unmodified -- it already excluded
`runtime_config.py` from the search. Added its mirror,
`test_runtime_config_itself_still_reads_the_legacy_env_var`, asserting the
three legacy names DO appear as an `os.getenv` read inside
`runtime_config.py`, so this fallback cannot be silently deleted again
without CI catching it. Added three behavioral tests: store unreachable +
`LINK_MINTING_ENABLED=true` in env -> minting on; store unreachable + no env
-> minting off (the historical fail-safe default still holds); a lowered
ceiling read once survives a later broken read even when the environment
holds a higher value (last-known-good still wins over env, not just over the
compiled constant). All four mutation-verified: reverting each corresponding
line in `_legacy_env_default` / `_resolve` turned its test red, restoring it
turned the suite green again.

Corrected every prose claim this bead had made that the env line was inert
or that minting falls to off after this change: this module's own docstring,
`docs/components/config-deployment.md`, `docs/components/auth.md`, this
journal entry (see the corrected "A consequence" note above and the
"Refuted" section), and `docs/technical_guide.md`'s route-table entry,
narrative section, and Surface contract 14. The deploy scripts themselves
needed no edit -- their env lines were already correct; only the module that
was supposed to read them was wrong.

STATUS after round 2: the deploy-time env fallback is restored and pinned by
CI; no further gaps outstanding for this bead.

## Files touched

- `backend/services/runtime_config.py` -- new module (the reader + fallback + TTL cache)
- `backend/tests/unit/test_runtime_config.py` -- new test file
- `backend/routes/link_routes.py` -- `_minting_enabled()` swapped to runtime_config
- `backend/services/link_budget.py` -- `firm_link_cap()` / `default_cost_ceiling_usd()` swapped to runtime_config
- `backend/tests/unit/test_link_routes.py` -- fixture + interlock test repatched off env
- `backend/tests/unit/test_link_budget.py` -- global-tuning tests repatched off env; malformed-value cases moved to test_runtime_config.py
- `backend/tests/unit/test_link_metering.py` -- allowance-tunability test repatched off env
- `backend/tests/unit/test_link_spend.py` -- retuned-ceiling test repatched off env
- `scripts/set_runtime_config.py` -- new operator CLI
- `docs/technical_guide.md` -- route-table entry + narrative correction + new Surface contract 14
- `docs/components/config-deployment.md` -- client-magic-links bullet correction + stamp bump
