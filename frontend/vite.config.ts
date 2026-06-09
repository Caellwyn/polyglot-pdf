/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
	plugins: [react()],
	// Test config lives here so `vitest run` (CI, bare invocation) uses jsdom
	// without needing the `--environment jsdom` CLI flag the npm "test" script
	// passes. Tests touch sessionStorage/DOM and fail under the default node
	// environment (bd polyglot-pdf-uov.1).
	test: {
		environment: 'jsdom',
	},
	server: {
		port: 5173,
		fs: {
			// Allow serving files from dist directory
			allow: ['..']
		},
		cors: {
			origin: '*',
			credentials: false
		},
		headers: {
			'Access-Control-Allow-Origin': '*',
			'Access-Control-Allow-Methods': 'GET, OPTIONS',
			'Access-Control-Allow-Headers': '*'
		}
	},
	publicDir: 'public',
})

