"""Shared pytest setup for the harness-tooling suite (bd polyglot-pdf-5xhbb).

This is one of pytest.ini's three testpaths (backend/tests and
admin_backend/tests are the others, each carrying this same module-level
guard in its own conftest.py). tests/test_stress_harness_units.py
constructs backend.config.Settings() directly (e.g. via
scripts/spikes/measure_form_session_costs.py's CLI-arg-to-Settings path),
so it inherits the same K_SERVICE-from-the-ambient-shell exposure
backend/tests/conftest.py exists to close -- but that fixture lives under
backend/tests and never runs for this suite.

Strip K_SERVICE at IMPORT time (before pytest collects anything under this
testpath), matching backend/tests/conftest.py's module-level guard. Ambient
K_SERVICE + VFF_DISABLE_AUTH=true otherwise reddens
test_dry_run_i90_full_emits_summary / test_dry_run_i90_full_drain_round_trip
/ test_dry_run_legacy_i90_arm_still_runs with the deployed-service
VFF_DISABLE_AUTH guard's ValidationError (reproduced).
"""
import os

os.environ.pop("K_SERVICE", None)
