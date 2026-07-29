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
 * Force the prefers-reduced-motion answer for one test.
 *
 * jsdom does NOT implement matchMedia at all -- `typeof window.matchMedia` is
 * `'undefined'` here and calling it throws (measured, not assumed). The
 * component uses `window.matchMedia?.(...)`, whose optional chain short-circuits
 * the whole expression to `undefined`, leaving the guard falsy -- which is why
 * the ~13 other tests in this file exercise the normal (non-reduced) path
 * without stubbing anything.
 *
 * That optional chain is therefore LOAD-BEARING, not defensive decoration:
 * removing it would make every amplitude test in this file throw.
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

describe('listening/speaking swap (maintainer feedback 2026-07-29)', () => {
  // Pins WHICH shape each state uses, not just that amplitude reaches the SVG
  // (the "reads OUTPUT/MIC energy" tests above cover that). Without this, an
  // accidental re-swap, partial revert, or copy-paste slip between the two
  // adjacent CSS blocks would pass the full suite silently -- there was
  // previously nothing here pinning listening to the halo shape and speaking to
  // the ray-breathing shape, unlike the connecting redesign below.
  function ruleFor(state: string, selector: string): string {
    const m = SOL_CSS.match(
      new RegExp(`\\.sol\\[data-state="${state}"\\]\\s*\\.${selector}\\s*\\{[^}]*\\}`)
    )
    expect(m).toBeTruthy()
    return m![0]
  }

  it('listening drives the HALO (corona/ring/ring2), not ray length', () => {
    expect(ruleFor('listening', 'corona')).toMatch(/var\(--eb\)/)
    expect(ruleFor('listening', 'ring')).toMatch(/var\(--eb\)/)
    expect(ruleFor('listening', 'ring2')).toMatch(/var\(--eb\)/)
    // rayscale must NOT be amplitude-driven for listening -- that is speaking's.
    expect(SOL_CSS).not.toMatch(/\.sol\[data-state="listening"\]\s*\.rayscale/)
  })

  it('listening nods the disc via --e/--eb, same shape speaking used to own', () => {
    const disc = ruleFor('listening', 'disc')
    expect(disc).toMatch(/var\(--e\)/)
    expect(disc).toMatch(/var\(--eb\)/)
  })

  it('speaking drives RAY LENGTH (rayscale) via --e, not the halo', () => {
    expect(ruleFor('speaking', 'rayscale')).toMatch(/var\(--e\)/)
    // .disc and .ring must NOT exist for speaking -- those are listening's now.
    expect(SOL_CSS).not.toMatch(/\.sol\[data-state="speaking"\]\s*\.disc\s*\{/)
    expect(SOL_CSS).not.toMatch(/\.sol\[data-state="speaking"\]\s*\.ring\b/)
  })

  it('speaking corona scales with --e but is not amplitude-opacity-driven (that is listening\'s halo swell)', () => {
    const corona = ruleFor('speaking', 'corona')
    expect(corona).toMatch(/var\(--e\)/)
    expect(corona).not.toMatch(/var\(--eb\)/)
  })

  it('both states freeze ray rotation -- neither should spin like thinking', () => {
    expect(SOL_CSS).toMatch(/\.sol\[data-state="listening"\]\s*\.rayA,\s*\.sol\[data-state="listening"\]\s*\.rayB\s*\{\s*animation-play-state:\s*paused/)
    expect(SOL_CSS).toMatch(/\.sol\[data-state="speaking"\]\s*\.rayA,\s*\.sol\[data-state="speaking"\]\s*\.rayB\s*\{\s*animation-play-state:\s*paused/)
  })
})

describe('Sol stylesheet invariants', () => {
  // Asserted against the exported CSS text because these are cascade facts no
  // jsdom render can observe (jsdom does not run animations or resolve
  // animated-vs-normal declaration precedence).

  // sol-grow-disc / sol-grow-corona are written as `@keyframes name { 0% {
  // ...} 50% {...} 100% {...} }` -- a run of nested `{...}` blocks closed by a
  // final `} }`. Extracted with a small brace-depth walk rather than a single
  // regex, since a naive `[^}]*` or non-greedy `.*?\}` either stops at the
  // FIRST inner `}` or (worse) spills into unrelated rules later in the
  // stylesheet -- which is exactly what happened the first time this was
  // written and made these tests read a value from a different rule entirely.
  function extractKeyframes(css: string, name: string): string {
    const start = css.indexOf(`@keyframes ${name}`)
    expect(start).toBeGreaterThanOrEqual(0)
    const openBrace = css.indexOf('{', start)
    let depth = 0
    for (let i = openBrace; i < css.length; i++) {
      if (css[i] === '{') depth++
      else if (css[i] === '}') {
        depth--
        if (depth === 0) return css.slice(start, i + 1)
      }
    }
    throw new Error(`unterminated @keyframes ${name}`)
  }

  it('connecting grows the disc from tiny (10%) to full size (100%)', () => {
    // Parse the actual scale values out of the keyframe rather than eyeballing
    // the source text -- a transcription slip (e.g. .1 vs 1.1) would read as
    // plausible CSS and pass a substring check.
    const kf = extractKeyframes(SOL_CSS, 'sol-grow-disc')
    const scales = [...kf.matchAll(/scale\((\.?\d*\.?\d+)\)/g)].map(m => parseFloat(m[1]))
    expect(scales.length).toBeGreaterThan(0)
    expect(Math.min(...scales)).toBeCloseTo(0.1, 5)
    expect(Math.max(...scales)).toBeCloseTo(1, 5)
  })

  it('connecting SNAPS back to tiny rather than easing symmetrically', () => {
    // The snap is the whole point (maintainer feedback 2026-07-29): a smooth
    // in-and-out reads as calm breathing, which is too settled for "trying to
    // start". A snap needs the full-size scale held almost to the end of the
    // cycle, then dropped in a step too small to perceive as motion.
    const kf = extractKeyframes(SOL_CSS, 'sol-grow-disc')
    const steps = [...kf.matchAll(/(\d+(?:\.\d+)?)%\s*\{\s*transform:\s*scale\((\.?\d*\.?\d+)\)/g)]
      .map(m => ({ pct: parseFloat(m[1]), scale: parseFloat(m[2]) }))
    expect(steps.length).toBeGreaterThanOrEqual(3)
    // Find the last step still at full size and the first step back at the
    // small size; the gap between their percentages must be small (a snap),
    // not spread across most of the cycle (which would be a smooth ease).
    const lastFull = Math.max(...steps.filter(s => s.scale > 0.9).map(s => s.pct))
    const firstSmall = Math.min(...steps.filter(s => s.pct > lastFull && s.scale < 0.5).map(s => s.pct))
    expect(firstSmall - lastFull).toBeLessThan(1)
  })

  it('connecting stays dimmer than idle at its brightest point', () => {
    // Parse BOTH values numerically rather than asserting one side and leaving
    // the comparison in a comment -- the round-2 lesson from the corona-
    // inversion bug: a test that only checks idle's value would let connecting
    // be set brighter and still pass.
    const opacityOf = (rule: string) => {
      const m = rule.match(/opacity:\s*(\.?\d*\.?\d+)/)
      expect(m).toBeTruthy()
      return parseFloat(m![1])
    }
    const idleRule = SOL_CSS.match(/\.sol \.corona\s*\{[^}]*\}/)![0]
    const idle = opacityOf(idleRule)

    const kf = extractKeyframes(SOL_CSS, 'sol-grow-corona')
    const opacities = [...kf.matchAll(/opacity:\s*(\.?\d*\.?\d+)/g)].map(m => parseFloat(m[1]))
    expect(opacities.length).toBeGreaterThan(0)
    expect(Math.max(...opacities)).toBeLessThan(idle)
  })
})
