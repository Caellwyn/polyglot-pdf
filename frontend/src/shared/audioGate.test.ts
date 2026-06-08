/**
 * Tests for shouldSendAudioChunk -- the mode-level audio routing gate.
 *
 * The key new behavior (PTT-as-a-gate over native VAD): native Gemini VAD always
 * runs on the backend, but Push-To-Talk can still gate which CLIENT audio bytes
 * reach Gemini (noisy-room support). So under native VAD, PTT-on + muted must
 * WITHHOLD audio -- the bug this fix addresses was that native mode streamed all
 * audio unconditionally, defeating PTT gating.
 */

import { describe, it, expect } from 'vitest'
import { shouldSendAudioChunk } from './audioManager'

describe('shouldSendAudioChunk (audio routing gate)', () => {
  describe('native VAD on', () => {
    it('PTT off: streams continuously regardless of mute/vad', () => {
      // Continuous native stream -- Gemini needs silence too.
      expect(shouldSendAudioChunk({ nativeVadEnabled: true, pttModeEnabled: false, inputMuted: true, vadActive: false })).toBe(true)
      expect(shouldSendAudioChunk({ nativeVadEnabled: true, pttModeEnabled: false, inputMuted: false, vadActive: false })).toBe(true)
    })

    it('PTT on + button held (not muted): SENDS audio', () => {
      expect(shouldSendAudioChunk({ nativeVadEnabled: true, pttModeEnabled: true, inputMuted: false, vadActive: false })).toBe(true)
    })

    it('PTT on + button released (muted): WITHHOLDS audio (the noisy-room gate)', () => {
      // This is the core fix: native mode no longer streams unconditionally when
      // PTT is gating.
      expect(shouldSendAudioChunk({ nativeVadEnabled: true, pttModeEnabled: true, inputMuted: true, vadActive: false })).toBe(false)
    })
  })

  describe('native VAD off, PTT on', () => {
    it('sends only while the button is held (not muted)', () => {
      expect(shouldSendAudioChunk({ nativeVadEnabled: false, pttModeEnabled: true, inputMuted: false, vadActive: false })).toBe(true)
      expect(shouldSendAudioChunk({ nativeVadEnabled: false, pttModeEnabled: true, inputMuted: true, vadActive: false })).toBe(false)
    })
  })

  describe('native VAD off, PTT off (client Silero VAD)', () => {
    it('sends only when NOT muted AND VAD detects speech', () => {
      expect(shouldSendAudioChunk({ nativeVadEnabled: false, pttModeEnabled: false, inputMuted: false, vadActive: true })).toBe(true)
      // muted -> withhold even if VAD active
      expect(shouldSendAudioChunk({ nativeVadEnabled: false, pttModeEnabled: false, inputMuted: true, vadActive: true })).toBe(false)
      // no speech -> withhold even if unmuted
      expect(shouldSendAudioChunk({ nativeVadEnabled: false, pttModeEnabled: false, inputMuted: false, vadActive: false })).toBe(false)
    })
  })
})
