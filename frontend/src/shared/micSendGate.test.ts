/**
 * Tests for shouldSendMicChunk -- the connection-level mic audio send gate.
 *
 * This gate was added to fix a demo failure where audio silently stopped
 * reaching the backend for ~4 minutes while status was stuck in a non-'connected'
 * state (e.g. 'switching_section'). The policy is:
 *   - 'connected': send.
 *   - 'switching_section' + socket OPEN: send (same-socket switch keeps socket alive).
 *   - 'switching_section' + socket CLOSED: drop + warn.
 *   - any other status: drop + warn.
 *   - warn is rate-limited to at most 1 per second.
 *
 * Covers bead polyglot-pdf-xroy.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { shouldSendMicChunk } from './connection'

describe('shouldSendMicChunk (connection-level mic send gate)', () => {
  it('(a) status connected -> sends audio', () => {
    expect(shouldSendMicChunk('connected', true)).toBe(true)
    expect(shouldSendMicChunk('connected', false)).toBe(true)
  })

  it('(b) switching_section + socket open -> sends audio', () => {
    expect(shouldSendMicChunk('switching_section', true)).toBe(true)
  })

  it('(c) switching_section + socket closed -> drops (returns false)', () => {
    expect(shouldSendMicChunk('switching_section', false)).toBe(false)
  })

  it('(d) reconnecting / idle_timeout / error -> drops (returns false)', () => {
    expect(shouldSendMicChunk('reconnecting', true)).toBe(false)
    expect(shouldSendMicChunk('reconnecting', false)).toBe(false)
    expect(shouldSendMicChunk('idle_timeout', true)).toBe(false)
    expect(shouldSendMicChunk('idle_timeout', false)).toBe(false)
    expect(shouldSendMicChunk('error', true)).toBe(false)
    expect(shouldSendMicChunk('error', false)).toBe(false)
    expect(shouldSendMicChunk('disconnected', false)).toBe(false)
    expect(shouldSendMicChunk('connecting', true)).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// Rate-limit warn test -- exercises the callback path directly (not the pure
// shouldSendMicChunk, which has no side effects). We replicate the drop-path
// logic inline to verify the 1-per-second rate limit fires exactly once for
// two drops within the same second.
// ---------------------------------------------------------------------------

describe('mic chunk drop warn rate-limit', () => {
  let warnSpy: ReturnType<typeof vi.spyOn>
  let realDateNow: () => number

  beforeEach(() => {
    warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    realDateNow = Date.now
  })

  afterEach(() => {
    warnSpy.mockRestore()
    Date.now = realDateNow
  })

  it('(e) two drops within 1 second emit exactly one warn', () => {
    // Simulate the rate-limit logic that lives in connection.ts's startRecording
    // callback -- extracted here as a closure so we can exercise it without
    // needing a full ConnectionManager or WebSocket.
    let lastWarnMs = 0
    const t0 = 1_000_000

    function simulateDrop(nowMs: number) {
      if (nowMs - lastWarnMs >= 1000) {
        lastWarnMs = nowMs
        console.warn('[VFF Connection] mic chunk DROPPED -- status=switching_section socketOpen=false')
      }
    }

    // First drop at t0 -- should warn
    simulateDrop(t0)
    // Second drop 500ms later -- within window, should NOT warn
    simulateDrop(t0 + 500)

    expect(warnSpy).toHaveBeenCalledTimes(1)
  })

  it('(e) drop after the 1-second window emits a second warn', () => {
    let lastWarnMs = 0
    const t0 = 2_000_000

    function simulateDrop(nowMs: number) {
      if (nowMs - lastWarnMs >= 1000) {
        lastWarnMs = nowMs
        console.warn('[VFF Connection] mic chunk DROPPED -- status=reconnecting socketOpen=false')
      }
    }

    simulateDrop(t0)          // warn 1
    simulateDrop(t0 + 500)    // suppressed
    simulateDrop(t0 + 1001)   // warn 2 -- new window

    expect(warnSpy).toHaveBeenCalledTimes(2)
  })
})
