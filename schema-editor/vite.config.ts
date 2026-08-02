/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
import path from 'node:path'
import { extractEndpoint } from './vite-plugins/extractEndpoint'
import { deployKitEndpoint } from './vite-plugins/deployKitEndpoint'

// Vite's dev server only serves files under server.fs.allow (default: the project
// root). When this editor is run from a GIT WORKTREE, node_modules is typically a
// junction/symlink into the MAIN checkout's node_modules, so a module Vite serves
// by real path (e.g. the pdfjs worker, loaded via new URL(..., import.meta.url))
// resolves OUTSIDE the worktree root and is refused with "403 Restricted". We add
// the REAL (link-resolved) node_modules path to the allowlist so that case works.
// In a normal (non-worktree) checkout node_modules is real and already inside the
// root, so realpath == the nested path and this is a harmless no-op.
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

export default defineConfig({
  // extractEndpoint adds a dev-only POST /api/extract that runs the PDF->schema
  // extractor on the host (bd 7a9.17). apply:'serve' keeps it out of prod builds.
  // deployKitEndpoint adds a dev-only POST /api/deploy-kit that uploads ONE
  // complete kit to the GCS bucket (bd polyglot-pdf-ipzh) -- kit data only, never
  // Cloud Run or Hosting. Same apply:'serve', so the hosted editor cannot publish.
  plugins: [react(), extractEndpoint(), deployKitEndpoint()],
  server: {
    port: 3001,
    open: true,
    fs: {
      // Permit the link-resolved node_modules so a worktree's junctioned deps
      // (esp. the pdfjs worker) are servable; see fsAllowList above.
      allow: fsAllowList(),
    },
  },
  resolve: {
    alias: {
      '@': '/src'
    }
  },
  build: {
    // pdfjs-dist ships top-level await; the default esbuild target (es2020/
    // chrome87...) rejects it, failing `npm run build`. esnext permits it.
    target: 'esnext'
  },
  optimizeDeps: {
    // Same top-level-await issue bites the dev dep-optimizer (it esbuild-
    // prebundles pdfjs-dist), so the dev server needs the esnext target too.
    esbuildOptions: {
      target: 'esnext'
    }
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    coverage: {
      // v8 provider + @vitest/coverage-v8. Opt-in via `vitest run --coverage`
      // (npm run test:coverage); not forced on every `vitest run` so the CI
      // test job and local watch stay fast (bd polyglot-pdf-uov.2).
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/**/*.{test,spec}.{ts,tsx}', 'src/**/*.d.ts', 'src/test/**'],
      reporter: ['text', 'text-summary'],
    },
  }
})
