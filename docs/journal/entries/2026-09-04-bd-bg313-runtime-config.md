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

**A consequence worth flagging rather than silently fixing:** `deploy-demo.sh`
and `deploy-staging.sh` still set `LINK_MINTING_ENABLED=true` in
`BACKEND_EXTRA_ENV` (predating this bead). That line is now INERT for this
key -- the deployed backend falls back to the compiled-in env default
(`false`) until an operator seeds `app_config/{channel}` via the new CLI or
the console route. This is exactly the intended migration (moving the
setting off env), but it means minting silently goes dark on the next deploy
of either channel unless someone runs the seed step first. `deploy-demo.sh`
and `deploy-staging.sh` are outside this bead's declared surfaces, so they
were not edited; both docs updated below flag the inertness explicitly so it
is not discovered live.

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

Review outcomes recorded in the closeout ping.

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
