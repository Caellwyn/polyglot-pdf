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
    ['connecting', 'connecting'],
    ['Setting up audio...', 'connecting'],
    ['warming', 'connecting'],
    ['warming up', 'connecting'],
    // A steady connected session with no activity flags: nothing to report yet.
    ['connected', 'idle'],
    ['connected section_2', 'idle'],
    ['switching_section', 'connecting'],
    ['reconnecting', 'connecting'],
    ['reconnecting (2/5)', 'connecting'],
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
  // animate Sol while the session is not actually carrying audio. These states
  // resolve to `connecting` (coming up / recovering) rather than to an activity
  // state -- `Ready` is the one that is genuinely pre-session, hence `idle`.
  const transient = ['connecting', 'switching_section', 'reconnecting', 'warming']

  it.each(transient)('%j ignores a stale speaking flag', (status) => {
    expect(deriveSolState({ status, speaking: true })).toBe('connecting')
  })

  it.each(transient)('%j ignores a stale thinking flag', (status) => {
    expect(deriveSolState({ status, thinking: true })).toBe('connecting')
  })

  it.each(transient)('%j ignores a stale micSending flag', (status) => {
    expect(deriveSolState({ status, micSending: true })).toBe('connecting')
  })

  it('Ready ignores every stale flag and stays idle', () => {
    expect(deriveSolState({ status: 'Ready', speaking: true })).toBe('idle')
    expect(deriveSolState({ status: 'Ready', thinking: true })).toBe('idle')
    expect(deriveSolState({ status: 'Ready', micSending: true })).toBe('idle')
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

describe('bd polyglot-pdf-bxng -- a live-but-transient session is never mistakable for a dead one', () => {
  // The bug bxng fixed: a session that is still live through `switching_section`
  // / `reconnecting` must not LOOK like one that is not running. Asserting
  // merely "not offline" is too weak -- it would pass if the transient states
  // collapsed into `idle`, i.e. the same picture as a cold, never-started
  // session. On the collapsed mobile FAB, Sol is the ONLY status visible (no
  // status text accompanies it), so that collapse would be the same user-facing
  // defect in a new guise.
  const transient = ['switching_section', 'reconnecting', 'reconnecting (3/5)', 'connecting']
  const dead = ['disconnected', 'error', 'idle_timeout', 'reconnect_failed']

  it.each(transient)('%j is distinguishable from a DEAD session', (status) => {
    const s = deriveSolState({ status })
    expect(s).not.toBe('offline')
    for (const d of dead) {
      expect(s).not.toBe(deriveSolState({ status: d }))
    }
  })

  it.each(transient)('%j is distinguishable from a COLD (never-started) session', (status) => {
    // This is the assertion the weaker "not offline" check was missing.
    expect(deriveSolState({ status })).not.toBe(deriveSolState({ status: 'Ready' }))
  })

  it('a transient state is also distinct from paused (a user choice, not a hiccup)', () => {
    for (const status of transient) {
      expect(deriveSolState({ status })).not.toBe('paused')
    }
  })
})

describe('SOL_STATE_LABEL', () => {
  it('names every state (accessible name must never be undefined)', () => {
    const states: SolState[] = [
      'idle', 'connecting', 'listening', 'thinking', 'speaking', 'paused', 'offline',
    ]
    for (const s of states) {
      expect(SOL_STATE_LABEL[s]).toBeTruthy()
    }
    // Labels must be distinct, or the screen-reader announcement collapses the
    // same states the visuals were just made to distinguish.
    const labels = states.map(s => SOL_STATE_LABEL[s])
    expect(new Set(labels).size).toBe(labels.length)
  })
})
