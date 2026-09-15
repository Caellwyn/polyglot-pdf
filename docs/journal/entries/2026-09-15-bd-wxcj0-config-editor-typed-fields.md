---
date: 2026-09-15
bead: polyglot-pdf-wxcj0
title: "feat(admin-console): runtime-config editor renders booleans as selects and numbers as number inputs, schema-driven"
sprint: 22
tags: [refactor, testing]
---

## Trigger

Maintainer feedback on 2026-09-15, right after their first sign-in to the
admin console: "in config, true/false flags should be select fields, not
text fields." The Runtime config page (`admin-console/src/components/
ConfigEditorPage.tsx`) rendered every `RUNTIME_CONFIG_KEYS` key -- bools,
ints, and a float -- as the same plain text input, so setting
`LINK_MINTING_ENABLED` meant typing the literal string `true` into a text
box with no guardrail against a typo like `1` or `yes`.

## What shipped

The type for each runtime-config key already existed exactly once, as the
comment block at the top of `backend/services/runtime_config.py` (bool /
float / int / bool / int for the five keys) -- but only as prose, never as
data anything could read. This bead turned that prose into a real dict,
`KEY_TYPES`, and exposed it to the console rather than letting the console
re-derive or hand-list the same five types a second time (CLAUDE.md scar
#8, "one rule, one home").

- `backend/services/runtime_config.py` gains `KEY_TYPES: dict[str, str]`
  (`"bool" | "int" | "float"` per key) and a new public `config_schema()`
  that returns `{key: {type, default}}` for every key in
  `RUNTIME_CONFIG_KEYS`, iterating the KEYS set (not KEY_TYPES) so a key
  present in one but not the other is a loud `KeyError`, never a silently
  incomplete schema. `default` calls the SAME `_legacy_env_default()` a real
  read already falls back to -- not a second copy of the env-parsing logic,
  and not a value frozen at import time (a `LINK_FIRM_CAP` env override is
  reflected in the schema immediately, pinned by a dedicated test).
- `admin_backend/routes/config_routes.py`'s `GET /admin/config/{channel}`
  response gains a `schema` field, `runtime_config.config_schema()` verbatim
  -- no new validation, no new Firestore read; the route already imported
  `runtime_config` for `RUNTIME_CONFIG_KEYS` and `coerce_value`.
- `admin-console/src/utils/adminApi.ts` gains the `ConfigKeySchema` type and
  `ChannelConfig.schema` field.
- `admin-console/src/components/ConfigEditorPage.tsx` now looks at
  `schema[key].type` to decide each row's control: `bool` renders a
  `<select>` of `true`/`false` plus an explicit "unset -- use the fallback"
  placeholder option (distinct from a real `false`); `int`/`float` render a
  number input with `step="1"` or `step="any"`; anything else (a type the
  console does not recognize, or a key `schema` never described -- a stale
  deploy skew) falls back to the original plain text input, unchanged.
  Whichever control renders, `handleSave` now converts the draft to a TYPED
  JSON value before calling `setChannelConfigKey` -- a real `true`/`false`
  boolean or a JS `Number`, never the string `"true"` a naive text binding
  would still send -- so `runtime_config.coerce_value` on the server sees
  exactly the type it already expects. An unparsable number input never
  reaches the server as `NaN` (which `JSON.stringify` would silently turn
  into `null`); it surfaces the same "not a valid value" shape a server
  rejection would show, client-side, before the PUT ever fires.
- No change to `app_config/{channel}`'s stored shape, `coerce_value`'s
  validation rules, or the audit-in-transaction write path -- this bead is
  purely "how does the console DISPLAY and EDIT a value", not "what values
  are valid" (that judgment still lives entirely server-side, per the
  route's own docstring).

Nothing was deferred; the bead's two exit criteria were both achievable in
one PR-sized change.

## Lessons

The type-per-key list already existed as a prose comment in
`runtime_config.py` before this bead -- it just was not DATA, so nothing
could consume it without re-typing the same five (key, type) pairs a second
time somewhere else. When a bead's job is "expose a fact the backend already
knows to a client," check whether that fact is sitting in a docstring/
comment first: turning prose into a small dict is often the whole fix, and
it is the CLAUDE.md scar #8 move (one home for a rule) rather than a
judgment call about design.

## Doc freshness

`docs/components/admin-service.md` (Tracks admin_backend/routes/
config_routes.py and admin-console/) bumped: a dated changelog entry for
this bead, and the Runtime config page bullet now describes the
schema-driven controls. `docs/technical_guide.md`'s Surface contract 14
(runtime config) and the `GET /admin/config/{channel}` route-table row are
NOT updated in this pass -- the bead's own Surfaces list does not name
`docs/technical_guide.md`, and the added `schema` field is additive (no
existing consumer's read of `values`/`known_keys`/`unknown_keys` changes),
so it is flagged for the outer reviewer as a changed contract rather than
edited unprompted.

`closeout_prep.py` also flags `docs/components/config-deployment.md` as
STALE relative to `admin_backend/routes/config_routes.py` and
`admin-console/`'s new mtimes (that doc's Tracks line names both paths for
DEPLOY-topology reasons -- env vars, Hosting sites, IAM). Reviewed: its
prose describes deploy mechanics, not the config route's response shape or
the console's rendering, and neither changed here (no new env var, deploy
step, Hosting site, or IAM grant) -- left as-is rather than bumping the
stamp with no real content change. Every other STALE doc `closeout_prep.py`
listed is stale against files this bead did not touch at all (websocket
routing, PDF filling, voice/VAD, etc.) and is left for whichever bead is
already working that surface.

Review outcomes recorded in the closeout ping.

## Files touched

- `backend/services/runtime_config.py` -- `KEY_TYPES` dict + `config_schema()`.
- `backend/tests/unit/test_runtime_config.py` -- `KEY_TYPES` coverage/shape tests, `config_schema()` shape + live-env-default test.
- `admin_backend/routes/config_routes.py` -- GET response gains `schema`.
- `admin_backend/tests/unit/test_config_routes.py` -- schema-matches-RUNTIME_CONFIG_KEYS test + a KEY_TYPES-drops-a-key mutation test.
- `admin-console/src/utils/adminApi.ts` -- `ConfigKeySchema` type, `ChannelConfig.schema` field.
- `admin-console/src/components/ConfigEditorPage.tsx` -- schema-driven bool-select/number-input/text rendering, typed PUT values.
- `admin-console/src/components/ConfigEditorPage.test.tsx` -- bool/int/float/unknown-type rendering tests, typed-value-sent tests, unset-select-does-not-save test.
- `docs/components/admin-service.md` -- dated entry + Runtime config bullet update.
