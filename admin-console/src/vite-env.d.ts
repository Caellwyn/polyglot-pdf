/// <reference types="vite/client" />
// Vite's client types: makes import.meta.env (VITE_* build config) typecheck.
// The admin console reads VITE_ADMIN_API_BASE_URL and VITE_FIREBASE_* (bd
// polyglot-pdf-b6943), mirroring schema-editor's vite-env.d.ts.

/** The commit SHA this build was made from, injected by vite.config.ts's
 * `define` block at BUILD time (bd polyglot-pdf-b6943). A `git rev-parse
 * HEAD` failure at build time (no git binary, build run outside a checkout)
 * falls back to the literal string 'unknown'. */
declare const __ADMIN_CONSOLE_GIT_SHA__: string;
