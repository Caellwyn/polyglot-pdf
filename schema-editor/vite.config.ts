import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3001,
    open: true
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
      exclude: ['src/**/*.test.{ts,tsx}', 'src/**/*.d.ts', 'src/test/**'],
      reporter: ['text', 'text-summary'],
    },
  }
})
