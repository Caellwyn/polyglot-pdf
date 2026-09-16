// @vitest-environment jsdom
//
// bd polyglot-pdf-ylokf: the three manual Clear-form / Start Fresh buttons
// (VoiceOverlay.tsx, VoiceOverlayMobile.tsx, SchemaFormDemo.tsx) used to skip
// SchemaFormStateManager.clearAllClientState() -- clearing the form state and
// onboarding selection directly instead -- so an explicit "clear my data"
// click left vff_client_link_token behind in sessionStorage.
//
// This seeds the token, clicks each of the two VoiceOverlay variants' Clear
// Form buttons, and asserts the token is gone afterward. Follows the render
// harness in VoiceOverlay.reconnectbutton.test.tsx (mocked connection
// manager + VAD hook; a stubbed sessionStorage backed by a real in-memory
// store so SchemaFormStateManager's own read/write calls are exercised, not
// bypassed).
//
// Mutation: revert either overlay's handleClearForm back to
// `SchemaFormStateManager.clear(); clearOnboardingState()` -- red (the token
// survives the click).
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
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
import { VoiceOverlayMobile } from './VoiceOverlayMobile'

const MINIMAL_SCHEMA: FormSchema = {
  source: 'web',
  form_metadata: { title: 'Test Form', version: '1.0', language: 'en' },
  sections: [{ id: 'section_1', label: 'Section 1', order: 1, fields: [] }],
  fields: [],
} as unknown as FormSchema

const TOKEN_KEY = 'vff_client_link_token'

function makeMockManager() {
  const audioManager = {
    flushAudioQueue: vi.fn(),
    resumePlayback: vi.fn(),
    setPTTMode: vi.fn(),
    setVADActive: vi.fn(),
    setEnergyCallback: vi.fn(),
    isSpeaking: vi.fn(() => false),
    muteInput: vi.fn(),
    unmuteInput: vi.fn(),
    pauseAudioContext: vi.fn(),
    resumeAudioContext: vi.fn(),
    getStream: vi.fn(() => null),
    isRecording: vi.fn(() => false),
    startRecording: vi.fn(async () => {}),
    stopRecording: vi.fn(),
    playAudio: vi.fn(async () => {}),
    destroy: vi.fn(),
  }
  return {
    getStatus: vi.fn(() => 'connected'),
    isSendingMicAudio: vi.fn(() => false),
    getAudioManager: vi.fn(() => audioManager),
    connect: vi.fn(async () => {}),
    disconnect: vi.fn(),
    pause: vi.fn(),
    resume: vi.fn(async () => {}),
    isPaused: vi.fn(() => false),
    sendActivityStart: vi.fn(),
    sendActivityEnd: vi.fn(async () => {}),
    switchToFirstSection: vi.fn(async () => {}),
    sendAudio: vi.fn(),
    sendPrompt: vi.fn(),
    sendRecoveryPrompt: vi.fn(),
    endGeminiSession: vi.fn(),
    setPushToTalkMode: vi.fn(),
    setPushToTalkHeld: vi.fn(),
    getPushToTalkMode: vi.fn(() => false),
    getFieldManager: vi.fn(() => null),
    startRecording: vi.fn(async () => {}),
    stopRecording: vi.fn(),
    isRecording: vi.fn(() => false),
    changeFillLanguage: vi.fn(async () => {}),
    readDisclaimer: vi.fn(),
    startSection: vi.fn(async () => {}),
    switchToSection: vi.fn(async () => {}),
    completeSection: vi.fn(async () => {}),
    getCurrentSectionId: vi.fn(() => 'section_1'),
    getCompletedSectionIds: vi.fn(() => new Set<string>()),
    onVADSpeechStart: vi.fn(),
    onVADSpeechEnd: vi.fn(),
    rearmAudioCapture: vi.fn(async () => {}),
  } as any
}

describe('Clear Form buttons clear the client-link token (bd ylokf)', () => {
  let store: Record<string, string>

  beforeEach(() => {
    store = {}
    vi.stubGlobal('sessionStorage', {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v },
      removeItem: (k: string) => { delete store[k] },
      clear: () => { for (const k of Object.keys(store)) delete store[k] },
      key: () => null,
      length: 0,
    })
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({}) })))
    vi.stubGlobal('confirm', vi.fn(() => true))
    // jsdom throws "Not implemented: navigation" on a real reload, and
    // window.location.reload is non-configurable in jsdom -- replace the
    // whole `location` object rather than spying on one property.
    vi.stubGlobal('location', { ...window.location, reload: vi.fn() })
    store[TOKEN_KEY] = 'a-real-client-link-token'
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  async function clickClearForm(
    Overlay: typeof VoiceOverlay | typeof VoiceOverlayMobile,
    isMobile: boolean,
  ) {
    const manager = makeMockManager()
    const { container } = render(
      <Overlay
        schema={MINIMAL_SCHEMA}
        connectionManager={manager}
        status="connected"
      />
    )

    if (isMobile) {
      const fab = container.querySelector('.vff-fab') as HTMLElement
      expect(fab).toBeTruthy()
      fireEvent.click(fab)
    }

    const clearButton = await screen.findByText(/Clear Form/i)
    fireEvent.click(clearButton)
  }

  it('VoiceOverlay: clicking Clear Form removes the client-link token', async () => {
    expect(store[TOKEN_KEY]).toBe('a-real-client-link-token')
    await clickClearForm(VoiceOverlay, false)
    expect(store[TOKEN_KEY]).toBeUndefined()
  })

  it('VoiceOverlayMobile: clicking Clear Form removes the client-link token', async () => {
    expect(store[TOKEN_KEY]).toBe('a-real-client-link-token')
    await clickClearForm(VoiceOverlayMobile, true)
    expect(store[TOKEN_KEY]).toBeUndefined()
  })
})
