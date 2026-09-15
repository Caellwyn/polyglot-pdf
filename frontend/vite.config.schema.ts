import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'
import { resolve } from 'path'

// Vite config for schema form demo
export default defineConfig({
	plugins: [react()],

	// Base public path -- ABSOLUTE, not relative (bd polyglot-pdf-3bsyv). This
	// app is always served from a Hosting site ROOT (staging/demo) or from
	// dev-local's root, never from a subdirectory, so a relative base ('./')
	// is never correct here: it made index.html reference './assets/...',
	// which resolves relative to the CURRENT PATH, not the site root. A cold
	// load at any path with a segment (e.g. /console/links or
	// /console/employees) then asked for /console/assets/... -- which does not
	// exist -- and firebase.json's catch-all `**` -> /index.html rewrite
	// answered with HTML instead of JS, so the browser refused the script
	// with "Expected a JavaScript-or-Wasm module script but the server
	// responded with a MIME type of text/html". Only the site root ever
	// worked on a cold load; client-side navigation FROM the root hid the
	// bug (no re-fetch of assets), which is why it survived. Pinned by
	// frontend/src/shared/buildAbsoluteAssetBase.test.ts -- both a static
	// read of this config's `base` value and a real production build whose
	// emitted index.html is asserted to reference /assets/ absolutely.
	base: '/',

	// Strip console.log/console.debug from the production bundle (bd
	// polyglot-pdf-8v8i7) -- NOT `drop: ['console']`, which would also remove
	// console.warn/console.error that staff read on staging (e.g. the
	// WebSocket-close diagnostic in webFormConnection.ts, promoted to
	// console.info for exactly this reason). Pinned by
	// frontend/src/shared/bundleNoConsoleLog.test.ts.
	esbuild: {
		pure: ['console.log', 'console.debug'],
	},

	// Build configuration
	build: {
		outDir: 'dist',
		emptyOutDir: true,
		sourcemap: false,
		target: 'es2020',

		rollupOptions: {
			input: {
				main: resolve(__dirname, 'index.html'),
			},
			output: {
				manualChunks: {
					'vendor-react': ['react', 'react-dom'],
				},
			},
		},

		minify: 'esbuild',
		reportCompressedSize: true,
		chunkSizeWarningLimit: 500,
	},

	// Dev server configuration
	server: {
		port: 5176, // Different port from other apps
		open: '/schema-form-demo.html',
		cors: true,
		fs: {
			// Allow serving files from project root (for PDF schema)
			allow: ['..'],
		},
	},

	// Resolve configuration
	resolve: {
		alias: {
			'@': resolve(__dirname, './src'),
		},
	},

	// Public directory (static assets)
	publicDir: 'public',

	// Define global constants
	define: {
		'process.env.NODE_ENV': JSON.stringify(process.env.NODE_ENV || 'development'),
	},
})
