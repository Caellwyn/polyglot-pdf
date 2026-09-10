doc: docs/standards/hipaa-pii-policy.md
verified: backend/tests/test_no_pii_logging.py
because: Updated in this same bead (polyglot-pdf-e4dt8): two new per-surface rows (exception rendering, WS close events) and a correction to the stale 'remaining blind spot is the sink/shape' paragraph, whose exception-message case is now closed at the processor. The stale flag is a same-day ordering artifact -- the doc was stamped 2026-09-09 and test_no_pii_logging.py gained its sentinel case later that same day.
sha: a3e18e74d
