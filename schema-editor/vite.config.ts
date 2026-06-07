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
  }
})
