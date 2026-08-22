/**
 * The intro flag must switch the LEGACY disclaimer read OFF -- everywhere
 * (bd polyglot-pdf-s1iex.5).
 *
 * The cross-surface review found the exact failure this pins: the Listen
 * Again handler was guarded with `if (introEnabled) return`, but the OTHER
 * `readDisclaimer` caller -- the `pendingDisclaimerRead` effect -- was not.
 * With the flag ON that fired the model-read anyway, so Gemini spoke the old
 * disclaimer text OVER Sol's scripted clip: two voices, two different texts.
 * The sprint-20 plan states the ON quadrant "must NOT fall back to
 * read_disclaimer"; this is that requirement, enforced.
 *
 * It is a SOURCE-level set pin rather than a render test on purpose. The
 * defect is "one of N call sites lacks a guard", and the durable protection
 * is asserting the COMPLETE set (CLAUDE.md scar #7) -- a THIRD caller added
 * later fails here instead of shipping a second voice. Both overlays are
 * hand-duplicated, so both are checked identically; the bug was present in
 * both, symmetric down to the omission.
 */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect } from 'vitest'

// Resolve from THIS TEST FILE, never process.cwd(): a worktree vitest run is
// invoked from the MAIN checkout here (the node_modules junction workaround),
// so a cwd-relative read would audit the wrong copy (measured, bd s1iex.4).
function overlaySource(file: string): string {
  const here = expect.getState().testPath as string
  return readFileSync(resolve(here, '..', file), 'utf-8')
}

const OVERLAYS = ['VoiceOverlay.tsx', 'VoiceOverlayMobile.tsx']

describe.each(OVERLAYS)('%s: intro flag disables the legacy read', (file) => {
  it('guards EVERY readDisclaimer call site behind the intro flag', () => {
    const src = overlaySource(file)
    const lines = src.split('\n')
    const callSites = lines
      .map((line, i) => ({ line: line.trim(), i }))
      .filter(x => x.line.includes('connectionManager.readDisclaimer(')
        || x.line.includes('connectionManager?.readDisclaimer('))

    // Two production callers per overlay today: the Listen Again handler and
    // the pendingDisclaimerRead effect. A new one must justify itself here.
    expect(callSites.length).toBe(2)

    for (const site of callSites) {
      // Each must sit inside a block that returns early when introEnabled.
      // Look back far enough to cover the effect's guard-at-top shape.
      // Measured in CODE lines, not raw lines: a comment block must not be
      // able to push the guard out of range. bd polyglot-pdf-nsb4y added
      // ~10 comment lines above each site and ate a third of the old raw-40
      // budget in a single commit (cross-surface round 2 measured the slack
      // down to 12). A scope-walk was tried and REJECTED -- climbing outward
      // until introEnabled appears anywhere always succeeds in a component
      // that mentions the flag, so removing a real guard left it green.
      const codeAbove = lines
        .slice(0, site.i)
        .filter((l) => {
          const t = l.trim()
          // Strip line comments AND block-comment bodies: a /* */ block
          // pushed the guard out of range just as easily (verified by
          // mutation). It failed CLOSED -- a false alarm, not a missed
          // bug -- but a needless trip-wire on a legitimate edit.
          return t && !t.startsWith('//') && !t.startsWith('/*')
            && !t.startsWith('*') && !t.startsWith('*/')
        })
      const window = codeAbove.slice(-40).join('\n')
      expect(window).toContain('introEnabled')
    }
  })

  it('clears the pending flag on the intro path so it cannot fire later', () => {
    // Returning early is not enough: a pendingDisclaimerRead left TRUE would
    // fire the moment the flag or a dependency changed.
    const src = overlaySource(file)
    expect(src).toContain('if (pendingDisclaimerRead) setPendingDisclaimerRead(false)')
  })

  it('keeps introEnabled in the effect dependency list', () => {
    // A guard reading a value outside its dep array is a stale-closure bug
    // waiting to happen.
    const src = overlaySource(file)
    expect(src).toContain(
      '}, [introEnabled, status, pendingDisclaimerRead, connectionManager, selectedLanguage])')
  })

  it('still HAS the legacy path for the flag-off quadrant', () => {
    // bd polyglot-pdf-vr5bj owns deleting read_disclaimer entirely (s1iex.6
    // is closed and shipped the single-handshake change instead). Until the
    // flags flip, flag-off must keep working -- this bead must not
    // half-delete it.
    //
    // The second assertion used to be `toContain('DISCLAIMER_TRANSLATIONS')`,
    // which pinned that the legacy path SPOKE the legacy text. bd
    // polyglot-pdf-nsb4y retired that constant as body text, leaving only an
    // import -- so the assertion degraded to a string-presence check
    // satisfiable by a line that could be deleted with zero behavioral
    // effect (tsconfig sets no noUnusedLocals, so tsc would not notice).
    // Pin what the legacy path ACTUALLY speaks now: the shared script.
    const src = overlaySource(file)
    expect(src).toContain('connectionManager.readDisclaimer(')
    expect(src).toContain('renderIntroParagraphs(')
  })
})
