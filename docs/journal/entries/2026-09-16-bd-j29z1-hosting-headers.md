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
  were dropped: the shipped SDK bundles never contact them);
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
  named in the detail, pinned in `tests/test_infra_posture_script.py`.
- **`tests/test_hosting_headers.py`**, derived from `firebase.json`: every
  target carries every header and no `X-Frame-Options`; the `/__/auth/**`
  ancestor list is exactly the five sites; `/fonts/**` is cached; every
  `a.run.app` host the three apps' env files name is in `connect-src` (the
  Cloud Run hash has drifted before, bd `emm7`); the CSP carries every required directive,
  every origin the apps need, never `'unsafe-eval'`, `http:` or a wildcard
  host, and `script-src` is exactly `'self'`; all five targets share one
  policy; the voice app's `index.html` names no third-party font host; every
  `url()` in `fonts.css` is local and its file exists. Red before the change
  (12 of 13 cases), green after.

## Verification

- `tests/test_hosting_headers.py`: 12 of 13 cases red on the untouched
  config, 13 green after; run together with every other test that parses
  `firebase.json` (`test_deploy_channel_isolation`, `test_deploy_admin_url_injection`,
  `test_infra_posture_script`, `test_form_kit_routes`) and the windowless-spawn
  pin over `scripts/` (the regenerator spawns nothing): 181 passed.
- Scar #9: eleven mutations, each RED (the config-parametrized ones in
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

REVIEW_RECORD

## Lessons

- **A shared config cannot stage a policy per site.** One `firebase.json`
  serves five sites; "report-only on staging, then enforce" becomes
  "report-only everywhere, then flip" -- and the test pins the report-only
  header name so the flip is a deliberate, reviewed change.
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
