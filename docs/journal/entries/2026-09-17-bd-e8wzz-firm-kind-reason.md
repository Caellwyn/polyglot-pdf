---
date: 2026-09-17
bead: polyglot-pdf-e8wzz
tags: [security-audit, logging, pii, admin]
surfaces: [admin_backend/routes/firm_routes.py, admin_backend/tests/unit/test_audit_log_shapes.py, docs/standards/security-posture.md]
---

# e8wzz: the firm-kind reason is bounded and never logged; the PF-9 set pinned at zero

Sprint 23's PF-9 residual (the security audit, epic `polyglot-pdf-uijam`).
Workstream A closed the credit-adjust route's free-text `reason` (bounded,
kept in the ledger and audit row, dropped from the log line) and its review
found the second site: `PATCH /admin/firms/{firm_id}/kind` logged
`admin_firm_kind_set` with `reason=body.reason`, unbounded. The closing
report listed it as a P1-class item with neither a fix nor a written
acceptance; the maintainer chose the fix on 2026-09-17.

## What changed

- `SetKindRequest.reason` is `Field(max_length=credit_ledger.REASON_MAX_LENGTH)`
  -- the one number both operator free-text doors share (the module already
  imported `credit_ledger`). The audit row keeps the bounded text; the
  `admin_firm_kind_set` log line carries firm id, kind, actor uid and
  request id only.
- The set (scar #8): an AST walk over every route module in BOTH backends
  found exactly one log kwarg of the shape `<free-text name>=<body>.<attr>`
  (the grep's other hit, `credit_routes.py`'s `reason=body.reason`, is the
  ledger writer's argument, not a log call). The new
  `test_no_log_line_in_either_backend_carries_client_supplied_free_text`
  asserts that set is empty (names `reason`/`note(s)`/`comment(s)`/
  `description`/`message` off `body`/`req`/`request`/`payload`/`data`, on the
  terminal levels AND on `bind`/`new` -- fresh-eyes found the binder gap), and
  names the site when it is not. The per-route pin mirrors A's
  (`test_admin_firm_kind_set_log_line_has_no_reason`), and the bound is
  pinned against the ledger's constant.
- `docs/standards/security-posture.md`: the decision table records what the
  maintainer decided today -- PF-5 rate limiting (the in-app limiter plus an
  instance ceiling, `polyglot-pdf-o2fub`; Cloud Armor deferred), this fix,
  the bucket's public-access prevention (enforced 2026-09-17), container
  scanning (enabled 2026-09-17), the Cloud Build identity (deferred), the
  two Owners (the sole operator's two accounts; an accepted risk), and the
  Vertex abuse-monitoring opt-out (requested from Google, pending). The
  processor table's live-setting cell says so. `hipaa-pii-policy.md`'s ledger
  row points at the set pin.

## Verification

- Targeted: `admin_backend/tests/unit/test_audit_log_shapes.py` and
  `test_firm_routes.py` -- 98 passed.
- Scar #9, one interpreter each, RED: `reason=body.reason` restored on the
  log line (the per-route pin AND the set pin, which names
  `firm_routes.py:<line> reason=body.reason`); the `Field(max_length=...)`
  dropped (the bound pin). Both red as stated (2 failed with the site named; 1 failed), green restored.
- Full suite (both services + repo-level): 6594 passed, 289 skipped.

## Review record

Fresh-eyes (Sonnet, read-only): one gap -- the set pin watched the terminal
log levels but not structlog's `bind`/`new`, which this codebase uses to
attach context earlier; widened, and a `log.bind(reason=body.reason)`
mutation reddens it. Opus cross-surface round 1: three gaps, all
docs/test-durability -- `technical_guide.md`'s kind row did not state the
new bound (fixed, and the credit row with it, closing `g2wib`); the set pin
had no walked-something floor (it now asserts >= 20 modules and >= 100 log
calls examined, the sibling sweep's shape); `security-posture.md`'s
decisions framing, stamp and processor intro contradicted the rows the
first commit changed (fixed). Nits: the admin console's kind dialog has no
`maxLength` and renders a 422 as an opaque status (folded into `uanl9`,
which already covers the credit dialog on the same code path); the hipaa
sentence now says exactly which syntactic shape the pin proves. Round 2:
NO-GAPS. It re-verified the floors against the real counts (27 route
modules, 300+ log calls), the two guide rows against `admin-service.md`, and
the zero-hit claim against the two benign look-alikes (`credit_routes.py`'s
ledger argument; `deploy_webhook.py`'s local assignment).

## Files

`admin_backend/routes/firm_routes.py`, `admin_backend/tests/unit/test_audit_log_shapes.py`,
`docs/standards/security-posture.md`, `docs/standards/hipaa-pii-policy.md`.
