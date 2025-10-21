import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'
import { existsSync, readFileSync } from 'fs'

// Plugin to serve AudioWorklet file and VAD assets in dev mode
function serveWorkletPlugin() {
	return {
		name: 'serve-worklet',
		configureServer(server: any) {
			server.middlewares.use((req: any, res: any, next: any) => {
				// Serve the AudioWorklet file from dist in dev mode
				if (req.url === '/src/shared/audio-processor.worklet.js') {
					const workletPath = resolve(__dirname, 'dist/shared/audio-processor.worklet.js')
					if (existsSync(workletPath)) {
						res.setHeader('Content-Type', 'application/javascript')
						res.end(readFileSync(workletPath))
						return
					}
				}

				// Serve ONNX Runtime .mjs files from public directory (fix Vite import restrictions)
				if (req.url?.startsWith('/vad-assets/')) {
					const assetPath = resolve(__dirname, 'public', req.url.split('?')[0])
					if (existsSync(assetPath)) {
						// Set correct MIME type based on extension
						if (assetPath.endsWith('.mjs')) {
							res.setHeader('Content-Type', 'application/javascript')
						} else if (assetPath.endsWith('.wasm')) {
							res.setHeader('Content-Type', 'application/wasm')
						} else if (assetPath.endsWith('.onnx')) {
							res.setHeader('Content-Type', 'application/octet-stream')
						} else if (assetPath.endsWith('.js')) {
							res.setHeader('Content-Type', 'application/javascript')
						}
						res.end(readFileSync(assetPath))
						return
					}
				}

				next()
			})
		},
	}
}

// Vite config for demo build (static site deployment to GCS/Cloud Run)
export default defineConfig({
	plugins: [react(), serveWorkletPlugin()],
	
	// Base public path - can be customized for CDN/custom domain
	base: './',
	
	// Build configuration
	build: {
		// Output directory
		outDir: 'dist/demo',
		emptyOutDir: true,
		
		// Generate source maps for debugging (disable for smaller build)
		sourcemap: false,
		
		// Target modern browsers
		target: 'es2020',
		
		// Rollup options
		rollupOptions: {
			input: {
				main: resolve(__dirname, 'demo.html'),
			},
			output: {
				// Manual chunking for better caching
				manualChunks: {
					'vendor-react': ['react', 'react-dom'],
				},
			},
			// Suppress warnings about missing source maps
			onwarn(warning, warn) {
				// Ignore sourcemap warnings from node_modules
				if (warning.code === 'SOURCEMAP_ERROR') return
				warn(warning)
			},
		},
		
		// Minification
		minify: 'esbuild',
		
		// Report bundle size
		reportCompressedSize: true,
		chunkSizeWarningLimit: 500, // Warn if chunks > 500KB
	},
	
	// Dev server configuration
	server: {
		port: 5174, // Different port from main app (5173)
		open: '/demo.html',
		cors: true,
		fs: {
			// Allow serving files from project root (for demos folder)
			allow: ['..', '../demos'],
		},
	},
	
	// Resolve configuration
	resolve: {
		alias: {
			'@': resolve(__dirname, './src'),
		},
	},
	
	// Dependency optimization
	optimizeDeps: {
		include: [
			'@ricky0123/vad-react',
			'@ricky0123/vad-web',
			'onnxruntime-web',
		],
		esbuildOptions: {
			// Ensure onnxruntime-web is treated as ESM
			mainFields: ['module', 'main'],
		},
	},
	
	// Asset handling
	assetsInclude: ['**/*.onnx', '**/*.wasm'],
	
	// Public directory (static assets)
	publicDir: 'public',
	
	// Define global constants
	define: {
		'process.env.NODE_ENV': JSON.stringify(process.env.NODE_ENV || 'development'),
	},
})
