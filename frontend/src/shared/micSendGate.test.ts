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
import { shouldSendMicChunk, createMicDropWarn } from './connection'

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
// Rate-limit warn test -- drives the real createMicDropWarn helper exported
// from connection.ts so the production rate-limit logic has real coverage
// (bd polyglot-pdf-b6k4, item 3: prior tests used a hand-copied closure).
// ---------------------------------------------------------------------------

describe('mic chunk drop warn rate-limit (createMicDropWarn)', () => {
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
    const warn = createMicDropWarn()
    const t0 = 1_000_000

    Date.now = () => t0
    warn('switching_section', false)   // first drop -- should warn

    Date.now = () => t0 + 500
    warn('switching_section', false)   // within window -- suppressed

    expect(warnSpy).toHaveBeenCalledTimes(1)
    expect(warnSpy).toHaveBeenCalledWith(
      '[VFF Connection] mic chunk DROPPED -- status=switching_section socketOpen=false'
    )
  })

  it('(e) drop after the 1-second window emits a second warn', () => {
    const warn = createMicDropWarn()
    const t0 = 2_000_000

    Date.now = () => t0
    warn('reconnecting', false)        // warn 1

    Date.now = () => t0 + 500
    warn('reconnecting', false)        // suppressed

    Date.now = () => t0 + 1001
    warn('reconnecting', false)        // warn 2 -- new window

    expect(warnSpy).toHaveBeenCalledTimes(2)
  })
})
