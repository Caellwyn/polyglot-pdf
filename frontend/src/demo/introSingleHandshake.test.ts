/**
 * Agree is the FIRST and ONLY connect on the intro path
 * (bd polyglot-pdf-s1iex.6).
 *
 * The epic's criterion 3: no Gemini Live session exists before Agree, and
 * Agree produces exactly ONE WebSocket handshake -- where today there are two
 * (connect-then-restart). That second handshake is what
 * `switchToFirstSection` does: a full disconnect, a 100ms sleep, and a
 * re-handshake, needed only because the model was mid-disclaimer and had to
 * be torn down before form-filling could start. With Sol's clip there is no
 * session to tear down.
 *
 * SOURCE-level, like introFlagQuadrant.test.ts and for the same reason: the
 * defect class is "one of N call sites still connects (or still restarts)",
 * and the durable guard is asserting the COMPLETE set of sites (CLAUDE.md
 * scar #7). A rendered-overlay test cannot enumerate call sites; it can only
 * sample the paths someone thought to drive. Both are wanted -- the rendered
 * complement is filed as polyglot-pdf-jd57a.
 */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect } from 'vitest'

// Resolve from THIS TEST FILE, never process.cwd(): a worktree vitest run is
// invoked from the MAIN checkout here (the node_modules junction workaround),
// so a cwd-relative read audits the wrong copy (measured, bd s1iex.4).
function overlaySource(file: string): string {
  const here = expect.getState().testPath as string
  return readFileSync(resolve(here, '..', file), 'utf-8')
}

const OVERLAYS = ['VoiceOverlay.tsx', 'VoiceOverlayMobile.tsx']

describe.each(OVERLAYS)('%s: one handshake on the intro path', (file) => {
  it('guards EVERY pre-Agree connect site behind the intro flag', () => {
    const src = overlaySource(file)
    const lines = src.split('\n')
    // The connect sites that run BEFORE Agree. handleDisclaimerAgree's own
    // connect is excluded by construction: it sits after the flag check, and
    // the assertion below confirms each guarded site precedes its await.
    const preAgree = lines
      .map((line, i) => ({ line: line.trim(), i }))
      .filter(x => x.line === 'await handleConnect()')

    // FOUR today, and the count is the point -- a fifth must justify itself:
    //   1. the mount effect            (guarded: deferred on the intro path)
    //   2. the language-select handler (guarded: deferred on the intro path)
    //   3. Agree's own connect         (the ONE we keep -- the flag gates INTO it)
    //   4. the stale-connection reconnect inside the LEGACY Agree sequence,
    //      which sits AFTER the intro early-return and so is unreachable when
    //      the flag is on. Verified POSITIONALLY below rather than assumed.
    expect(preAgree.length).toBe(4)

    const introReturnLine = lines.findIndex(
      l => l.includes('Intro path - single connect on Agree'))
    expect(introReturnLine).toBeGreaterThan(-1)

    for (const site of preAgree) {
      // Below the early return: legacy-only by POSITION, which is a stronger
      // guarantee than a nearby-keyword check.
      if (site.i > introReturnLine) continue
      const window = lines.slice(Math.max(0, site.i - 30), site.i).join('\n')
      expect(window).toContain('introEnabled')
    }
  })

  it('does not restart the session on the intro path', () => {
    // switchToFirstSection is the SECOND handshake (disconnect + 100ms sleep +
    // re-handshake). It must be unreachable when the flag is on.
    const src = overlaySource(file)
    const lines = src.split('\n')
    const restarts = lines
      .map((line, i) => ({ line: line.trim(), i }))
      .filter(x => x.line.includes('switchToFirstSection('))
    expect(restarts.length).toBe(1)
    // POSITION is the guarantee: the intro early-return sits ABOVE it inside
    // handleDisclaimerAgree, so the restart is unreachable when the flag is
    // on. A keyword-proximity check would still pass if the return moved
    // BELOW it -- exactly the regression that resurrects the second handshake.
    const introReturnLine = lines.findIndex(
      l => l.includes('Intro path - single connect on Agree'))
    expect(introReturnLine).toBeGreaterThan(-1)
    expect(restarts[0].i).toBeGreaterThan(introReturnLine)
  })

  it('does not send the interrupt sequence on the intro path', () => {
    // activity_start/flush/resume/activity_end exist ONLY to cut off a model
    // mid-disclaimer. With no session they are meaningless, and an unmatched
    // activity_end is a real defect class (bd ala0).
    const src = overlaySource(file)
    const introReturn = src.indexOf('Intro path - single connect on Agree')
    expect(introReturn).toBeGreaterThan(-1)
    const agreeStart = src.lastIndexOf('handleDisclaimerAgree', introReturn)
    const beforeReturn = src.slice(agreeStart, introReturn)
    // Nothing in the Agree handler BEFORE the intro branch may interrupt.
    expect(beforeReturn).not.toContain('sendActivityStart')
    expect(beforeReturn).not.toContain('flushAudioQueue')
  })

  it('sets the FILL language before the single connect', () => {
    // Fresh-eyes round 1 caught this: the legacy path set fillLanguage as a
    // SIDE EFFECT of switchToFirstSection -- the only production caller that
    // moved it off createConnectionManager's hardcoded 'English'. Deleting the
    // restart therefore shipped fill_language="English" in the handshake, so a
    // Spanish user would HEAR Spanish while every field's guidance told the
    // model to write the values in English. Silent, and invisible in audio.
    //
    // Order matters: it must be set BEFORE handleConnect() so the value rides
    // the handshake rather than being corrected after the session starts.
    const src = overlaySource(file)
    const lines = src.split('\n')
    const setLine = lines.findIndex(l => l.includes('changeFillLanguage(selectedLanguage)'))
    expect(setLine).toBeGreaterThan(-1)

    const introReturnLine = lines.findIndex(
      l => l.includes('Intro path - single connect on Agree'))
    // Inside the intro branch...
    expect(setLine).toBeGreaterThan(introReturnLine)
    // ...and BEFORE that branch's connect.
    const connectAfter = lines.findIndex(
      (l, i) => i > introReturnLine && l.trim() === 'await handleConnect()')
    expect(connectAfter).toBeGreaterThan(setLine)
  })

  it('PRESERVES the mount connect for the already-accepted (reload) branch', () => {
    // The one thing this bead must NOT break: a reload user never sees Agree,
    // so removing the mount connect wholesale would leave them with no
    // session at all. The guard is conjunctive on purpose.
    const src = overlaySource(file)
    expect(src).toContain('if (introEnabled && !alreadyAccepted) {')
  })

  it('still HAS the legacy connect-then-restart path for flag-off', () => {
    // Flag-off must remain exactly today's behavior; bead s1iex.7 owns the
    // dead-path deletion, not this bead.
    const src = overlaySource(file)
    expect(src).toContain('switchToFirstSection(')
    expect(src).toContain('sendActivityStart')
  })
})
