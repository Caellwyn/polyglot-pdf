doc: docs/standards/section-reset-deprecation.md
verified: backend/config.py, frontend/src/webFormConnection.ts
because: Reviewed for bd polyglot-pdf-bwevj (sprint 23 C2). The tracked files changed only by the WebSocket credential moving from the URL into the first frame (plus the Origin check, the text-frame cap, the K_SERVICE gate on the dev sockets and the staff kit-scope gate on /ws/fill), the shared browser_origins() list in config.py/main.py, and the channel env CORS lists; this doc's claims were re-read against the diff and hold.
sha: 7d4b81b77
