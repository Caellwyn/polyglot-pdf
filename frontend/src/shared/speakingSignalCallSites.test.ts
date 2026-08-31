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

import { readFileSync, readdirSync } from 'node:fs'
import { resolve, basename } from 'node:path'
import { describe, it, expect } from 'vitest'

const SRC = resolve(__dirname, '..')

// The files that consume a speaking signal TODAY. This is the classification's
// index, not its protection boundary -- `discoverConsumers()` below walks the
// whole tree, so a consumer in a NEW file is caught rather than silently
// escaping (fresh-eyes round 1: a hardcoded allowlist only guards edits INSIDE
// already-listed files, which is the weaker half of what this test promises).
const SCANNED = [
  'demo/VoiceOverlay.tsx',
  'demo/VoiceOverlayMobile.tsx',
  'schema-forms/components/SchemaForm.tsx',
  'shared/connection.ts',
  'shared/useGeminiSpeaking.ts',
]

/** Every production .ts/.tsx under src/, tests and generated output excluded. */
function allProductionFiles(dir = SRC, acc: string[] = []): string[] {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const full = resolve(dir, e.name)
    if (e.isDirectory()) {
      if (e.name === 'node_modules' || e.name === '__fixtures__') continue
      allProductionFiles(full, acc)
    } else if (/\.tsx?$/.test(e.name) && !/\.test\.tsx?$/.test(e.name)) {
      acc.push(full)
    }
  }
  return acc
}

/**
 * Files that reference a speaking accessor, discovered from source.
 * audioManager.ts itself DEFINES them, so it is excluded from call-site duty.
 */
function discoverConsumers(): string[] {
  return allProductionFiles()
    .filter(f => basename(f) !== 'audioManager.ts')
    // CALL-shaped, not a bare name match: a file merely MENTIONING the
    // accessors in prose (a comment, a doc reference) is not a decision
    // site. Reusing CALL keeps discovery and classification in agreement.
    .filter(f => CALL.test(readFileSync(f, 'utf8')))
}

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
  {
    file: 'SchemaForm.tsx',
    fragment: "if (typeof audio?.IS_SPEAKING === 'function' && audio.IS_SPEAKING()) {",
    signal: 'isModelSpeaking',
    why:
      'click-to-focus suppression (bd polyglot-pdf-a08po) -- asks "is the model ' +
      'mid-utterance?", the same question barge-in asks. A click during an ' +
      'overlap must NOT move the search origin: under DTI the model holds one ' +
      "field's schema and the backend coercion pointer is singular, so " +
      'retargeting mid-question mis-fills the spoken answer. isSpeaking() reads ' +
      'false during a model+clip overlap, which would let exactly that through.',
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

function codeLinesAbs(abs: string): string[] {
  // Delegates to the same splitter codeLines() uses, so the two cannot drift.
  return splitCodeLines(readFileSync(abs, 'utf8'))
}

/**
 * Resolve the anchor for the call site at line INDEX i.
 *
 * Index-based, not indexOf(text) (bd polyglot-pdf-wge8m): when a regression
 * makes two sites byte-identical -- exactly what happens if the RESUME half is
 * regressed to match the flush half -- indexOf returns the FIRST for both, so
 * the resume site silently binds to the flush site's anchor and the accessor
 * assertion passes on a real deadlock regression.
 */
function anchorAtIndex(lines: string[], i: number): string | undefined {
  for (let j = i; j >= 0 && j > i - 12; j--) {
    for (const a of ANCHORS) if (lines[j].includes(a)) return a
  }
  return undefined
}

function nearestAnchorAbs(abs: string, target: string): string | undefined {
  const lines = codeLinesAbs(abs)
  const idx = lines.indexOf(target)
  if (idx < 0) return undefined
  for (let i = idx; i >= 0 && i > idx - 12; i--) {
    for (const a of ANCHORS) if (lines[i].includes(a)) return a
  }
  return undefined
}

function splitCodeLines(text: string): string[] {
  return text
    .split('\n')
    .map(l => l.replace(/\r$/, ''))
    .filter(l => {
      const t = l.trim()
      return !t.startsWith('//') && !t.startsWith('*') && !t.startsWith('/*')
    })
}

function codeLines(file: string): string[] {
  return splitCodeLines(readFileSync(resolve(SRC, file), 'utf8'))
}

// ANY receiver, not just a variable literally named `audioManager` (my own
// first cut missed `connectionManager?.getAudioManager()?.isSpeaking()`,
// which is exactly the shape a new caller reaches for). Match the method
// call itself and let the classification table sort out which site it is.
// Three shapes, because the first two cuts each missed one (fresh-eyes r1):
//   .isSpeaking()            member call, incl. optional chaining and any
//                            receiver (`getAudioManager()?.isSpeaking()`)
//   ['isModelSpeaking']()    computed member
//   isSpeaking()             a bare call from a destructured binding
const CALL = /(?:\.\s*|\[\s*['"`]|)(isSpeaking|isModelSpeaking)(?:['"`]\s*\])?\s*\(\s*\)/

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

    // Walk every DISCOVERED consumer, so a new FILE cannot escape.
    for (const abs of discoverConsumers()) {
      const name = basename(abs)
      const fileLines = codeLinesAbs(abs)
      for (let li = 0; li < fileLines.length; li++) {
        const line = fileLines[li]
        const m = CALL.exec(line)
        if (!m) continue
        const used = m[1]
        const key = siteKey(line)
        const entry = CLASSIFIED.find(
          c => c.file === name
            && key.includes(c.fragment)
            && (!c.anchor || anchorAtIndex(fileLines, li) === c.anchor),
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

  it('SCANNED still matches what discovery finds', () => {
    // SCANNED is documentation, not protection -- but a stale index is
    // misleading. If discovery finds a consumer file SCANNED does not list,
    // the classification table above needs a look, not just this constant.
    const found = discoverConsumers().map(f => basename(f)).sort()
    const listed = SCANNED.map(f => basename(f)).sort()
    expect(
      found,
      `discovery found consumer files that SCANNED does not list. Add them to `
      + `SCANNED and classify their call sites in CLASSIFIED (or, if the file `
      + `only MENTIONS the accessor names in prose, this is a false positive `
      + `worth narrowing).`,
    ).toEqual(listed)
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
