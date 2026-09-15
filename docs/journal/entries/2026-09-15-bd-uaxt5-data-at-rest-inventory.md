---
date: 2026-09-15
bead: polyglot-pdf-uaxt5
title: "audit(data-at-rest): A -- every persistent store inventoried, the operator's free text bounded and kept out of the logs, store shapes pinned"
tags: [security-audit, firestore, logging, testing, audit-scripts]
---

## Trigger

Sprint 23 (the security + data-leak audit, epic `polyglot-pdf-uijam`, plan
`docs/sprint_23_security-audit_plan.md`), workstream A, threat actor T3
(an insider with console or log access). Two pre-findings: PF-9, the
credit-adjust `reason` was unbounded operator free text stored verbatim in
the ledger AND the audit row AND written to Cloud Logging, with no
content allowlist on `admin_audit_log.before/after`; and PF-8's retention
half -- no store had a documented retention decision. Built by a Sonnet
builder in an isolated worktree over two rounds; the orchestrator ran the
review loops and closeout.

## What shipped

**The guard.** The credit-adjust `reason` is bounded at 500 characters at
BOTH doors -- the Pydantic model on the HTTP route and
`credit_ledger._validate`, which every ledger writer including the
`grant_credits.py` CLI passes through (one shared constant,
`REASON_MAX_LENGTH`) -- and the `admin_credits_adjusted` log line carries
ids and the amount only. `admin_backend/tests/unit/test_audit_log_shapes.py` pins
the exact `before`/`after` key set for EVERY route family that writes
`admin_audit_log` (credit, firm, user x3, sweep, link, kit, config, alert)
and two completeness tests make the set self-enumerating: every
`routes/*.py` file that calls `audit_log.record_*` must have a table row,
and every action constant referenced must be tabled -- the latter walks
the code with `ast`, follows an `action=` through function parameters and
the `asyncio.to_thread` indirection to each caller, and fails loudly on
anything it cannot resolve (a regex version had silently seen nothing
in three of the eight files). `firms` doc keys,
the links mint record and the `link_redemptions` record (a union that
includes `link_spend.py`'s spend fields, found during the round-2
derivation) are pinned in `backend/tests/unit/test_store_shapes.py`.

**The inventory.** `scripts/audit/inventory_stores.py` is the recurring
read-only check: operator ADC, `--project` required with the dead-project
and ADC-mismatch refusals from `scripts/grant_credits.py`, per collection
a sample of N docs reduced to key names, value types and max string
length -- never a value, with nested map keys reported by name one level
down -- flagged against `PINNED_ALLOWLISTS`, including the four
subcollections (`ledger`, `usage` under firms and kits, `link_usage`);
the kit bucket listed for unexpected objects; the BigQuery views' schemas. Exit
0 ran, 2 refused, 3 a store unreachable (never a silent skip).

**The live run (2026-09-15, redacted).** Every sampled document in every
collection sits inside its allowlist; the bucket holds 53 kit objects and
nothing unexpected; of the five BigQuery views only
`hosting_cost_by_service_month` exists on the project. The run itself
found two allowlist gaps before the clean pass -- `confirmation_events`
carries `section_id`/`link_jti`/`employee_id` from the session-start
event, which the sink's own test never covered, and `admin_audit_log`
gains `committed_ts`/`error` from the commit/fail transitions. The full
inventory table (store, key set, PII class, retention, readers, guard) is
on the bead for workstream G. Retention decisions are filed, not made:
`polyglot-pdf-t5v83`.

## Review record

**Fresh-eyes (sonnet): two rounds.** Round 1 GAPS-FOUND (1): the audit-log
pins covered 2 of the 8 route families -- the enumerate-the-set tell --
fixed in round 2 with the completeness tests; plus the attribution of the
refusal pattern to `read_confirmations.py` (it lives in
`grant_credits.py`) fixed in the script and the sprint plan. Recorded, not
gaps: the 422 on an over-long reason echoes the input (B1a's handler,
`wfgjz`); `user_routes.py` embeds the staff email in `admin_audit_log.target`
(a free-form string by design; noted for G).

**Opus cross-surface review: two rounds.** Round 1 GAPS-FOUND (2), both
adopted: the action-completeness test's regex matched nothing in three
files (rewritten with `ast`); the links allowlist lacked `opened_at`,
which every opened link carries, so the live inventory would have cried
wolf. Two of its three filed findings sat inside this bead's surfaces and
were fixed here rather than left filed: the CLI's unbounded door into the
ledger (`polyglot-pdf-bnkuv`) and the three usage subcollections missing
from the inventory (`polyglot-pdf-wg9yz`); the third, the admin console's
opaque 422 on a long reason, stays filed (`polyglot-pdf-uanl9`). Round 2
NO-GAPS: every ledger writer with a reason traced (the CLI surfaces the
bound as a clean refusal; the monthly top-up's templated reason is short;
refunds and mint debits carry none), the subcollection allowlists match
`usage_routes.py`'s reader allowlists exactly, nested keys never print a
value, and employee ids as map keys were judged internal identifiers, not
values. Filed: `polyglot-pdf-q2cu7` (two blind spots in the ast resolver:
an action passed by `**kwargs` spread, and a cross-module helper -- both
backstopped by `test_admin_audit_coverage.py`), `polyglot-pdf-g2wib` (the
technical guide's route row omits the 500-char bound); a third duplicated
`e8wzz` and was closed.

**Housekeeping reviewed and left:** other sessions' in-progress beads; the
stale-doc flags for files this branch did not touch. Prep suite: 6018
passed; final full suite after round 3: 6037 passed.

## Lessons

- **Sample the live store before trusting the writer's test.** The sink
  test pinned two of four event shapes; twenty real documents found the
  other two in one run. An allowlist derived from tests alone is only as
  complete as the tests.
- **A per-route pin needs a completeness test or it is a per-route
  example.** Two routes pinned looked like coverage until the grep counted
  eight.
- **Local tool breakage is not a finding.** `bq` failed on a stray
  `python3.14` shim; the script says so and exits 3 instead of pretending
  the store is fine.

## Doc freshness

Bumped: `docs/components/admin-service.md` (the credits/adjust row + one
stamp line). Reviewed and left: `docs/standards/hipaa-pii-policy.md` -- the
ledger `reason` and audit-log `before/after` rows are workstream G's
per-surface additions, per the plan.

## Files touched

- admin_backend/routes/credit_routes.py -- reason bounded; log line ids only
- backend/services/credit_ledger.py -- REASON_MAX_LENGTH enforced for every ledger writer
- scripts/audit/inventory_stores.py -- the read-only inventory (new)
- admin_backend/tests/unit/test_audit_log_shapes.py -- per-route pins + completeness (new)
- backend/tests/unit/test_store_shapes.py -- links / link_redemptions pins (new)
- tests/test_inventory_stores_script.py -- refusal + redaction pins (new)
- docs/components/admin-service.md -- row + stamp
- docs/sprint_23_security-audit_plan.md -- one attribution phrase
- docs/journal/entries/2026-09-15-bd-uaxt5-data-at-rest-inventory.md -- this entry
