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
 * The REAL predicate discoverConsumers() applies to each file's content --
 * pulled out and named so a test can drive the exact production logic
 * directly, instead of hand-recomposing CALL + splitCodeLines inline (a
 * hand-recomposed copy can silently drift from what discoverConsumers()
 * actually runs, pinning nothing real -- CLAUDE.md scar #8).
 *
 * CALL-shaped, not a bare name match: a file merely MENTIONING the
 * accessors in prose (a comment, a doc reference) is not a decision site.
 * Reusing CALL keeps discovery and classification in agreement -- and
 * COMMENTS ARE STRIPPED FIRST (splitCodeLines, the same stripper the
 * per-line classification walk uses below), so a JSDoc mention of e.g.
 * isAnyAudioPlaying() cannot make a file a "consumer" on the strength of
 * prose alone (bd polyglot-pdf-hb583: this used to be true only by
 * accident, because the pre-fix CALL regex's third alternative was a
 * literal 0x08 byte that happened to also never match comment text).
 */
function isConsumerContent(rawText: string): boolean {
  return CALL.test(splitCodeLines(rawText).join('\n'))
}

/**
 * Files that reference a speaking accessor, discovered from source.
 * audioManager.ts itself DEFINES them, so it is excluded from call-site duty.
 */
function discoverConsumers(): string[] {
  return allProductionFiles()
    .filter(f => basename(f) !== 'audioManager.ts')
    .filter(f => isConsumerContent(readFileSync(f, 'utf8')))
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
    fragment: "if (typeof audio?.IS_ANY_AUDIO === 'function' && audio.IS_ANY_AUDIO()) {",
    signal: 'isAnyAudioPlaying',
    why:
      'click-to-focus suppression (bd polyglot-pdf-a08po) -- asks "is the user ' +
      'HEARING anything right now?", so it wants the UNION, not turn-taking. ' +
      'A click must not move the search origin mid-playback: under DTI the ' +
      "model holds one field's schema and the backend coercion pointer is " +
      'singular. isModelSpeaking() would be WRONG here (outer review): it is ' +
      'model PCM only and cannot count a clip, and the spell-back player waits ' +
      'for that count to reach zero before playing -- so it reads false for the ' +
      'whole spell-back window. name_spellback carries no field_id and resolves ' +
      'via computeNextField, so a click there would spell a DIFFERENT field back.',
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
    fragment: '? audioManager.IS_ANY_AUDIO()',
    signal: 'isAnyAudioPlaying',
    why:
      'avatar reconcile, PREFERRED path (bd s1iex.4) -- the avatar must stay ' +
      'animated for a clip too, so it wants the union. Newly visible to this ' +
      'enumeration now that CALL covers isAnyAudioPlaying (bd polyglot-pdf-a08po); ' +
      'only its legacy fallback below was classified before.',
  },
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
//
// isAnyAudioPlaying is in the set too (bd polyglot-pdf-a08po): it is one of the
// three signals this file exists to keep straight, and a consumer of it can ask
// the wrong question just as easily as a consumer of the other two.
//
// MERGE NOTE: dev and this branch each fixed a DIFFERENT half of this regex.
// dev replaced the third alternative's literal 0x08 BACKSPACE byte with a real
// word boundary (bd polyglot-pdf-hb583) -- that byte was why a bare
// destructured call was invisible to discovery. This branch widened the
// accessor alternation to cover the union. BOTH fixes are kept here: dropping
// either half re-opens the hole it closed.
const CALL = /(?:\.\s*|\[\s*['"`]|\b)(isSpeaking|isModelSpeaking|isAnyAudioPlaying)(?:['"`]\s*\])?\s*\(\s*\)/

// Match a site by its ACCESSOR-INDEPENDENT shape, so regressing the accessor
// still MATCHES the entry and trips the accessor assertion (the informative
// failure) rather than merely going stale. Fragments below therefore omit the
// method name; `anchor` disambiguates two sites sharing a line shape.
function siteKey(line: string): string {
  // isAnyAudioPlaying normalizes to its OWN token, not IS_SPEAKING: it answers a
  // DIFFERENT question (is the user hearing anything, clips included) from the
  // turn-taking pair. Collapsing all three would let a swap between the union
  // and a turn-taking accessor keep matching the same entry and slip through.
  return line
    .replace(/isAnyAudioPlaying/g, 'IS_ANY_AUDIO')
    .replace(/is(Model)?Speaking/g, 'IS_SPEAKING')
    .trim()
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
      + 'which of the THREE questions the site asks -- "is the model '
      + 'mid-utterance?" (isModelSpeaking, for flush/barge-in), "is it safe to '
      + 'suspend the playback context?" (isSpeaking, for the suspend/resume '
      + 'pair), or "is the user HEARING anything, clips included?" '
      + '(isAnyAudioPlaying, the union -- the avatar, and any gate on whether '
      + 'audio is audible) -- then add it to CLASSIFIED. Picking wrong is '
      + 'SILENT in every direction.',
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

  it('CALL matches a bare destructured call, not just member calls (bd polyglot-pdf-hb583)', () => {
    // The third documented shape (line ~199 above): "isSpeaking() a bare call
    // from a destructured binding". Mutation-verified: this goes red against
    // the pre-fix regex, whose third alternative was a literal 0x08 byte that
    // matches nothing in real source, so only the FIRST two shapes (member
    // call, computed member) were ever actually reachable.
    expect(CALL.test('if (isSpeaking()) { flush() }')).toBe(true)
    // FLIPPED from false by bd polyglot-pdf-a08po (merge with hb583). When
    // hb583 wrote this line, isAnyAudioPlaying was genuinely outside the
    // alternation, so a bare destructured call to it was correctly expected NOT
    // to match. a08po added the union to the name group on purpose -- a
    // consumer of it can ask the wrong question just as easily as a consumer of
    // the other two -- so this shape must now be DISCOVERED, not ignored.
    //
    // The two beads fixed different halves of the same regex: hb583 the third
    // alternative (0x08 -> a real word boundary), a08po the name group. This
    // assertion is where the two meet: it only passes if BOTH landed, since it
    // needs the bare-call shape (hb583) AND the union in the names (a08po).
    expect(CALL.test('const { isAnyAudioPlaying } = am; if (isAnyAudioPlaying()) return')).toBe(true)
    expect(CALL.test('return isModelSpeaking() ? 1 : 0')).toBe(true)
    // The other two shapes must keep matching -- this bead must not narrow them.
    expect(CALL.test('audio.isSpeaking()')).toBe(true)
    expect(CALL.test("obj['isModelSpeaking']()")).toBe(true)
  })

  it('a comment-only mention does not make a file a "consumer" (bd polyglot-pdf-hb583)', () => {
    // Calls isConsumerContent() DIRECTLY -- the exact predicate
    // discoverConsumers() applies to every file's content, not a
    // hand-recomposed CALL+splitCodeLines expression that could silently
    // drift from the real one (CLAUDE.md scar #8: a mutation-test caught
    // exactly this drift risk during review -- the first version of this
    // test called CALL.test() directly and stayed green even when
    // discoverConsumers()'s own comment-stripping was reverted). Not a
    // throwaway fixture FILE, because the production behavior IS "run
    // isConsumerContent on this text" -- calling the real function is the
    // faithful, minimal pin; a fixture file would only re-derive the same
    // call through an extra layer of disk I/O.
    const commentOnly = '/**\n * calls isModelSpeaking() eventually\n */\nexport const x = 1\n'
    const realCall = '  const x = () => { isModelSpeaking() }\n'
    expect(
      isConsumerContent(commentOnly),
      'a comment-only mention must NOT make a file a "consumer"',
    ).toBe(false)
    expect(
      isConsumerContent(realCall),
      'a real call must still make a file a "consumer"',
    ).toBe(true)
  })
})
