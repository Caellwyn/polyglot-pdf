/**
 * The voice harness's kit-agnostic target discovery (bd polyglot-pdf-tcemw).
 *
 * tests/e2e/voice-harness/harness.js is injected into a live page, so it has no
 * module exports; this evaluates its source in jsdom and drives the installed
 * window.__VFF_HARNESS. Every schema here is SYNTHETIC -- the point of the
 * discovery is that no test (and no harness default) names a real kit's field
 * ids (CLAUDE.md scar #10).
 */
import { describe, it, expect, beforeEach } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

const HARNESS_SRC = fs.readFileSync(
  path.join(__dirname, '../../../tests/e2e/voice-harness/harness.js'), 'utf8')

type Field = Record<string, unknown> & { id: string; type: string }

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Harness = any

function install(fields: Field[], hook?: Record<string, unknown>): Harness {
  sessionStorage.clear()
  sessionStorage.setItem('schema_form_state', JSON.stringify({
    schema: { fields, sections: [] }, fieldValues: {},
  }))
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const w = window as any
  w.__VFF_TEST_INJECT = hook ?? null
  w.__VFF_HARNESS = undefined
  new Function(HARNESS_SRC)()
  return w.__VFF_HARNESS
}

// A hook whose seedFieldConfirmed writes the same sessionStorage shape the app's
// SchemaFormStateManager does, so the harness's read-back check sees it.
function seedingHook(): Record<string, unknown> {
  return {
    getLastNextField: () => null,
    seedFieldConfirmed: (id: string, value: string) => {
      const st = JSON.parse(sessionStorage.getItem('schema_form_state') as string)
      st.fieldValues[id] = { value, confirmed: true }
      sessionStorage.setItem('schema_form_state', JSON.stringify(st))
      return true
    },
  }
}

const text = (id: string, extra: Record<string, unknown> = {}): Field =>
  ({ id, type: 'text', name: id, spoken_name: id.replace(/_/g, ' '), ...extra })

describe('findDigitsTarget', () => {
  beforeEach(() => sessionStorage.clear())

  it('prefers a field whose own pattern accepts the value over an earlier numeric-label field', () => {
    const H = install([
      text('given_name'),
      text('reference_number'),
      text('member_code', { validation: { pattern: '^[0-9]{7,9}$' } }),
    ])
    expect(H.findDigitsTarget('1234567')).toMatchObject({ fieldId: 'member_code', tier: 'pattern' })
  })

  it('falls back to the first field whose id or spoken name reads as a number', () => {
    const H = install([text('given_name'), text('tax_id_number'), text('zip_code')])
    expect(H.findDigitsTarget('1234567')).toMatchObject({ fieldId: 'tax_id_number', tier: 'numeric-label' })
  })

  it('never picks a field whose pattern rejects the value, even with a numeric label', () => {
    const H = install([
      text('zip_number', { validation: { pattern: '^[0-9]{5}$' } }),
      text('account_number'),
    ])
    expect(H.findDigitsTarget('1234567')).toMatchObject({ fieldId: 'account_number' })
  })

  it('ignores a number word that appears only in the long printed name', () => {
    const H = install([
      text('street', { name: 'Street address, apartment number, or rural route number', spoken_name: 'street address' }),
      text('passport_no'),
    ])
    expect(H.findDigitsTarget('1234567')).toMatchObject({ fieldId: 'passport_no' })
  })

  it('skips conditional, hidden, read-only, multiline, non-text and too-short fields', () => {
    const H = install([
      text('a_number', { show_if: { field: 'x', operator: 'equals', value: 'y' } }),
      text('b_number', { hidden: true }),
      text('c_number', { read_only: true }),
      text('d_number', { multiline: true }),
      { id: 'e_number', type: 'date' },
      text('f_number', { max_length: 5 }),
    ])
    expect(H.findDigitsTarget('1234567')).toBeNull()
  })

  describe('without the app validator (local fallback)', () => {
    it('rejects a format_preset field, whose rules only the app knows', () => {
      const H = install([
        text('applicant_ssn', { validation: { format_preset: 'ssn' } }),
        text('member_number'),
      ])
      expect(H.findDigitsTarget('1234567')).toMatchObject({ fieldId: 'member_number' })
    })

    it('rejects a field whose min_length the value does not reach', () => {
      const H = install([text('tax_id', { validation: { min_length: 9 } }), text('member_number')])
      expect(H.findDigitsTarget('1234567')).toMatchObject({ fieldId: 'member_number' })
    })

    it('rejects a field whose numeric max the value exceeds', () => {
      const H = install([
        { id: 'count_number', type: 'number', spoken_name: 'count number', validation: { max: 100 } },
        text('member_number'),
      ])
      expect(H.findDigitsTarget('1234567')).toMatchObject({ fieldId: 'member_number' })
    })
  })

  describe('with the app validator on the inject hook', () => {
    it("defers to the app's verdict, rejecting what it rejects", () => {
      const H = install([text('first_number'), text('second_number')], {
        validateFieldValue: (id: string) => (id === 'first_number' ? 'must be 9 digits' : null),
      })
      expect(H.findDigitsTarget('1234567')).toMatchObject({ fieldId: 'second_number' })
    })

    it("accepts a preset field the app accepts (the local fallback is not consulted)", () => {
      const H = install([text('alien_number', { validation: { format_preset: 'a_number' } })], {
        validateFieldValue: () => null,
      })
      expect(H.findDigitsTarget('1234567')).toMatchObject({ fieldId: 'alien_number', tier: 'numeric-label' })
    })

    it('still requires a pattern-tier field to pass the app validator', () => {
      const H = install([
        text('code_a', { validation: { pattern: '^[0-9]+$' } }),
        text('code_b', { validation: { pattern: '^[0-9]+$' } }),
      ], {
        validateFieldValue: (id: string) => (id === 'code_a' ? 'rejected' : null),
      })
      expect(H.findDigitsTarget('1234567')).toMatchObject({ fieldId: 'code_b', tier: 'pattern' })
    })
  })
})

describe('seedPrefixBefore / prepareDigitsTarget', () => {
  it('seeds exactly the fields before the target, in schema order, with shape-appropriate values', () => {
    const H = install([
      { id: 'kind', type: 'radio', options: [{ value: 'first' }, { value: 'second' }] },
      { id: 'dob', type: 'date' },
      text('given_name', { show_if: { field: 'kind', operator: 'equals', value: 'first' } }),
      text('tax_id_number'),
      text('after_target'),
    ], seedingHook())

    const t = H.prepareDigitsTarget('1234567')
    expect(t).toMatchObject({ fieldId: 'tax_id_number', seeded: 3, failed: [] })

    const st = JSON.parse(sessionStorage.getItem('schema_form_state') as string)
    expect(Object.keys(st.fieldValues)).toEqual(['kind', 'dob', 'given_name'])
    expect(st.fieldValues.kind.value).toBe('first')
    expect(st.fieldValues.dob.value).toBe('01/01/1990')
    expect(st.fieldValues.given_name.value).toBe('Test')
  })

  it('reports a kit with no eligible field instead of seeding anything', () => {
    const H = install([text('given_name'), text('family_name')], seedingHook())
    expect(H.prepareDigitsTarget('1234567')).toMatchObject({ fieldId: null })
    const st = JSON.parse(sessionStorage.getItem('schema_form_state') as string)
    expect(st.fieldValues).toEqual({})
  })
})

describe('runCycle without a fieldId', () => {
  it('is a setup error when the session has not been pointed at any field', async () => {
    const H = install([text('tax_id_number')], seedingHook())
    const r = await H.runCycle({})
    expect(r.verdict).toBe('FLAKY')
    expect(r.reason).toMatch(/^setup-error/)
  })
})
