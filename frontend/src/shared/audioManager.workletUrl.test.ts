/**
 * AudioWorklet URL resolution (bd polyglot-pdf-43dxt).
 *
 * The worklet URL must be an ABSOLUTE path served from the Hosting site
 * root, independent of the current route's path depth. A path-relative
 * resolution (new URL('../shared/...', window.location.href)) is the exact
 * class of bug bd polyglot-pdf-3bsyv fixed for index.html assets: it happens
 * to cancel out for a one-segment route by coincidence, then breaks silently
 * on the first two-segment route, which the mic path does not exercise
 * today but is one nested route away from hitting.
 *
 * ASCII only. jsdom env (vite.config test.environment).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createAudioManager } from './audioManager'

let addedModuleUrls: string[] = []

class FakeAudioWorkletNode {
  port = { onmessage: null as any, postMessage: vi.fn() }
  connect = vi.fn()
  disconnect = vi.fn()
}

class FakeAudioContext {
  state: 'running' | 'suspended' | 'closed' = 'running'
  destination = {}
  audioWorklet = {
    addModule: vi.fn(async (url: string) => { addedModuleUrls.push(url) }),
  }
  createMediaStreamSource = vi.fn(() => ({ connect: vi.fn(), disconnect: vi.fn() }))
  resume = vi.fn(async () => { this.state = 'running' })
  suspend = vi.fn(async () => { this.state = 'suspended' })
  close = vi.fn(async () => { this.state = 'closed' })
}

function armFakes() {
  const fakeTrack = { stop: vi.fn(), readyState: 'live' }
  const fakeStream = { getTracks: () => [fakeTrack] } as unknown as MediaStream

    ; (globalThis as any).navigator = (globalThis as any).navigator || {}
    ; (globalThis as any).navigator.mediaDevices = {
      getUserMedia: vi.fn(async () => fakeStream),
    }
    ; (globalThis as any).AudioContext = FakeAudioContext as any
    ; (globalThis as any).AudioWorkletNode = FakeAudioWorkletNode as any
}

beforeEach(() => {
  addedModuleUrls = []
  armFakes()
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('audioManager worklet URL resolution (bd 43dxt)', () => {
  const routes = ['/', '/f', '/console/links', '/console/links/history']

  it.each(routes)('resolves the same absolute worklet URL on route %s (localhost)', async (path) => {
    window.history.pushState({}, '', path)
    const am = createAudioManager()
    await am.startRecording(vi.fn())

    expect(addedModuleUrls).toEqual(['/shared/audio-processor.worklet.js'])
  })

  // The old bug only manifested on a non-localhost hostname (the deployed
  // "isProduction" branch); jsdom's default hostname IS localhost, so a
  // mutation test on the routes above alone would never redden even if the
  // relative-URL bug came back. This is the case that must actually fail
  // under the old `new URL('../shared/...', window.location.href)` form.
  it.each(routes)('resolves the same absolute worklet URL on route %s (deployed hostname)', async (path) => {
    vi.stubGlobal('location', new URL(`https://app.example.com${path}`))
    window.history.pushState({}, '', path)
    const am = createAudioManager()
    await am.startRecording(vi.fn())

    expect(addedModuleUrls).toEqual(['/shared/audio-processor.worklet.js'])
  })
})
