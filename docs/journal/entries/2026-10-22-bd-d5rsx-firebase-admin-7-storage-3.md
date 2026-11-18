---
date: 2026-10-22
bead: polyglot-pdf-d5rsx
title: "chore(deps): upgrade firebase-admin 6 -> 7 and google-cloud-storage 2 -> 3 (IAM envelope checked)"
tags: [security, testing]
---

## Trigger

Pinned back by bd niwcu: deploy-sensitive majors the unit suite (which stubs both SDKs) cannot validate (CLAUDE.md scar #7).

## What shipped

Changelog review against every call site: firebase-admin 7 removed messaging send_all/send_multicast and AutoML, and requires Python >= 3.10; google-cloud-storage 3 removed num_retries/text_mode and turned on checksums + retries by default. The backend uses none of the removed APIs. Live READ-ONLY parity on the shared project, old vs new libraries, through the backend's own GCSFormKitStore plus firestore/auth: identical (7 kits listed, schema + PDF loaded, Firestore read, auth list/get) -- same REST endpoints, so no new IAM permission for the runtime service account. Full suite: 6763 passed. Hold released. Staging verification is a separate per-instance deploy ask.

## Lessons

Local ADC user credentials need GOOGLE_CLOUD_QUOTA_PROJECT for the Auth admin API; the error is identical on old and new libraries, so it is environmental, not a regression.

## Doc freshness

No tier-1/2 doc pins these versions.

## Files touched

- backend/requirements.txt
- .github/dependabot.yml, tests/test_dependabot_config.py (hold released)
