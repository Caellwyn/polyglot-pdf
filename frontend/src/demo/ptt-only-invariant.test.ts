/**
 * Push-to-talk is the ONLY input mode (bd polyglot-pdf-v1m8g).
 *
 * PTT *knows* when the user is speaking -- they are holding the button. Gemini's
 * automatic activity detection *infers* it from the audio. Running both meant a
 * signal we can state exactly was second-guessed by one that can only estimate,
 * and the two could disagree. So there is exactly ONE mechanism deciding when a
 * turn starts and ends, and no UI to switch away from it.
 *
 * This pins the SET of ways the mode could come back (CLAUDE.md scar #8) by
 * reading the shipped source, rather than one symptom. The gap it closes is real:
 * the first cut of v1m8g removed the VAD plumbing but LEFT the toggle wired to a
 * handler, which -- combined with the new single-arm audio gate -- would have
 * silently stranded the mic (fresh-eyes finding).
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const SRC = resolve(__dirname, '..')
const OVERLAYS = ['demo/VoiceOverlay.tsx', 'demo/VoiceOverlayMobile.tsx']

function source(rel: string): string {
  return readFileSync(resolve(SRC, rel), 'utf8')
}

describe('PTT-only invariant (bd polyglot-pdf-v1m8g)', () => {
  it.each(OVERLAYS)('%s has no mode-toggle handler', (rel) => {
    expect(source(rel)).not.toContain('handlePushToTalkToggle')
  })

  it.each(OVERLAYS)('%s never flips pushToTalkMode in React state', (rel) => {
    // The React setter is what a toggle would need. connectionManager
    // .setPushToTalkMode(...) is a DIFFERENT call (it pushes the constant down to
    // the audio layer) and is expected to remain.
    const s = source(rel)
    expect(s).not.toMatch(/(?<!connectionManager[?.]{0,2})\bsetPushToTalkMode\(\s*(true|false|newMode|!)/)
  })

  it.each(OVERLAYS)('%s renders no input-mode toggle control', (rel) => {
    const s = source(rel)
    expect(s).not.toContain('vff-ptt-toggle')
  })

  it('the input-mode translation keys are gone from every language', () => {
    // They labelled the removed control. Leaving them would be orphaned copy in
    // 18 languages, and the bead named these three explicitly.
    const t = source('demo/overlayTranslations.ts')
    for (const key of ['inputMode', 'modeAuto', 'modePTT']) {
      expect(t, `${key} still present in overlayTranslations`).not.toContain(`${key}:`)
    }
  })

  it('no native-VAD accessor survives on the client', () => {
    // The other half of the two-gate problem: the backend used to tell the client
    // which detector was driving turns.
    for (const rel of [...OVERLAYS, 'shared/connection.ts', 'shared/audioManager.ts', 'webFormConnection.ts']) {
      const s = source(rel)
      for (const dead of ['isNativeVad', 'setNativeVad', 'onNativeVadMode', 'native_vad']) {
        expect(s, `${dead} still referenced in ${rel}`).not.toContain(dead)
      }
    }
  })
})
