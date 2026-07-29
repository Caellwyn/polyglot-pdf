// @vitest-environment jsdom
//
// Component-level tests for Sol (bd polyglot-pdf-2p4y).
//
// The status -> state mapping is covered in solState.test.ts. This file pins the
// things only a render can prove:
//   - every state reaches the DOM as `data-state`, which is the entire CSS API;
//   - the SVG defs are per-instance, so two Sols on one page cannot collide on
//     gradient/mask ids (the mobile overlay renders TWO: the FAB and the panel);
//   - every `url(#...)` reference resolves INSIDE its own <svg> -- a cross-
//     instance reference renders an unpainted disc when the other instance
//     unmounts, which is exactly the bug per-instance ids exist to prevent;
//   - the accessible name is present (or correctly suppressed when decorative).
import { render, cleanup } from '@testing-library/react'
import { describe, it, expect, afterEach, vi } from 'vitest'
import { Sol, SOL_CSS } from './Sol'
import type { SolState } from './solState'

afterEach(cleanup)

/**
 * Force the prefers-reduced-motion answer for one test. jsdom supplies a
 * matchMedia that always reports `matches: false`, so the normal path is live by
 * default and only the reduced case needs stubbing.
 */
function stubReducedMotion(matches: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: query.includes('prefers-reduced-motion') ? matches : false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
}

const frame = () => new Promise(r => requestAnimationFrame(() => r(null)))

const STATES: SolState[] = [
  'idle', 'connecting', 'listening', 'thinking', 'speaking', 'paused', 'offline',
]

describe('Sol rendering', () => {
  it.each(STATES)('exposes state %s as data-state', (state) => {
    const { container } = render(<Sol state={state} />)
    const svg = container.querySelector('[data-testid="sol-avatar"]')
    expect(svg?.getAttribute('data-state')).toBe(state)
  })

  it('gives every instance its own gradient + mask ids', () => {
    const { container } = render(
      <>
        <Sol state="idle" />
        <Sol state="speaking" />
        <Sol state="paused" />
      </>
    )
    const ids = [...container.querySelectorAll('defs [id]')].map(n => n.id)
    expect(ids.length).toBeGreaterThan(0)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('resolves every url(#id) reference within its own svg', () => {
    const { container } = render(
      <>
        <Sol state="idle" />
        <Sol state="paused" />
      </>
    )
    const svgs = [...container.querySelectorAll('[data-testid="sol-avatar"]')]
    expect(svgs).toHaveLength(2)
    for (const svg of svgs) {
      const refs: string[] = []
      for (const el of svg.querySelectorAll('[fill], [mask]')) {
        for (const attr of ['fill', 'mask']) {
          const v = el.getAttribute(attr)
          if (v && v.startsWith('url(#')) refs.push(v.slice(5, -1))
        }
      }
      expect(refs.length).toBeGreaterThan(0)
      // Collect the ids this svg actually defines and compare as sets. (Avoids
      // CSS.escape, which jsdom does not implement, and an id selector, which
      // would need escaping for ids that start with a digit.)
      const own = new Set([...svg.querySelectorAll('defs [id]')].map(n => n.id))
      for (const id of refs) {
        // Must be defined in THIS svg, not merely somewhere in the document.
        expect(own.has(id)).toBe(true)
      }
    }
  })

  it('carries an accessible name by default', () => {
    const { container } = render(<Sol state="listening" />)
    const svg = container.querySelector('[data-testid="sol-avatar"]')!
    expect(svg.getAttribute('role')).toBe('img')
    expect(svg.getAttribute('aria-label')).toBe('Listening')
    expect(svg.getAttribute('aria-hidden')).toBeNull()
  })

  it('is hidden from assistive tech when decorative (the FAB labels itself)', () => {
    const { container } = render(<Sol state="listening" decorative />)
    const svg = container.querySelector('[data-testid="sol-avatar"]')!
    expect(svg.getAttribute('aria-hidden')).toBe('true')
    expect(svg.getAttribute('aria-label')).toBeNull()
    expect(svg.getAttribute('role')).toBeNull()
  })

  it('scales motion inversely with size -- small instances move MORE', () => {
    const { container } = render(
      <>
        <Sol state="idle" size={56} />
        <Sol state="idle" size={120} />
      </>
    )
    const [small, large] = [...container.querySelectorAll('[data-testid="sol-avatar"]')] as HTMLElement[]
    const kSmall = parseFloat(small.style.getPropertyValue('--k'))
    const kLarge = parseFloat(large.style.getPropertyValue('--k'))
    expect(kSmall).toBeGreaterThan(kLarge)
    expect(kLarge).toBeGreaterThanOrEqual(1)
  })

  it('parks the energy vars at zero in states that do not consume amplitude', () => {
    const { container } = render(<Sol state="paused" energy={90} />)
    const svg = container.querySelector('[data-testid="sol-avatar"]') as HTMLElement
    expect(svg.style.getPropertyValue('--e')).toBe('0')
    expect(svg.style.getPropertyValue('--eb')).toBe('0')
  })

  it('reads OUTPUT energy while speaking and MIC energy while listening', async () => {
    // The mic is near-silent while the assistant talks, so the speaking halo must
    // not be driven by `energy` -- if it were, the state would look dead.
    const getOutputEnergy = vi.fn(() => 80)

    const { rerender } = render(
      <Sol state="speaking" energy={0} getOutputEnergy={getOutputEnergy} />
    )
    // Let the rAF loop run a frame.
    await new Promise(r => requestAnimationFrame(() => r(null)))
    expect(getOutputEnergy).toHaveBeenCalled()

    // Listening must NOT consult the output getter -- it visualises the user.
    getOutputEnergy.mockClear()
    rerender(<Sol state="listening" energy={50} getOutputEnergy={getOutputEnergy} />)
    await new Promise(r => requestAnimationFrame(() => r(null)))
    await new Promise(r => requestAnimationFrame(() => r(null)))
    expect(getOutputEnergy).not.toHaveBeenCalled()
  })

  it('survives a missing output getter (pre-connect / mocked managers)', async () => {
    const { container } = render(<Sol state="speaking" energy={0} />)
    await frame()
    const svg = container.querySelector('[data-testid="sol-avatar"]') as HTMLElement
    // No getter -> treated as silence, not NaN (which would break every calc()).
    expect(Number.isNaN(parseFloat(svg.style.getPropertyValue('--e')))).toBe(false)
  })
})

describe('Sol reduced-motion handling', () => {
  // These pin the two behavioural changes that shipped in the corona-fix commit.
  // Both are invisible to every other test in the suite: an inverted guard would
  // kill the amplitude animation on EVERY normal device, and a reverted keyframe
  // would restore the corona inversion, with 1100+ tests still green either way.
  afterEach(() => { vi.unstubAllGlobals() })

  it('skips the amplitude loop entirely under prefers-reduced-motion', async () => {
    stubReducedMotion(true)
    const getOutputEnergy = vi.fn(() => 80)
    const { container } = render(
      <Sol state="speaking" energy={90} getOutputEnergy={getOutputEnergy} />
    )
    await frame()
    await frame()
    const svg = container.querySelector('[data-testid="sol-avatar"]') as HTMLElement
    // Every rule --e/--eb feed is overridden under reduced motion, so running the
    // loop would be a per-frame FFT copy for no visual effect.
    expect(svg.style.getPropertyValue('--e')).toBe('0')
    expect(svg.style.getPropertyValue('--eb')).toBe('0')
    expect(getOutputEnergy).not.toHaveBeenCalled()
  })

  it('DOES run the amplitude loop when reduced motion is off (guard not inverted)', async () => {
    stubReducedMotion(false)
    const getOutputEnergy = vi.fn(() => 80)
    render(<Sol state="speaking" energy={0} getOutputEnergy={getOutputEnergy} />)
    await frame()
    // The mirror of the test above: without this, inverting the guard would pass.
    expect(getOutputEnergy).toHaveBeenCalled()
  })
})

describe('Sol stylesheet invariants', () => {
  // Asserted against the exported CSS text because these are cascade facts no
  // jsdom render can observe (jsdom does not run animations or resolve
  // animated-vs-normal declaration precedence).

  it('the connecting corona pulses in SIZE ONLY, never via sol-pulse', () => {
    // sol-pulse animates opacity as well as transform, and an animated
    // declaration outranks a normal one -- so borrowing it here silently voids
    // the corona's `opacity: .5` and swings it 0.78-1.0, BRIGHTER than idle's
    // steady .85. That is the exact bug this pins: the state whose whole brief
    // is "quietly waiting" became the loudest one Sol has.
    const coronaRule = SOL_CSS.match(
      /\.sol\[data-state="connecting"\]\s*\.corona\s*\{[^}]*\}/
    )
    expect(coronaRule).toBeTruthy()
    expect(coronaRule![0]).toContain('sol-pulse-size')
    expect(coronaRule![0]).not.toMatch(/animation:\s*sol-pulse\s/)
    expect(coronaRule![0]).toContain('opacity: .5')
  })

  it('sol-pulse-size animates transform only (no opacity to override with)', () => {
    const kf = SOL_CSS.match(/@keyframes sol-pulse-size\s*\{[\s\S]*?\}\s*\}/)
    expect(kf).toBeTruthy()
    expect(kf![0]).not.toContain('opacity')
  })

  it('connecting stays dimmer than idle -- the whole point of the state', () => {
    const idle = SOL_CSS.match(/\.sol \.corona\s*\{[^}]*\}/)![0]
    expect(idle).toContain('opacity: .85')
    // .5 (connecting) < .85 (idle): quieter, not louder.
  })
})
