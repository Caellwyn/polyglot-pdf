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

- #905's three OTHER bumps, taken from Dependabot's Linux-generated lockfile:
  chart.js 4.6.1, @testing-library/user-event 14.6.10, tsx 4.23.15.
- `@ricky0123/vad-react` HELD at 0.0.34 (vad-web 0.0.28, onnxruntime-web
  1.23.0): the four lock entries and the package.json range were restored to
  dev's byte-for-byte (JSON surgery on #905's lock -- no Windows `npm install`,
  so no lockfile skew). Added to `NPM_HELD_FOR_UPGRADE` and to every npm
  entry's ignore + group exclude in `.github/dependabot.yml`; the upgrade is bd
  `polyglot-pdf-lpk9k`.
- The asset versions now live in `frontend/src/demo/vadAssetVersions.ts`
  (0.0.28 / 1.23.0, unchanged from dev); `useDemoVAD.ts` imports the bases from
  there. Two stale comments in the hook corrected.
- `vadAssetVersions.test.ts` reads `package-lock.json` and fails when either
  constant, or either URL, drifts from the locked version. Mutation-verified:
  reverting VAD_WEB_VERSION, reverting ORT_WEB_VERSION, or hard-coding the ORT
  URL each fail it. The held-package test was mutation-checked too (dropping one
  vad-react ignore line fails it).

Why vad-react is held (Opus cross-surface review, round 1, GAPS-FOUND 3):
- F1 (adopted -> hold): vad-web 0.0.31's `MicVAD.destroy()` throws "MicVAD has
  null stream, audio context, or processor adapter" when `start()` never ran,
  and under push-to-talk it never runs. Every overlay unmount then logs an
  unhandled rejection (I saw exactly this error during the browser run), and
  vad-react 0.0.37 surfaces it as `errored` on the StrictMode-cancelled setup
  branch, breaking the vad-tuning dashboard in dev.
- F2 (moot with the hold, carried to lpk9k): vad-web 0.0.31 imports
  `onnxruntime-web/wasm`, whose non-jsep loader has no `new Function`, which
  would make the CSP docs' 'unsafe-eval' story stale.
- F3 (moot with the hold): in 0.0.31 the worklet loads at `start()`; in the
  0.0.28 that ships, `MicVAD.new` -> `AudioNodeVAD.new` -> `setupAudioNode`
  loads it at mount, which is what voice-and-vad.md now says.

Browser verification (local stack, W-7 voice overlay, test-harness auth
bypass), run on the 0.0.37 candidate before the hold: with matched URLs the
assets loaded (200) with no "Voice detection error"; a control arm with the old
URLs against the new JS ALSO loaded without a visible error. So the URL drift
alone was a correctness/hygiene issue, not a proven outage -- the triage's
earlier "very likely breaks voice detection" was overstated; the real problem
with the bump was F1. The shipped VAD JS + URLs are now identical to dev's, so
the voice overlay's VAD path is unchanged by this PR.

Fresh-eyes (Sonnet, 1 round): NO-GAPS. Left as-is (no bead):
`frontend/download-vad-assets.sh` still pins old URLs -- dead (nothing runs it;
the app does not self-host). `token-monitor/dashboard.html` pins chart.js 4.4.0
from a CDN -- a separate static page.

## Lessons

- A library whose JS is bundled but whose binary assets are fetched from a CDN
  at runtime has TWO version pins; a dependency bump moves only one. Pin the
  pair with a test that reads the lockfile, because the unit suite mocks the
  library and cannot see the mismatch.
- Run the control arm before claiming a breakage: the URL mismatch looked like
  a sure outage on paper and loaded cleanly in the browser -- while the real
  defect in the same bump (destroy-before-start) was in an unhandled-rejection
  line I had dismissed as HMR noise. Read every new console error against the
  bump, not just the one you went looking for.

## Doc freshness

- `docs/standards/voice-and-vad.md` (tracks `useDemoVAD.ts`): added the
  runtime-asset/version-pin paragraph; stamp bumped.
- `docs/standards/testing.md` (tracks `frontend/package.json`,
  `.github/dependabot.yml`, `tests/test_dependabot_config.py`): reviewed, left --
  it states no per-package hold list; it was already stale from other files.
- Other prep-flagged stale docs track files this branch did not touch; left.
- Prep also flagged stale in-progress bead `polyglot-pdf-h06sv` (beads GCS
  cutover, not this work); left for its owner.

## Files touched

- `frontend/package.json`, `frontend/package-lock.json` -- three of #905's bumps
- `frontend/src/demo/vadAssetVersions.ts` -- new: pinned CDN asset versions
- `frontend/src/demo/vadAssetVersions.test.ts` -- new: lockfile-match guard
- `frontend/src/demo/useDemoVAD.ts` -- import the bases; comments corrected
- `.github/dependabot.yml`, `tests/test_dependabot_config.py` -- hold vad-react
- `docs/standards/voice-and-vad.md` -- runtime-asset paragraph
