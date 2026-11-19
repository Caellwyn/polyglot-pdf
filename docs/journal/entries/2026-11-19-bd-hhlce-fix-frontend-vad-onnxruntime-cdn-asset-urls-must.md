---
date: 2026-11-19
bead: polyglot-pdf-hhlce
title: "fix(frontend): VAD/onnxruntime CDN asset URLs must match the locked versions (#905 vad-react bump)"
tags: [testing, conventions]
---

## Trigger

An open-PR triage (maintainer request, 2026-11-17/18) found that Dependabot #905
(the frontend minor/patch group) bumps `@ricky0123/vad-react` 0.0.34 -> 0.0.37,
which moves the bundled `@ricky0123/vad-web` 0.0.28 -> 0.0.31 and
`onnxruntime-web` 1.23.0 -> 1.31.1. `useDemoVAD.ts` hard-coded the runtime CDN
asset URLs (`baseAssetPath`: Silero model + worklet; `onnxWASMBasePath`: ORT WASM)
at the OLD versions, so merging #905 alone would pair the new JS with the old
assets. Vitest mocks the VAD library, so green CI could not see it. The
maintainer approved fixing it and browser-testing before asking to merge.

## What shipped

- #905's four bumps taken verbatim (package.json + Dependabot's lockfile):
  vad-react 0.0.37, chart.js 4.6.1, @testing-library/user-event, tsx 4.23.15.
- The two asset versions moved into `frontend/src/demo/vadAssetVersions.ts`
  (0.0.31 / 1.31.1); `useDemoVAD.ts` imports the bases from there. Two stale
  comments in the hook ("self-hosted location", "library uses jsdelivr by
  default") corrected.
- `vadAssetVersions.test.ts` reads `package-lock.json` and fails when either
  constant, or either URL, drifts from the locked version. Mutation-verified:
  reverting VAD_WEB_VERSION, reverting ORT_WEB_VERSION, or hard-coding the ORT
  URL each fail it.
- Browser verification (local stack, W-7 voice overlay, test-harness auth
  bypass): the fixed build fetched `vad-web@0.0.31/dist/silero_vad_legacy.onnx`
  and `onnxruntime-web@1.31.1/dist/ort-wasm-simd-threaded.{mjs,wasm}`, all 200,
  no "Voice detection error". Control arm: with the OLD URLs restored against the
  new JS, the assets also loaded with no visible error. So this is a
  correctness/hygiene fix, NOT a proven outage fix -- the triage's earlier
  "very likely breaks voice detection" was overstated. Under push-to-talk the
  model loads at mount but never runs (`shouldRunVAD` requires
  `!pushToTalkMode`), so a mismatch could only surface on the non-PTT path.
- Fresh-eyes (Sonnet, 1 round): NO-GAPS. Adopted: the two stale comments.
  Left as-is (noted, no bead): `frontend/download-vad-assets.sh` still pins
  0.0.28 / 1.23.0 -- it is dead (nothing runs it; the app does not self-host;
  its 0.0.28 `silero_vad.onnx` URL already 404s) and is out of scope.
  `token-monitor/dashboard.html` pins chart.js 4.4.0 from a CDN -- a separate
  static page, unrelated to the frontend dependency.

## Lessons

- A library whose JS is bundled but whose binary assets are fetched from a CDN
  at runtime has TWO version pins; a dependency bump moves only one. Pin the
  pair with a test that reads the lockfile, because the unit suite mocks the
  library and cannot see the mismatch.
- Run the control arm before claiming a breakage: the mismatch looked like a
  sure outage on paper and loaded cleanly in the browser.

## Doc freshness

- `docs/standards/voice-and-vad.md` (tracks `useDemoVAD.ts`): added the
  runtime-asset/version-pin paragraph; stamp bumped.
- `docs/standards/testing.md` (tracks `frontend/package.json`): reviewed, left --
  no testing rule changed; it was already stale from other tracked files.
- Other prep-flagged stale docs track files this branch did not touch; left.
- Prep also flagged stale in-progress bead `polyglot-pdf-h06sv` (beads GCS
  cutover, not this work); left for its owner.

## Files touched

- `frontend/package.json`, `frontend/package-lock.json` -- #905's bumps
- `frontend/src/demo/vadAssetVersions.ts` -- new: pinned CDN asset versions
- `frontend/src/demo/vadAssetVersions.test.ts` -- new: lockfile-match guard
- `frontend/src/demo/useDemoVAD.ts` -- import the bases; comments corrected
- `docs/standards/voice-and-vad.md` -- runtime-asset paragraph
