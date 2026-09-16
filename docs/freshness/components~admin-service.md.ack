doc: docs/components/admin-service.md
verified: scripts/bootstrap_admin_user.py
because: bd polyglot-pdf-rdftu touched these ONLY to add creationflags=windowless_creationflags() to their existing subprocess spawns -- Windows console-window suppression (CREATE_NO_WINDOW), which is a no-op off Windows. No behavior, CLI surface, env var, IAM grant or deploy step changed, so nothing this doc asserts about these scripts is affected. Re-read the doc's claims about them and they remain accurate.
sha: f2d77ce19
