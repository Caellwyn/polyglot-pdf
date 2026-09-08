// @vitest-environment jsdom
//
// Regression pin for bd polyglot-pdf-4l7p (sprint-11 UI sweep): in
// continuous-session mode the MOBILE overlay must show NO section-session UX
// anywhere -- no section label, no section nav, no section-scoped counter. The
// only field info mobile renders is the whole-form "{N} fields - {M} required"
// line, computed straight from the schema prop. Mobile's dead section-display
// machinery (currentSectionId/completedSections/sectionFieldCount + the 1s
// poll) was deleted in the same bead; this test keeps a section render from
// silently coming back unguarded.
import { render, cleanup, waitFor, fireEvent } from '@testing-library/react'
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

import { VoiceOverlayMobile } from './VoiceOverlayMobile'
import { SchemaFormStateManager } from '../schema-forms/state/schemaFormState'

// Title and section labels DIFFER so a section-label leak is distinguishable.
const SCHEMA: FormSchema = {
  source: 'web',
  form_metadata: { title: 'Application for Something', version: '1.0', language: 'en' },
  sections: [
    { id: 'section_1', label: 'Name', order: 1, fields: ['f1', 'f2'] },
    { id: 'section_2', label: 'Address', order: 2, fields: ['f3'] },
  ],
  fields: [
    { id: 'f1', name: 'First', spoken_name: 'first', type: 'text', section_id: 'section_1', validation: { required: true } },
    { id: 'f2', name: 'Last', spoken_name: 'last', type: 'text', section_id: 'section_1', validation: {} },
    { id: 'f3', name: 'Street', spoken_name: 'street', type: 'text', section_id: 'section_2', validation: {} },
  ],
} as unknown as FormSchema

function makeManager() {
  return {
    connect: vi.fn(async () => {}),
    disconnect: vi.fn(),
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
    // Methods the mount/connect path calls -- without them handleConnect's
    // try/catch swallows a TypeError and the flow silently no-ops
    // (fresh-eyes mock-fidelity note on this bead).
    isPaused: vi.fn(() => false),
    startRecording: vi.fn(async () => {}),
    getStatus: vi.fn(() => 'connected'),
    isSendingMicAudio: vi.fn(() => false),
  } as any
}

describe('VoiceOverlayMobile continuous mode shows no section-session UX (bd polyglot-pdf-4l7p)', () => {
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

  it('renders no section label/nav and shows the whole-form field counts', async () => {
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
    vi.spyOn(SchemaFormStateManager, 'init').mockImplementation(
      () => SchemaFormStateManager.load() as any
    )
    vi.spyOn(SchemaFormStateManager, 'save').mockImplementation(() => {})

    const { container } = render(
      <VoiceOverlayMobile
        schema={SCHEMA}
        connectionManager={makeManager()}
        status="connected"
        initialLanguage="English"
      />
    )

    // Expand the FAB (a div with an onClick, not a button) so the full panel
    // -- the only place field info renders -- is up.
    const fab = container.querySelector('.vff-fab')
    expect(fab).not.toBeNull()
    fireEvent.click(fab as HTMLElement)

    await waitFor(() => {
      // Whole-form counts render (3 fields, 1 required in this schema)...
      expect(container.textContent).toContain('3 fields')
      expect(container.textContent).toContain('1 required')
    })

    // ...and NO section-session UX leaks: no section label/nav nodes, and no
    // section LABEL text anywhere in the panel.
    expect(document.querySelector('.vff-section-label')).toBeNull()
    expect(document.querySelector('.vff-section-nav')).toBeNull()
    expect(container.textContent).not.toContain('Name')
    expect(container.textContent).not.toContain('Address')
    expect(container.textContent).not.toContain('Unknown Part')
  })
})
