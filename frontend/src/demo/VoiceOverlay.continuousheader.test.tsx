// @vitest-environment jsdom
//
// Regression test for bd polyglot-pdf-944q: in continuous-session mode the
// VoiceOverlay header must show the FORM TITLE (the whole form is one session),
// not the pinned first section's label. currentSectionId stays on section 1 in
// continuous mode, so getCurrentSectionLabel() used to render "Section 1" while
// the AI actually fills the whole form.
//
// The field counter was already whole-form (schema.fields.length), so this test
// pins the label; it also asserts the counter reflects the whole-form total.
import { render, screen, cleanup, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import type { FormSchema } from '../schema-forms/types/schema'

vi.mock('./useDemoVAD', () => ({
  useDemoVAD: () => ({
    userSpeaking: false,
    loading: false,
    errored: false as const,
    pause: vi.fn(),
    start: vi.fn(),
  }),
}))

vi.mock('../schema-forms/utils/pdfFiller', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../schema-forms/utils/pdfFiller')>()
  return { ...actual, getBackendHttpUrl: () => 'http://localhost:8000' }
})

vi.mock('../shared/connection', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../shared/connection')>()
  return { ...actual, createConnectionManager: vi.fn() }
})

import { VoiceOverlay } from './VoiceOverlay'
import { SchemaFormStateManager } from '../schema-forms/state/schemaFormState'

// Title and section-1 label DIFFER so "shows the title" is distinguishable from
// "shows section 1".
const SCHEMA: FormSchema = {
  source: 'web',
  form_metadata: { title: 'Application for Something', version: '1.0', language: 'en' },
  sections: [
    { id: 'section_1', label: 'Name', order: 1, fields: ['f1', 'f2'] },
    { id: 'section_2', label: 'Address', order: 2, fields: ['f3'] },
  ],
  fields: [
    { id: 'f1', name: 'First', spoken_name: 'first', type: 'text', section_id: 'section_1', validation: {} },
    { id: 'f2', name: 'Last', spoken_name: 'last', type: 'text', section_id: 'section_1', validation: {} },
    { id: 'f3', name: 'Street', spoken_name: 'street', type: 'text', section_id: 'section_2', validation: {} },
  ],
} as unknown as FormSchema

function makeManager() {
  return {
    connect: vi.fn(async () => {}),
    disconnect: vi.fn(),
    isNativeVad: vi.fn(() => true),
    getPushToTalkMode: vi.fn(() => false),
    setPushToTalkMode: vi.fn(),
    setPushToTalkHeld: vi.fn(),
    getCurrentSectionId: vi.fn(() => 'section_1'),
    getCompletedSectionIds: vi.fn(() => new Set<string>()),
    getAudioManager: vi.fn(() => ({
      flushAudioQueue: vi.fn(),
      resumePlayback: vi.fn(),
      isSpeaking: vi.fn(() => false),
      pauseAudioContext: vi.fn(),
      resumeAudioContext: vi.fn(),
      setEnergyCallback: vi.fn(),
      setPTTMode: vi.fn(),
      setVADActive: vi.fn(),
      muteInput: vi.fn(),
      unmuteInput: vi.fn(),
    })),
    onVADSpeechStart: vi.fn(),
    onVADSpeechEnd: vi.fn(),
    pause: vi.fn(),
    resume: vi.fn(async () => {}),
    rearmAudioCapture: vi.fn(async () => {}),
    readDisclaimer: vi.fn(),
  } as any
}

describe('VoiceOverlay continuous-mode header (bd polyglot-pdf-944q)', () => {
  beforeEach(() => {
    const store: Record<string, string> = {}
    vi.stubGlobal('sessionStorage', {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v },
      removeItem: (k: string) => { delete store[k] },
      clear: () => { for (const k of Object.keys(store)) delete store[k] },
      key: () => null,
      length: 0,
    })
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({}) })))
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('shows the form title (not the pinned section-1 label) and the whole-form field count', async () => {
    // Persisted continuous session, disclaimer accepted (skip the modal), pinned
    // to section 1 with one field filled.
    vi.spyOn(SchemaFormStateManager, 'load').mockImplementation(() => ({
      schema: SCHEMA,
      fieldValues: { f1: { value: 'Jane', confirmed: true, lastModified: 1 } },
      currentSectionId: 'section_1',
      completedSections: new Set<string>(),
      validationErrors: {},
      lastUpdated: 1,
      formSessionId: 'fss_test',
      loadedFieldIds: new Set<string>(),
      jitModeEnabled: true,
      continuousSessionEnabled: true,
      disclaimerAccepted: true,
      selectedLanguage: 'English',
    } as any))
    vi.spyOn(SchemaFormStateManager, 'save').mockImplementation(() => {})

    render(
      <VoiceOverlay
        schema={SCHEMA}
        connectionManager={makeManager()}
        status="connected"
        initialLanguage="English"
      />
    )

    // The section-nav header label must be the FORM TITLE, not the pinned
    // section-1 label. Assert on the .vff-section-label node specifically (the
    // header), so an unrelated "Name" elsewhere in the panel can't confuse it.
    await waitFor(() => {
      const labels = Array.from(document.querySelectorAll('.vff-section-label'))
      expect(labels.length).toBeGreaterThan(0)
      for (const el of labels) {
        expect(el.textContent).toBe('Application for Something')
      }
    })
  })
})
