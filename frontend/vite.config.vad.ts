import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// https://vitejs.dev/config/
export default defineConfig({
	plugins: [react()],
	build: {
		outDir: 'dist/vad-tuning',
		rollupOptions: {
			input: {
				main: resolve(__dirname, 'vad-tuning.html'),
			},
		},
	},
	server: {
		port: 5175,
	},
})
