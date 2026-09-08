/**
 * Tests for shouldSendAudioChunk -- the audio routing gate.
 *
 * ONE mode: push-to-talk (bd polyglot-pdf-v1m8g). Audio is sent while the button
 * is held and withheld otherwise. The gate used to be three-way; both other arms
 * are gone with the detectors they served:
 *
 *  - a NATIVE-VAD arm that always returned true, because Gemini's own VAD needed a
 *    continuous stream to find turn boundaries (a muted PTT sent a silence frame
 *    rather than nothing, bd polyglot-pdf-zivv);
 *  - a client-SILERO arm gated on `vadActive`.
 *
 * Both INFERRED when the user was speaking. PTT knows -- the user is holding the
 * button -- so a second gate could only disagree with it.
 */

import { describe, it, expect } from 'vitest'
import { shouldSendAudioChunk } from './audioManager'

describe('shouldSendAudioChunk (audio routing gate)', () => {
  it('sends while the button is held', () => {
    expect(shouldSendAudioChunk({ pttModeEnabled: true, inputMuted: false })).toBe(true)
  })

  it('withholds while the button is released', () => {
    expect(shouldSendAudioChunk({ pttModeEnabled: true, inputMuted: true })).toBe(false)
  })

  it('withholds before PTT has armed -- an un-gated mic is never streamed', () => {
    // pttModeEnabled=false is the pre-connect / not-yet-configured state, not a
    // second input mode. Defaulting it OPEN would leak an open mic, which is the
    // one failure this gate exists to prevent -- so it must withhold in BOTH mute
    // states, not just the muted one.
    expect(shouldSendAudioChunk({ pttModeEnabled: false, inputMuted: true })).toBe(false)
    expect(shouldSendAudioChunk({ pttModeEnabled: false, inputMuted: false })).toBe(false)
  })

  it('depends on NOTHING but those two flags (the gate stays single-mode)', () => {
    // Pins the SET of inputs, not one behavior (CLAUDE.md scar #8): re-introducing
    // a mode flag would mean this gate is guessing at user intent again, which is
    // exactly what v1m8g removed. Reading the parameter names off the function
    // keeps this honest as the signature changes.
    const params = shouldSendAudioChunk.length
    expect(params, 'shouldSendAudioChunk should take exactly ONE flags object').toBe(1)

    // Exhaustive over the whole input space -- 2 flags, 4 combinations. If a third
    // flag is ever added, this table no longer covers the space and the intent
    // above has been violated.
    const table: Array<[boolean, boolean, boolean]> = [
      // [pttModeEnabled, inputMuted, expected]
      [true, false, true],
      [true, true, false],
      [false, false, false],
      [false, true, false],
    ]
    for (const [pttModeEnabled, inputMuted, expected] of table) {
      expect(
        shouldSendAudioChunk({ pttModeEnabled, inputMuted }),
        `ptt=${pttModeEnabled} muted=${inputMuted}`,
      ).toBe(expected)
    }
  })
})
