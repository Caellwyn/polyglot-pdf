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
import { describe, it, expect, afterEach } from 'vitest'
import { Sol } from './Sol'
import type { SolState } from './solState'

afterEach(cleanup)

const STATES: SolState[] = ['idle', 'listening', 'thinking', 'speaking', 'paused', 'offline']

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
})
