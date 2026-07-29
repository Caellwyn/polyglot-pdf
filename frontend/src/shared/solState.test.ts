// Unit tests for the Sol status mapping (bd polyglot-pdf-2p4y).
//
// This is the single place the two hand-duplicated overlays agree on what the
// avatar means, so the precedence rules are pinned here rather than being
// re-derived (and drifting) in each component. The status strings exercised
// below are the REAL set the overlays can receive -- the ConnectionStatus union
// plus the extra values the UI layer injects ('Ready', 'Setting up audio...',
// 'paused', '*warming*', 'connected <suffix>').
import { describe, it, expect } from 'vitest'
import { deriveSolState, SOL_STATE_LABEL } from './solState'
import type { SolState } from './solState'

const LIVE = 'connected'

describe('deriveSolState -- status coverage', () => {
  // Every status string the overlays can actually pass, with no thinking /
  // speaking / micSending flags set. Anything not explicitly paused or terminal
  // must land on `idle`: warm and awake, committing to nothing.
  const cases: Array<[string, SolState]> = [
    ['Ready', 'idle'],
    ['ready', 'idle'],
    ['connecting', 'idle'],
    ['Setting up audio...', 'idle'],
    ['warming', 'idle'],
    ['warming up', 'idle'],
    ['connected', 'idle'],
    ['connected section_2', 'idle'],
    ['switching_section', 'idle'],
    ['reconnecting', 'idle'],
    ['reconnecting (2/5)', 'idle'],
    ['paused', 'paused'],
    ['disconnected', 'offline'],
    ['error', 'offline'],
    ['idle_timeout', 'offline'],
    ['reconnect_failed', 'offline'],
  ]

  it.each(cases)('status %j -> %s', (status, expected) => {
    expect(deriveSolState({ status })).toBe(expected)
  })

  it('is case-insensitive (the UI layer mixes casing)', () => {
    expect(deriveSolState({ status: 'PAUSED' })).toBe('paused')
    expect(deriveSolState({ status: 'Disconnected' })).toBe('offline')
    expect(deriveSolState({ status: 'CONNECTED' , micSending: true })).toBe('listening')
  })

  it('treats an empty / undefined-ish status as idle rather than throwing', () => {
    expect(deriveSolState({ status: '' })).toBe('idle')
    expect(deriveSolState({ status: undefined as unknown as string })).toBe('idle')
  })
})

describe('deriveSolState -- precedence', () => {
  it('speaking beats thinking (agent_processing can stay armed into the first audio)', () => {
    expect(
      deriveSolState({ status: LIVE, thinking: true, speaking: true })
    ).toBe('speaking')
  })

  it('speaking beats listening (half-duplex: we are talking, not taking a turn)', () => {
    expect(
      deriveSolState({ status: LIVE, speaking: true, micSending: true })
    ).toBe('speaking')
  })

  it('thinking beats listening', () => {
    expect(
      deriveSolState({ status: LIVE, thinking: true, micSending: true })
    ).toBe('thinking')
  })

  it('paused outranks every activity flag -- never claim to consume a paused mic', () => {
    expect(
      deriveSolState({ status: 'paused', thinking: true, speaking: true, micSending: true })
    ).toBe('paused')
  })

  it('offline outranks every activity flag', () => {
    for (const status of ['disconnected', 'error', 'idle_timeout', 'reconnect_failed']) {
      expect(
        deriveSolState({ status, thinking: true, speaking: true, micSending: true })
      ).toBe('offline')
    }
  })
})

describe('deriveSolState -- activity requires a live session', () => {
  // A stale speaking/thinking flag left over from a dropped socket must not
  // animate Sol while the session is not actually carrying audio.
  const notLive = ['connecting', 'switching_section', 'reconnecting', 'Ready', 'warming']

  it.each(notLive)('%j ignores a stale speaking flag', (status) => {
    expect(deriveSolState({ status, speaking: true })).toBe('idle')
  })

  it.each(notLive)('%j ignores a stale thinking flag', (status) => {
    expect(deriveSolState({ status, thinking: true })).toBe('idle')
  })

  it.each(notLive)('%j ignores a stale micSending flag', (status) => {
    expect(deriveSolState({ status, micSending: true })).toBe('idle')
  })

  it('listening requires micSending, not merely being connected', () => {
    // This is the whole point of the 1dvp fix: "listening" must mean audio is
    // genuinely reaching the backend, not just that a socket is open.
    expect(deriveSolState({ status: LIVE })).toBe('idle')
    expect(deriveSolState({ status: LIVE, micSending: true })).toBe('listening')
  })

  it('a connected <suffix> session is live too', () => {
    expect(deriveSolState({ status: 'connected section_3', micSending: true })).toBe('listening')
    expect(deriveSolState({ status: 'connected section_3', speaking: true })).toBe('speaking')
  })
})

describe('SOL_STATE_LABEL', () => {
  it('names every state (accessible name must never be undefined)', () => {
    const states: SolState[] = ['idle', 'listening', 'thinking', 'speaking', 'paused', 'offline']
    for (const s of states) {
      expect(SOL_STATE_LABEL[s]).toBeTruthy()
    }
  })
})
