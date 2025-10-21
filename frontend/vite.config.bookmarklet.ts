import { defineConfig } from 'vite'
import { resolve } from 'path'

// Vite config for bookmarklet bundle (IIFE format)
export default defineConfig({
	build: {
		// Library mode configuration
		lib: {
			entry: resolve(__dirname, 'src/bookmarklet/index.ts'),
			name: 'VoiceFormFiller', // Global variable name
			formats: ['iife'], // Single IIFE bundle
			fileName: () => 'bookmarklet.bundle.js', // Output filename
		},
		
		// Output configuration
		outDir: 'dist/bookmarklet',
		emptyOutDir: false, // Don't empty - worklet file already built there
		
		// Minification and optimization (using esbuild - faster than terser)
		minify: 'esbuild',
		
		// Target modern browsers (Chrome 114+)
		target: 'es2020',
		
		// Inline all dynamic imports into single file
		rollupOptions: {
			output: {
				inlineDynamicImports: true, // Critical: single file output
				// Add version banner
				banner: `/*! Voice Form Filler Bookmarklet v${process.env.npm_package_version || '1.0.0'} | ${new Date().toISOString()} */`,
			},
			// Treat worklet as external - it will be loaded separately
			external: ['./audio-processor.worklet.js'],
		},
		
		// Source maps for debugging (can disable in prod)
		sourcemap: false,
		
		// Report bundle size
		reportCompressedSize: true,
		chunkSizeWarningLimit: 200, // Warn if > 200KB
	},
	
	// Don't include dev server plugins
	plugins: [],
	
	// Resolve configuration
	resolve: {
		alias: {
			'@': resolve(__dirname, './src'),
		},
	},
	
	// Define global constants
	define: {
		'process.env.NODE_ENV': JSON.stringify('production'),
	},
})
