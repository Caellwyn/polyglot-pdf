---
date: 2026-09-16
bead: polyglot-pdf-j29z1
title: "feat(hosting): E2 -- security headers on all five Hosting sites (CSP report-only first) and self-hosted fonts"
tags: [security-audit, hosting, csp, frontend]
---

## Trigger

Sprint 23 (the security + data-leak audit, epic `polyglot-pdf-uijam`, plan
`docs/sprint_23_security-audit_plan.md`), workstream E2, threat actors T1
and T4: PF-4 (`firebase.json` set no response header on any of the five
Hosting sites -- no CSP, HSTS, frame protection, referrer or permissions
policy) and PF-15 (the voice app loaded Inter and Outfit from Google Fonts,
the one remaining third-party egress from the browser). Sequenced after E1
because the CSP's `connect-src` is built from E1's final inventory of what
the apps actually contact. Built in-session; every command a hidden single
process.

## What shipped

- **One header block on every Hosting target** (`app`, `app-staging`,
  `editor`, `admin`, `admin-candidate`), applied to `**`: HSTS with
  `includeSubDomains; preload` (inert on the Google-owned parents, noted for
  a future custom domain); `X-Content-Type-Options: nosniff`; `Referrer-Policy: no-referrer`;
  `Permissions-Policy` allowing the microphone to the site itself and denying
  camera, geolocation, payment, USB and interest-cohort; and the CSP.
- **The CSP, in report-only mode.** `default-src 'self'`; `script-src 'self'
  https://apis.google.com` (Vite emits module tags only and there is no
  inline script; the one external script is the gapi loader the Firebase
  Auth SDK injects before opening the sign-in popup -- the outer review
  traced it in the shipped bundle); `style-src 'self' 'unsafe-inline'` (React
  inline style attributes); `font-src 'self'`; `img-src 'self' data: blob:`
  (nothing renders a remote image; the profile photo is stored, not shown);
  `connect-src` naming exactly what the apps contact -- the three Cloud Run
  services over https and wss (demo backend, staging backend, admin, in the
  project-hashed hostname form; the admin's short form too), Firebase Auth
  (`identitytoolkit`, `securetoken`) and Firestore over https and its
  websocket transport (the installations endpoint and `www.googleapis.com`
  were dropped: the shipped SDK bundles never contact them), and
  `https://cdn.jsdelivr.net` -- the outer review found that the voice
  overlay's speech detector (`useDemoVAD.ts`) fetches its ONNX model and
  audio worklet from there and `onnxruntime-web` its WASM runtime, on both
  overlays, at mount; the CDN is therefore in `connect-src` and `script-src`
  (a worklet is script) with `'wasm-unsafe-eval'`, so the soak stays
  readable and the policy stays honest. The third outer round then read the
  ORT glue itself: `'wasm-unsafe-eval'` covers WASM compilation only, and
  the jsep variant the app selects also calls `new Function` (embind's
  method-caller factory), which only `'unsafe-eval'` permits -- not granted;
  whether the Silero inference path reaches it is what the soak must watch
  for. Executable code from a third-party CDN is the largest remaining
  browser egress and a supply-chain exposure; the prerequisite for the
  enforcement flip is `polyglot-pdf-18o7c`: self-host the assets AND pick
  the non-jsep ORT build, which has no `new Function`;
  `frame-src` for the auth popup on the project's auth domain and Google's
  account chooser; `worker-src 'self' blob:` (pdf.js); `media-src 'self'
  blob: data:` (spellback and intro audio); `object-src 'none'`; `base-uri
  'self'`; `form-action 'self'`; `frame-ancestors 'none'`. There is NO
  `X-Frame-Options`: the `app` site is the project's auth domain and serves
  Firebase Auth's reserved `/__/auth/iframe`, which every `signInWithPopup`
  on our own pages frames -- a blanket DENY (not report-only!) would have
  broken Google sign-in on the next deploy. Framing is governed by
  `frame-ancestors` alone, and a second block on `/__/auth/**` allows exactly
  our five sites (both hostnames each) as ancestors. A third block caches
  `/fonts/**` for a week. It ships as
  `Content-Security-Policy-Report-Only` on all five targets: `firebase.json`
  is one file for every site, so the staging soak the plan asks for cannot
  be staging-only, and enforcing on the demo without that soak is the wrong
  risk. Browsers write violations to the devtools console; the staging
  test-drive reads it. The flip to `Content-Security-Policy` is its own
  change once the app's own traffic shows no violation.
- **Self-hosted fonts.** `scripts/fetch_fonts.py` (urllib only, no
  subprocess) fetches the Google Fonts stylesheet with a modern user agent,
  keeps every unicode-range woff2 subset Google serves for Inter and Outfit
  (latin, latin-ext, cyrillic, cyrillic-ext, greek, greek-ext, vietnamese:
  45 files, ~2 MB -- the UI is translated into languages that use those
  scripts, and those users got the glyphs from Google before) into
  `frontend/public/fonts/`, and writes `fonts.css`
  with local `url()`s; `frontend/index.html` links that stylesheet instead
  of `fonts.googleapis.com`. The editor and admin console never loaded a
  remote font.
- **The live posture runbook understands the soak.** `scripts/audit/
  infra_posture.sh`'s Hosting check (D's check 10) matched only the enforcing
  header name and would have reported every site FAIL during report-only;
  it now accepts `Content-Security-Policy-Report-Only` as PASS with the mode
  named in the detail, and no longer requires `X-Frame-Options` (the second
  outer round caught that the runbook, its pin and the plan's criterion 4
  all still named XFO after this bead removed it -- the scar #8 shape, one
  rule in three places); pinned in `tests/test_infra_posture_script.py`.
- **`tests/test_hosting_headers.py`**, derived from `firebase.json`: every
  target carries every header and no `X-Frame-Options`; the `/__/auth/**`
  ancestor list is exactly the five sites; `/fonts/**` is cached; every
  `a.run.app` host the three apps' env files name is in `connect-src` (the
  Cloud Run hash has drifted before, bd `emm7`); the CSP carries every required directive,
  every origin the apps need, never `'unsafe-eval'`, `http:` or a wildcard
  host, and `script-src` is exactly our origin, the gapi loader, the VAD
  CDN and WASM; all five targets share one
  policy; the voice app's `index.html` names no third-party font host; every
  `url()` in `fonts.css` is local and its file exists. Red before the change
  (12 of 13 cases), green after.

## Verification

- `tests/test_hosting_headers.py`: 12 of 13 cases red on the untouched
  config, 13 green after; run together with every other test that parses
  `firebase.json` (`test_deploy_channel_isolation`, `test_deploy_admin_url_injection`,
  `test_infra_posture_script`, `test_form_kit_routes`) and the windowless-spawn
  pin over `scripts/` (the regenerator spawns nothing): 181 passed.
- Scar #9: thirteen mutations, each RED (the CDN dropped from `script-src`;
  `x-frame-options` put back into the runbook's required list) (the config-parametrized ones in
  their own interpreter, since the targets are read at import): the
  `/__/auth/**` block dropped; `apis.google.com` dropped; a demo wss host
  dropped (the env-derived pin); `X-Frame-Options` reintroduced; the fonts
  cache block dropped; the runbook's report-only branch removed; the headers block dropped from one target;
  `frame-ancestors` removed; `'unsafe-eval'` added to `script-src`; the
  staging backend's wss origin dropped from `connect-src`; the Google Fonts
  link restored in `index.html`; one referenced woff2 deleted.
- Not run locally: a frontend build (the worktree has no node_modules and a
  local install spawns console windows on this machine); CI's frontend job
  and the next staging deploy exercise the new `/fonts/fonts.css` link. The
  live header check (criterion 2) is the staging deploy's.

## Review record

Fresh-eyes (Sonnet, read-only): round 1 found the doc naming only the
latin subsets and the admin short-form origin missing from the pin; clean
after. Opus cross-surface, four rounds: round 1 found `X-Frame-Options`
would deny our own pages the Firebase Auth iframe the app site serves,
`script-src` missing the gapi loader, the hash-drift risk on the Cloud Run
hosts, two dead allowances and the fonts cache; round 2 found the posture
runbook, its pin and the plan's criterion 4 still naming XFO, and the
voice overlay's VAD/ONNX assets loading from jsdelivr; round 3 read the
ONNX glue and found `new Function` beyond what `'wasm-unsafe-eval'`
covers; round 4: NO-GAPS. Filed by the reviews: `polyglot-pdf-18o7c`
(self-host the VAD assets, non-jsep ORT -- the enforcement prerequisite),
`polyglot-pdf-p3o51` (the env-derived pin's wss demand and the stale
in-code WS fallback), `polyglot-pdf-b45a4` (the dead self-hosting
script); `polyglot-pdf-h5016` (stale ack/journal claims) was fixed here
and closed. Every pin was mutation-verified, the config-parametrized ones
in their own interpreter.

## Lessons

- **A shared config cannot stage a policy per site.** One `firebase.json`
  serves five sites; "report-only on staging, then enforce" becomes
  "report-only everywhere, then flip" -- and the test pins the report-only
  header name so the flip is a deliberate, reviewed change.
- **A CSP token is a claim about a library's internals.** `'wasm-unsafe-eval'`
  sounded like "the WASM runtime"; it is "WebAssembly.compile". The runtime's
  glue also builds functions from strings, and only reading the shipped
  bytes showed it. Every allowance now says what it covers.
- **Build the allowlist from what the code contacts, then pin the list.**
  The `connect-src` set came from the apps' env files and deploy scripts;
  the test names each origin so a dropped one fails CI before it breaks a
  voice session under enforcement.

## Doc freshness

Bumped: `docs/components/config-deployment.md` (new "Hosting security headers"
section). Acked: `docs/technical_guide.md`, which tracks `firebase.json` for its
rewrites and makes no claim about response headers or fonts (`auth.md`, which
also tracks it, was already fresh).

## Files touched

- firebase.json -- the header block on all five targets
- frontend/index.html -- local font stylesheet
- frontend/public/fonts/ -- 45 woff2 files + fonts.css (new)
- scripts/fetch_fonts.py -- regenerator (new)
- tests/test_hosting_headers.py -- new
- scripts/audit/infra_posture.sh, tests/test_infra_posture_script.py -- report-only CSP reads as the planned soak
- docs/journal/entries/2026-09-16-bd-j29z1-hosting-headers.md -- this entry
