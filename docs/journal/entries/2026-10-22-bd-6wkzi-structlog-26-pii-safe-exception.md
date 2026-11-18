---
date: 2026-10-22
bead: polyglot-pdf-6wkzi
title: "chore(deps): upgrade structlog 23.2 -> 26.x with the PII exception guard intact"
tags: [security, testing]
---

## Trigger

Pinned back by bd niwcu after the grouped Dependabot #882 broke the staging verify gate: under structlog 26.1, six PII-guard tests failed (test_error_shape, test_no_pii_logging, test_structlog_json_output).

## What shipped

Root cause: structlog >= 24 forwards BoundLogger.exception() to logging.Logger.exception, which stamps the live exception onto the stdlib LogRecord; the root handler's Formatter then appended the full traceback -- exception MESSAGE (a field value) included -- after the already-scrubbed JSON line. structlog < 24 routed .exception() through .error(), keeping exc_info inside the processor chain. backend/utils/logging.py now configures PiiSafeBoundLogger, whose .exception() restores that routing. Mutation-verified: the stock BoundLogger turns exactly the six tests red under 26.1. Full suite under 26.1: 6763 passed. The niwcu Dependabot hold on structlog is released here.

## Lessons

A PII guard implemented as a processor only protects what passes through the processor chain; a library change at the stdlib boundary can bypass it entirely. Only the end-to-end tests that read the real handler OUTPUT caught this.

## Doc freshness

docs/standards/hipaa-pii-policy.md and logging-and-cost.md describe pii_safe_exception_processor; neither names the BoundLogger class, so no claim changed.

## Files touched

- backend/requirements.txt, backend/utils/logging.py
- .github/dependabot.yml, tests/test_dependabot_config.py (hold released)
