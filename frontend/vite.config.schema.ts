import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'
import { resolve } from 'path'

// Vite config for schema form demo
export default defineConfig({
	plugins: [react()],

	// Base public path
	base: './',

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
