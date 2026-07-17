// @vitest-environment jsdom
//
// Regression test for bd polyglot-pdf-b2yj: the Reconnect button must render on
// the generic "disconnected" status, not only on "idle_timeout".
//
// The bug: when the voice connection dropped to "disconnected" the overlay set
// the error "Connection lost - please click Reconnect" but rendered NO button --
// the inline reconnect button was gated on `status === 'idle_timeout'` and the
// ConnectionTimeoutModal only shows for `status === 'reconnect_failed'`. The user
// was told to click a button that did not exist. This test renders each overlay
// with status="disconnected" and asserts a Reconnect button is present and wired
// to the connect path (handleConnect -> connectionManager.connect()).
//
// Extended for bd polyglot-pdf-m77y: the SAME dead-end existed for a bare 'error'
// status -- set by connect()'s catch when BOTH the localhost and cloud connect
// attempts fail (a completely-failed initial connect or resume). It fell through
// the Reconnect/Resume/Pause ternary to `null`, leaving no recovery control at
// all (page refresh only). The same assertion now also covers status="error".
//
// We render WITHOUT initialLanguage so the mount-time auto-connect effect (gated
// on `initialLanguage && !showLanguageModal`) never runs and cannot overwrite the
// injected "disconnected" status. The language-selection modal renders as an
// overlay, but the panel body -- including the controls row -- still renders
// underneath, so the Reconnect button is queryable.
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import type { FormSchema } from '../schema-forms/types/schema'

// The VAD hook touches getUserMedia / WASM -- unavailable in jsdom.
vi.mock('./useDemoVAD', () => ({
  useDemoVAD: () => ({
    userSpeaking: false,
    loading: false,
    errored: false as const,
    pause: vi.fn(),
    start: vi.fn(),
  }),
}))

// getBackendHttpUrl reads import.meta.env / window.location.
vi.mock('../schema-forms/utils/pdfFiller', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../schema-forms/utils/pdfFiller')>()
  return { ...actual, getBackendHttpUrl: () => 'http://localhost:8000' }
})

// Never build a real connection manager; we inject our mock as the prop.
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

// Minimal manager: getStatus reports the same "disconnected" we inject as the
// status prop, and connect() is the call the Reconnect button must trigger. Every
// other method the render/mount effects may touch is a harmless stub.
function makeMockManager() {
  const audioManager = {
    flushAudioQueue: vi.fn(),
    resumePlayback: vi.fn(),
    setPTTMode: vi.fn(),
    setVADActive: vi.fn(),
    setNativeVad: vi.fn(),
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
    getStatus: vi.fn(() => 'disconnected'),
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
    isNativeVad: vi.fn(() => true),
    getFieldManager: vi.fn(() => null),
    startRecording: vi.fn(async () => {}),
    stopRecording: vi.fn(),
    isRecording: vi.fn(() => false),
    changeFillLanguage: vi.fn(async () => {}),
    changeSpokenLanguage: vi.fn(),
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

describe('Reconnect button on "disconnected" status (bd b2yj)', () => {
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

  async function assertReconnectButtonShows(
    Overlay: typeof VoiceOverlay | typeof VoiceOverlayMobile,
    isMobile: boolean,
    status: 'disconnected' | 'error' = 'disconnected',
  ) {
    const manager = makeMockManager()
    const { container } = render(
      <Overlay
        schema={MINIMAL_SCHEMA}
        connectionManager={manager}
        status={status}
      />
    )

    // The mobile overlay renders as a collapsed FAB; its action buttons live in
    // the expanded panel. Tap the FAB to expand before querying for the button.
    if (isMobile) {
      const fab = container.querySelector('.vff-fab') as HTMLElement
      expect(fab).toBeTruthy()
      fireEvent.click(fab)
    }

    // The button exists (regression: it used to render only for idle_timeout)...
    const reconnectButton = await screen.findByText(/Reconnect/)
    expect(reconnectButton).toBeTruthy()

    // ...and it is wired to the connect path.
    fireEvent.click(reconnectButton)
    expect(manager.connect).toHaveBeenCalled()
  }

  it('desktop (VoiceOverlay): shows a Reconnect button when disconnected', async () => {
    await assertReconnectButtonShows(VoiceOverlay, false)
  })

  it('mobile (VoiceOverlayMobile): shows a Reconnect button when disconnected', async () => {
    await assertReconnectButtonShows(VoiceOverlayMobile, true)
  })

  // bd polyglot-pdf-m77y: a bare 'error' status (both localhost + cloud connect
  // failed) must also offer a recovery control, not fall through to no button.
  it('desktop (VoiceOverlay): shows a Reconnect button on error status', async () => {
    await assertReconnectButtonShows(VoiceOverlay, false, 'error')
  })

  it('mobile (VoiceOverlayMobile): shows a Reconnect button on error status', async () => {
    await assertReconnectButtonShows(VoiceOverlayMobile, true, 'error')
  })
})
