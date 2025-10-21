import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
	plugins: [react()],
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

