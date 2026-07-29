// @vitest-environment jsdom
//
// Regression test for the reversed listening indicator (bd polyglot-pdf-1dvp).
//
// The old `.vff-vad-indicator` "Listening" badge was gated on
// `vad.userSpeaking && !pushToTalkMode && !nativeVad`, which in native-VAD mode
// (the deployed default) lit when paused/disconnected and never when actually
// listening. It was replaced with `.vff-listening` (ear glyph + mic-energy
// meter), gated on a dedicated `isListening` flag = a steady `connected` session
// ONLY, NOT the broader `isConnected` (which stays true through `reconnecting`)
// and NOT the transient `switching_section` / `reconnecting` windows where the
// mic send gate can drop audio (Codex PR #278).
//
// This pins the gate so a revert to the old VAD-based condition fails CI. Since
// bd polyglot-pdf-3to5 the ear is ALSO shown -- CROSSED-OUT (--muted) -- during the
// not-listening-yet transient states, so the handshake / reconnect window reads as
// "not listening" instead of the ear vanishing:
//   - connected            -> indicator SHOWN, listening (not --muted)
//   - connecting           -> indicator SHOWN, --muted (not listening yet)
//   - switching_section    -> indicator SHOWN, --muted (socket may be closed mid-switch)
//   - reconnecting         -> indicator SHOWN, --muted (mic gate drops audio)
//   - paused               -> indicator HIDDEN
//   - disconnected         -> indicator HIDDEN
// Exercised for BOTH the desktop and mobile overlays. The LISTENING (green/grey,
// meter) state stays `connected*`-only; the transient states render the muted
// (crossed-out, no meter) variant because the mic send gate drops audio there.
//
// Mobile note: the indicator lives in the EXPANDED panel, so the test expands
// it (the FAB is collapsed by default). The desktop panel is always expanded.
//
// This file also pins the two sibling mobile gates that share this harness:
//   - the FAB mic-activity badge (bd polyglot-pdf-8v53): `isListening && micSending`,
//     replacing the same dead `vad.userSpeaking && !nativeVad` condition 1dvp
//     removed from the panel row;
//   - the broader `isConnected` gate (bd polyglot-pdf-bxng): status dot / FAB
//     color / thinking indicator stay "live" through `switching_section` and
//     `reconnecting`, matching the desktop overlay.
import { render, cleanup, within, fireEvent, act } from '@testing-library/react'
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

function makeMockManager(status: string, opts?: { sendingMic?: boolean }): ConnectionManager {
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
    isSendingMicAudio: vi.fn(() => opts?.sendingMic ?? false),
    sendAudio: vi.fn(),
    sendActivityStart: vi.fn(),
    sendActivityEnd: vi.fn(async () => {}),
    sendPrompt: vi.fn(),
    sendRecoveryPrompt: vi.fn(),
    endGeminiSession: vi.fn(),
    setPushToTalkMode: vi.fn(),
    setPushToTalkHeld: vi.fn(),
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

// Shared env stubs (sessionStorage / fetch / state-manager spies) used by every
// describe block below; each block picks its own fake-timer config.
function stubEnv() {
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
}

describe('Voice overlay listening indicator gate (bd polyglot-pdf-1dvp)', () => {
  beforeEach(() => {
    // Fake timers so the overlay's connect-poll loop (a 5s setTimeout loop in
    // handleConnect, reached for the not-yet-live statuses) never runs in real
    // time or leaks past the test (Codex PR #278). These are render-only gate
    // assertions -- we render, assert synchronously, and unmount; the poll loop
    // is abandoned without ticking the clock.
    vi.useFakeTimers()
    stubEnv()
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
  const mutedEl = (c: HTMLElement) => c.querySelector('.vff-listening--muted')

  it('desktop: SHOWS (listening, not muted) when connected', () => {
    const { container } = renderDesktop('connected')
    const el = listeningEl(container)
    expect(el).toBeTruthy()
    // ear glyph + nested mic-energy meter present, NOT the crossed-out muted state
    expect(within(el as HTMLElement).queryByText('\u{1F442}')).toBeTruthy()
    expect((el as HTMLElement).querySelector('.vff-mic-meter')).toBeTruthy()
    expect(mutedEl(container)).toBeNull()
  })

  it('desktop: SHOWS crossed-out (muted) during connecting (bd polyglot-pdf-3to5)', () => {
    const { container } = renderDesktop('connecting')
    const el = listeningEl(container)
    expect(el).toBeTruthy()
    expect(mutedEl(container)).toBeTruthy()
    // No live meter while not listening.
    expect((el as HTMLElement).querySelector('.vff-mic-meter')).toBeNull()
  })

  it('desktop: SHOWS crossed-out (muted) during switching_section (bd polyglot-pdf-3to5)', () => {
    const { container } = renderDesktop('switching_section')
    expect(listeningEl(container)).toBeTruthy()
    expect(mutedEl(container)).toBeTruthy()
  })

  it('desktop: HIDDEN when paused', () => {
    const { container } = renderDesktop('paused')
    expect(listeningEl(container)).toBeNull()
  })

  it('desktop: HIDDEN when disconnected', () => {
    const { container } = renderDesktop('disconnected')
    expect(listeningEl(container)).toBeNull()
  })

  it('desktop: SHOWS crossed-out (muted) while reconnecting (bd polyglot-pdf-3to5)', () => {
    const { container } = renderDesktop('reconnecting')
    expect(listeningEl(container)).toBeTruthy()
    expect(mutedEl(container)).toBeTruthy()
  })

  it('mobile: SHOWS (listening, not muted) when connected', () => {
    const { container } = renderMobileExpanded('connected')
    const el = listeningEl(container)
    expect(el).toBeTruthy()
    expect((el as HTMLElement).querySelector('.vff-mic-meter')).toBeTruthy()
    expect(mutedEl(container)).toBeNull()
  })

  it('mobile: SHOWS crossed-out (muted) during connecting (bd polyglot-pdf-3to5)', () => {
    const { container } = renderMobileExpanded('connecting')
    expect(listeningEl(container)).toBeTruthy()
    expect(mutedEl(container)).toBeTruthy()
  })

  it('mobile: SHOWS crossed-out (muted) during switching_section (bd polyglot-pdf-3to5)', () => {
    const { container } = renderMobileExpanded('switching_section')
    expect(listeningEl(container)).toBeTruthy()
    expect(mutedEl(container)).toBeTruthy()
  })

  it('mobile: HIDDEN when paused', () => {
    const { container } = renderMobileExpanded('paused')
    expect(listeningEl(container)).toBeNull()
  })

  it('mobile: SHOWS crossed-out (muted) while reconnecting (bd polyglot-pdf-3to5)', () => {
    const { container } = renderMobileExpanded('reconnecting')
    expect(listeningEl(container)).toBeTruthy()
    expect(mutedEl(container)).toBeTruthy()
  })
})

describe('Mobile FAB mic-activity badge (bd polyglot-pdf-8v53)', () => {
  // The badge is driven by `micSending`, which the energy-meter effect computes
  // inside a requestAnimationFrame tick -- so this block fakes rAF + performance
  // and advances one frame after feeding the worklet energy callback. Runs in
  // native VAD mode (the mock manager's isNativeVad() is true and the mocked
  // useDemoVAD keeps userSpeaking false), proving the badge no longer depends on
  // the dead client-VAD gate.
  beforeEach(() => {
    vi.useFakeTimers({
      toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval',
               'Date', 'performance', 'requestAnimationFrame', 'cancelAnimationFrame'],
    })
    stubEnv()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  const badge = (c: HTMLElement) => c.querySelector('.vff-fab-vad-badge')

  // Render the (collapsed) mobile overlay -- the badge sits on the FAB itself --
  // and return the energy callback the meter effect registered, if any.
  function renderFab(status: string, sendingMic: boolean) {
    const manager = makeMockManager(status, { sendingMic })
    const utils = render(
      <VoiceOverlayMobile
        schema={MINIMAL_SCHEMA}
        connectionManager={manager}
        status={status}
        initialLanguage="English"
      />
    )
    const audio = manager.getAudioManager() as any
    const cb = audio.setEnergyCallback.mock.calls.at(-1)?.[0]
    return { ...utils, cb }
  }

  it('SHOWN when connected and audio is reaching the backend', () => {
    const { container, cb } = renderFab('connected', true)
    expect(typeof cb).toBe('function')
    act(() => { cb(42, true) })                 // worklet frame: energy 42, gate open
    act(() => { vi.advanceTimersToNextFrame() }) // one rAF tick computes micSending
    expect(badge(container)).toBeTruthy()
  })

  it('HIDDEN when connected but the connection send gate is closed', () => {
    const { container, cb } = renderFab('connected', false)
    expect(typeof cb).toBe('function')
    act(() => { cb(42, true) })                 // worklet says sending...
    act(() => { vi.advanceTimersToNextFrame() }) // ...but isSendingMicAudio() is false
    expect(badge(container)).toBeNull()
  })

  it('HIDDEN when paused', () => {
    const { container } = renderFab('paused', true)
    expect(badge(container)).toBeNull()
  })

  it('HIDDEN when disconnected', () => {
    const { container } = renderFab('disconnected', true)
    expect(badge(container)).toBeNull()
  })
})

describe('Mobile isConnected includes transient live states (bd polyglot-pdf-bxng)', () => {
  // The mobile overlay must keep reading as a LIVE session during
  // `switching_section` and `reconnecting`, and as NOT-live when disconnected.
  //
  // Sol replaced the coloured status dot (bd polyglot-pdf-2p4y), so the
  // invariant is now asserted on Sol's `data-state` rather than on a green
  // background: the transient states must NOT fall through to `offline`, which
  // is the state reserved for a session that is genuinely gone. `disconnected`
  // must. This is the same bxng guarantee, pinned on the element that now
  // carries it -- the LISTENING indicator deliberately stays connected-only in
  // both overlays (Codex PR #278), covered by the 1dvp block above.
  beforeEach(() => {
    vi.useFakeTimers()
    stubEnv()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  function renderExpanded(status: string, thinking = false) {
    const utils = render(
      <VoiceOverlayMobile
        schema={MINIMAL_SCHEMA}
        connectionManager={makeMockManager(status)}
        status={status}
        thinking={thinking}
        initialLanguage="English"
      />
    )
    const fab = utils.container.querySelector('.vff-fab') as HTMLElement
    fireEvent.click(fab)
    return utils
  }

  // The panel's Sol (the FAB carries one too, so scope to the panel).
  const panelSol = (c: HTMLElement) =>
    c.querySelector('.vff-panel-mobile [data-testid="sol-avatar"]') as HTMLElement

  it('Sol does not read as offline during switching_section', () => {
    const { container } = renderExpanded('switching_section')
    expect(panelSol(container).getAttribute('data-state')).not.toBe('offline')
  })

  it('Sol does not read as offline while reconnecting', () => {
    const { container } = renderExpanded('reconnecting')
    expect(panelSol(container).getAttribute('data-state')).not.toBe('offline')
  })

  it('Sol reads as offline when disconnected', () => {
    const { container } = renderExpanded('disconnected')
    expect(panelSol(container).getAttribute('data-state')).toBe('offline')
  })

  it('thinking indicator survives a section switch', () => {
    const { container } = renderExpanded('switching_section', true)
    expect(container.querySelector('.vff-thinking-indicator')).toBeTruthy()
  })
})
