/**
 * CDN versions of the VAD runtime assets (bd polyglot-pdf-hhlce).
 *
 * MicVAD fetches its model + audio worklet from `baseAssetPath` and the
 * ONNX Runtime WASM binaries from `onnxWASMBasePath` at RUNTIME, while the
 * JavaScript that loads them is BUNDLED from node_modules. The two halves
 * must be the same release: onnxruntime-web's JS refuses (or mis-loads) a
 * WASM build from a different version. These constants therefore MUST equal
 * the versions locked in frontend/package-lock.json for
 * node_modules/@ricky0123/vad-web and node_modules/onnxruntime-web --
 * vadAssetVersions.test.ts fails CI when a dependency bump moves the lock
 * without moving these.
 */

export const VAD_WEB_VERSION = '0.0.31'
export const ORT_WEB_VERSION = '1.31.1'

export const VAD_ASSET_BASE =
	`https://cdn.jsdelivr.net/npm/@ricky0123/vad-web@${VAD_WEB_VERSION}/dist/`
export const ORT_ASSET_BASE =
	`https://cdn.jsdelivr.net/npm/onnxruntime-web@${ORT_WEB_VERSION}/dist/`
