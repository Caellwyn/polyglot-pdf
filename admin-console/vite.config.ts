/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { execSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

// Vite's dev server only serves files under server.fs.allow (default: the project
// root). When this console is run from a GIT WORKTREE, node_modules is typically a
// junction/symlink into the MAIN checkout's node_modules, so a module Vite serves
// by real path resolves OUTSIDE the worktree root and is refused with "403
// Restricted". We add the REAL (link-resolved) node_modules path to the allowlist
// so that case works. In a normal (non-worktree) checkout node_modules is real and
// already inside the root, so realpath == the nested path and this is a harmless
// no-op. Mirrors schema-editor/vite.config.ts's fsAllowList (bd polyglot-pdf-b6943).
function fsAllowList(): string[] {
  const root = __dirname
  const allow = [root]
  try {
    const real = fs.realpathSync(path.join(root, 'node_modules'))
    allow.push(real)
  } catch {
    // node_modules not present (fresh clone before install) -- nothing to add.
  }
  return allow
}

// The commit this build was made from, baked in via Vite's `define` (bd
// polyglot-pdf-b6943). Same purpose as the backend's `GET /version` git_sha
// (bd polyglot-pdf-9hzod) -- the console's "what is live" view needs to say
// which commit the CONSOLE ITSELF was built from, which /version cannot
// answer (that route reports the BACKEND's commit, a separate deploy this
// console app calls over HTTP, not the console's own).
// `git rev-parse HEAD` runs at BUILD time (not runtime -- Vite `define` is a
// compile-time text substitution), so a git failure (missing git binary, a
// build run outside a checkout) falls back to 'unknown' rather than failing
// the whole build over a diagnostic string.
function buildGitSha(): string {
  try {
    return execSync('git rev-parse HEAD', { cwd: __dirname }).toString().trim()
  } catch {
    return 'unknown'
  }
}

export default defineConfig({
  plugins: [react()],
  define: {
    __ADMIN_CONSOLE_GIT_SHA__: JSON.stringify(buildGitSha()),
  },
  server: {
    port: 3002,
    open: true,
    watch: {
      // Never watch sibling git worktrees -- same reasoning as schema-
      // editor/vite.config.ts: the repo root holds .claude/worktrees/ with
      // many full checkouts, and reloading this dev server on their edits
      // would be pure noise for a console session.
      ignored: ['**/.claude/worktrees/**'],
    },
    fs: {
      // Permit the link-resolved node_modules so a worktree's junctioned
      // deps are servable; see fsAllowList above.
      allow: fsAllowList(),
    },
  },
  resolve: {
    alias: {
      '@': '/src'
    }
  },
  // Strip console.log/console.debug from the production bundle (bd
  // polyglot-pdf-8v8i7) -- NOT `drop: ['console']`, which would also remove
  // console.warn/console.error. Pinned by
  // admin-console/src/bundleNoConsoleLog.test.ts.
  esbuild: {
    pure: ['console.log', 'console.debug'],
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/**/*.{test,spec}.{ts,tsx}', 'src/**/*.d.ts', 'src/test/**'],
      reporter: ['text', 'text-summary'],
    },
  }
})
