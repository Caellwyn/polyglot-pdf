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

## Fresh-eyes fix round (2026-09-15)

The outer cross-surface review (Opus) came back GAPS-FOUND(1), with two
findings; both were ADOPTED, no rejections or deferrals:

- **Adopted -- Surface contract 17's producer-shape prose was stale.**
  `docs/technical_guide.md`'s Surface contract 17 (admin console -> admin
  service) documented `GET /admin/config/{channel}`'s response as
  `{channel, values, known_keys, unknown_keys}` -- true on `origin/dev`,
  but this bead's own `schema` addition (contract 1 above) made it
  incomplete without a matching edit here. Unlike contract 14 (deliberately
  left alone above, because it covers the write/consumer path this bead did
  not touch), contract 17 IS the GET response's own producer-shape bullet,
  so the gap was real and in-scope. Fixed both the contract-17 prose (line
  ~1276) and the `/admin/config/{channel}` route-table row (line 166) to
  name `schema` and point at `config_schema()`.
- **Adopted -- `CONFIG_KEY_TYPES`/`ConfigKeyType` were dead exports.**
  `adminApi.ts` defined `CONFIG_KEY_TYPES` specifically to be the console's
  one source of truth for a key's type, but `ConfigEditorPage.tsx`'s
  `controlKind()` re-hardcoded the literal strings `'bool'`/`'int'`/
  `'float'` instead of consuming it -- the exact "second hand-typed list"
  CLAUDE.md scar #8 exists to prevent, and it would have silently drifted
  from `CONFIG_KEY_TYPES` if a fourth type were ever added there. Added
  `isKnownConfigKeyType()`, a type guard built directly off
  `CONFIG_KEY_TYPES`, and rewrote `controlKind()` to use it instead of the
  literals. Mutation-verified: temporarily dropping `'float'` from
  `CONFIG_KEY_TYPES` reddened the two float-control tests in
  `ConfigEditorPage.test.tsx` (they were previously insensitive to the
  constant's contents), confirming the wiring is real, then restored the
  file byte-for-byte.

Both fixes are non-behavioral for the app's runtime (same controls render,
same values are sent) except that the second one now makes a future type
added to `CONFIG_KEY_TYPES` alone insufficient on its own to add a control
for it -- exactly the intended tightening. Re-ran the full suites after
both fixes: backend 3752 passed / 195 skipped / 3 deselected, admin_backend
587 passed, root tests 1653 passed / 92 skipped, admin-console vitest 152
passed (11 in `ConfigEditorPage.test.tsx`), `tsc --noEmit` clean.

## Cross-surface review round (2026-09-15)

A second review pass (Opus cross-surface) came back GAPS-FOUND(1) against
the tree from the fresh-eyes fix round above. Breakdown:

- **Deferred (filed as a bead, not fixed here) -- pre-existing int
  truncation.** `runtime_config._coerce()`'s `int(raw)` silently truncates a
  fractional value (e.g. `45.7` -> `45`) for an int-typed key instead of
  rejecting it. The reviewer confirmed this line is byte-identical on
  `origin/dev` -- this bead did not introduce the truncation, it only made
  it easier to trigger by hand by replacing a plain text box with a number
  spinner that invites fractional entry for an int field. Per the
  pre-existing/out-of-scope routing rule, filed as its own bug bead,
  `polyglot-pdf-w6kq1` (bug(runtime-config): int-typed config keys silently
  truncate a fractional value instead of rejecting it), rather than treated
  as a gap in this diff.
- **Deferred (nit, filed as a bead, not fixed here) -- empty-draft-Save
  silent no-op.** `handleSave`'s new UNSET guard
  (`if (draft === undefined || draft === UNSET) return;`) silently no-ops
  instead of surfacing any feedback when Save is clicked on an UNSET draft.
  The reviewer classified this as a nit rather than a rubric-fail or
  blocker: it is currently unreachable (all five `RUNTIME_CONFIG_KEYS` are
  typed bool/int/float, so no live path clicks Save on a lingering UNSET
  draft today), and it does not violate either of the bead's two exit
  criteria. It IS inside this bead's own newly-touched `handleSave` code
  (not a separate pre-existing defect), so it was recorded as in-scope
  commentary but not filed as a standalone bead by the reviewer. Bundled
  into a new nits bead, `polyglot-pdf-djnr3` (chore(nits): deferred review
  nits from polyglot-pdf-wxcj0), filed during this fix round since the
  reviewer had not filed one itself.
- **No code changes this round.** Both findings route to beads rather than
  an inline fix -- one because it is a pre-existing, out-of-scope defect,
  the other because it is a nit with zero current reachability. Re-ran the
  full backend and admin-console suites after filing both beads to confirm
  the tree was already green (no behavior changed): unchanged from the
  fresh-eyes round's counts above.

## Files touched

- `backend/services/runtime_config.py` -- `KEY_TYPES` dict + `config_schema()`.
- `backend/tests/unit/test_runtime_config.py` -- `KEY_TYPES` coverage/shape tests, `config_schema()` shape + live-env-default test.
- `admin_backend/routes/config_routes.py` -- GET response gains `schema`.
- `admin_backend/tests/unit/test_config_routes.py` -- schema-matches-RUNTIME_CONFIG_KEYS test + a KEY_TYPES-drops-a-key mutation test.
- `admin-console/src/utils/adminApi.ts` -- `ConfigKeySchema` type, `ChannelConfig.schema` field.
- `admin-console/src/components/ConfigEditorPage.tsx` -- schema-driven bool-select/number-input/text rendering, typed PUT values; fresh-eyes round adds `isKnownConfigKeyType()` wiring `controlKind()` to `CONFIG_KEY_TYPES`.
- `admin-console/src/components/ConfigEditorPage.test.tsx` -- bool/int/float/unknown-type rendering tests, typed-value-sent tests, unset-select-does-not-save test.
- `docs/components/admin-service.md` -- dated entry + Runtime config bullet update.
- `docs/technical_guide.md` -- fresh-eyes round: Surface contract 17 producer-shape prose and the `/admin/config/{channel}` route-table row now name the `schema` field.
