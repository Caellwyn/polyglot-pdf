/**
 * Barge-in must fire during a model-PCM + clip OVERLAP (bd polyglot-pdf-uxc6s).
 *
 * `isSpeaking()` is `geminiIsSpeaking && activeClipCount === 0`. That is correct
 * for the suspend/resume deadlock pair it was written for (bd s1iex.4), but it
 * cannot answer the BARGE-IN question during an overlap: `geminiIsSpeaking` is
 * set true by BOTH producers (the PCM scheduler AND attachClipElement), so
 * subtracting `activeClipCount` cannot recover the model-only fact. A model+clip
 * overlap (true, 1) is indistinguishable from a clip alone (true, 1) and both
 * read FALSE -- so every barge-in site skipped its flush while the model was
 * genuinely talking over the user.
 *
 * The overlap is reachable, and the s1iex.4 diff documents why: spellbackPlayer's
 * pre-clip drain-wait is BOUNDED (DRAIN_WAIT_CAP_MS) and "plays anyway on
 * timeout", so a clip can start while model PCM is still scheduled.
 *
 * The existing clip tests never schedule real PCM -- they drive clips only --
 * which is exactly why this was invisible to them.
 */

import { describe, it, expect, afterEach } from 'vitest'
import { createAudioManager } from './audioManager'

// A jsdom-safe AudioContext rich enough for playAudio() to actually SCHEDULE a
// buffer source (the existing clip tests stub only what attachClipElement
// needs, so they cannot produce an overlap at all).
function installAudioContext() {
  const prev = (globalThis as any).AudioContext
  ;(globalThis as any).AudioContext = function () {
    return {
      state: 'running',
      currentTime: 0,
      destination: {},
      sampleRate: 24000,
      createAnalyser: () => ({
        fftSize: 256,
        connect: () => {},
        getByteTimeDomainData: () => {},
      }),
      createMediaElementSource: () => ({ connect: () => {}, disconnect: () => {} }),
      createBuffer: (_ch: number, len: number) => ({
        getChannelData: () => new Float32Array(len),
      }),
      createBufferSource: () => ({
        buffer: null as any,
        onended: null as null | (() => void),
        connect: () => {},
        disconnect: () => {},
        start: () => {},
        stop: () => {},
      }),
      resume: async () => {},
      close: async () => {},
    }
  } as any
  return () => {
    if (prev === undefined) delete (globalThis as any).AudioContext
    else (globalThis as any).AudioContext = prev
  }
}

// One frame of model PCM. decodeGeminiFrame accepts a raw Int16 buffer.
function pcmFrame(samples = 480): ArrayBuffer {
  return new Int16Array(samples).buffer
}

describe('isModelSpeaking during a model+clip overlap (bd polyglot-pdf-uxc6s)', () => {
  let restore: (() => void) | undefined
  afterEach(() => {
    restore?.()
    restore = undefined
    delete (window as any).vffOnAudioPlaybackStart
    delete (window as any).vffOnAudioPlaybackEnd
  })

  it('reports the MODEL as speaking while a clip overlaps its PCM', async () => {
    restore = installAudioContext()
    const am = createAudioManager()

    await am.playAudio(pcmFrame())
    expect(am.isModelSpeaking(), 'model PCM alone').toBe(true)
    expect(am.isSpeaking(), 'model PCM alone').toBe(true)

    const release = am.attachClipElement({} as HTMLAudioElement)
    try {
      // THE BUG. Both signals disagree here, and that disagreement is the
      // whole point of the split:
      //   isSpeaking()      -> false (clip subtracted; correct for SUSPEND)
      //   isModelSpeaking() -> true  (model PCM IS scheduled; correct for FLUSH)
      expect(am.isModelSpeaking(), 'OVERLAP: model is still mid-utterance').toBe(true)
      expect(am.isSpeaking(), 'OVERLAP: suspend sites must still see false').toBe(false)
    } finally {
      release()
    }
  })

  it('a clip ALONE never reports the model as speaking', async () => {
    // The other direction: isModelSpeaking must not become a second union, or
    // a barge-in would flush an empty model queue and the PTT press would
    // report a phantom interruption.
    restore = installAudioContext()
    const am = createAudioManager()

    const release = am.attachClipElement({} as HTMLAudioElement)
    try {
      expect(am.isModelSpeaking(), 'clip only: model is NOT speaking').toBe(false)
      expect(am.isAnyAudioPlaying(), 'clip only: something IS audible').toBe(true)
    } finally {
      release()
    }
  })

  it('flushing the queue clears the model signal even while a clip plays', async () => {
    // The post-barge-in state. flushAudioQueue() stops the model sources; the
    // clip is deliberately untouched (it lives on its own element), so the
    // model signal must fall while the union stays up.
    restore = installAudioContext()
    const am = createAudioManager()

    await am.playAudio(pcmFrame())
    const release = am.attachClipElement({} as HTMLAudioElement)
    try {
      expect(am.isModelSpeaking()).toBe(true)
      am.flushAudioQueue()
      expect(am.isModelSpeaking(), 'flush stopped the model PCM').toBe(false)
      expect(am.isAnyAudioPlaying(), 'the clip is still audible').toBe(true)
    } finally {
      release()
    }
  })

  it('is silent when nothing plays at all', async () => {
    restore = installAudioContext()
    const am = createAudioManager()
    expect(am.isModelSpeaking()).toBe(false)
    expect(am.isSpeaking()).toBe(false)
    expect(am.isAnyAudioPlaying()).toBe(false)
  })

  it('destroy() clears the model signal -- no stranded source (bd wge8m/2z5ms)', async () => {
    // cleanup() resets activeClipCount and geminiIsSpeaking; isModelSpeaking()
    // reads a THIRD piece of state (the PCM source list) and was initially
    // missed. A stranded entry survives teardown -- the sources are stopped and
    // their context closed, so onended never fires to drain them -- and would
    // permanently report the model as talking, suppressing the post-resume
    // re-prompt guard for the life of the manager.
    restore = installAudioContext()
    const am = createAudioManager()

    await am.playAudio(pcmFrame())
    expect(am.isModelSpeaking()).toBe(true)

    am.destroy()
    expect(am.isModelSpeaking(), 'a destroyed manager is not speaking').toBe(false)
    expect(am.isSpeaking()).toBe(false)
    expect(am.isAnyAudioPlaying()).toBe(false)
  })

  it('the three signals are genuinely DISTINCT, not aliases', async () => {
    // A refactor that collapses any two of these re-introduces either this
    // bug or the s1iex.4 deadlock. Pin that each pair differs on some input.
    restore = installAudioContext()
    const am = createAudioManager()

    await am.playAudio(pcmFrame())
    const release = am.attachClipElement({} as HTMLAudioElement)
    try {
      const model = am.isModelSpeaking()   // true
      const turn = am.isSpeaking()          // false  (clip-suppressed)
      const union = am.isAnyAudioPlaying()  // true
      expect(model).not.toBe(turn)          // model vs turn-taking
      expect(turn).not.toBe(union)          // turn-taking vs union
      expect(model).toBe(true)
      expect(union).toBe(true)
    } finally {
      release()
    }
  })
})
