---
date: 2026-10-22
bead: polyglot-pdf-m9h4w
title: "chore(deps): upgrade librosa 0.10 -> 1.0 and soundfile 0.12 -> 0.14"
tags: [testing]
---

## Trigger

Pinned back by bd niwcu (librosa 1.0 is a major).

## What shipped

No deployed backend code imports librosa or soundfile; the call sites are tests/e2e/voice-harness/gen_fixtures.py (librosa.load(mp3, sr=16000, mono=True) then sf.write PCM_16) and scripts/spikes (sf.read of WAV as int16/float32, and of MP3 from a BytesIO buffer). Every one of those call shapes was exercised under librosa 1.0.0 / soundfile 0.14.0 (libsndfile 1.2.2): all OK. gen_fixtures.py was also run END TO END under the new pins with OUT_DIR redirected to a temp dir (it writes the committed fixtures otherwise): all 30 fixtures generated via gTTS, each 16 kHz / mono / PCM_16. The spike scripts' Gemini parts were not run (API spend), but every spike's REAL audio function was: each module was imported and its audio helper called directly (no Gemini) -- the gTTS synth helpers (_synth_pcm16 x4, _synth x2, synth_cached) and the fixture loaders (_load_pcm x2) -- under librosa 0.10.1/soundfile 0.12.1 AND 1.0.0/0.14.0: all 9 outputs BYTE-IDENTICAL (same SHA-1) -- though the synth_cached row is not independent evidence: the first run wrote its on-disk audio cache, so the second run was a cache hit (the same BytesIO decode is covered by the _synth rows; the stray cache file was removed from the branch). measure_intro_duration (billed Cloud TTS) and measure_spellback_loudness read an MP3 FILE from disk with sf.read(path) -- a distinct decode from the BytesIO path, and NOT covered by the WAV reads; round-3 fresh-eyes decoded a gTTS MP3 from a file with sf.read under soundfile 0.12.1 (libsndfile 1.2.0) and 0.14.0 (libsndfile 1.2.2): identical (n=55296, rate=24000, rms=0.108037). Both were then RUN as script paths with only the billed Cloud TTS call replaced by one fixed gTTS MP3 (same bytes for every run): measure_intro_duration.measure(path, 'English', 'mp3') and measure_spellback_loudness.measure_clips(0.0, dir) + measure_model(pattern), under both pin sets -- outputs identical (duration, peak, per-clip RMS and peak). Fixture-generator output, old vs new libs (same gTTS input): 28 of 30 fixtures sample-identical; 2 differ (answer_new_itin, read_all_options) with identical length and correlation >= 0.99994, max |diff| ~390 of 32767 -- consistent with the newer bundled MP3 decoder/resampler, audibly the same. This PR regenerates no committed fixture. librosa 1.0.0 no longer imports pkg_resources (imports clean with -W error in a venv with no setuptools), so the `setuptools<81` prerequisite note was removed from gen_fixtures.py and the voice-harness SKILL.md. Full suite: 6763 passed. Hold released. Dropping both from the runtime image is filed as bd zmlgd.

## Lessons

A runtime requirements file can carry packages nothing at runtime imports; grep for importers before assuming a bump is deploy-relevant.

## Doc freshness

README lists the librosa/soundfile versions in its install notes -- see Files touched.

## Files touched

- backend/requirements.txt
- .github/dependabot.yml, tests/test_dependabot_config.py (hold released)
