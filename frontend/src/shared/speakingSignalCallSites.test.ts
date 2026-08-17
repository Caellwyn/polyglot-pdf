/**
 * Every consumer of a "is Gemini talking?" signal reads the RIGHT one
 * (bd polyglot-pdf-uxc6s).
 *
 * Three signals exist and they are NOT interchangeable:
 *
 *   isModelSpeaking()   model PCM is scheduled, clip or no clip.
 *                       -> BARGE-IN / FLUSH and the re-prompt guard: "would
 *                          flushing stop the model mid-utterance?"
 *   isSpeaking()        model PCM AND no clip (clip-suppressed).
 *                       -> the SUSPEND/RESUME deadlock pair ONLY. A clip lives
 *                          inside the playback context, so suspending during
 *                          one would cut it mid-word and never resume it
 *                          (bd s1iex.4).
 *   isAnyAudioPlaying() the union. -> the avatar's energy gate + watchdog.
 *
 * Picking the wrong one is SILENT both ways: a flush site on isSpeaking()
 * skips barge-in during an overlap (the bug this bead fixes), and a suspend
 * site on isModelSpeaking() re-introduces the s1iex.4 deadlock. Neither throws,
 * neither shows up in a type check, and the overlap window needs an 8s drain
 * timeout to reach -- so nothing but an enumeration catches a new offender.
 *
 * This pins the SET, not one instance (CLAUDE.md scar #7): it derives the call
 * sites from source and fails when an unclassified one appears.
 */

import { readFileSync } from 'node:fs'
import { resolve, basename } from 'node:path'
import { describe, it, expect } from 'vitest'

const SRC = resolve(__dirname, '..')

// Files that legitimately consume a speaking signal.
const SCANNED = [
  'demo/VoiceOverlay.tsx',
  'demo/VoiceOverlayMobile.tsx',
  'shared/connection.ts',
  'shared/useGeminiSpeaking.ts',
]

/**
 * The COMPLETE classification. Every isSpeaking() / isModelSpeaking() call in
 * the scanned files must appear here, keyed by the code fragment.
 *
 * `signal` is the accessor the site MUST use. Adding a call site without
 * adding it here fails the test -- which is the point: the author is forced to
 * decide which of the three questions their site is asking.
 */
const CLASSIFIED: Array<{
  file: string; fragment: string; signal: string; why: string; anchor?: string;
}> = [
  // --- FLUSH / BARGE-IN: must be model-only, clips are irrelevant -----------
  {
    file: 'VoiceOverlay.tsx',
    fragment: 'const geminiSpeaking = audioManager?.IS_SPEAKING()',
    signal: 'isModelSpeaking',
    why: 'full barge-in flush after MIN_TURN_DURATION_MS',
  },
  {
    file: 'VoiceOverlayMobile.tsx',
    fragment: 'const geminiSpeaking = audioManager?.IS_SPEAKING()',
    signal: 'isModelSpeaking',
    why: 'full barge-in flush (mobile)',
  },
  {
    file: 'VoiceOverlayMobile.tsx',
    fragment: 'if (audioManager?.IS_SPEAKING()) {',
    signal: 'isModelSpeaking',
    why: 'PTT press barge-in flush',
  },
  {
    file: 'connection.ts',
    fragment: 'const geminiSpeaking = audioManager.IS_SPEAKING()',
    anchor: 'sendActivityStart',
    signal: 'isModelSpeaking',
    why: 'onVADSpeechStart barge-in flush',
  },
  {
    file: 'connection.ts',
    fragment: 'if (audioManager?.IS_SPEAKING()) return',
    signal: 'isModelSpeaking',
    why: 'post-resume re-prompt guard -- must not re-prompt over the model',
  },

  // --- SUSPEND / RESUME: MUST keep clip-suppression (s1iex.4 deadlock) ------
  {
    file: 'VoiceOverlay.tsx',
    fragment: 'if (audioManager && audioManager.IS_SPEAKING()) {',
    signal: 'isSpeaking',
    why: 'SUSPEND half -- pauseAudioContext; a clip inside the context must not be cut',
  },
  {
    file: 'VoiceOverlayMobile.tsx',
    fragment: 'if (audioManager && audioManager.IS_SPEAKING()) {',
    signal: 'isSpeaking',
    why: 'SUSPEND half (mobile)',
  },
  {
    file: 'connection.ts',
    fragment: 'const geminiSpeaking = audioManager.IS_SPEAKING()',
    anchor: 'pushToTalkMode',
    signal: 'isSpeaking',
    why: 'RESUME half (onVADSpeechEnd) -- must be the exact complement of suspend',
  },

  // --- AVATAR: the union, with a legacy-shape fallback ----------------------
  {
    file: 'useGeminiSpeaking.ts',
    fragment: ': audioManager.IS_SPEAKING()',
    signal: 'isSpeaking',
    why: 'avatar reconcile -- prefers isAnyAudioPlaying(); this is the older-manager fallback',
  },
]

function codeLines(file: string): string[] {
  return readFileSync(resolve(SRC, file), 'utf8')
    .split('\n')
    .map(l => l.replace(/\r$/, ''))
    .filter(l => {
      const t = l.trim()
      return !t.startsWith('//') && !t.startsWith('*') && !t.startsWith('/*')
    })
}

// ANY receiver, not just a variable literally named `audioManager` (my own
// first cut missed `connectionManager?.getAudioManager()?.isSpeaking()`,
// which is exactly the shape a new caller reaches for). Match the method
// call itself and let the classification table sort out which site it is.
const CALL = /\.\s*(isSpeaking|isModelSpeaking)\s*\(\s*\)/

// Match a site by its ACCESSOR-INDEPENDENT shape, so regressing the accessor
// still MATCHES the entry and trips the accessor assertion (the informative
// failure) rather than merely going stale. Fragments below therefore omit the
// method name; `anchor` disambiguates two sites sharing a line shape.
function siteKey(line: string): string {
  return line.replace(/is(Model)?Speaking/g, 'IS_SPEAKING').trim()
}

/**
 * Two connection.ts sites share a line shape (`const geminiSpeaking =
 * audioManager.X()`) but ask OPPOSITE questions -- one is the barge-in flush,
 * the other the resume half of the deadlock pair. Disambiguate by the nearest
 * preceding distinguishing token rather than by line number, which would rot
 * on the first edit above them.
 */
const ANCHORS = ['sendActivityStart', 'pushToTalkMode']

function nearestAnchor(rel: string, target: string): string | undefined {
  const lines = codeLines(rel)
  const idx = lines.indexOf(target)
  if (idx < 0) return undefined
  for (let i = idx; i >= 0 && i > idx - 12; i--) {
    for (const a of ANCHORS) if (lines[i].includes(a)) return a
  }
  return undefined
}

describe('speaking-signal call sites are classified (bd polyglot-pdf-uxc6s)', () => {
  it('every call site appears in CLASSIFIED with the right accessor', () => {
    const unclassified: string[] = []

    for (const rel of SCANNED) {
      const name = basename(rel)
      for (const line of codeLines(rel)) {
        const m = CALL.exec(line)
        if (!m) continue
        const used = m[1]
        const key = siteKey(line)
        const entry = CLASSIFIED.find(
          c => c.file === name
            && key.includes(c.fragment)
            && (!c.anchor || nearestAnchor(rel, line) === c.anchor),
        )
        if (!entry) {
          unclassified.push(`${name}: ${line.trim().slice(0, 100)}`)
          continue
        }
        expect(
          used,
          `${name} uses ${used}() where the classification says ${entry.signal}() `
          + `(${entry.why}). Flush/barge-in sites need isModelSpeaking (a clip `
          + `overlap makes isSpeaking false while the model talks); the `
          + `suspend/resume pair needs isSpeaking (a clip lives inside the `
          + `playback context and must not be cut mid-word).`,
        ).toBe(entry.signal)
      }
    }

    expect(
      unclassified,
      'These call sites read a speaking signal but are not classified. Decide '
      + 'which question the site asks -- "is the model mid-utterance?" '
      + '(isModelSpeaking, for flush/barge-in) or "is it safe to suspend the '
      + 'playback context?" (isSpeaking, for the suspend/resume pair) -- then '
      + 'add it to CLASSIFIED. Picking wrong is SILENT in both directions.',
    ).toEqual([])
  })

  it('the classification is live -- every entry still matches real code', () => {
    // A stale entry silently whitelists whatever moves into that fragment.
    for (const c of CLASSIFIED) {
      const rel = SCANNED.find(f => basename(f) === c.file)
      expect(rel, `no scanned file named ${c.file}`).toBeTruthy()
      const hits = codeLines(rel!).filter(
        l => siteKey(l).includes(c.fragment)
          && (!c.anchor || nearestAnchor(rel!, l) === c.anchor),
      )
      expect(
        hits.length,
        `stale classification: ${c.file} no longer contains "${c.fragment}" `
        + `(${c.why}). Update or remove the entry.`,
      ).toBeGreaterThan(0)
    }
  })

  it('both flush-side and suspend-side sites actually exist', () => {
    // Guards against the whole table drifting to one signal, which would make
    // the per-site assertions vacuously agree with a broken codebase.
    const model = CLASSIFIED.filter(c => c.signal === 'isModelSpeaking')
    const turn = CLASSIFIED.filter(c => c.signal === 'isSpeaking')
    expect(model.length, 'no barge-in sites classified').toBeGreaterThanOrEqual(5)
    expect(turn.length, 'no suspend/resume sites classified').toBeGreaterThanOrEqual(3)
  })
})
