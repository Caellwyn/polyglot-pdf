/**
 * The CDN asset versions MicVAD loads at runtime must equal the versions
 * bundled from node_modules (bd polyglot-pdf-hhlce). A dependency bump that
 * moves the lockfile but not vadAssetVersions.ts fails here instead of in a
 * user's browser (vitest mocks @ricky0123/vad-react, so nothing else sees it).
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
	ORT_ASSET_BASE,
	ORT_WEB_VERSION,
	VAD_ASSET_BASE,
	VAD_WEB_VERSION,
} from './vadAssetVersions'

const lock = JSON.parse(
	readFileSync(resolve(__dirname, '../../package-lock.json'), 'utf-8'),
) as { packages: Record<string, { version?: string }> }

function locked(name: string): string | undefined {
	return lock.packages[`node_modules/${name}`]?.version
}

describe('VAD runtime asset versions match the lockfile', () => {
	it.each([
		['@ricky0123/vad-web', VAD_WEB_VERSION, VAD_ASSET_BASE],
		['onnxruntime-web', ORT_WEB_VERSION, ORT_ASSET_BASE],
	])('%s', (pkg, version, base) => {
		const lockedVersion = locked(pkg)
		expect(lockedVersion, `${pkg} is not in package-lock.json`).toBeTruthy()
		expect(version).toBe(lockedVersion)
		expect(base).toBe(`https://cdn.jsdelivr.net/npm/${pkg}@${lockedVersion}/dist/`)
	})
})
