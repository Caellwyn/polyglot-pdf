/**
 * In-flight arming guard for audioManager.startRecording (bd polyglot-pdf-z9bc).
 *
 * `recording` is set true only at the END of startRecording, after getUserMedia +
 * AudioContext + addModule all await. The reconnect audio re-arm fix means BOTH
 * the overlay's status-poll and the onSessionReady re-arm can call startRecording
 * on initial connect; without an IN-FLIGHT guard (not just the post-completion
 * `recording` flag) the two would run getUserMedia + worklet setup concurrently
 * and clobber each other. This test pins that a second concurrent call awaits the
 * first instead of starting a duplicate setup.
 *
 * ASCII only. jsdom env (vite.config test.environment).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createAudioManager } from './audioManager'

// A getUserMedia we can hold open to widen the race window: it does not resolve
// until we release the deferred, so a second startRecording is guaranteed to
// arrive while the first is still mid-await.
function deferred<T>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((r) => { resolve = r })
  return { promise, resolve }
}

let getUserMediaCalls = 0
let addModuleCalls = 0
let gumGate: ReturnType<typeof deferred<MediaStream>>

class FakeAudioWorkletNode {
  port = { onmessage: null as any, postMessage: vi.fn() }
  connect = vi.fn()
  disconnect = vi.fn()
}

class FakeAudioContext {
  state: 'running' | 'suspended' | 'closed' = 'running'
  destination = {}
  audioWorklet = {
    addModule: vi.fn(async () => { addModuleCalls++ }),
  }
  createMediaStreamSource = vi.fn(() => ({ connect: vi.fn(), disconnect: vi.fn() }))
  resume = vi.fn(async () => { this.state = 'running' })
  suspend = vi.fn(async () => { this.state = 'suspended' })
  close = vi.fn(async () => { this.state = 'closed' })
}

beforeEach(() => {
  getUserMediaCalls = 0
  addModuleCalls = 0
  gumGate = deferred<MediaStream>()

  const fakeTrack = { stop: vi.fn(), readyState: 'live' }
  const fakeStream = { getTracks: () => [fakeTrack] } as unknown as MediaStream

    ; (globalThis as any).navigator = (globalThis as any).navigator || {}
    ; (globalThis as any).navigator.mediaDevices = {
      getUserMedia: vi.fn(async () => {
        getUserMediaCalls++
        return gumGate.promise
      }),
    }
    ; (globalThis as any).AudioContext = FakeAudioContext as any
    ; (globalThis as any).AudioWorkletNode = FakeAudioWorkletNode as any
    // audioManager builds the worklet URL from import.meta / location; a stub is
    // enough since addModule is faked.
    ; (globalThis as any).URL = (globalThis as any).URL
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('audioManager.startRecording in-flight guard (bd z9bc)', () => {
  it('two concurrent startRecording calls run getUserMedia only ONCE', async () => {
    const am = createAudioManager()

    // Fire two starts before the first finishes arming (gumGate is still open).
    const p1 = am.startRecording(vi.fn())
    const p2 = am.startRecording(vi.fn())

    // Both are in flight; getUserMedia must have been entered exactly once.
    expect(getUserMediaCalls).toBe(1)

    // Release the mic + let both settle.
    gumGate.resolve({ getTracks: () => [{ stop: vi.fn(), readyState: 'live' }] } as unknown as MediaStream)
    await Promise.all([p1, p2])

    // Still exactly one setup: no duplicate getUserMedia / addModule.
    expect(getUserMediaCalls).toBe(1)
    expect(addModuleCalls).toBe(1)
    expect(am.isRecording()).toBe(true)
  })

  it('a start AFTER arming completes is a no-op (recording already true)', async () => {
    const am = createAudioManager()
    const p1 = am.startRecording(vi.fn())
    gumGate.resolve({ getTracks: () => [{ stop: vi.fn(), readyState: 'live' }] } as unknown as MediaStream)
    await p1
    expect(am.isRecording()).toBe(true)

    await am.startRecording(vi.fn())
    expect(getUserMediaCalls).toBe(1) // no second setup
  })
})
