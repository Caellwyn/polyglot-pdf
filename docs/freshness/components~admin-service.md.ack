doc: docs/components/admin-service.md
verified: admin-console, admin_backend/main.py, admin_backend/routes/usage_routes.py, deploy-admin.sh, scripts/setup-admin-service.sh
because: Reviewed for bd polyglot-pdf-wfgjz (sprint 23 B1a). B1a changed only: the value-free 422 handler installed in backend/main.py + admin_backend/main.py, a K_SERVICE INFO floor in backend/utils/logging.py, K_SERVICE forcing LIVE_DEV_TRANSCRIPTS/LIVE_DEV_AUDIO_DUMP off in backend/config.py, the SEND_TRANSCRIPT env knob gated on no K_SERVICE in websocket_routes.py, and the token-usage print banner -> structlog event + .env.DEV gate on the token file in live_ai_gemini.py. This doc makes no claim about any of those; its other claims were not re-verified here.
sha: eb9992862
