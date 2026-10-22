---
date: 2026-10-22
bead: polyglot-pdf-m9h4w
title: "chore(deps): upgrade librosa 0.10 -> 1.0 and soundfile 0.12 -> 0.14"
tags: [testing]
---

## Trigger

Pinned back by bd niwcu (librosa 1.0 is a major).

## What shipped

No deployed backend code imports librosa or soundfile; the call sites are tests/e2e/voice-harness/gen_fixtures.py (librosa.load(mp3, sr=16000, mono=True) then sf.write PCM_16) and scripts/spikes (sf.read of WAV as int16/float32, and of MP3 from a BytesIO buffer). Every one of those call shapes was exercised under librosa 1.0.0 / soundfile 0.14.0 (libsndfile 1.2.2): all OK. gen_fixtures.py was also run END TO END under the new pins with OUT_DIR redirected to a temp dir (it writes the committed fixtures otherwise): all 30 fixtures generated via gTTS, each 16 kHz / mono / PCM_16. The spike scripts need live Gemini and were not run; their only soundfile calls are the sf.read shapes exercised above. librosa 1.0.0 no longer imports pkg_resources (imports clean with -W error in a venv with no setuptools), so the `setuptools<81` prerequisite note was removed from gen_fixtures.py and the voice-harness SKILL.md. Full suite: 6763 passed. Hold released. Dropping both from the runtime image is filed as bd zmlgd.

## Lessons

A runtime requirements file can carry packages nothing at runtime imports; grep for importers before assuming a bump is deploy-relevant.

## Doc freshness

README lists the librosa/soundfile versions in its install notes -- see Files touched.

## Files touched

- backend/requirements.txt
- .github/dependabot.yml, tests/test_dependabot_config.py (hold released)
