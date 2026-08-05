/**
 * Guard: every site that PERSISTS SchemaFormState from WebFormConnection must
 * reconcile fieldValues first (bd polyglot-pdf-uw3w / 3irc / qim7 / tare / 6iwn).
 *
 * WHY A SOURCE-LEVEL GUARD. Every SchemaFormStateManager mutator spread-replaces
 * the WHOLE state and calls save() internally, so ANY of them called on a stale
 * `this.state` persists that stale copy over whatever the React UI wrote -- the
 * two-writer bug. Four successive pre-PR review rounds each found one MORE
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
      'pinField',                // handleSwitchFieldRequest  -- reconciled
      'enqueueValidatorFindings',// handleValidationResult    -- reconciled
      'markFieldsSteered',       // handleDrainFindingsResult -- reconciled
      'consumeValidatorFindings',// handleDrainFindingsResult -- same reconcile
      'updateField',             // applyValue -- the stamping write itself
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

  it('reconcileFieldValues is actually imported and used at multiple sites', () => {
    expect(SRC).toContain('reconcileFieldValues')
    const uses = LINES.filter(l => isCode(l) && l.includes('reconcileFieldValues(')).length
    // One per reconciled handler: session_ready, confirm, skip, section_switched,
    // drain_findings_result, validation_result, switch_field, form_updated.
    expect(uses).toBe(8)
  })
})
