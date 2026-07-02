// @vitest-environment jsdom
//
// Regression test for the reversed listening indicator (bd polyglot-pdf-1dvp).
//
// The old `.vff-vad-indicator` "Listening" badge was gated on
// `vad.userSpeaking && !pushToTalkMode && !nativeVad`, which in native-VAD mode
// (the deployed default) lit when paused/disconnected and never when actually
// listening. It was replaced with `.vff-listening` (ear glyph + mic-energy
// meter), gated on a dedicated `isListening` flag = the send-capable states
// (`connected` / `switching_section`), NOT the broader `isConnected` (which
// stays true through `reconnecting`, where the mic gate drops all audio --
// Codex PR #278).
//
// This pins the gate so a revert to the old VAD-based condition fails CI:
//   - connected            -> indicator SHOWN
//   - switching_section    -> indicator HIDDEN (socket may be closed mid-switch)
//   - paused               -> indicator HIDDEN
//   - disconnected         -> indicator HIDDEN
//   - reconnecting         -> indicator HIDDEN (mic gate drops audio)
// Exercised for BOTH the desktop and mobile overlays. The gate is `connected*`
// only -- the transient turn-taking states are deliberately excluded because the
// mic send gate can drop audio in those windows (Codex PR #278).
//
// Mobile note: the indicator lives in the EXPANDED panel, so the test expands
// it (the FAB is collapsed by default). The desktop panel is always expanded.
import { render, cleanup, within, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import type { FormSchema } from '../schema-forms/types/schema'
import { SchemaFormStateManager } from '../schema-forms/state/schemaFormState'
import type { ConnectionManager } from '../shared/connection'

// --- mock the VAD hook (real one calls getUserMedia + loads WASM). Crucially
//     userSpeaking stays false, so any indicator that shows is NOT relying on
//     the old `vad.userSpeaking` gate -- it must be the new isListening gate.
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

function makeMockManager(status: string): ConnectionManager {
  const audioManager = {
    setPTTMode: vi.fn(),
    setVADActive: vi.fn(),
    setNativeVad: vi.fn(),
    setEnergyCallback: vi.fn(),
    isSpeaking: vi.fn(() => false),
    muteInput: vi.fn(),
    unmuteInput: vi.fn(),
    pauseAudioContext: vi.fn(),
    resumeAudioContext: vi.fn(),
    flushAudioQueue: vi.fn(),
    resumePlayback: vi.fn(),
    getStream: vi.fn(() => null),
    isRecording: vi.fn(() => false),
    startRecording: vi.fn(async () => {}),
    stopRecording: vi.fn(),
    playAudio: vi.fn(async () => {}),
    destroy: vi.fn(),
  }
  const manager = {
    connect: vi.fn(async () => {}),
    disconnect: vi.fn(),
    pause: vi.fn(),
    resume: vi.fn(async () => {}),
    getStatus: vi.fn(() => status),
    getThinking: vi.fn(() => false),
    isSendingMicAudio: vi.fn(() => false),
    sendAudio: vi.fn(),
    sendActivityStart: vi.fn(),
    sendActivityEnd: vi.fn(async () => {}),
    sendPrompt: vi.fn(),
    sendRecoveryPrompt: vi.fn(),
    endGeminiSession: vi.fn(),
    setPushToTalkMode: vi.fn(),
    getPushToTalkMode: vi.fn(() => true),
    isNativeVad: vi.fn(() => true),  // deployed default: native VAD
    getFieldManager: vi.fn(() => null),
    getAudioManager: vi.fn(() => audioManager),
    startRecording: vi.fn(async () => {}),
    stopRecording: vi.fn(),
    isRecording: vi.fn(() => false),
    isPaused: vi.fn(() => status === 'paused'),
    rearmAudioCapture: vi.fn(async () => {}),
    changeFillLanguage: vi.fn(async () => {}),
    changeSpokenLanguage: vi.fn(),
    readDisclaimer: vi.fn(),
    switchToFirstSection: vi.fn(async () => {}),
    startSection: vi.fn(async () => {}),
    switchToSection: vi.fn(async () => {}),
    completeSection: vi.fn(async () => {}),
    getCurrentSectionId: vi.fn(() => 'section_1'),
    getCompletedSectionIds: vi.fn(() => new Set<string>()),
    onVADSpeechStart: vi.fn(),
    onVADSpeechEnd: vi.fn(),
  }
  return manager as unknown as ConnectionManager
}

const LIVE_STATE = {
  schema: MINIMAL_SCHEMA, fieldValues: {}, currentSectionId: 'section_1',
  completedSections: new Set<string>(), validationErrors: {}, lastUpdated: 0,
  formSessionId: 'fss_test', loadedFieldIds: new Set<string>(),
  jitModeEnabled: false, disclaimerAccepted: true, selectedLanguage: 'English',
}

describe('Voice overlay listening indicator gate (bd polyglot-pdf-1dvp)', () => {
  beforeEach(() => {
    // Fake timers so the overlay's connect-poll loop (a 5s setTimeout loop in
    // handleConnect, reached for the not-yet-live statuses) never runs in real
    // time or leaks past the test (Codex PR #278). These are render-only gate
    // assertions -- we render, assert synchronously, and unmount; the poll loop
    // is abandoned without ticking the clock.
    vi.useFakeTimers()
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
    vi.spyOn(SchemaFormStateManager, 'load').mockImplementation(() => ({ ...LIVE_STATE } as any))
    vi.spyOn(SchemaFormStateManager, 'save').mockImplementation(() => {})
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  function renderDesktop(status: string) {
    return render(
      <VoiceOverlay
        schema={MINIMAL_SCHEMA}
        connectionManager={makeMockManager(status)}
        status={status}
        initialLanguage="English"
      />
    )
  }

  // Mobile: the indicator is inside the expanded panel; expand the FAB first.
  // fireEvent flushes the state update synchronously (act), so the panel is
  // present immediately -- no waitFor (which would stall under fake timers).
  function renderMobileExpanded(status: string) {
    const utils = render(
      <VoiceOverlayMobile
        schema={MINIMAL_SCHEMA}
        connectionManager={makeMockManager(status)}
        status={status}
        initialLanguage="English"
      />
    )
    const fab = utils.container.querySelector('.vff-fab') as HTMLElement
    expect(fab).toBeTruthy()
    fireEvent.click(fab)
    expect(utils.container.querySelector('.vff-panel-mobile')).toBeTruthy()
    return utils
  }

  const listeningEl = (c: HTMLElement) => c.querySelector('.vff-listening')

  it('desktop: SHOWS when connected', () => {
    const { container } = renderDesktop('connected')
    const el = listeningEl(container)
    expect(el).toBeTruthy()
    // ear glyph + nested mic-energy meter present
    expect(within(el as HTMLElement).queryByText('\u{1F442}')).toBeTruthy()
    expect((el as HTMLElement).querySelector('.vff-mic-meter')).toBeTruthy()
  })

  it('desktop: HIDDEN during switching_section (socket may be closed mid-switch)', () => {
    const { container } = renderDesktop('switching_section')
    expect(listeningEl(container)).toBeNull()
  })

  it('desktop: HIDDEN when paused', () => {
    const { container } = renderDesktop('paused')
    expect(listeningEl(container)).toBeNull()
  })

  it('desktop: HIDDEN when disconnected', () => {
    const { container } = renderDesktop('disconnected')
    expect(listeningEl(container)).toBeNull()
  })

  it('desktop: HIDDEN while reconnecting (mic gate drops audio -- Codex PR #278)', () => {
    const { container } = renderDesktop('reconnecting')
    expect(listeningEl(container)).toBeNull()
  })

  it('mobile: SHOWS when connected', () => {
    const { container } = renderMobileExpanded('connected')
    const el = listeningEl(container)
    expect(el).toBeTruthy()
    expect((el as HTMLElement).querySelector('.vff-mic-meter')).toBeTruthy()
  })

  it('mobile: HIDDEN during switching_section (socket may be closed mid-switch)', () => {
    const { container } = renderMobileExpanded('switching_section')
    expect(listeningEl(container)).toBeNull()
  })

  it('mobile: HIDDEN when paused', () => {
    const { container } = renderMobileExpanded('paused')
    expect(listeningEl(container)).toBeNull()
  })

  it('mobile: HIDDEN while reconnecting (Codex PR #278)', () => {
    const { container } = renderMobileExpanded('reconnecting')
    expect(listeningEl(container)).toBeNull()
  })
})
