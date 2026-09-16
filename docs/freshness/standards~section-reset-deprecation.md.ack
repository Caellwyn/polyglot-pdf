doc: docs/standards/section-reset-deprecation.md
verified: backend/services/callback_handler.py, backend/services/form_filling_service.py, backend/services/request_coordinator.py
because: Reviewed for bd polyglot-pdf-2kbo0 (sprint 23 B1b). The only change to this doc's tracked files is the uniform log-kwarg rename error=str(exc) -> error_type=type(exc).__name__ (193 sites, AST-driven, no behavior or contract change) plus the /health trim in backend/main.py; this doc's claims were re-read against the diff and hold.
sha: ee134d0a0
