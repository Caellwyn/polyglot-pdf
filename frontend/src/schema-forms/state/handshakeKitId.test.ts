/**
 * kit_id must ride EVERY handshake, not just the JIT one
 * (bd polyglot-pdf-s1iex.6).
 *
 * kit_id is the UNIQUE kit key: two kits can share a form_number, and only
 * kit_id tells them apart in the confirmation audit trail (bd
 * polyglot-pdf-47r3). It is deliberately NOT a `form_metadata` key, so the
 * backend has no fallback -- whatever the handshake omits is simply absent
 * from every confirmation record for that session, permanently.
 *
 * The bug this pins: `getHandshakePayload` picks the JIT builder only when
 * `state.jitModeEnabled` is true, and that flag is set ONLY from the
 * backend's `session_ready`. So a session's FIRST handshake ALWAYS takes the
 * legacy branch -- which omitted kit_id. That was harmless while the
 * form-filling handshake was the SECOND one (bd s1iex.6 deletes that second
 * handshake), and became silent audit-trail loss the moment Agree's single
 * connect was the only handshake. Found by the Opus cross-surface review.
 *
 * Pinned on BOTH builders so a future edit cannot drop it from either.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { SchemaFormStateManager } from './schemaFormState'

vi.mock('../onboardingStorage', () => ({
  loadOnboardingState: () => ({ formId: 'i-90', language: 'Spanish' }),
  clearOnboardingState: () => {},
}))

// Schema shape per the real FormSchema: fields live in a TOP-LEVEL array and
// sections reference them by id (extractSectionFields filters the array).
const SCHEMA = {
  form_metadata: { title: 'Test', form_number: 'I-90' },
  fields: [
    { id: 'f1', label: 'First Name', type: 'text', spoken_name: 'first name' },
  ],
  sections: [
    { id: 's1', label: 'Section One', order: 1, fields: ['f1'] },
  ],
} as any

function baseState(overrides: Record<string, unknown> = {}) {
  return {
    schema: SCHEMA,
    formSessionId: 'fs-1',
    currentSectionId: 's1',
    fieldValues: {},
    loadedFieldIds: new Set<string>(),
    completedSections: [],
    jitModeEnabled: false,
    selectedLanguage: 'Spanish',
    ...overrides,
  } as any
}

describe('handshake carries kit_id (bd s1iex.6)', () => {
  beforeEach(() => {
    try { window.sessionStorage.clear() } catch { /* jsdom */ }
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('LEGACY payload carries kit_id -- the FIRST handshake always uses it', () => {
    // jitModeEnabled is false until the backend's session_ready arrives, so
    // this branch IS the first handshake of every session. With the intro
    // path's single connect it is the ONLY one.
    const payload: any = SchemaFormStateManager.getHandshakePayload(
      baseState({ jitModeEnabled: false }), 'Spanish', false)
    expect(payload.kit_id).toBe('i-90')
  })

  it('JIT payload still carries kit_id', () => {
    const payload: any = SchemaFormStateManager.getHandshakePayload(
      baseState({ jitModeEnabled: true }), 'Spanish', false)
    expect(payload.kit_id).toBe('i-90')
  })

  it('both builders agree on the kit_id VALUE', () => {
    // A drift between the two would make the audit trail depend on which
    // handshake happened to run -- the defect class this pins.
    const legacy: any = SchemaFormStateManager.getHandshakePayload(
      baseState({ jitModeEnabled: false }), 'Spanish', false)
    const jit: any = SchemaFormStateManager.getHandshakePayload(
      baseState({ jitModeEnabled: true }), 'Spanish', false)
    expect(legacy.kit_id).toBe(jit.kit_id)
  })

  it('carries the fill language the caller passed, on both builders', () => {
    // The sibling of the same bug: fill_language rode switchToFirstSection's
    // side effect until bd s1iex.6 set it explicitly before connecting.
    for (const jitModeEnabled of [false, true]) {
      const payload: any = SchemaFormStateManager.getHandshakePayload(
        baseState({ jitModeEnabled }), 'Spanish', false)
      expect(payload.fill_language).toBe('Spanish')
    }
  })
})
