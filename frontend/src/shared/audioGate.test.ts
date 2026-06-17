/**
 * Tests for shouldSendAudioChunk -- the mode-level audio routing gate.
 *
 * Native Gemini VAD needs a CONTINUOUS stream to detect turn boundaries, so under
 * native VAD this gate ALWAYS returns true -- something must always be sent.
 * Push-To-Talk under native VAD is purely an audio gate: when PTT is muted the
 * CALLER substitutes a silence frame (so the mic is not leaked) rather than
 * dropping the chunk. Withholding audio on PTT-mute would strand native VAD and
 * Gemini "stops responding" after release (bd polyglot-pdf-zivv). Native VAD and
 * the manual turn signals (activity_start, activity_end, audio_stream_end) are
 * mutually exclusive.
 */

import { describe, it, expect } from 'vitest'
import { shouldSendAudioChunk } from './audioManager'

describe('shouldSendAudioChunk (audio routing gate)', () => {
  describe('native VAD on -- always streams (silence substituted by caller when PTT-muted)', () => {
    it('PTT off: streams continuously regardless of mute/vad', () => {
      expect(shouldSendAudioChunk({ nativeVadEnabled: true, pttModeEnabled: false, inputMuted: true, vadActive: false })).toBe(true)
      expect(shouldSendAudioChunk({ nativeVadEnabled: true, pttModeEnabled: false, inputMuted: false, vadActive: false })).toBe(true)
    })

    it('PTT on + button held (not muted): SENDS real audio', () => {
      expect(shouldSendAudioChunk({ nativeVadEnabled: true, pttModeEnabled: true, inputMuted: false, vadActive: false })).toBe(true)
    })

    it('PTT on + button released (muted): STILL sends (caller substitutes silence -- stream must stay continuous)', () => {
      // The fix for bd polyglot-pdf-zivv: native VAD must NOT lose the stream on
      // PTT mute, or the turn never closes. The gate sends; the caller zeroes it.
      expect(shouldSendAudioChunk({ nativeVadEnabled: true, pttModeEnabled: true, inputMuted: true, vadActive: false })).toBe(true)
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
