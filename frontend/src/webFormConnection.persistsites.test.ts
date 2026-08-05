/**
 * Guard: every site that PERSISTS SchemaFormState from WebFormConnection must
 * reconcile fieldValues first (bd polyglot-pdf-uw3w / 3irc / qim7 / tare / 6iwn).
 *
 * WHY A SOURCE-LEVEL GUARD. Every SchemaFormStateManager mutator spread-replaces
 * the WHOLE state and calls save() internally, so ANY of them called on a stale
 * `this.state` persists that stale copy over whatever the React UI wrote -- the
 * two-writer bug. Successive pre-PR review rounds each found one MORE
 * handler doing this (confirm/skip, then session_ready, then section_switched,
 * then drain_findings_result, then validation_result). Behavioural tests only
 * cover the handlers someone thought to test; this pins the SHAPE so the next
 * added persist site fails here instead of shipping.
 *
 * The fix could not be pushed down into SchemaFormStateManager.save() itself:
 * confirmField deliberately does NOT bump lastModified (it changes only
 * confirmation metadata, never the value), so a reconcile inside save() would
 * see a tie and prefer the persisted entry -- silently dropping `confirmed:true`
 * on every confirmation. Verified by probe. Hence per-call-site reconciles, and
 * hence this guard.
 *
 * ALLOWLIST, not a blacklist: it asserts the COMPLETE set of persist sites, so a
 * NEW one is a failure by default rather than something the pattern has to
 * anticipate.
 */

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'

const SRC = readFileSync(join(__dirname, 'webFormConnection.ts'), 'utf8')
const LINES = SRC.split('\n')

/** Strip line comments so commented-out examples never count as call sites. */
function isCode(line: string): boolean {
  return !/^\s*(\/\/|\*|\/\*)/.test(line)
}

/**
 * Mutators that spread the whole state (fieldValues included) and save().
 * Calling any of these on an unreconciled this.state persists stale fieldValues.
 */
const PERSISTING_MUTATORS = [
  'setSessionId',
  'setJitMode',
  'setContinuousSession',
  'markFieldSchemaLoaded',
  'confirmField',
  'markFieldSkipped',
  'pinField',
  'enqueueValidatorFindings',
  'markFieldsSteered',
  'consumeValidatorFindings',
  'updateField',
  // Section mutators persist the whole state too. They are called on a freshly
  // load()ed LOCAL rather than on this.state, so they are safe for a different
  // reason than the rest -- but they belong in the allowlist, or a NEW call site
  // passing this.state would slip past this check entirely.
  'switchToSection',
  'markSectionComplete',
]

describe('WebFormConnection fieldValues persist sites (two-writer guard)', () => {
  it('every persisting call site is one of the KNOWN, reconciled sites', () => {
    const found: string[] = []
    LINES.forEach((line, i) => {
      if (!isCode(line)) return
      for (const m of PERSISTING_MUTATORS) {
        if (line.includes(`SchemaFormStateManager.${m}(`)) {
          found.push(`${i + 1}:${m}`)
        }
      }
    })

    // Every entry below is reconciled immediately before the call (or, for
    // updateField, IS the stamping write itself -- it sets lastModified, so its
    // own entry wins the reconcile at the next site). If this list changes, the
    // new site needs a reconcileFieldValues() call before it -- or a documented
    // reason it cannot go stale -- and then this list gets updated.
    const EXPECTED = [
      'setSessionId',            // handleSessionReady        -- reconciled
      'setJitMode',              // handleSessionReady        -- same reconcile
      'setContinuousSession',    // handleSessionReady        -- same reconcile
      'markFieldSchemaLoaded',   // handleFormUpdated         -- reconciled
      'confirmField',            // handleConfirmFieldRequest -- reconciled
      'markFieldSkipped',        // handleSkipFieldRequest    -- reconciled
      'enqueueValidatorFindings',// handleValidationResult    -- reconciled
      'markFieldsSteered',       // handleDrainFindingsResult -- reconciled
      'consumeValidatorFindings',// handleDrainFindingsResult -- same reconcile
      'updateField',             // the CHOKEPOINT -- reconciled; its own write
                                 // stamps lastModified, so it wins its own reconcile
      // Safe WITHOUT a reconcile, each for a stated reason:
      'pinField',                // handleSwitchFieldRequest ADOPTS the persisted
                                 // snapshot wholesale at entry (bd ezg2), so
                                 // this.state cannot be stale by the time it runs
      'switchToSection',         // x3: called on a freshly load()ed local, not
      'switchToSection',         //     this.state (1636, 4120, and 4299 which
      'switchToSection',         //     re-reads AFTER its buffer-drain await)
      'markSectionComplete',     // same -- freshly load()ed local (4379)
    ]

    expect(found.map(f => f.split(':')[1]).sort()).toEqual([...EXPECTED].sort())
  })

  it('every bare save(this.state) is one of the KNOWN, reconciled sites', () => {
    const sites = LINES
      .map((line, i) => ({ line, n: i + 1 }))
      .filter(({ line }) => isCode(line) && line.includes('SchemaFormStateManager.save(this.state)'))

    // Four sites: handleSectionSwitched, handleConfirmFieldRequest,
    // handleSkipFieldRequest (all reconciled at handler entry), and
    // maybeEmitValidateWindows -- which does NOT reconcile because it is not an
    // entry point: all four of its callers reconcile earlier in the same
    // synchronous run. A new caller must reconcile before calling it.
    expect(sites).toHaveLength(4)
  })

  it('no persisting mutator reads a state snapshot captured BEFORE an await', () => {
    // The SECOND staleness shape, and the one the textual checks above cannot
    // see: `const s = load()` ... `await ...` ... `mutator(s, ...)`. Here
    // this.state is irrelevant -- the local snapshot goes stale across the await,
    // and the mutator persists it. switchToSection had exactly this (its
    // waitForBufferDrain polls for up to a full second).
    //
    // Heuristic: inside each method body, find a load() into a local, then an
    // await, then a persisting-mutator call passing that same local. Flag it.
    const PERSISTING = /SchemaFormStateManager\.(switchToSection|markSectionComplete|updateField|confirmField|markFieldSkipped|markFieldsSteered|consumeValidatorFindings|enqueueValidatorFindings|pinField|markFieldSchemaLoaded)\(\s*([A-Za-z_$][\w$]*)/

    const offenders: string[] = []
    let pendingLocals = new Map<string, number>()  // local name -> line captured
    let sawAwaitSince = new Set<string>()

    LINES.forEach((raw, i) => {
      if (!isCode(raw)) return
      const n = i + 1

      // A method boundary resets the tracking. Must NOT match control-flow
      // keywords (`if (`, `for (`, `while (`, `catch (`, `switch (`) -- an
      // earlier version did, which reset the tracking one line after the
      // capture and made this whole check silently vacuous.
      const methodStart = /^\s{2}(?:(?:private|public|protected|static|async)\s+)*[A-Za-z_$][\w$]*\s*\(/.test(raw)
        && !/^\s*(?:if|for|while|switch|catch|return|await|else)\b/.test(raw.trim())
      if (methodStart) {
        pendingLocals = new Map()
        sawAwaitSince = new Set()
      }

      // Matches `const s = load()`, `let s = load()`, AND a bare re-assignment
      // `s = load()` -- the last one matters: switchToSection declares the local
      // with its type on one line and assigns it on another, so requiring
      // const/let here would miss exactly the site this check exists for.
      const cap = raw.match(/(?:(?:const|let|var)\s+)?([A-Za-z_$][\w$]*)\s*=\s*SchemaFormStateManager\.load\(\)/)
      if (cap) {
        pendingLocals.set(cap[1], n)
        sawAwaitSince.delete(cap[1])
      }

      // Follow ALIASES: `const b = a` where `a` is a tracked local makes `b`
      // tracked too, inheriting its staleness. Without this, renaming through an
      // intermediate silently defeats the check -- two review rounds defeated
      // earlier versions exactly that way, the second by packing TWO alias
      // assignments onto one physical line. So scan EVERY match on the line
      // (matchAll, not match) and iterate to a fixpoint, rather than looking at
      // the first assignment only.
      for (let pass = 0; pass < 5; pass++) {
        let grew = false
        for (const alias of raw.matchAll(
          /(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*([A-Za-z_$][\w$]*)\s*(?:\?\?|;|,|\)|$)/g
        )) {
          const [, target, source] = alias
          if (pendingLocals.has(source) && !pendingLocals.has(target)) {
            pendingLocals.set(target, pendingLocals.get(source) as number)
            if (sawAwaitSince.has(source)) sawAwaitSince.add(target)
            grew = true
          }
        }
        if (!grew) break
      }

      if (/\bawait\b/.test(raw)) {
        for (const name of pendingLocals.keys()) sawAwaitSince.add(name)
      }

      const use = raw.match(PERSISTING)
      if (use) {
        const arg = use[2]
        if (pendingLocals.has(arg) && sawAwaitSince.has(arg)) {
          offenders.push(`${n}: ${use[1]}(${arg}) -- captured at line ${pendingLocals.get(arg)}, stale across an await`)
        }
      }
    })

    expect(offenders).toEqual([])
  })

  it('reconcileFieldValues is actually imported and used at multiple sites', () => {
    expect(SRC).toContain('reconcileFieldValues')
    const uses = LINES.filter(l => isCode(l) && l.includes('reconcileFieldValues(')).length
    // session_ready, confirm, skip, section_switched, drain_findings_result,
    // validation_result, form_updated, field_update, and updateField -- the
    // CHOKEPOINT every AI fill and manual edit funnels through (its persisting
    // call sits two frames below the handler, so a handler-level audit does not
    // see it).
    //
    // field_update and form_updated reconcile at HANDLER ENTRY, not just before
    // their writes: their availability gate READS this.state.fieldValues, and on
    // a stale copy a field whose show_if is satisfied by an on-screen answer
    // reads as unavailable, so the fill is REFUSED and the model is told not to
    // retry. A stale read is as damaging as a stale write there.
    //
    // handleSwitchFieldRequest is deliberately NOT here: it adopts the persisted
    // snapshot wholesale at entry (bd polyglot-pdf-ezg2), so its pinField write
    // cannot be stale. A reconcile there was added and then removed as dead code
    // -- mutation showed the test only failed when the ENTRY REFRESH was removed,
    // never when the reconcile was.
    expect(uses).toBe(9)
  })
})
