---
date: 2026-10-22
bead: polyglot-pdf-m9h4w
title: "chore(deps): upgrade librosa 0.10 -> 1.0 and soundfile 0.12 -> 0.14"
tags: [testing]
---

## Trigger

Pinned back by bd niwcu (librosa 1.0 is a major).

## What shipped

No deployed backend code imports librosa or soundfile; the call sites are tests/e2e/voice-harness/gen_fixtures.py (librosa.load(mp3, sr=16000, mono=True) then sf.write PCM_16) and scripts/spikes (sf.read of WAV as int16/float32, and of MP3 from a BytesIO buffer). Every one of those call shapes was exercised under librosa 1.0.0 / soundfile 0.14.0 (libsndfile 1.2.2): all OK. Full suite: 6763 passed. Hold released. Dropping both from the runtime image is filed as bd zmlgd.

## Lessons

A runtime requirements file can carry packages nothing at runtime imports; grep for importers before assuming a bump is deploy-relevant.

## Doc freshness

README lists the librosa/soundfile versions in its install notes -- see Files touched.

## Files touched

- backend/requirements.txt
- .github/dependabot.yml, tests/test_dependabot_config.py (hold released)
